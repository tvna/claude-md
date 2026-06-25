"""Pure parser/signal layer for ``scripts/auto_retro.py``.

The base (lowest) layer of the auto-retro refactor (Refs #1725, a
precondition for #1702): non-IO, non-orchestration functions and the
module-level constants they consume. Everything here is a pure function
of its arguments; no GitHub API calls, no subprocess, no filesystem --
so the parser, the signal computation, and the label-derived prior tally
can be unit-tested in isolation and reused by the triage and renderer
layers without importing the IO/orchestration shell.

``scripts/auto_retro.py`` re-exports every public and underscore-prefixed
name defined here so existing ``import auto_retro as ar; ar.<X>`` callers
and tests keep working unchanged. This module imports only stdlib plus the
constants-only helpers (``_retro_labels``, ``_trusted_bots``,
``issue_link``); it never imports ``auto_retro`` or the sibling triage /
render helpers, keeping the dependency graph acyclic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from _trusted_bots import _TRUSTED_BOT_LOGINS
from issue_link import strip_html_comments

# Section names mirror body_policy._ISSUE_COMMON_REQUIRED so the
# auto-opened retro issue passes verify-body-policy. Drift between the
# two is caught by tests/test_auto_retro.py::test_required_sections_align.
_REQUIRED_SECTIONS: tuple[str, ...] = (
    "Scope",
    "Facts",
    "Proposed work",
    "Verification",
    "Acceptance criteria",
)

# Conservative match: lowercase Conventional Commit token with optional
# parenthetic scope. A non-matching source PR title yields an empty token;
# the retro body records the parse failure in its Facts section.
_TYPE_SCOPE_RE = re.compile(r"^([a-z][a-z0-9-]*(?:\([a-z0-9-]+\))?)\s*:")

# Patterns for reading the post-2026-05-26 PR shape. Kept literally
# aligned with scripts/body_policy.py to make the hook + server gate +
# retro reader share one truth. tests/test_auto_retro.py contains an
# alignment test (test_verification_regex_align_with_body_policy) that
# fails on drift.
_VERIFICATION_COMMAND_RE = re.compile(
    r"^-[ \t]+command:[ \t]*`[^`\n]+`[ \t]*$",
    re.MULTILINE,
)
_VERIFICATION_RESULT_RE = re.compile(
    r"^[ \t]{2}result:[ \t]*\S.*$",
    re.MULTILINE,
)

_RESULT_PASSING_PREFIXES: tuple[str, ...] = (
    "exit 0",
    "ok",
    "ok:",
    "pass",
    "passed",
    "success",
    # Common tool-natural-language pass shapes. Refs #417.
    "all hooks",
    "all checks",
    "all tests",
    # Successful verification evidence captured in the #592 corpus.
    # These are proof that the operator ran a check and observed the
    # expected passing state, not repair rows. Refs #593.
    "compilation completed successfully",
    "required test coverage",
    "parses",
    "shows",
    "matches",
    # nix hash prefix: `sha256-<base64>` is the standard nix SRI hash
    # format output by `nix eval ... .src.outputHash` and by python
    # base64/binascii hash helpers. Refs #927.
    "sha256-",
)

# Successful verification is often recorded as an observation sentence
# rather than a tool-status token. Keep this list concrete: every phrase
# below comes from the #592 G3 retro corpus and describes proof that the
# verification did what the operator expected, not a generic failure.
_RESULT_PASSING_OBSERVATION_PHRASES: tuple[str, ...] = (
    "ascii-clean",
    "completed successfully",
    "diff is confined",
    "exit 0",
    "exits 0",
    "gate trips as designed",
    "insertions",
    "insertions(+)",
    "no hits",
    "no matches",
    "one commit on the branch",
    "only the intentional",
    "parsed without exception",
    "parses;",
    " passed in ",
    "required test coverage",
    "ruff / mypy / prek pass",
    "shows chapter",
    "total coverage",
    # Phrases from the #927 corpus: observations confirmed as successful
    # verification proof in open retros #742, #810, #829. Refs #927.
    "compiled successfully",
    "all gates pass",
    "guard block present",
    "tarball contains",
)

# Pure numeric result (e.g., a count from `grep -c` or `wc -l`). The
# operator chose count-style verification, so the value is a measured
# quantity rather than a status code; treat as passing. Refs #417.
_RESULT_PASSING_NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# "all <token> hooks|checks|tests" pattern. Tools like pre-commit, prek,
# and `gh pr checks` interpolate a count or qualifier between "all" and
# the unit noun ("all six hooks Passed", "all 3 checks have passed").
# The literal prefixes in _RESULT_PASSING_PREFIXES only catch the bare
# "all hooks" / "all checks" / "all tests" forms, so this regex covers
# the natural-language variants without widening the allowlist into
# free-form prose. Refs #411.
_RESULT_PASSING_ALL_UNIT_RE = re.compile(
    r"^all\s+\S+\s+(?:hooks|checks|tests)\b",
    re.IGNORECASE,
)

# pytest-style count summary: `246 passed in 198.59s`, `1476 passed,
# coverage 94.24%`, `22 passed in 0.09s`. Anchored to start so trailing
# prose (timing, coverage) is tolerated but a leading failure count is
# not silently swallowed. Refs #453.
_RESULT_PASSING_COUNT_RE = re.compile(r"^\d+\s+passed\b", re.IGNORECASE)

# Trailing `ok` word marker: `yaml syntax ok`, `config ok.`. Word
# boundary keeps `not ok` and `lookup` out of the match. Refs #453.
_RESULT_PASSING_TRAILING_OK_RE = re.compile(r"\bok\b\.?\s*$", re.IGNORECASE)

# ASCII cleanliness checks usually print key/value facts rather than a
# status word. Treat the exact zero-count observation as success. Refs #596.
_RESULT_PASSING_NON_ASCII_ZERO_RE = re.compile(
    r"\bnon_ascii\s*=\s*0\b",
    re.IGNORECASE,
)

# nix eval quoted-string output (e.g. `"1.2.3"`, `"sha256-abc=="`).
# A successful `nix eval` on a string-typed attribute always wraps the
# value in double-quotes; evaluation errors use the un-quoted `error: ...`
# prefix instead. Refs #927.
_RESULT_PASSING_NIX_QUOTED_RE = re.compile(r'^"[^"\n]+"$')

# grep -n match output: `18:aka.ms`. A non-empty `linenum:content` result
# means the operator's pattern was found in the file; i.e. the file
# contains the expected entry. Refs #927.
_RESULT_PASSING_GREP_N_RE = re.compile(r"^\d+:\S")

# sha256sum / shasum standard output: 64 hex chars + whitespace + filename
# (e.g. `a0b896...  apm-linux-x86_64.tar.gz`). Only sha256 (64 chars)
# is covered; sha1 / md5 are matched by _RESULT_PASSING_HEX_HASH_RE.
# Refs #927.
_RESULT_PASSING_SHASUM_RE = re.compile(r"^[0-9a-f]{64}\s+\S", re.IGNORECASE)

# Pure hex hash string of 8+ chars (e.g. `15e7b5dfd8e654725ff0`).
# Operators using hash-based verification record a bare hex digest as the
# measured result; any 8+ char hex string is treated as a quantity, not a
# status. Refs #927.
_RESULT_PASSING_HEX_HASH_RE = re.compile(r"^[0-9a-f]{8,}$", re.IGNORECASE)

# Package name-version string (e.g. `bubblewrap-0.11.0`, `uv-1.2.3`).
# Output of `nix eval .#packages.<system>.NAME.name` or similar when the
# derivation exists and is evaluable. Refs #927.
_RESULT_PASSING_PKG_VERSION_RE = re.compile(
    r"^[a-z][a-z0-9_-]*-\d+\.\d+", re.IGNORECASE
)

# nix-prefixed tool or shell name (e.g. `nix-shell`, `nix-develop`).
# Output of `nix eval .#devShells.<system>.NAME.name --raw`. Refs #927.
_RESULT_PASSING_NIX_TOOL_RE = re.compile(r"^nix-[a-z][a-z0-9-]*$", re.IGNORECASE)

# Explicit failure-count marker that must NOT be treated as passing even
# if the rest of the string smells like a pass (`0 passed, 3 failed`).
# Refs #453.
_RESULT_FAILING_COUNT_RE = re.compile(r"\b\d+\s+failed\b", re.IGNORECASE)

# Zero exit / return code anywhere in the result is a pass even when the
# surrounding text uses a non-standard prefix that the prefix allowlist
# misses (`total preflight exit=0`, `PREFLIGHT_EXIT=0`, `skip: ... (rc=0)`).
# Only an explicit zero matches: `exit=1` and a bare version like `0.11`
# do not (the `0` must not be followed by a digit or a dot). Refs #1227.
_RESULT_PASSING_EXIT_ZERO_RE = re.compile(
    r"\b(?:exit(?:[ _-]?code)?|rc|preflight_exit)\b[ \t]*[=:]?[ \t]*0(?![.\d])",
    re.IGNORECASE,
)

# Environment-prerequisite-unavailable markers. A verification that could
# not run because a CI-only token or tool was absent locally is a skip, not
# a repair signal: `blocked: GH_TOKEN unset`, `skip: PR is a retro-close PR`,
# `skipped on missing local prereqs`, `not applicable`. A genuine local
# failure (`blocked: ModuleNotFoundError`, `required uv ==X, local uv is Y`,
# `not run; ... does not match`) carries none of these markers and stays a
# failure. Refs #1227, #851.
_RESULT_ENV_SKIP_RE = re.compile(
    r"^[ \t]*skip(?:ped)?\b"
    r"|\bunset\b"
    r"|\bmissing (?:env|local prereq)"
    r"|\bnot applicable\b"
    r"|\bn/a\b",
    re.IGNORECASE,
)

# Append-to-existing-retro markers used by append_repair_history_row.
_AUTO_FILLED_OPEN = "<!-- auto-filled:repair-history -->"
_AUTO_FILLED_CLOSE = "<!-- /auto-filled:repair-history -->"
_APPENDED_OPEN = "<!-- appended-follow-up-fixes -->"
_APPENDED_CLOSE = "<!-- /appended-follow-up-fixes -->"

# Visible sentinels marking an unfilled Repair history Cause / Next action
# cell. They let verify_retro_repair_completeness mechanically detect rows
# the operator has not yet completed. Static strings keep build_retro_body
# byte-identical on event re-run.
_REPAIR_CAUSE_FILL = "(fill: cause; how this repair arose)"
_REPAIR_NEXT_ACTION_FILL = (
    "(fill: next action; gate or issue to prevent recurrence)"
)

# Logins whose comments do NOT count as operator engagement for the
# sentinel "untouched" check. Extends _TRUSTED_BOT_LOGINS with the
# repository's own Actions identity, which is the author of the retro
# issue itself; a self-comment from it would not signal triage. Consumed
# by is_retro_untouched (renderer layer) and by the sentinel
# orchestration retained in auto_retro.py.
_SENTINEL_IGNORED_COMMENT_LOGINS: frozenset[str] = (
    _TRUSTED_BOT_LOGINS | frozenset({"github-actions[bot]"})
)


@dataclass(frozen=True)
class VerificationPair:
    command: str
    result: str
    passed: bool


@dataclass(frozen=True)
class MergedPR:
    number: int
    title: str
    merged: bool
    merged_at: str
    merged_by_login: str | None
    user_login: str | None
    layer_labels: tuple[str, ...]
    html_url: str
    body: str = ""
    commits: int = 0


def parse_event(event: dict[str, Any]) -> MergedPR:
    """Extract the fields the retro flow needs from a pull_request event.

    Raises :class:`ValueError` when the event payload has no
    ``pull_request`` object or no ``number``. ``merged == false`` is NOT
    raised here; callers (run, _cmd_run) decide what to do with an
    unmerged event so the workflow stays composable.
    """
    pr = event.get("pull_request") or {}
    number = pr.get("number")
    if number is None:
        raise ValueError("event payload has no pull_request.number")

    merged_by = pr.get("merged_by") or {}
    user = pr.get("user") or {}
    labels = pr.get("labels") or []
    layer_labels = tuple(
        (lbl.get("name") or "")
        for lbl in labels
        if (lbl.get("name") or "").startswith("layer:")
    )
    return MergedPR(
        number=int(number),
        title=str(pr.get("title") or ""),
        merged=bool(pr.get("merged")),
        merged_at=str(pr.get("merged_at") or ""),
        merged_by_login=merged_by.get("login"),
        user_login=user.get("login"),
        layer_labels=layer_labels,
        html_url=str(pr.get("html_url") or ""),
        body=str(pr.get("body") or ""),
        commits=int(pr.get("commits") or 0),
    )


def extract_type_scope(pr_title: str) -> str:
    """Extract the ``type(scope)`` token from a Conventional Commit title.

    Returns ``""`` when the title does not match; callers handle the empty
    token explicitly.
    """
    match = _TYPE_SCOPE_RE.match(pr_title)
    if match is None:
        return ""
    return match.group(1)


def is_retro_pr(pr_title: str) -> bool:
    """True if the PR is itself a retrospective (skip to avoid recursion).

    Matches when the title's ``type(scope)`` token literally contains
    ``(auto-retro)``; covering both auto-opened retros and retro-closing
    PRs like ``fix(auto-retro): ...`` / ``docs(auto-retro): ...`` that the
    title policy forces to use an allowed Conventional Commit type with an
    ``auto-retro`` scope.
    """
    stripped = pr_title.lstrip().lower()
    token = extract_type_scope(stripped) or ""
    return "(auto-retro)" in token


def is_retro_issue_title(title: str) -> bool:
    """True if *title* is an auto-opened retrospective issue title.

    Single source of truth for retro-issue title detection. Matches the
    canonical ``chore(auto-retro): review PR #<N> repair loops`` prefix and
    the legacy ``fix(auto-retro)`` prefix (case-insensitive after lstrip).
    Both shapes are recognized so dedup, the sentinel, the label-derived
    prior, and the no-direct-PR gate keep covering closed historical retros
    that were not renamed during the prefix migration (Refs #1069). Older
    ``retro(`` / ``retro:`` titles were fully migrated and are not matched.
    """
    stripped = title.lstrip().lower()
    return stripped.startswith("chore(auto-retro)") or stripped.startswith(
        "fix(auto-retro)"
    )


def is_per_pr_retro_title(title: str) -> bool:
    """Dedup-only (Refs #1995, #1998): True only when the scope is exactly
    ``retro`` (hand-authored). Auto-retro shapes stay with is_retro_issue_title
    (find_existing_retro ORs both); never dedup non-retro feat/docs(auto-retro)."""
    token = extract_type_scope(title.lstrip().lower())
    return token.endswith("(retro)")


def should_skip(
    pr: MergedPR, trusted_bots: frozenset[str] = _TRUSTED_BOT_LOGINS
) -> tuple[bool, str]:
    """Return ``(skip, reason)``. Empty *reason* when not skipping."""
    if pr.merged_by_login is not None and pr.merged_by_login in trusted_bots:
        return True, f"merged by trusted bot ({pr.merged_by_login})"
    if pr.user_login is not None and pr.user_login in trusted_bots:
        return True, f"authored by trusted bot ({pr.user_login})"
    if is_retro_pr(pr.title):
        return True, "PR is itself a retrospective (avoid recursion)"
    return False, ""


# Commit-subject prefixes recorded as "rebase debt before merge" in the
# Repair history table. The squash-only, linear-history merge policy in
# .github/rulesets/main.json forces branches behind main to rebase or
# merge main in before merge, so these commits are a structural side
# effect of the policy rather than evidence of a repair loop.
_MERGE_FROM_MAIN_PREFIXES: tuple[str, ...] = (
    "Merge branch 'main'",
    "Merge remote-tracking branch 'origin/main'",
    "Merge branch 'master'",
    "Merge remote-tracking branch 'origin/master'",
)

# Leading marker on the right-hand cell of merge-from-main rows. Lets
# operators skip the row when filling the section 3 classification
# column: the row is a structural artifact of the squash + linear-history
# + strict-status-checks ruleset, not a repair loop. Issue #400.
_POLICY_ARTIFACT_MARKER = "[policy-artifact]"


@dataclass(frozen=True)
class RepairHistoryRow:
    """One generated Repair history row before markdown rendering."""

    repair: str
    detail: str
    policy_artifact: bool = False
    next_action: str = ""


def _count_merge_from_main(subjects: list[str]) -> int:
    """Return the number of *subjects* that are merge-from-main commits.

    Shared by :func:`compute_repair_signals` (to exempt rebase debt from
    the ``multi_commit_pr`` gate) and :func:`_build_repair_history_table`
    (to render the "Merge from main" rows). Matches the prefixes in
    :data:`_MERGE_FROM_MAIN_PREFIXES`.
    """
    return sum(
        1
        for subject in subjects
        if any(
            subject.strip().startswith(prefix)
            for prefix in _MERGE_FROM_MAIN_PREFIXES
        )
    )


# Commit-subject markers for `git revert` commits. Kept parallel to
# _MERGE_FROM_MAIN_PREFIXES rather than merged into one matcher: the
# Git-standard revert subject is NOT Conventional (`Revert "<subject>"`),
# while the Conventional forms (`revert(scope): ...`) carry a type slot, so a
# single literal-prefix list cannot cover both without muddying each. Per
# CLAUDE.md section 3 `git revert` is the default rollback path, so a revert
# commit is an expected artifact, not a repair loop on its own; but unlike
# merge-from-main (pure structural rebase debt) it is an anomaly *hint*: it
# subtracts from the multi_commit_pr count yet is still recorded for co-fire
# correlation (refs #1287).
_REVERT_PREFIXES: tuple[str, ...] = ('Revert "',)

# Conventional revert subjects: `revert: ...`, `revert(scope): ...`, and the
# breaking `revert!: ` / `revert(scope)!: `. The `: ` separator is required so
# `revert this thing` (no colon) and `fix(revert): ...` (revert only in the
# scope slot, a real fix commit) do NOT match; consistent with
# title_policy.pr_title_ref_is_exempt, which only treats the *type* slot as a
# revert. Matched case-sensitively: Git emits capital `Revert "`, Conventional
# types are lowercase per .github/title-policy.toml `scope_pattern`
# (kept in sync here as a self-contained literal to avoid importing
# title_policy's regex internals).
_REVERT_CONVENTIONAL_RE = re.compile(r"^revert(?:\([a-z0-9][a-z0-9-]*\))?!?: ")


def _is_revert_subject(subject: str) -> bool:
    """Return True if *subject* is a Git-standard or Conventional revert.

    A double revert (``Revert "Revert "feat: x""``) is still one commit and
    matches once; nesting depth is not counted. Lowercase ``revert "...``
    (neither Git-standard nor Conventional) does not match, to avoid false
    positives on prose.
    """
    stripped = subject.strip()
    return any(
        stripped.startswith(prefix) for prefix in _REVERT_PREFIXES
    ) or bool(_REVERT_CONVENTIONAL_RE.match(stripped))


def _count_revert(subjects: list[str]) -> int:
    """Return the number of *subjects* that are revert commits.

    Shared by :func:`compute_repair_signals` (to subtract reverts from the
    ``multi_commit_pr`` count so a revert alone does not fire the gate) and
    :func:`_repair_history_rows` (to render the ``Revert commit`` rows).
    Mirrors :func:`_count_merge_from_main`; see :func:`_is_revert_subject`
    for the per-subject predicate.
    """
    return sum(1 for subject in subjects if _is_revert_subject(subject))


def _slice_section(body: str, heading: str) -> str:
    """Return the slice of ``body`` under ``## heading`` up to the next H2.

    HTML comments are stripped first so a commented heading does not
    pretend to terminate the range. Case-insensitive match on the
    heading text. Returns ``""`` when the heading is absent.
    """
    cleaned = strip_html_comments((body or "").replace("\r", ""))
    lines = cleaned.splitlines()
    target = heading.strip().casefold()
    h2_pattern = re.compile(r"^##[ \t]+(.+?)[ \t]*$")
    start: int | None = None
    end = len(lines)
    for i, line in enumerate(lines):
        match = h2_pattern.match(line)
        if match is None:
            # H3+ inside an active section is part of the slice.
            continue
        text = match.group(1).rstrip(":").strip()
        if start is None:
            if text.casefold() == target:
                start = i + 1
            continue
        end = i
        break
    if start is None:
        return ""
    return "\n".join(lines[start:end])


def _result_is_passing(result: str) -> bool:
    """Return True if a Verification result line text looks like a pass.

    Strips surrounding backticks and leading whitespace, then:

    * a purely numeric result (matched by :data:`_RESULT_PASSING_NUMERIC_RE`)
      is treated as a measured quantity from a count-style verification
      and accepted as passing;
    * a result matching :data:`_RESULT_PASSING_ALL_UNIT_RE` (``all <N>
      hooks/checks/tests ...``) is accepted as passing, covering natural
      tool output where a count or qualifier is interpolated between
      ``all`` and the unit noun (refs #411);
    * pytest-style ``N passed ...`` counts (matched by
      :data:`_RESULT_PASSING_COUNT_RE`) are accepted as passing;
    * a string ending in the word ``ok`` (matched by
      :data:`_RESULT_PASSING_TRAILING_OK_RE`) is accepted as passing;
    * otherwise the lowercased text is matched against the prefix
      allowlist in :data:`_RESULT_PASSING_PREFIXES` (``exit 0``, ``OK:``,
      ``pass``, ``passed``, ``success``, ``ok``, plus common tool
      summaries such as ``all hooks ...``).

    An explicit ``N failed`` token anywhere in the text (matched by
    :data:`_RESULT_FAILING_COUNT_RE`) forces a failure verdict even if
    another marker would have accepted it.

    Additional patterns from the #927 corpus (retros #742, #788, #802,
    #807, #810, #829, #900) are matched by dedicated regexes for nix eval
    quoted-string output, grep -n line results, sha256sum output, pure hex
    hashes, package name-version strings, and nix-prefixed tool names.

    A zero exit / return code anywhere in the text (matched by
    :data:`_RESULT_PASSING_EXIT_ZERO_RE`: ``exit=0``, ``rc=0``,
    ``PREFLIGHT_EXIT=0``) is a pass even behind a non-standard prefix, and an
    environment-prerequisite-unavailable result (matched by
    :data:`_RESULT_ENV_SKIP_RE`: ``skip:``/``skipped``, ``... unset``,
    ``missing env``/``missing local prereq``, ``not applicable``/``n/a``) is a
    skip rather than a repair signal. A genuine local failure such as
    ``blocked: ModuleNotFoundError`` carries none of these markers and stays a
    failure. Refs #1227, #851.

    Anything else (including ``exit 1``, ``failed``, free-form prose) is
    treated as a failure signal. Refs #411, #417, #453, #927.
    """
    raw_text = result.strip()
    text = raw_text
    if text.startswith("`") and text.endswith("`") and len(text) >= 2:
        text = text[1:-1].strip()
    # Strip a trailing operator-commentary parenthetical so it does not
    # mask a pass marker on the primary value (e.g.
    # `\`yaml syntax ok\` (parsed without exception)` --> `\`yaml syntax ok\``,
    # `1476 passed, coverage 94.24% (gate 92.71%)` --> `1476 passed, ...`).
    # Re-strip backticks if newly applicable. Refs #453.
    stripped = re.sub(r"\s*\([^()]*\)\s*$", "", text).strip()
    if stripped != text:
        text = stripped
        if text.startswith("`") and text.endswith("`") and len(text) >= 2:
            text = text[1:-1].strip()
    if _RESULT_FAILING_COUNT_RE.search(text):
        return False
    if _RESULT_PASSING_NUMERIC_RE.match(text):
        return True
    if _RESULT_PASSING_ALL_UNIT_RE.match(text):
        return True
    if _RESULT_PASSING_COUNT_RE.match(text):
        return True
    if _RESULT_PASSING_TRAILING_OK_RE.search(text):
        return True
    if _RESULT_PASSING_NON_ASCII_ZERO_RE.search(raw_text):
        return True
    if _RESULT_PASSING_NIX_QUOTED_RE.match(text):
        return True
    if _RESULT_PASSING_GREP_N_RE.match(text):
        return True
    if _RESULT_PASSING_SHASUM_RE.match(text):
        return True
    if _RESULT_PASSING_HEX_HASH_RE.match(text):
        return True
    if _RESULT_PASSING_PKG_VERSION_RE.match(text):
        return True
    if _RESULT_PASSING_NIX_TOOL_RE.match(text):
        return True
    if _RESULT_PASSING_EXIT_ZERO_RE.search(text):
        return True
    if _RESULT_ENV_SKIP_RE.search(text):
        return True
    lower = text.lower()
    raw_lower = raw_text.lower()
    return any(lower.startswith(prefix) for prefix in _RESULT_PASSING_PREFIXES) or any(
        phrase in raw_lower for phrase in _RESULT_PASSING_OBSERVATION_PHRASES
    )


def extract_verification_pairs(body: str) -> list[VerificationPair]:
    """Parse ``## Verification`` from a PR body into command/result pairs.

    Returns an empty list when the section is absent or empty. Pairing
    is order-dependent (command line followed immediately by a result
    line on the next physical line) so a stray ``command:`` or
    ``result:`` does not produce a half pair.
    """
    section = _slice_section(body, "Verification")
    if not section.strip():
        return []
    lines = section.splitlines()
    pairs: list[VerificationPair] = []
    i = 0
    while i < len(lines):
        cmd_match = _VERIFICATION_COMMAND_RE.fullmatch(lines[i])
        if cmd_match is not None and i + 1 < len(lines):
            res_match = _VERIFICATION_RESULT_RE.fullmatch(lines[i + 1])
            if res_match is not None:
                cmd_text = lines[i].split("command:", 1)[1].strip()
                res_text = lines[i + 1].split("result:", 1)[1].strip()
                pairs.append(
                    VerificationPair(
                        command=cmd_text,
                        result=res_text,
                        passed=_result_is_passing(res_text),
                    )
                )
                i += 2
                continue
        i += 1
    return pairs


def extract_post_merge_checklist(body: str) -> list[tuple[str, bool]]:
    """Parse ``## Checklist > ### Post-merge`` into ``[(item, checked)]``.

    Returns ``[]`` when the Checklist section or its Post-merge H3 is
    absent. ``After-merge`` and ``Bootstrap`` siblings are not included.
    The subsection match is case-insensitive and tolerates a trailing
    parenthetic clarifier (``### Post-merge (auto-retro signal)``).

    Not called at merge time after #418: the Post-merge subsection is
    structurally unchecked when auto-retro opens the issue. Retained
    here for the deferred re-scan workflow tracked in #421, which will
    revisit the merged PR body after the observation window closes.
    """
    section = _slice_section(body, "Checklist")
    if not section.strip():
        return []
    lines = section.splitlines()
    h3_pattern = re.compile(r"^###[ \t]+(.+?)[ \t]*$")
    item_pattern = re.compile(r"^[ \t]*-[ \t]+\[([ xX])\][ \t]+(.+?)\s*$")
    start: int | None = None
    end = len(lines)
    for i, line in enumerate(lines):
        match = h3_pattern.match(line)
        if match is None:
            continue
        text = match.group(1).rstrip(":").strip()
        base = text.split("(", 1)[0].strip().casefold()
        if start is None:
            if base == "post-merge":
                start = i + 1
            continue
        end = i
        break
    if start is None:
        return []
    items: list[tuple[str, bool]] = []
    for line in lines[start:end]:
        m = item_pattern.match(line)
        if m is None:
            continue
        checked = m.group(1).lower() == "x"
        items.append((m.group(2).strip(), checked))
    return items


def compute_repair_signals(
    pr: MergedPR,
    has_inline_comments: bool,
    commit_subjects: list[str] | None = None,
) -> dict[str, bool]:
    """Return a dict of `signal_name -> fired` describing observable repair
    evidence on the merged PR. Used by :func:`run` to decide whether to open
    a retrospective issue.

    Each signal is independently weak; their logical OR is the gate. The
    historical signal (`has_inline_comments`) is retained verbatim; the
    remaining heuristics catch repair loops captured outside the PR's
    review thread; in sibling issues, in fix-typed titles, or in
    fix-up commits squashed at merge. See issue #298 for the reproducer:
    PR #275 and PR #288 merged with zero inline review comments yet
    carried substantial repair history in issues #287 and #273.

    ``body_cites_refs`` was retired as a standalone trigger in #1227, and
    ``verification_pairs_failed`` was retired the same way in #1236: both
    keyed off non-discriminating or untrusted PR-body prose and dominated
    label-prior pollution. Repair loops captured in sibling issues are still
    caught by the remaining signals (review comments, fix-typed titles,
    fix-up / iteration commits) and by the deterministic GitHub check-run
    state surfaced in :func:`_repair_history_rows`.

    Signals returned:

    - ``inline_review_comments``: at least one comment on the PR's
      review thread (the legacy gate).
    - ``fix_typed_title``: PR title starts with ``fix(`` (Conventional
      Commit `fix` type).
    - ``multi_commit_pr``: source branch had more than one commit before
      the merge. When *commit_subjects* is supplied, merge-from-main
      commits (see :data:`_MERGE_FROM_MAIN_PREFIXES`) and revert commits
      (see :func:`_count_revert`) are subtracted from the count. Rebase
      debt created by the squash-only, linear-history merge policy does
      not fire the gate on its own, and a revert; the default rollback
      path per CLAUDE.md section 3; is an anomaly *hint* that must not
      open a retro alone: it only matters when it co-fires with another
      signal (review comments, failed CI, failed verification). The revert
      is still surfaced as a ``Revert commit`` row in the repair-history
      table for that correlation (refs #1287). When *commit_subjects* is
      ``None`` (the legacy two-arg call shape, retained for tests that do
      not exercise the gate ordering in :func:`run`) the gate falls back
      to ``pr.commits > 1``; subjects are required to subtract either
      artifact class, so the fallback fires more readily by design.
    """
    fix_typed = pr.title.lstrip().lower().startswith("fix(")
    if commit_subjects is None:
        multi_commit = pr.commits > 1
    else:
        pure_commits = (
            pr.commits
            - _count_merge_from_main(commit_subjects)
            - _count_revert(commit_subjects)
        )
        multi_commit = pure_commits > 1
    # `post_merge_unchecked` was removed in #418: the Post-merge subsection
    # is documented to be checked by the operator AFTER observing the merge,
    # so it is structurally unchecked at merge time. Re-scanning the subsection
    # is deferred to the workflow tracked in #421.
    #
    # `verification_pairs_failed` was retired as a signal in #1236, mirroring
    # the #1227 `body_cites_refs` retirement. It keyed off `_result_is_passing`
    # over free-form PR-body `## Verification` prose, which CLAUDE.md section 2
    # treats as untrusted: the heuristic both under-recognized passing prose
    # (`no docs/generated drift`, `single commit over main`, `pre-push ... all
    # pass`) and could not tell an intended negative-test / before-state demo
    # (`exit 1` by design) from a real repair, making it the dominant FP source
    # behind the #1235..#1459 retro flood. Genuine repair loops are still
    # caught deterministically by the surviving signals (inline review
    # comments, fix-typed titles, multi-commit / iteration commits) and by the
    # GitHub check-run state read in `_repair_history_rows`. The prose rows are
    # retained as non-actionable policy-artifact anomaly hints (see
    # `_repair_history_rows`) for co-fire correlation only.
    return {
        "inline_review_comments": bool(has_inline_comments),
        "fix_typed_title": fix_typed,
        "multi_commit_pr": multi_commit,
    }


def render_repair_signals(signals: dict[str, bool]) -> str:
    """Render a one-line summary of the signal aggregate for log/summary use."""
    return ", ".join(f"{name}={str(fired).lower()}" for name, fired in signals.items())


# Single source of truth for the signal universe. Mirrors the keys
# returned by :func:`compute_repair_signals` and is consumed by the
# label-derived prior helpers below. Kept as a tuple (not a frozenset)
# so the rendered "Signals fired:" line has a stable ordering across
# runs; required for byte-identical retro bodies on re-run of the
# same merge event. Refs #582.
_SIGNAL_NAMES: tuple[str, ...] = (
    "inline_review_comments",
    "fix_typed_title",
    "multi_commit_pr",
)


def render_signals_fired_line(signals: dict[str, bool]) -> str:
    """Render the ``- Signals fired: ...`` Facts-section line.

    Lists every signal whose ``fired`` flag is True in declaration
    order, comma-separated. Returns ``- Signals fired: (none)`` when
    no signal fires; empty payload is still parseable by
    :func:`parse_signals_from_retro_body`.

    The shape is fixed because :func:`parse_signals_from_retro_body`
    parses it as a deterministic feature when reconstructing past
    retros for the prior calculator. Refs #582.
    """
    fired = [name for name in _SIGNAL_NAMES if signals.get(name, False)]
    if not fired:
        return "- Signals fired: (none)"
    return "- Signals fired: " + ", ".join(fired)


_SIGNALS_FIRED_LINE_RE = re.compile(
    r"^\s*-\s+Signals fired:\s*(.*?)\s*$", re.MULTILINE
)


def parse_signals_from_retro_body(body: str) -> frozenset[str]:
    """Extract the signal-name set from a retro body's Facts section.

    Returns an empty frozenset when the body has no ``Signals fired:``
    line (legacy retros from before #582 landed) or when the line
    contains the sentinel ``(none)``. Tolerates extra whitespace and
    case variation in the signal names but rejects names not in
    :data:`_SIGNAL_NAMES` so a typo on the producing side does not
    silently poison the prior. Refs #582.
    """
    cleaned = strip_html_comments(body or "")
    match = _SIGNALS_FIRED_LINE_RE.search(cleaned)
    if match is None:
        return frozenset()
    payload = match.group(1).strip()
    if not payload or payload.lower() == "(none)":
        return frozenset()
    known = set(_SIGNAL_NAMES)
    names = {part.strip() for part in payload.split(",") if part.strip()}
    return frozenset(names & known)
