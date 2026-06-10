#!/usr/bin/env python3
"""Auto-open a retrospective issue when a pull request is merged.

Invoked from ``.github/workflows/post-merge.yml`` as the single
``python3 scripts/auto_retro.py run`` entry point. The workflow only
marshals env vars; all logic lives here and is unit-tested in
``tests/test_auto_retro.py``.

Implements CLAUDE.md section 3: "After each merge, auto-open a
retrospective issue -- make this deterministic, not operator-memory."
Refs #234.

Follows the refactor pattern established by ``scripts/scan_non_ascii.py``:
pure functions on top, a thin :func:`gh_api` subprocess boundary at the
bottom, monkeypatched in tests.

Skip conditions:

* the merged PR is itself a retrospective. Detected when the title's
  ``type(scope)`` token contains the literal ``(auto-retro)`` scope (e.g.
  ``fix(auto-retro):``, ``docs(auto-retro):``) -- covering both the
  auto-opened retro shape and retro-closing PRs. Avoids recursion.
* the merged PR was authored or merged by a login in
  ``_trusted_bots._TRUSTED_BOT_LOGINS``
* a retro issue already exists for the source PR (open or closed)
* the merged PR has zero inline review comments (positive-control
  merge: no observable repair history to record). Falls back to
  creating the retro when the comments lookup raises, so transient
  API errors preserve the audit trail.

Issue shape mirrors ``body_policy._ISSUE_COMMON_REQUIRED`` so the
auto-opened issue passes ``verify-body-policy``. The script does not
import that constant to avoid a circular dependency at workflow load
time; ``tests/test_auto_retro.py`` asserts the two stay aligned.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from _retro_labels import (
    ALL_RETRO_LABELS,
    PRIOR_EPOCH_MIN_RETRO_NUMBER,
    PRIOR_FETCH_LIMIT,
    PRIOR_MIN_SAMPLE_SIZE,
    PRIOR_SKIP_THRESHOLD,
    PRIOR_TENTATIVE_THRESHOLD,
    RETRO_FP,
    RETRO_FP_CANDIDATE,
    RETRO_TENTATIVE,
    RETRO_TP,
)
from _trusted_bots import _TRUSTED_BOT_LOGINS
from issue_link import extract_refs, strip_html_comments
from pr_upsert import upsert_single_file_pr
from script_ast_graph import (
    GraphEdge as DecisionTreeEdge,
)
from script_ast_graph import (
    GraphNode as DecisionTreeNode,
)
from script_ast_graph import (
    build_function_graph,
    render_mermaid,
)

_TRIAGE_REPORT_DOC_PATH = Path("docs/generated/scripts/auto-retro-triage-report.md")

# Fixed branch / PR identity for the post-merge triage-report refresh. The
# branch name is reused across runs, but the snapshot commit is published with
# recreate=True (pr_upsert.upsert_single_file_pr): on each drift the branch is
# deleted and re-created off main with one signed createCommitOnBranch commit, so
# it never accumulates ancestry. The earlier reuse-and-append design (#1466) left
# a legacy unsigned ancestor on the branch that permanently violated the main
# required_signatures rule while non_fast_forward blocked rewriting it (#1560). A
# delete+create is not a force-push, so non_fast_forward is still honored.
# Refs #1042, #1386, #1466, #1560.
_TRIAGE_REPORT_PR_BRANCH = "chore/refresh-auto-retro-triage-report"
_TRIAGE_REPORT_PR_TITLE = "chore(auto-retro): refresh triage report"
_TRIAGE_REPORT_COMMIT_TRAILER = "Refs #1042"
_TRIAGE_REPORT_PR_BODY = (
    "Refreshes the auto-retro triage report snapshot from the current\n"
    "retro-issue label state after a merge to `main`.\n"
    "\n"
    "This report is non-deterministic (it depends on live GitHub state), so\n"
    "it is refreshed on merge and opened as a pull request rather than\n"
    "regenerated as part of the deterministic generated docs. The snapshot commit is\n"
    "created server-side via the signed createCommitOnBranch path. The fixed\n"
    "refresh branch is re-created from main on each run (delete then create, not a\n"
    "force-push) so it never accumulates an unsigned ancestor that would block the\n"
    "required_signatures rule.\n"
    "\n"
    "Refs #1042. Refs #1386. Refs #1466. Refs #1560.\n"
)

# Refs issue #380: GitHub may not finalize merge_commit_sha by the time
# pull_request_target.closed fires; retry the PR-detail fetch with
# bounded exponential backoff before falling through to the empty-list
# soft-fail. Total max wait = sum(_MERGE_SHA_RETRY_BACKOFF) seconds.
_MERGE_SHA_RETRY_ATTEMPTS: int = 4
_MERGE_SHA_RETRY_BACKOFF: tuple[float, ...] = (2.0, 4.0, 8.0)

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
# means the operator's pattern was found in the file -- i.e. the file
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
_REPAIR_CAUSE_FILL = "(fill: cause -- how this repair arose)"
_REPAIR_NEXT_ACTION_FILL = (
    "(fill: next action -- gate or issue to prevent recurrence)"
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


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


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
    ``(auto-retro)`` -- covering both auto-opened retros and retro-closing
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
# commit is an expected artifact, not a repair loop on its own -- but unlike
# merge-from-main (pure structural rebase debt) it is an anomaly *hint*: it
# subtracts from the multi_commit_pr count yet is still recorded for co-fire
# correlation (refs #1287).
_REVERT_PREFIXES: tuple[str, ...] = ('Revert "',)

# Conventional revert subjects: `revert: ...`, `revert(scope): ...`, and the
# breaking `revert!: ` / `revert(scope)!: `. The `: ` separator is required so
# `revert this thing` (no colon) and `fix(revert): ...` (revert only in the
# scope slot, a real fix commit) do NOT match -- consistent with
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
    review thread -- in sibling issues, in fix-typed titles, or in
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
      not fire the gate on its own, and a revert -- the default rollback
      path per CLAUDE.md section 3 -- is an anomaly *hint* that must not
      open a retro alone: it only matters when it co-fires with another
      signal (review comments, failed CI, failed verification). The revert
      is still surfaced as a ``Revert commit`` row in the repair-history
      table for that correlation (refs #1287). When *commit_subjects* is
      ``None`` (the legacy two-arg call shape, retained for tests that do
      not exercise the gate ordering in :func:`run`) the gate falls back
      to ``pr.commits > 1`` -- subjects are required to subtract either
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
# runs -- required for byte-identical retro bodies on re-run of the
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
    no signal fires -- empty payload is still parseable by
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


@dataclass(frozen=True)
class PastRetro:
    """A past retro issue's signal set and label set, captured for the prior.

    ``signals`` is the frozenset of signal names parsed from the retro
    body's ``- Signals fired:`` line (empty for pre-#582 retros).
    ``labels`` is the frozenset of label strings currently applied to
    the retro -- the prior only cares whether ``retro:fp`` is among
    them, but the full set is preserved so future retrofits can layer
    on other labels without changing the dataclass shape.

    ``state`` (``"open"``/``"closed"``) and ``title`` default to the
    pre-#1386 values so the prior/drift/sentinel construction sites and
    every existing test keep working unchanged; the triage-report
    dashboard (recent-retros list, open-untriaged count) reads them when
    populated by :func:`fetch_past_retro_labels`.
    """

    number: int
    signals: frozenset[str]
    labels: frozenset[str]
    state: str = "open"
    title: str = ""


def compute_prior_from_labels(
    past_retros: list[PastRetro],
    signal_names: tuple[str, ...] = _SIGNAL_NAMES,
    epoch_min_number: int = 0,
) -> dict[str, tuple[float, int]]:
    """For each signal name, return ``(fp_rate, sample_size)``.

    ``fp_rate`` is

        |{r in eligible : signal in r.signals and RETRO_FP in r.labels}|
        / max(1, |{r in eligible : signal in r.signals}|)

    and ``sample_size`` is the denominator (un-floored). Empty input
    yields ``(0.0, 0)`` for every signal -- the consumer
    (:func:`should_skip_by_prior`) gates on ``sample_size >=
    PRIOR_MIN_SAMPLE_SIZE`` so the empty-prior case degrades to
    "open normally" rather than to a silent skip. Refs #582.

    *epoch_min_number* drops retros whose issue ``number`` is below the
    boundary from the population before any counting -- the live skip
    decision in :func:`run` passes
    :data:`PRIOR_EPOCH_MIN_RETRO_NUMBER` so retros opened under the old
    (pre-#1227) signal semantics do not poison the prior. The default
    ``0`` keeps the function a pure tally over the supplied population
    (used by the descriptive triage report and by the unit tests).
    Refs #1227.
    """
    eligible = (
        past_retros
        if epoch_min_number <= 0
        else [r for r in past_retros if r.number >= epoch_min_number]
    )
    prior: dict[str, tuple[float, int]] = {}
    for name in signal_names:
        denom = sum(1 for r in eligible if name in r.signals)
        if denom == 0:
            prior[name] = (0.0, 0)
            continue
        numer = sum(
            1 for r in eligible if name in r.signals and RETRO_FP in r.labels
        )
        prior[name] = (numer / denom, denom)
    return prior


# Triage labels in the fixed display order used by the triage report.
# Mirrors the universe in :data:`ALL_RETRO_LABELS` but is ordered so the
# rendered pie/table is byte-stable across runs. Refs #1042.
_TRIAGE_LABELS: tuple[str, ...] = (
    RETRO_TP,
    RETRO_FP,
    RETRO_FP_CANDIDATE,
    RETRO_TENTATIVE,
)
_UNLABELLED_KEY: str = "unlabelled"

# How many most-recent retros (by issue number) the dashboard lists, and
# the trailing window over which it recomputes the FP rate for the trend
# line. Numbers are the recency proxy: a higher issue number is newer.
# Refs #1386.
_RECENT_RETRO_COUNT: int = 10
_FP_TREND_WINDOW: int = 20


def _retro_status(labels: frozenset[str]) -> str:
    """Return the single display status for a retro from its label set.

    Triage labels are checked in :data:`_TRIAGE_LABELS` priority order so
    a multi-labelled retro renders one stable status; a retro carrying no
    triage label is ``"untriaged"``.
    """
    for label in _TRIAGE_LABELS:
        if label in labels:
            return label
    return "untriaged"


def _retro_fp_rate(retros: list[PastRetro]) -> tuple[float, int]:
    """Return ``(fp_rate, triaged_count)`` over *retros*.

    A retro is *triaged* iff it carries ``retro:tp`` or ``retro:fp``; the
    rate is ``|retro:fp| / |triaged|``. An empty triaged population yields
    ``(0.0, 0)`` so callers can render "n/a" without a zero-division guard
    at each site.
    """
    triaged = [r for r in retros if (RETRO_FP in r.labels or RETRO_TP in r.labels)]
    if not triaged:
        return 0.0, 0
    fp = sum(1 for r in triaged if RETRO_FP in r.labels)
    return fp / len(triaged), len(triaged)


@dataclass(frozen=True)
class SignalStat:
    """Per-signal occurrence and false-positive statistics for the report.

    ``fire_count`` is the number of past retros whose ``Signals fired:``
    line carries this signal; ``fire_rate`` is that count over the total
    retro population. ``fp_count`` / ``fp_rate`` reuse the exact prior
    definition from :func:`compute_prior_from_labels` (a retro counts as
    a false positive iff it carries ``retro:fp``). ``sample_size`` equals
    ``fire_count`` and is surfaced so a reader can judge whether
    ``fp_rate`` clears :data:`PRIOR_MIN_SAMPLE_SIZE` before trusting it.
    """

    name: str
    fire_count: int
    fire_rate: float
    fp_count: int
    fp_rate: float
    sample_size: int

    @property
    def is_anomaly(self) -> bool:
        """True when the prior would skip a future retro on this signal.

        Mirrors the gate in :func:`should_skip_by_prior`: the FP rate is
        at or above :data:`PRIOR_SKIP_THRESHOLD` AND the sample is large
        enough (:data:`PRIOR_MIN_SAMPLE_SIZE`) to trust the estimate.
        This is the anomaly a human should catch by inspection.
        """
        return (
            self.sample_size >= PRIOR_MIN_SAMPLE_SIZE
            and self.fp_rate >= PRIOR_SKIP_THRESHOLD
        )


@dataclass(frozen=True)
class RecentRetro:
    """One row of the dashboard's recent-retros list.

    ``status`` is the :func:`_retro_status` display label; ``state`` is the
    GitHub issue state (``"open"``/``"closed"``).
    """

    number: int
    title: str
    status: str
    state: str


@dataclass(frozen=True)
class TriageReport:
    """Cross-retro aggregate: triage-status counts plus per-signal stats.

    ``total`` is the size of the observed retro population. ``label_counts``
    maps each triage label (and the :data:`_UNLABELLED_KEY` bucket) to the
    number of retros carrying it -- a single retro may carry more than one
    triage label, so the label counts are independent tallies and need not
    sum to ``total``. ``signal_stats`` is ordered by :data:`_SIGNAL_NAMES`.

    The remaining fields back the #1386 dashboard sections and default to
    empty/zero so older construction sites and tests stay valid:
    ``open_untriaged`` counts open retros carrying no triage label;
    ``recent`` is the most-recent slice (newest first) for the recent-retros
    table; ``fp_rate_all``/``fp_triaged`` are the all-time retro-level FP
    rate and its triaged denominator; ``fp_rate_recent``/``fp_recent_triaged``
    are the same over the trailing :data:`_FP_TREND_WINDOW` for the trend.
    """

    total: int
    label_counts: dict[str, int]
    signal_stats: tuple[SignalStat, ...]
    open_untriaged: int = 0
    recent: tuple[RecentRetro, ...] = ()
    fp_rate_all: float = 0.0
    fp_triaged: int = 0
    fp_rate_recent: float = 0.0
    fp_recent_triaged: int = 0

    @property
    def anomalies(self) -> tuple[SignalStat, ...]:
        """Signals whose prior would skip a future retro -- the headline set."""
        return tuple(s for s in self.signal_stats if s.is_anomaly)


def compute_triage_report(
    past_retros: list[PastRetro],
    signal_names: tuple[str, ...] = _SIGNAL_NAMES,
) -> TriageReport:
    """Aggregate *past_retros* into a :class:`TriageReport`.

    Pure and GitHub-independent: the caller supplies the population
    (typically from :func:`fetch_past_retro_labels`). Triage-label tallies
    count each label independently (a retro may carry several); the
    ``unlabelled`` bucket counts retros with none of
    :data:`ALL_RETRO_LABELS`. Per-signal FP statistics are taken verbatim
    from :func:`compute_prior_from_labels` so the report and the live skip
    decision can never disagree on the numbers. Refs #1042.
    """
    total = len(past_retros)
    label_counts: dict[str, int] = {
        label: sum(1 for r in past_retros if label in r.labels)
        for label in _TRIAGE_LABELS
    }
    label_counts[_UNLABELLED_KEY] = sum(
        1 for r in past_retros if not (r.labels & ALL_RETRO_LABELS)
    )
    prior = compute_prior_from_labels(past_retros, signal_names)
    signal_stats: list[SignalStat] = []
    for name in signal_names:
        fp_rate, sample = prior[name]
        # numer is an exact integer (fp_rate == numer / sample), so
        # round() recovers it without float drift for any realistic
        # population size.
        fp_count = round(fp_rate * sample)
        fire_rate = sample / total if total else 0.0
        signal_stats.append(
            SignalStat(
                name=name,
                fire_count=sample,
                fire_rate=fire_rate,
                fp_count=fp_count,
                fp_rate=fp_rate,
                sample_size=sample,
            )
        )
    open_untriaged = sum(
        1
        for r in past_retros
        if r.state == "open" and not (r.labels & ALL_RETRO_LABELS)
    )
    by_recency = sorted(past_retros, key=lambda r: r.number, reverse=True)
    recent = tuple(
        RecentRetro(
            number=r.number,
            title=r.title,
            status=_retro_status(r.labels),
            state=r.state,
        )
        for r in by_recency[:_RECENT_RETRO_COUNT]
    )
    fp_rate_all, fp_triaged = _retro_fp_rate(past_retros)
    fp_rate_recent, fp_recent_triaged = _retro_fp_rate(
        by_recency[:_FP_TREND_WINDOW]
    )
    return TriageReport(
        total=total,
        label_counts=label_counts,
        signal_stats=tuple(signal_stats),
        open_untriaged=open_untriaged,
        recent=recent,
        fp_rate_all=fp_rate_all,
        fp_triaged=fp_triaged,
        fp_rate_recent=fp_rate_recent,
        fp_recent_triaged=fp_recent_triaged,
    )


def render_triage_report_markdown(report: TriageReport) -> str:
    """Render a :class:`TriageReport` as the checked-in Markdown document.

    The shape lets a human detect an anomaly by inspection (CLAUDE.md
    section 6): the Anomalies block sits at the top, a Mermaid pie shows
    the triage-status mix, the FP-rate trend and recent-retros list make
    the live backlog visible, and the per-signal table flags every signal
    whose prior would skip a future retro. The report depends on live
    GitHub label state, so it is a non-deterministic snapshot and is NOT
    part of the deterministic generated docs. Refs #1042, #1386.
    """
    lines: list[str] = [
        "# Auto-retro triage report",
        "",
        "This file is generated from live GitHub retro-issue labels by "
        "`python3 scripts/auto_retro.py triage-report`. Do not edit it by "
        "hand. Unlike the per-script AST docs it is a non-deterministic "
        "snapshot of repository state, so it is refreshed on merge by the "
        "`post-merge.yml` workflow (which opens a pull request when the "
        "snapshot drifts) rather than as part of the deterministic generated docs.",
        "",
        f"Retros observed: **{report.total}**",
        "",
        f"Open untriaged: **{report.open_untriaged}**",
        "",
        "## Anomalies",
        "",
    ]
    if report.anomalies:
        lines.append(
            f"Signals whose prior FP rate is at or above "
            f"{PRIOR_SKIP_THRESHOLD:.2f} (n >= {PRIOR_MIN_SAMPLE_SIZE}); "
            f"these signals now suppress new retros via "
            f"`should_skip_by_prior`:"
        )
        lines.append("")
        for stat in report.anomalies:
            lines.append(
                f"- `{stat.name}`: FP rate {stat.fp_rate:.2f} "
                f"(n={stat.sample_size})"
            )
    else:
        lines.append(
            "None: no fired signal clears both the FP-rate and "
            "sample-size thresholds."
        )
    lines.extend(["", "## Triage status", ""])
    if report.total == 0:
        lines.append("No retros observed yet.")
    else:
        lines.append("```mermaid")
        lines.append("pie showData")
        lines.append('    title Triage status')
        for label in (*_TRIAGE_LABELS, _UNLABELLED_KEY):
            lines.append(f'    "{label}" : {report.label_counts[label]}')
        lines.append("```")
    lines.extend(
        [
            "",
            "## Signal occurrence and false-positive rates",
            "",
            "| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |",
            "| --- | --: | --: | --: | --: | --: | :-: |",
        ]
    )
    for stat in report.signal_stats:
        marker = "!!" if stat.is_anomaly else ""
        lines.append(
            f"| `{stat.name}` | {stat.fire_count} | "
            f"{stat.fire_rate:.2f} | {stat.fp_count} | "
            f"{stat.fp_rate:.2f} | {stat.sample_size} | {marker} |"
        )
    lines.extend(_render_fp_trend(report))
    lines.extend(_render_recent_retros(report))
    return "\n".join(lines) + "\n"


def _render_fp_trend(report: TriageReport) -> list[str]:
    """Render the retro-level FP-rate trend section.

    Compares the all-time FP rate against the trailing
    :data:`_FP_TREND_WINDOW`-retro window so a human can see at a glance
    whether triaged retros are trending more or less false-positive.
    """
    lines = ["", "## False-positive rate trend", ""]
    if report.fp_triaged == 0:
        lines.append("No triaged retros yet (no `retro:tp`/`retro:fp` labels).")
        return lines
    delta = report.fp_rate_recent - report.fp_rate_all
    if report.fp_recent_triaged == 0:
        direction = "n/a"
    elif abs(delta) < 0.005:
        direction = "flat"
    elif delta > 0:
        direction = "rising"
    else:
        direction = "falling"
    lines.append(
        f"- All-time: {report.fp_rate_all:.2f} (n={report.fp_triaged} triaged)"
    )
    lines.append(
        f"- Last {_FP_TREND_WINDOW} retros: {report.fp_rate_recent:.2f} "
        f"(n={report.fp_recent_triaged} triaged) -- {direction}"
    )
    return lines


def _render_recent_retros(report: TriageReport) -> list[str]:
    """Render the most-recent-retros table (newest first)."""
    lines = ["", "## Recent retros", ""]
    if not report.recent:
        lines.append("No retros observed yet.")
        return lines
    lines.append("| # | State | Status | Title |")
    lines.append("| --: | :-- | :-- | :-- |")
    for r in report.recent:
        title = r.title or "(no title)"
        lines.append(f"| {r.number} | {r.state} | {r.status} | {title} |")
    return lines


def auto_retro_decision_tree() -> tuple[
    tuple[DecisionTreeNode, ...], tuple[DecisionTreeEdge, ...]
]:
    """Extract the current ``run`` control-flow tree from Python AST."""
    graph = build_function_graph(Path(__file__), "run")
    return graph.nodes, graph.edges


def auto_retro_decision_tree_edges() -> tuple[DecisionTreeEdge, ...]:
    """Return AST-derived Mermaid edges for compatibility with tests."""
    _nodes, edges = auto_retro_decision_tree()
    return edges


def render_decision_tree_mermaid() -> str:
    """Render the AST-derived auto-retro decision tree as Mermaid."""
    graph = build_function_graph(Path(__file__), "run")
    return render_mermaid(graph)


def _max_active_fp(
    signals: dict[str, bool],
    prior: dict[str, tuple[float, int]],
    min_sample_size: int,
) -> tuple[float, str | None, int]:
    """Return ``(max_fp_rate, signal_name, sample_size)`` over active signals.

    Only signals that fired on the current PR AND have a sample_size of
    at least ``min_sample_size`` are considered. When no qualifying
    signal exists, returns ``(0.0, None, 0)``. Shared helper used by
    both :func:`should_skip_by_prior` and :func:`is_tentative_by_prior`
    to keep the "max wins" rule centralised.
    """
    best: tuple[float, str | None, int] = (0.0, None, 0)
    for name, fired in signals.items():
        if not fired:
            continue
        rate, sample = prior.get(name, (0.0, 0))
        if sample < min_sample_size:
            continue
        if rate >= best[0]:
            best = (rate, name, sample)
    return best


def should_skip_by_prior(
    signals: dict[str, bool],
    prior: dict[str, tuple[float, int]],
    skip_threshold: float = PRIOR_SKIP_THRESHOLD,
    min_sample_size: int = PRIOR_MIN_SAMPLE_SIZE,
) -> tuple[bool, str]:
    """Return ``(skip, reason)`` based on the label-derived prior.

    Skips when the MAX fp_rate over signals that fired on the current
    PR (and meet the sample-size floor) is greater than or equal to
    ``skip_threshold``. The "worst signal wins" rule matches
    :func:`scripts.scan_retro_followup_drift.aggregate_drift`. When
    no signal qualifies, returns ``(False, "")`` -- the empty-prior
    safety net.
    """
    rate, name, sample = _max_active_fp(signals, prior, min_sample_size)
    if name is not None and rate >= skip_threshold:
        return True, (
            f"prior FP rate {rate:.2f} for signal {name!r} "
            f"(n={sample}) >= {skip_threshold}"
        )
    return False, ""


def is_tentative_by_prior(
    signals: dict[str, bool],
    prior: dict[str, tuple[float, int]],
    tentative_threshold: float = PRIOR_TENTATIVE_THRESHOLD,
    skip_threshold: float = PRIOR_SKIP_THRESHOLD,
    min_sample_size: int = PRIOR_MIN_SAMPLE_SIZE,
) -> bool:
    """True when the prior places the retro in the tentative band.

    The tentative band is ``[tentative_threshold, skip_threshold)``:
    the prior is high enough that the retro might be a false positive
    but not high enough to skip outright. The caller (``run``) records
    this verdict by adding ``retro:tentative`` to the issue labels so
    operators see the uncertainty at triage time.

    Sample-size gating matches :func:`should_skip_by_prior` so the
    same population is considered for both decisions.
    """
    rate, name, _sample = _max_active_fp(signals, prior, min_sample_size)
    if name is None:
        return False
    return tentative_threshold <= rate < skip_threshold


def build_retro_title(pr: MergedPR) -> str:
    """``chore(auto-retro): review PR #<N> repair loops``.

    The title is a fixed ``chore(auto-retro)`` Conventional Commit token:
    ``chore`` is an allowed type in ``.github/title-policy.toml`` and
    ``auto-retro`` is the canonical scope, so the auto-opened retro title
    is policy-conformant. ``chore`` is deliberately neutral: a retro issue
    is a triage signal, not a directly actionable fix, so the prefix must
    not read as ``fix`` and invite a direct implementation PR off an
    un-triaged retro (Refs #1069). The source PR's own ``type(scope)`` is
    not encoded in the title; it remains recorded in the issue body's Facts
    section.
    """
    return f"chore(auto-retro): review PR #{pr.number} repair loops"


# check_run conclusion values that count as a repair signal. Excludes
# success / neutral / skipped (no repair to record).
_CHECK_RUN_FAIL_CONCLUSIONS: frozenset[str] = frozenset(
    {"failure", "timed_out", "cancelled", "action_required"}
)

# Bound the rendered Repair history table: emit at most this many failed
# check_run rows, then a single overflow row summarising the remainder.
# Keeps the retro issue body well under GitHub's 65,536-char limit even
# with a CI explosion. Refs issue #381.
_CHECK_RUN_DISPLAY_CAP: int = 20

# Per-row cap on the truncated annotation summary string, so a verbose
# annotation message cannot inflate the retro body unbounded. Refs #381.
_ANNOTATION_SUMMARY_MAX: int = 200

# Annotations fetched per failed check_run. Small ceiling so the
# auto-retro orchestrator stays well within GitHub REST rate limits even
# on a CI fanout; we only need to land on the first ``failure``-level
# entry. Refs #381.
_ANNOTATION_FETCH_LIMIT: int = 5


def _escape_table_cell(text: str) -> str:
    """Escape a string for safe placement inside one markdown-table cell.

    Replaces ``|`` with ``\\|`` (so a commit subject containing a pipe
    does not split the row) and collapses any embedded newline or
    carriage return to a single space (so a multi-line value does not
    break out of the cell).
    """
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _repair_history_rows(
    check_runs: list[dict[str, Any]] | None,
    commit_subjects: list[str],
    pr_commit_count: int,
    verification_pairs: list[VerificationPair] | None = None,
    pr_type: str = "",
) -> list[RepairHistoryRow]:
    """Return generated Repair history rows before markdown rendering.

    Walks deterministic signal classes in fixed order: CI failures,
    fix-up commits (canonical fix exempted on fix-typed PRs as a
    distinct ``Fix commit`` row -- see #413), merge-from-main commits,
    multi-commit summary, and failed Verification pairs. Emits a
    sentinel row only when all classes produced zero rows. The
    Post-merge checklist class was removed in #418 because its items
    are unchecked at merge time by design; deferred re-scan is tracked
    in #421.

    When ``pr_type == "fix"``, the first non-merge-from-main commit
    subject that itself starts with ``fix(`` is rendered as a
    ``Fix commit`` row instead of ``Iteration commit``: it is the
    canonical fix the PR was opened to land, not evidence of an earlier
    silent failure. ``fixup!`` and ``squash!`` subjects remain
    unconditional iteration markers regardless of PR type because they
    are explicit iteration prefixes by convention.

    Cells are run through :func:`_escape_table_cell` so commit subjects
    containing ``|`` cannot break the table. The shape mirrors the
    canonical hand-rewrites of #305, #307, #317, #333, #334, #336 on
    2026-05-25. Refs issue #343.
    """
    rows: list[RepairHistoryRow] = []

    rendered_failed = 0
    total_failed = 0
    for entry in check_runs or []:
        conclusion = str(entry.get("conclusion") or "")
        if conclusion not in _CHECK_RUN_FAIL_CONCLUSIONS:
            continue
        total_failed += 1
        if rendered_failed >= _CHECK_RUN_DISPLAY_CAP:
            continue
        rendered_failed += 1
        name = str(entry.get("name") or "(unnamed)")
        completed = str(entry.get("completed_at") or "(no completed_at)")
        html_url = str(entry.get("html_url") or "").strip()
        summary_raw = entry.get("_annotation_summary")
        summary = str(summary_raw).strip() if summary_raw else ""
        parts = [f"conclusion={conclusion} at {completed}"]
        if html_url:
            parts.append(f"logs: {html_url}")
        if summary:
            parts.append(f"annotation: {summary}")
        detail = "; ".join(parts) or _REPAIR_CAUSE_FILL
        rows.append(
            RepairHistoryRow(
                f"CI fail: {name}",
                detail,
                next_action=_REPAIR_NEXT_ACTION_FILL,
            )
        )

    overflow = total_failed - _CHECK_RUN_DISPLAY_CAP
    if overflow > 0:
        rows.append(
            RepairHistoryRow(
                f"CI fail: + {overflow} more failures",
                "see PR check-run list (truncated)",
                next_action=_REPAIR_NEXT_ACTION_FILL,
            )
        )

    # Issue #413: on a fix-typed PR the first non-merge-from-main commit
    # that itself starts with `fix(` is the canonical fix the PR landed,
    # not an iteration on an earlier silent failure. Compute its index
    # once so the row-emit loop below can split it out as a `Fix commit`
    # row. Reuses _MERGE_FROM_MAIN_PREFIXES so the "non-merge" definition
    # stays consistent with _count_merge_from_main and the policy-artifact
    # rows below.
    canonical_fix_index: int | None = None
    if pr_type == "fix":
        for i, subject in enumerate(commit_subjects):
            stripped_i = subject.strip()
            if any(
                stripped_i.startswith(prefix)
                for prefix in _MERGE_FROM_MAIN_PREFIXES
            ):
                continue
            if stripped_i.startswith("fix("):
                canonical_fix_index = i
            break

    for i, subject in enumerate(commit_subjects):
        stripped = subject.strip()
        if i == canonical_fix_index:
            rows.append(
                RepairHistoryRow(
                    "Fix commit",
                    f"{_POLICY_ARTIFACT_MARKER} `{subject}` -- "
                    "canonical fix commit on fix-typed PR",
                    policy_artifact=True,
                    next_action="--",
                )
            )
            continue
        if (
            stripped.startswith("fix(")
            or stripped.startswith("fixup!")
            or stripped.startswith("squash!")
        ):
            rows.append(
                RepairHistoryRow(
                    "Iteration commit",
                    f"{_POLICY_ARTIFACT_MARKER} `{subject}` -- "
                    "signals an earlier silent failure",
                    policy_artifact=True,
                    next_action="--",
                )
            )

    for subject in commit_subjects:
        stripped = subject.strip()
        if any(
            stripped.startswith(prefix) for prefix in _MERGE_FROM_MAIN_PREFIXES
        ):
            rows.append(
                RepairHistoryRow(
                    "Merge from main",
                    f"{_POLICY_ARTIFACT_MARKER} `{subject}` -- "
                    "rebase debt before merge",
                    policy_artifact=True,
                    next_action="--",
                )
            )

    # Revert commits are an anomaly *hint*, not a standalone trigger (refs
    # #1287). compute_repair_signals subtracts them from multi_commit_pr, so a
    # revert-only PR does not fire the gate; this row keeps the revert visible
    # for co-fire correlation. Marked policy-artifact (and not "Iteration
    # commit") so _has_only_exempt_policy_artifact_rows skips a revert-only PR
    # while any genuine co-firing signal still opens the retro. Revert subjects
    # never start with fix(/fixup!/squash!, so the loops above leave them
    # untouched.
    for subject in commit_subjects:
        if _is_revert_subject(subject):
            rows.append(
                RepairHistoryRow(
                    "Revert commit",
                    f"{_POLICY_ARTIFACT_MARKER} `{subject}` -- rollback; "
                    "confirm via co-firing CI / review / verification signal",
                    policy_artifact=True,
                    next_action="--",
                )
            )

    if pr_commit_count > 1:
        rows.append(
            RepairHistoryRow(
                "Multi-commit PR",
                f"{_POLICY_ARTIFACT_MARKER} {pr_commit_count} "
                "commits squash-merged",
                policy_artifact=True,
                next_action="--",
            )
        )

    # Verification-prose rows are non-actionable anomaly hints, not a
    # standalone trigger (refs #1236). `_result_is_passing` runs over
    # free-form `## Verification` prose (untrusted per CLAUDE.md section 2)
    # and cannot reliably distinguish a real repair from an intended
    # negative-test / before-state demo or from passing prose it fails to
    # recognize. The row is kept for co-fire correlation when a deterministic
    # signal (CI failure, inline review, iteration commit) opens the retro,
    # but marked policy-artifact so `_has_only_exempt_policy_artifact_rows`
    # skips a verification-only PR -- mirroring the `Revert commit` row.
    for pair in verification_pairs or []:
        if pair.passed:
            continue
        rows.append(
            RepairHistoryRow(
                f"Verification fail: {pair.command}",
                f"{_POLICY_ARTIFACT_MARKER} observed: {pair.result} -- "
                "PR-body prose heuristic; confirm via co-firing CI / review / "
                "iteration signal before classifying",
                policy_artifact=True,
                next_action="--",
            )
        )

    # Post-merge subsection rows were removed in #418: the items are
    # checked AFTER the merge by design, so they are always unchecked at
    # the moment auto-retro runs. Deferred re-scan tracked in #421.
    return rows


def _has_only_exempt_policy_artifact_rows(rows: list[RepairHistoryRow]) -> bool:
    """True when rows contain only low-noise policy artifacts.

    Iteration commits keep their marker for operator taxonomy purposes,
    but they still represent a repeated repair commit and remain
    actionable for retro creation. Refs #594.
    """
    return bool(rows) and all(
        row.policy_artifact and row.repair != "Iteration commit" for row in rows
    )


def _build_repair_history_table(
    check_runs: list[dict[str, Any]] | None,
    commit_subjects: list[str],
    pr_commit_count: int,
    verification_pairs: list[VerificationPair] | None = None,
    pr_type: str = "",
) -> str:
    """Render the Repair history markdown table (header + rows, no surrounds)."""
    rows = _repair_history_rows(
        check_runs,
        commit_subjects,
        pr_commit_count,
        verification_pairs,
        pr_type,
    )

    header = (
        "| # | Repair | Cause | Next action |\n"
        "|---|--------|-------|-------------|\n"
    )
    if not rows:
        return (
            header
            + "| -- | (no automated repair signals detected) "
            "| positive-control: no repair taxonomy classification requested "
            "| -- |\n"
        )
    body_rows = "".join(
        f"| {idx} | {_escape_table_cell(row.repair)} "
        f"| {_escape_table_cell(row.detail)} "
        f"| {_escape_table_cell(row.next_action)} |\n"
        for idx, row in enumerate(rows, start=1)
    )
    footnote = ""
    if any(row.policy_artifact for row in rows):
        footnote = (
            "\n"
            f"_{_POLICY_ARTIFACT_MARKER} rows are forced by the squash + "
            "linear-history + strict-status-checks policy in "
            "`.github/rulesets/main.json`. They are exempt from the "
            "CLAUDE.md section 3 classification taxonomy and may be "
            "skipped when filling the classification column._\n"
        )
    return header + body_rows + footnote


def build_retro_body(
    pr: MergedPR,
    commit_subjects: list[str],
    check_runs: list[dict[str, Any]] | None = None,
    verification_pairs: list[VerificationPair] | None = None,
    signals: dict[str, bool] | None = None,
) -> str:
    """Return the markdown body. Contains every section in :data:`_REQUIRED_SECTIONS`.

    ``check_runs`` defaults to ``None`` so legacy two-arg callers keep
    working; in that case the Repair history table falls back to
    commit-subject signals only (and emits the sentinel row when those
    are also empty).

    ``signals`` is the :func:`compute_repair_signals` output for the
    source PR; when provided, a ``- Signals fired:`` line is added to
    the Facts section so future :func:`compute_prior_from_labels`
    invocations can reconstruct the signal set deterministically
    without re-fetching the source PR. When omitted (legacy callers),
    the line is rendered as ``- Signals fired: (none)`` -- contributing
    zero observations to the prior, which is the safe degradation. Refs #582.
    """
    type_scope = extract_type_scope(pr.title)
    # Bare type (scope stripped) drives the canonical-fix exemption in
    # _build_repair_history_table.
    pr_type = type_scope.split("(", 1)[0] if type_scope else ""
    fallback_note = ""
    if not type_scope:
        fallback_note = (
            "\n- Note: source PR title did not parse as a Conventional "
            "Commit-style `type(scope): subject`; the source type is "
            "recorded as empty for repair-history classification.\n"
        )
    layer_str = (
        ", ".join(pr.layer_labels) if pr.layer_labels else "(none on source PR)"
    )
    commits_block = (
        "\n".join(f"  - {subj}" for subj in commit_subjects)
        if commit_subjects
        else "  - (no commit subjects fetched)"
    )
    repair_table = _build_repair_history_table(
        check_runs,
        commit_subjects,
        pr.commits,
        verification_pairs,
        pr_type=pr_type,
    )
    # Idempotent date stamp: derive from pr.merged_at (already an ISO
    # 8601 string from the event payload) rather than datetime.now() so
    # the body is byte-identical on re-run of the same event.
    triage_date = pr.merged_at[:10] if pr.merged_at else "YYYY-MM-DD"
    positive_control = "(no automated repair signals detected)" in repair_table
    proposed_work_tail = (
        "\n"
        "<!-- operator-fill:remaining-steps -->\n"
        "2. Classification -- (operator) tag each repair above as one of: "
        "`missing deterministic gate` / `unclear agent instruction` / "
        "`external or human decision that cannot be automated`.\n"
        "3. Earliest prevention point -- (operator) per repair, name the "
        "deterministic gate that should have caught it (workflow, hook, "
        "ruleset, label, preflight).\n"
        "4. No-repair reproduction path -- (operator) numbered steps the next "
        "similar PR should follow to land in one shot.\n"
        "5. Follow-up issues -- (operator) list deferred gates as "
        "`- [ ] type(scope): TITLE -- RATIONALE` or write `(none)`.\n"
        "<!-- /operator-fill:remaining-steps -->\n"
    )
    verification_block = (
        "- Every repair in the table has a classification from the "
        "section 3 taxonomy.\n"
        "- Every non-artifact repair row has a non-empty Cause and Next "
        "action cell (no '(fill: ...)' sentinel remains).\n"
        "- Every repair has a named earliest prevention point.\n"
        "- The no-repair reproduction path matches what would happen if "
        "the deterministic gates from this retrospective were in place.\n"
        "- The `## Follow-up issues` section (if any) is machine-parseable "
        "per the bullet convention above.\n"
    )
    acceptance_block = (
        "- [ ] Repair history table complete.\n"
        "- [ ] Every non-artifact repair row has Cause and Next action "
        "filled.\n"
        "- [ ] Each repair classified with the section 3 taxonomy.\n"
        "- [ ] Each repair has an earliest prevention point.\n"
        "- [ ] No-repair reproduction path stated.\n"
        "- [ ] `## Follow-up issues` filed (or explicitly stated `(none)`).\n"
    )
    if positive_control:
        proposed_work_tail = (
            "\n"
            "2. Positive-control outcome -- no automated repair signals were "
            "detected, so no repair taxonomy classification is requested.\n"
        )
        verification_block = (
            "- The repair history table is explicitly labelled as a "
            "positive-control no-signal outcome.\n"
            "- No operator repair taxonomy classification is requested.\n"
        )
        acceptance_block = (
            "- [ ] Positive-control no-signal outcome recorded.\n"
            "- [ ] No repair taxonomy classification requested.\n"
        )
    return (
        "## Scope\n"
        "\n"
        f"Retrospective for merged PR #{pr.number} (`{pr.title}`). "
        "Review repair-free merge reproducibility per CLAUDE.md section 3: "
        "list every repair required between PR open and merge; identify the "
        "earliest deterministic gate that should have prevented each repair; "
        "and state how the next run will reproduce the no-repair path.\n"
        "\n"
        "## Facts\n"
        "\n"
        f"- Source PR: #{pr.number} -- {pr.title}\n"
        f"- Source PR URL: {pr.html_url}\n"
        f"- Merged at (UTC): {pr.merged_at}\n"
        f"- Merged by: {pr.merged_by_login or '(unknown)'}\n"
        f"- Source PR author: {pr.user_login or '(unknown)'}\n"
        f"- Layer labels inherited from source PR: {layer_str}\n"
        f"{render_signals_fired_line(signals or {})}\n"
        "- Commit subjects in PR (repair-history candidates):\n"
        f"{commits_block}\n"
        f"{fallback_note}"
        "\n"
        "## Proposed work\n"
        "\n"
        "<!-- auto-filled:repair-history -->\n"
        "1. Repair history -- the table below is pre-filled from "
        "check_runs + commit subjects. Fill the Next action cell of every "
        "non-artifact row; edit Cause only to correct or add missed "
        "repairs.\n"
        "\n"
        f"{repair_table}"
        "<!-- /auto-filled:repair-history -->\n"
        f"{proposed_work_tail}"
        "\n"
        "## Verification\n"
        "\n"
        f"{verification_block}"
        "\n"
        "## Acceptance criteria\n"
        "\n"
        f"{acceptance_block}"
        "\n"
        "## Parent\n"
        "\n"
        "Refs CLAUDE.md section 3 (\"After each merge, auto-open a "
        f"retrospective issue\"). Source PR: #{pr.number}.\n"
        "\n"
        "_Opened automatically by `.github/workflows/post-merge.yml`. "
        f"Proposed work pre-filled by retro triage {triage_date} "
        "(auto-filled rows: check_runs + commit subjects; operator-filled "
        "rows: classification, prevention point, no-repair path, "
        "follow-ups)._\n"
    )


def verify_retro_repair_completeness(body: str) -> list[str]:
    """Return ``::error::`` strings for unfilled Repair history rows.

    Scans the ``<!-- auto-filled:repair-history -->`` block of a retro
    issue body and flags every non-artifact data row whose Cause cell
    (column 3) or Next action cell (column 4) is empty or still carries
    a ``(fill: ...)`` sentinel. Pure function consumed by the
    ``verify-retro-completeness`` CLI gate.

    Fail-safe by construction:

    - When the auto-filled block is absent the body is not a generated
      retro, so ``[]`` is returned (nothing to enforce).
    - Header and separator rows are skipped.
    - Rows carrying the ``[policy-artifact]`` marker are exempt (forced
      by repository merge policy, not actionable repairs), as is the
      positive-control no-signal sentinel row.

    A row with fewer than four cells is malformed and itself reported as
    an ``::error::``. Returns ``[]`` when the table is well-formed.
    """
    open_idx = body.find(_AUTO_FILLED_OPEN)
    close_idx = body.find(_AUTO_FILLED_CLOSE)
    if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
        return []
    block = body[open_idx:close_idx]
    errors: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        # Header row.
        if "# | Repair" in stripped:
            continue
        # Separator row: only dashes / pipes / spaces / colons.
        if set(stripped) <= set("|-: "):
            continue
        # Exemptions: policy-artifact rows and the positive-control row.
        if _POLICY_ARTIFACT_MARKER in stripped:
            continue
        if "(no automated repair signals detected)" in stripped:
            continue
        # Split into cells: drop the leading/trailing pipe, then split on
        # UNescaped pipes only. _escape_table_cell renders an in-cell pipe
        # (e.g. a verification command like `grep x | wc -l`) as ``\|``;
        # a naive split("|") would over-split that row and shift the Cause
        # / Next action columns, silently passing an unfilled retro. The
        # negative lookbehind keeps escaped pipes inside their cell, and we
        # unescape them back for the emptiness / sentinel checks.
        cells = [
            cell.strip().replace("\\|", "|")
            for cell in re.split(r"(?<!\\)\|", stripped[1:-1])
        ]
        repair_name = cells[1] if len(cells) > 1 else "(unknown)"
        if len(cells) < 4:
            errors.append(
                f"::error::repair row '{repair_name}' is malformed: "
                f"expected 4 cells (# | Repair | Cause | Next action), "
                f"got {len(cells)}."
            )
            continue
        cause = cells[2]
        next_action = cells[3]
        if not cause or "(fill:" in cause:
            errors.append(
                f"::error::repair row '{repair_name}' has an empty or "
                f"unfilled Cause cell (a '(fill: ...)' sentinel remains)."
            )
        if not next_action or "(fill:" in next_action:
            errors.append(
                f"::error::repair row '{repair_name}' has an empty or "
                f"unfilled Next action cell (a '(fill: ...)' sentinel "
                f"remains)."
            )
    return errors


def find_target_retro_from_refs(
    pr: MergedPR,
    referenced_titles: dict[int, str],
) -> int | None:
    """Return the retro issue number a fix-typed PR is amending, or ``None``.

    Used by :func:`run` to decide whether a freshly merged ``fix(...)``
    PR should append to an existing retro issue rather than open a new
    one. The match requires both:

    - the PR title starts with ``fix(`` (Conventional Commit ``fix``
      type), AND
    - the PR body has at least one line-anchored ``Refs|Closes|Fixes|
      Resolves #N`` whose target issue title is a retro issue title (see
      :func:`is_retro_issue_title`).

    The first match wins so the body order determines priority. Pure
    function: callers supply ``referenced_titles`` via :func:`fetch_issue_titles`.
    """
    if not pr.title.lstrip().lower().startswith("fix("):
        return None
    body_without_comments = strip_html_comments(pr.body or "")
    refs = extract_refs(body_without_comments)
    for number in refs:
        title = referenced_titles.get(number)
        if title is None:
            continue
        if is_retro_issue_title(title):
            return number
    return None


def render_appended_row(pr: MergedPR) -> tuple[str, str, str]:
    """Render the (repair, cause, next_action) cells for a follow-up fix row."""
    return (
        _escape_table_cell(f"Follow-up fix PR: #{pr.number}"),
        _escape_table_cell(f"`{pr.title}` merged at {pr.merged_at}"),
        _escape_table_cell(_REPAIR_NEXT_ACTION_FILL),
    )


def _next_table_index(table_text: str) -> int:
    """Return the next available row index for the auto-filled table.

    Scans existing ``| N | ... |`` rows and returns ``max(N) + 1``,
    falling back to 1 when no numbered rows exist.
    """
    pattern = re.compile(r"^\|\s*(\d+)\s*\|", re.MULTILINE)
    indexes = [int(m.group(1)) for m in pattern.finditer(table_text)]
    return max(indexes) + 1 if indexes else 1


def _insert_appended_row(
    body: str, row: tuple[str, str, str], pr_number: int
) -> tuple[str, bool]:
    """Append a row to the retro body's auto-filled block.

    Returns ``(new_body, changed)``. ``changed`` is False when:
    - the auto-filled markers are missing (caller should fail-soft), or
    - a row mentioning ``#<pr_number>`` is already present (idempotent).

    The row is inserted as a new line just before the
    ``<!-- /auto-filled:repair-history -->`` close marker.
    """
    open_idx = body.find(_AUTO_FILLED_OPEN)
    close_idx = body.find(_AUTO_FILLED_CLOSE)
    if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
        return body, False
    block = body[open_idx:close_idx]
    needle = re.compile(rf"#{pr_number}(?!\d)")
    if needle.search(block):
        return body, False
    next_idx = _next_table_index(block)
    new_line = f"| {next_idx} | {row[0]} | {row[1]} | {row[2]} |\n"
    new_body = body[:close_idx] + new_line + body[close_idx:]
    return new_body, True


def find_existing_retro(
    search_items: list[dict[str, Any]], pr_number: int
) -> int | None:
    """Return the matching retro issue number from search results, or None.

    Match heuristic: title is a retro issue title (see
    :func:`is_retro_issue_title`) AND contains ``PR #<N>`` not followed by
    another digit. The trailing ``(?!\\d)`` lookahead prevents PR-number
    prefix collisions (e.g. a lookup for #249 must not match a retro for
    #2490). The prefix guard avoids matching an unrelated issue that
    happens to mention the same PR number.
    """
    needle = re.compile(rf"PR #{pr_number}(?!\d)")
    for item in search_items:
        title = item.get("title") or ""
        if not is_retro_issue_title(title):
            continue
        if needle.search(title):
            return item.get("number")
    return None


_ACCEPTANCE_CHECKBOX_RE = re.compile(
    r"^[ \t]*-[ \t]+\[([ xX])\][ \t]+", re.MULTILINE
)


def is_retro_untouched(body: str, comments: list[dict[str, Any]]) -> bool:
    """Return True when the retro body and comments show no operator engagement.

    Sentinel signal for issue #414. "Untouched" means BOTH:

    * every acceptance-criteria checkbox in the body is still ``[ ]``
      (no operator marked any progress); AND
    * the issue has no comments from logins outside
      :data:`_SENTINEL_IGNORED_COMMENT_LOGINS` (no operator wrote a
      triage note instead of editing the body).

    The acceptance-criteria slice is read via :func:`_slice_section`
    rather than scanning the whole body so that operator-fill rows
    elsewhere (e.g. the Classification table under the auto-fill
    block) do not falsely satisfy the checkbox check.

    Returns False whenever the section is missing (defensive: treat
    unparseable bodies as touched so the sentinel never auto-closes
    something it cannot read).
    """
    section = _slice_section(body or "", "Acceptance criteria")
    if not section.strip():
        return False
    checkboxes = _ACCEPTANCE_CHECKBOX_RE.findall(section)
    if not checkboxes:
        return False
    if any(state.lower() == "x" for state in checkboxes):
        return False
    for comment in comments or []:
        user = comment.get("user") or {}
        login = user.get("login") or ""
        if login and login not in _SENTINEL_IGNORED_COMMENT_LOGINS:
            return False
    return True


def is_retro_age_exceeded(
    created_at: str, now_iso: str, days: int
) -> bool:
    """Return True when ``now_iso - created_at`` exceeds ``days``.

    Both arguments are ISO 8601 strings (``YYYY-MM-DDTHH:MM:SSZ``).
    Returns False on any parse failure so the sentinel never closes a
    retro whose timestamps it cannot read (fail-safe per CLAUDE.md
    section 4).
    """
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    delta = now - created
    return delta.days > days


def issue_labels(
    layer_labels: tuple[str, ...], *, tentative: bool = False
) -> list[str]:
    """Return the label list for the retro issue.

    Always ``type:docs`` + ``layer:meta``; appends any additional
    ``layer:*`` labels inherited from the source PR. Deduplicates while
    preserving order. When ``tentative`` is True, appends
    ``retro:tentative`` so operators see at triage time that the
    label-derived prior placed the retro in the uncertain band
    (refs #582).
    """
    labels = ["type:docs", "layer:meta"]
    for lbl in layer_labels:
        if lbl and lbl not in labels:
            labels.append(lbl)
    if tentative and RETRO_TENTATIVE not in labels:
        labels.append(RETRO_TENTATIVE)
    return labels


# ---------------------------------------------------------------------------
# Side-effecting boundary -- mocked in tests
# ---------------------------------------------------------------------------


def gh_api(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    *,
    timeout: int = 30,
) -> str:
    """Thin wrapper around ``gh api``. Returns stdout text.

    Raises :class:`subprocess.CalledProcessError` on any non-zero exit
    so the orchestrator fails loudly (CLAUDE.md section 4).
    """
    cmd = ["gh", "api", "--method", method, path]
    if json_body is not None:
        # S603 justification: fixed argv (no shell, no user input in argv[0]); `gh` is
        # provisioned by the workflow runner. `path` is built from event payload
        # numbers narrowed to int upstream.
        result = subprocess.run(  # noqa: S603 — fixed argv, shell=False
            [*cmd, "--input", "-"],
            input=json.dumps(json_body),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    else:
        result = subprocess.run(  # noqa: S603 — fixed argv, shell=False
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    return result.stdout


def fetch_pr_commits(repo: str, pr_number: int) -> list[str]:
    """Return commit subjects (first line of each message) for the PR."""
    raw = gh_api("GET", f"/repos/{repo}/pulls/{pr_number}/commits?per_page=100")
    commits = json.loads(raw) if raw.strip() else []
    subjects: list[str] = []
    for entry in commits:
        message = ((entry.get("commit") or {}).get("message") or "")
        subjects.append(message.split("\n", 1)[0].strip())
    return subjects


def fetch_check_runs(
    repo: str,
    pr_number: int,
    *,
    sleeper: Callable[[float], None] | None = None,
) -> list[dict[str, Any]]:
    """Return failed check_run entries for the PR's merge commit.

    Two-step fetch:

    1. ``GET /repos/{repo}/pulls/{pr_number}`` to read
       ``merge_commit_sha``. GitHub may not have finalized the SHA when
       ``pull_request_target.closed`` fires (refs issue #380), so the
       PR-detail call is retried up to :data:`_MERGE_SHA_RETRY_ATTEMPTS`
       times with the :data:`_MERGE_SHA_RETRY_BACKOFF` sequence between
       attempts. If every attempt still yields ``None``, emit a
       ``::warning::`` line and soft-fail to ``[]`` -- check_runs is an
       augmenting signal for the Repair history table, not a correctness
       invariant. The ``sleeper`` parameter is injectable for tests
       (mirrors ``scripts/_github_api.py`` ``apply_call`` precedent).
    2. ``GET /repos/{repo}/commits/{sha}/check-runs?per_page=100`` to
       enumerate runs against that SHA.

    Returns only entries whose ``conclusion`` is in
    :data:`_CHECK_RUN_FAIL_CONCLUSIONS`. The ``per_page=100`` cap is
    sufficient for this repo today (each PR runs <30 checks); overflow
    is treated as best-effort and is not paginated. Refs issue #343.

    Each returned entry is enriched with a string-or-None
    ``_annotation_summary`` field carrying a truncated single-line
    summary of the first ``failure``-level annotation (or ``None`` when
    no annotation is available, when ``id`` is missing on the entry,
    when the annotation API fails, or beyond the
    :data:`_CHECK_RUN_DISPLAY_CAP` enrichment ceiling). Refs issue #381.
    """
    # Resolve at call time so a ``time.sleep`` patch neutralises the backoff
    # wait that ``run``-level tests would otherwise pay in full (refs #985).
    sleeper = sleeper if sleeper is not None else time.sleep
    sha: str | None = None
    for attempt in range(1, _MERGE_SHA_RETRY_ATTEMPTS + 1):
        raw = gh_api("GET", f"/repos/{repo}/pulls/{pr_number}")
        pr_detail = json.loads(raw) if raw.strip() else {}
        sha = pr_detail.get("merge_commit_sha")
        if sha:
            break
        if attempt < _MERGE_SHA_RETRY_ATTEMPTS:
            sleeper(_MERGE_SHA_RETRY_BACKOFF[attempt - 1])
    if not sha:
        print(
            f"::warning::fetch_check_runs: merge_commit_sha still null "
            f"for {repo}#{pr_number} after {_MERGE_SHA_RETRY_ATTEMPTS} "
            f"attempts (backoff {list(_MERGE_SHA_RETRY_BACKOFF)}s); "
            "Repair history will use commit-subject signals only "
            "(refs issue #380)",
            file=sys.stderr,
        )
        return []
    raw = gh_api(
        "GET",
        f"/repos/{repo}/commits/{sha}/check-runs?per_page=100",
    )
    payload = json.loads(raw) if raw.strip() else {}
    all_runs = list(payload.get("check_runs") or [])
    failed_runs = [
        run
        for run in all_runs
        if str(run.get("conclusion") or "") in _CHECK_RUN_FAIL_CONCLUSIONS
    ]
    # Enrich the first _CHECK_RUN_DISPLAY_CAP runs with an annotation
    # summary so the retro Repair history rows carry recoverable context
    # after Actions log retention expires. Beyond the cap we leave the
    # field None: the overflow row in _build_repair_history_table
    # already signals truncation. Refs issue #381.
    for index, run in enumerate(failed_runs):
        run["_annotation_summary"] = None
        if index >= _CHECK_RUN_DISPLAY_CAP:
            continue
        run_id = run.get("id")
        if not isinstance(run_id, int):
            continue
        try:
            annotations = fetch_check_run_annotations(
                repo, run_id, limit=_ANNOTATION_FETCH_LIMIT
            )
        except subprocess.CalledProcessError as exc:
            # Fail-soft per acceptance criterion 3 of issue #381: a
            # single annotation lookup failure must not block the other
            # rows. The base "conclusion + completed_at" cell still
            # carries the audit signal.
            print(
                f"::warning::fetch_check_run_annotations failed for "
                f"check_run id={run_id} (exit {exc.returncode}); falling "
                "back to summary-less row",
                file=sys.stderr,
            )
            continue
        run["_annotation_summary"] = _summarize_annotations(annotations)
    return failed_runs


def fetch_check_run_annotations(
    repo: str, check_run_id: int, *, limit: int = _ANNOTATION_FETCH_LIMIT
) -> list[dict[str, Any]]:
    """Return annotations for a check_run via the REST API.

    Thin :func:`gh_api` wrapper around
    ``GET /repos/{repo}/check-runs/{id}/annotations?per_page={limit}``.
    Returns ``[]`` when the response is empty or not a JSON list. The
    caller (:func:`fetch_check_runs`) translates
    :class:`subprocess.CalledProcessError` into a fail-soft summary-less
    row; do not swallow it here so unexpected failures stay observable.
    Refs issue #381.
    """
    raw = gh_api(
        "GET",
        f"/repos/{repo}/check-runs/{check_run_id}/annotations?per_page={limit}",
    )
    if not raw.strip():
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        return []
    return parsed


def _summarize_annotations(
    annotations: list[dict[str, Any]],
) -> str | None:
    """Return a single-line summary of the first failure-level annotation.

    Picks the first entry whose ``annotation_level == "failure"`` (skips
    ``notice`` / ``warning`` since those are not the repair signal).
    Joins ``title`` and the first line of ``message`` with ``": "``;
    truncates the result to :data:`_ANNOTATION_SUMMARY_MAX` chars with a
    trailing ellipsis when the source is longer. Returns ``None`` when
    no failure-level entry is present, or when both ``title`` and
    ``message`` are empty. Refs issue #381.
    """
    for entry in annotations:
        level = str(entry.get("annotation_level") or "")
        if level != "failure":
            continue
        title = str(entry.get("title") or "").strip()
        message = str(entry.get("message") or "").strip()
        first_line = message.split("\n", 1)[0].strip() if message else ""
        if title and first_line:
            summary = f"{title}: {first_line}"
        elif title:
            summary = title
        elif first_line:
            summary = first_line
        else:
            return None
        if len(summary) > _ANNOTATION_SUMMARY_MAX:
            summary = summary[: _ANNOTATION_SUMMARY_MAX - 3] + "..."
        return summary
    return None


def search_retro_issues(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Search open + closed issues for an existing retro referencing pr_number."""
    query = f'repo:{repo} type:issue in:title "PR #{pr_number}" "retro"'
    encoded = quote(query, safe="")
    raw = gh_api("GET", f"/search/issues?q={encoded}&per_page=50")
    data = json.loads(raw) if raw.strip() else {}
    return list(data.get("items") or [])


def fetch_past_retro_labels(
    repo: str, limit: int = PRIOR_FETCH_LIMIT
) -> list[PastRetro]:
    """Return up to *limit* past retros as :class:`PastRetro` records.

    Uses a single search query matching the
    ``auto_retro.issue_labels`` convention (``type:docs`` +
    ``layer:meta`` + title contains ``retro``), then parses each
    item's body for the ``- Signals fired:`` line. Soft-fails on
    search errors and on per-item JSON shape errors -- the prior
    degrades to empty (no skip, no tentative) rather than aborting
    the retro flow.

    The query mirrors
    :func:`scripts.scan_retro_followup_drift.search_retro_issues`
    so PR1's scanner and PR2's prior population observe the same
    retro population.
    Refs #582.
    """
    query = (
        f"repo:{repo} is:issue label:type:docs "
        f"label:layer:meta in:title retro"
    )
    encoded = quote(query, safe="")
    per_page = min(max(limit, 1), 100)
    try:
        raw = gh_api(
            "GET", f"/search/issues?q={encoded}&per_page={per_page}"
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"::warning::fetch_past_retro_labels search failed "
            f"(exit {exc.returncode}); prior will be empty",
            file=sys.stderr,
        )
        return []
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return []
    items = list(data.get("items") or [])[:limit]
    out: list[PastRetro] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        if not isinstance(number, int):
            continue
        labels_raw = item.get("labels") or []
        names: set[str] = set()
        for lbl in labels_raw:
            if isinstance(lbl, dict):
                name = lbl.get("name")
                if isinstance(name, str) and name:
                    names.add(name)
        body = item.get("body")
        if not isinstance(body, str) or not body:
            body = ""
        signals = parse_signals_from_retro_body(body)
        state = item.get("state")
        state = state if isinstance(state, str) and state else "open"
        title = item.get("title")
        title = title if isinstance(title, str) else ""
        out.append(
            PastRetro(
                number=number,
                signals=signals,
                labels=frozenset(names),
                state=state,
                title=title,
            )
        )
    return out


def has_review_comments(repo: str, pr_number: int) -> bool:
    """True iff the PR has at least one inline review (diff) comment.

    Used as a zero-repair signal: an empty list from
    ``/repos/{repo}/pulls/{pr_number}/comments`` means no reviewer left
    an inline comment, so the merge has no observable repair history to
    record. The orchestrator (:func:`run`) treats any exception from
    this call as fail-safe (proceeds to open the retro) so a transient
    API error never silently swallows the audit trail.
    """
    raw = gh_api(
        "GET", f"/repos/{repo}/pulls/{pr_number}/comments?per_page=1"
    )
    items = json.loads(raw) if raw.strip() else []
    return bool(items)


def fetch_issue_titles(
    repo: str, numbers: list[int]
) -> dict[int, str]:
    """Return ``{number: title}`` for each issue in *numbers* that resolves.

    Issues that fail to fetch (404, transient error, malformed JSON) are
    omitted from the returned dict so callers can treat the lookup as
    best-effort. Used by :func:`find_target_retro_from_refs`.
    """
    out: dict[int, str] = {}
    for number in numbers:
        try:
            raw = gh_api("GET", f"/repos/{repo}/issues/{number}")
        except subprocess.CalledProcessError:
            continue
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            continue
        title = data.get("title")
        if isinstance(title, str):
            out[number] = title
    return out


def fetch_issue_body(repo: str, number: int) -> str:
    """Return the body of issue ``<repo>#<number>`` or ``""`` on failure."""
    try:
        raw = gh_api("GET", f"/repos/{repo}/issues/{number}")
    except subprocess.CalledProcessError:
        return ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return ""
    body = data.get("body")
    return body if isinstance(body, str) else ""


def patch_issue_body(
    repo: str, number: int, body: str
) -> dict[str, Any]:
    """PATCH /repos/{repo}/issues/{number} with the new body and return JSON."""
    raw = gh_api(
        "PATCH",
        f"/repos/{repo}/issues/{number}",
        {"body": body},
    )
    return json.loads(raw) if raw.strip() else {}


def append_repair_history_row(
    repo: str,
    retro_number: int,
    pr: MergedPR,
) -> tuple[bool, str]:
    """Append a follow-up fix row to ``retro_number``'s auto-filled block.

    Returns ``(changed, detail)``. ``changed`` is False when the retro
    body lacks the auto-filled markers or when an idempotent skip fires.
    Caller-friendly *detail* string is suitable for the step summary.
    """
    body = fetch_issue_body(repo, retro_number)
    if not body:
        return (
            False,
            f"could not fetch retro #{retro_number} body (skipping append)",
        )
    row = render_appended_row(pr)
    new_body, changed = _insert_appended_row(body, row, pr.number)
    if not changed:
        return (
            False,
            f"retro #{retro_number} already records PR #{pr.number} "
            "(or auto-filled markers absent)",
        )
    patch_issue_body(repo, retro_number, new_body)
    return (
        True,
        f"appended follow-up row for PR #{pr.number} to retro "
        f"#{retro_number}",
    )


def create_issue(
    repo: str, title: str, body: str, labels: list[str]
) -> dict[str, Any]:
    """POST /repos/{repo}/issues and return the parsed response."""
    raw = gh_api(
        "POST",
        f"/repos/{repo}/issues",
        {"title": title, "body": body, "labels": labels},
    )
    return json.loads(raw) if raw.strip() else {}


# Marker used to locate a previously-posted back-link comment so the
# back-link step is idempotent. Same shape as the marker convention in
# scripts/scan_non_ascii.py (see find_existing_comment_id at
# scan_non_ascii.py:313-326).
_BACK_LINK_MARKER = "<!-- auto-retro:back-link -->"

# Marker for the skip-notification comment posted on the source PR when
# auto-retro evaluates a merged PR and decides no retro is warranted.
# Idempotency anchor: reruns update the existing comment rather than
# stacking duplicates (same convention as _BACK_LINK_MARKER).
_SKIP_COMMENT_MARKER = "<!-- auto-retro:skip -->"

# Label applied to the source PR after the retro issue is opened and
# the back-link comment is posted. Emission is the harness contract --
# subscribed Claude sessions and operators read it as the signal that
# the PR has reached terminal state and no further session attention
# is required. Consumption (e.g. unsubscribe_pr_activity) is platform
# / session policy and out of scope here. SoT entry lives in
# .github/labels.json; tests/test_auto_retro.py guards the drift.
_TERMINAL_LABEL = "harness:retro-opened"

# Sentinel marker for the auto-close comment posted by the retro sentinel
# workflow (issue #414). Idempotency anchor: a retro carrying this
# marker has already been triaged by the sentinel and must not be
# re-closed on subsequent cron runs.
_SENTINEL_CLOSE_MARKER = "<!-- auto-retro-sentinel:closed -->"

# Default age threshold (in days) for the retro sentinel to consider a
# retro stale. Overridable at runtime via the AUTO_RETRO_SENTINEL_DAYS
# env var. Starting at 14 per the operator runbook rationale recorded
# in issue #414.
_DEFAULT_SENTINEL_DAYS: int = 14

# Logins whose comments do NOT count as operator engagement for the
# sentinel "untouched" check. Extends _TRUSTED_BOT_LOGINS with the
# repository's own Actions identity, which is the author of the retro
# issue itself; a self-comment from it would not signal triage.
_SENTINEL_IGNORED_COMMENT_LOGINS: frozenset[str] = (
    _TRUSTED_BOT_LOGINS | frozenset({"github-actions[bot]"})
)

# Per-page cap for the sentinel's retro search. Each cron tick processes
# at most this many open retros; overflow rolls into the next tick. A
# healthy repo carries far fewer than 50 open retros at a time, so this
# is a soft ceiling rather than a correctness constraint.
_SENTINEL_SEARCH_PAGE_SIZE: int = 50


def find_existing_back_link_id(
    repo: str, pr_number: int, marker: str = _BACK_LINK_MARKER
) -> int | None:
    """Return the id of a prior back-link comment on *pr_number*, or None.

    Pages once with ``per_page=100``; the back-link is posted exactly
    once per merge by this script, so the first page is sufficient. The
    match requires *marker* at the start of the comment body, mirroring
    the convention in :func:`scripts.scan_non_ascii.find_existing_comment_id`.
    """
    raw = gh_api(
        "GET", f"/repos/{repo}/issues/{pr_number}/comments?per_page=100"
    )
    comments = json.loads(raw) if raw.strip() else []
    for comment in comments:
        body = comment.get("body") or ""
        if body.startswith(marker):
            return comment.get("id")
    return None


_PR_COMMENTS_ENV = "AUTO_RETRO_PR_COMMENTS"


def _pr_comments_enabled() -> bool:
    """True iff PR-thread auto-retro comments are opted in.

    Phase 1 of #1386 makes the back-link and skip comments off by default:
    the triage-report dashboard
    (``docs/generated/scripts/auto-retro-triage-report.md``) is the human
    inspection surface, so a per-PR comment on every merge is redundant
    notification noise. The retro issue (quiet labeled ledger) and the
    PR-side terminal label still record the audit trail. Set
    ``AUTO_RETRO_PR_COMMENTS`` to a truthy value (``1``/``true``/``yes``/``on``)
    to restore the legacy commenting behavior.
    """
    return os.environ.get(_PR_COMMENTS_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def post_back_link_comment(
    repo: str, pr_number: int, retro_number: int
) -> str:
    """PATCH an existing back-link comment, else POST a new one.

    Idempotent via :data:`_BACK_LINK_MARKER`. The comment body is the
    marker followed by a single line ``Retrospective: #<retro_number>``;
    this is the PR -> retro reverse pointer that complements the retro
    body's ``Source PR: #`` line. Returns ``"updated <id>"`` or
    ``"created"`` for the orchestrator log.
    """
    body = f"{_BACK_LINK_MARKER}\nRetrospective: #{retro_number}"
    existing = find_existing_back_link_id(repo, pr_number)
    if existing is not None:
        gh_api(
            "PATCH",
            f"/repos/{repo}/issues/comments/{existing}",
            {"body": body},
        )
        return f"updated {existing}"
    gh_api(
        "POST",
        f"/repos/{repo}/issues/{pr_number}/comments",
        {"body": body},
    )
    return "created"


def apply_terminal_label(
    repo: str, pr_number: int, label: str = _TERMINAL_LABEL
) -> None:
    """POST *label* to the source PR's labels endpoint.

    GitHub's labels endpoint is naturally idempotent (re-adding an
    existing label is a no-op), so no pre-check is needed. The orchestrator
    is responsible for the fail-soft policy: the retro issue is already
    created by the time this fires, so a failed label add must not roll
    back the audit trail.
    """
    gh_api(
        "POST",
        f"/repos/{repo}/issues/{pr_number}/labels",
        {"labels": [label]},
    )


def post_skip_comment(repo: str, pr_number: int, reason: str) -> str:
    """PATCH an existing skip comment, else POST a new one.

    Idempotent via :data:`_SKIP_COMMENT_MARKER`. Called on evaluation-based
    skip paths so the source PR always carries evidence that auto-retro ran
    and found nothing to act on, distinguishing intentional skips from silent
    workflow failures. Returns ``"updated <id>"`` or ``"created"``.
    """
    body = f"{_SKIP_COMMENT_MARKER}\nauto-retro skipped: {reason}"
    existing = find_existing_back_link_id(
        repo, pr_number, marker=_SKIP_COMMENT_MARKER
    )
    if existing is not None:
        gh_api(
            "PATCH",
            f"/repos/{repo}/issues/comments/{existing}",
            {"body": body},
        )
        return f"updated {existing}"
    gh_api(
        "POST",
        f"/repos/{repo}/issues/{pr_number}/comments",
        {"body": body},
    )
    return "created"


def _post_skip_comment_soft(repo: str, pr_number: int, reason: str) -> None:
    """Call :func:`post_skip_comment`, surfacing API failures as warnings.

    Fail-soft: a transient network error must NOT change the exit code --
    the skip is already recorded in the step summary and stdout log. The
    warning keeps the audit trail intact without masking the original skip.

    No-op when PR-thread comments are off by default (#1386 Phase 1): the
    skip outcome is still recorded in the step summary and stdout, so the
    audit trail is intact without per-PR comment noise.
    """
    if not _pr_comments_enabled():
        return
    try:
        post_skip_comment(repo, pr_number, reason)
    except subprocess.CalledProcessError as exc:
        print(
            f"::warning::post_skip_comment failed "
            f"(exit {exc.returncode}); skip outcome not visible on PR",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Retro sentinel I/O boundary (issue #414)
# ---------------------------------------------------------------------------


def search_open_retro_issues(repo: str) -> list[dict[str, Any]]:
    """Return open retro issues for *repo* (paginated to one page).

    Filter: ``layer:meta`` + ``type:docs`` labels (the two labels every
    auto-opened retro carries per :func:`issue_labels`) AND a retro issue
    title (see :func:`is_retro_issue_title`), filtered client-side because
    the GitHub search API does not honor leading parens in ``in:title``.

    The per-page cap (:data:`_SENTINEL_SEARCH_PAGE_SIZE`) is a soft
    ceiling -- if it overflows the next cron tick processes the
    remainder. Returns the raw search items so the caller can read
    ``number``, ``title``, ``created_at``, and ``body``.
    """
    query = (
        f"repo:{repo} is:issue is:open in:title retro "
        "label:layer:meta label:type:docs"
    )
    encoded = quote(query, safe="")
    raw = gh_api(
        "GET",
        f"/search/issues?q={encoded}&per_page={_SENTINEL_SEARCH_PAGE_SIZE}",
    )
    data = json.loads(raw) if raw.strip() else {}
    items = list(data.get("items") or [])
    out: list[dict[str, Any]] = []
    for item in items:
        title = item.get("title") or ""
        if is_retro_issue_title(title):
            out.append(item)
    return out


def fetch_issue_comments(repo: str, number: int) -> list[dict[str, Any]]:
    """Return issue comments for ``<repo>#<number>``; ``[]`` on parse failure.

    Single page (``per_page=100``) is sufficient for the sentinel: the
    threshold (:func:`is_retro_untouched`) only needs to know whether at
    least one non-bot comment exists, not the full list. Caller wraps
    the gh_api error so a transient failure on one retro does not block
    the rest of the cron tick.
    """
    raw = gh_api(
        "GET", f"/repos/{repo}/issues/{number}/comments?per_page=100"
    )
    if not raw.strip():
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        return []
    return parsed


def has_sentinel_marker(comments: list[dict[str, Any]]) -> bool:
    """Return True when any comment carries :data:`_SENTINEL_CLOSE_MARKER`.

    Idempotency anchor: prevents the sentinel from re-closing a retro
    it has already triaged on a previous cron tick.
    """
    for comment in comments or []:
        body = comment.get("body") or ""
        if _SENTINEL_CLOSE_MARKER in body:
            return True
    return False


def post_sentinel_comment(repo: str, retro_number: int, days: int) -> None:
    """POST the sentinel auto-close comment on *retro_number*.

    Comment shape: marker line + a single explanation line that names
    the inactivity threshold and the reopen instruction. Callers must
    have already checked :func:`has_sentinel_marker` to avoid double
    posting.
    """
    body = (
        f"{_SENTINEL_CLOSE_MARKER}\n"
        f"auto-retro sentinel closed this retro after {days} days of "
        "inactivity (no acceptance-criteria checked, no operator "
        "comments). Reopen if a missed repair surfaces. "
        "Refs issue #414."
    )
    gh_api(
        "POST",
        f"/repos/{repo}/issues/{retro_number}/comments",
        {"body": body},
    )


def close_issue_as_not_planned(repo: str, number: int) -> None:
    """PATCH the issue to ``state=closed`` with ``state_reason=not_planned``.

    ``not_planned`` is the GitHub state_reason that semantically maps
    to "closed without action" -- preserves the audit trail (the issue
    existed) while signalling that no follow-up landed.
    """
    gh_api(
        "PATCH",
        f"/repos/{repo}/issues/{number}",
        {"state": "closed", "state_reason": "not_planned"},
    )


# ---------------------------------------------------------------------------
# Orchestrator + CLI
# ---------------------------------------------------------------------------


def _append_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as fp:
        fp.write(text)


def _build_summary(pr: MergedPR, action: str, detail: str) -> str:
    return (
        "## auto-retro summary\n"
        "\n"
        "| Field | Value |\n"
        "|---|---|\n"
        f"| Source PR | #{pr.number} |\n"
        f"| Source PR title | `{pr.title}` |\n"
        f"| Merged at | {pr.merged_at} |\n"
        f"| Action | `{action}` |\n"
        f"| Detail | {detail} |\n"
    )


def run(event: dict[str, Any], repo: str) -> int:
    """Top-level orchestrator. Returns process exit code."""
    pr = parse_event(event)

    if not pr.merged:
        msg = f"PR #{pr.number} is not merged"
        print(f"skip: {msg}")
        _append_summary(_build_summary(pr, "skip", msg))
        return 0

    skip, reason = should_skip(pr)
    if skip:
        print(f"skip: {reason}")
        _append_summary(_build_summary(pr, "skip", reason))
        return 0

    existing_items = search_retro_issues(repo, pr.number)
    existing = find_existing_retro(existing_items, pr.number)
    if existing is not None:
        msg = f"existing retro issue #{existing} for PR #{pr.number}"
        print(f"skip: {msg}")
        _append_summary(_build_summary(pr, "skip", msg))
        return 0

    # Follow-up fix() PR that references a retro: append a row to the
    # target retro instead of opening a new one. Idempotent on the
    # (retro, source PR) pair.
    if pr.title.lstrip().lower().startswith("fix("):
        body_without_comments = strip_html_comments(pr.body or "")
        candidate_refs = extract_refs(body_without_comments)
        if candidate_refs:
            try:
                titles = fetch_issue_titles(repo, candidate_refs)
            except subprocess.CalledProcessError as exc:
                print(
                    f"::warning::fetch_issue_titles failed "
                    f"(exit {exc.returncode}); proceeding to open new retro",
                    file=sys.stderr,
                )
                titles = {}
            target = find_target_retro_from_refs(pr, titles)
            if target is not None:
                try:
                    changed, detail = append_repair_history_row(
                        repo, target, pr
                    )
                except subprocess.CalledProcessError as exc:
                    print(
                        f"::warning::append_repair_history_row failed "
                        f"(exit {exc.returncode}); NOT falling back to new "
                        "retro to avoid duplicates",
                        file=sys.stderr,
                    )
                    _append_summary(
                        _build_summary(
                            pr,
                            "append-failed",
                            f"PATCH retro #{target} failed; investigate manually",
                        )
                    )
                    return 0
                action = "appended" if changed else "skip"
                print(f"{action}: {detail}")
                _append_summary(_build_summary(pr, action, detail))
                return 0

    try:
        has_inline_comments = has_review_comments(repo, pr.number)
    except subprocess.CalledProcessError as exc:
        # Fail-safe: a transient comments-endpoint failure must NOT
        # silently swallow the retro creation. Surface the warning and
        # proceed as if comments were present.
        print(
            f"::warning::has_review_comments failed "
            f"(exit {exc.returncode}); proceeding to open retro",
            file=sys.stderr,
        )
        has_inline_comments = True

    # Fetch commit subjects ahead of the gate so compute_repair_signals can
    # exempt merge-from-main commits from the multi_commit_pr count. When
    # pr.commits <= 1 the gate is False by definition, so skip the API call.
    commit_subjects: list[str] | None = None
    if pr.commits > 1:
        try:
            commit_subjects = fetch_pr_commits(repo, pr.number)
        except subprocess.CalledProcessError as exc:
            # Fail-soft: a transient commits-endpoint failure must NOT
            # silently swallow the gate evaluation. Fall back to the
            # legacy pr.commits-only path; the body-building fetch below
            # will retry and either succeed or surface the error there.
            print(
                f"::warning::fetch_pr_commits failed ahead of gate "
                f"(exit {exc.returncode}); falling back to "
                "pr.commits-only multi_commit_pr evaluation",
                file=sys.stderr,
            )
            commit_subjects = None

    signals = compute_repair_signals(pr, has_inline_comments, commit_subjects)
    signal_summary = render_repair_signals(signals)
    if not any(signals.values()):
        msg = f"no repair signal fired ({signal_summary})"
        print(f"skip: {msg}")
        _append_summary(_build_summary(pr, "skip", msg))
        _post_skip_comment_soft(repo, pr.number, msg)
        return 0

    # Label-derived prior (refs #582): short the gate when the active
    # signal mix historically produced false positives. Evaluated AFTER
    # signal computation because the prior is irrelevant when no signal
    # fires. Fail-soft: a transient search-API error degrades the
    # prior to empty, which routes through the empty-prior safety
    # net (open normally).
    past_retros = fetch_past_retro_labels(repo)
    prior = compute_prior_from_labels(
        past_retros, epoch_min_number=PRIOR_EPOCH_MIN_RETRO_NUMBER
    )
    prior_skip, prior_reason = should_skip_by_prior(signals, prior)
    if prior_skip:
        print(f"skip: {prior_reason}")
        _append_summary(_build_summary(pr, "skip", prior_reason))
        _post_skip_comment_soft(repo, pr.number, prior_reason)
        return 0
    tentative = is_tentative_by_prior(signals, prior)

    if commit_subjects is None:
        commit_subjects = fetch_pr_commits(repo, pr.number)
    check_runs_unknown = False
    try:
        check_runs = fetch_check_runs(repo, pr.number)
    except subprocess.CalledProcessError as exc:
        # Fail-soft: check-runs is an augmenting signal for the Repair
        # history table. A transient API failure here must NOT block the
        # retro -- the commit-subject signals still carry it. fetch_pr_commits
        # remains fail-loud because its data is required for the body.
        print(
            f"::warning::fetch_check_runs failed (exit {exc.returncode}); "
            "Repair history table will use commit-subject signals only",
            file=sys.stderr,
        )
        check_runs = []
        check_runs_unknown = True
    verification_pairs = extract_verification_pairs(pr.body or "")
    pr_type = (extract_type_scope(pr.title) or "").split("(", 1)[0]
    repair_rows = _repair_history_rows(
        check_runs,
        commit_subjects,
        pr.commits,
        verification_pairs,
        pr_type=pr_type,
    )
    if (
        not check_runs_unknown
        and (
            not repair_rows
            or (
                not has_inline_comments
                and _has_only_exempt_policy_artifact_rows(repair_rows)
            )
        )
    ):
        if repair_rows:
            msg = f"only policy-artifact repair rows generated ({signal_summary})"
        else:
            msg = f"no standalone repair workload ({signal_summary})"
        print(f"skip: {msg}")
        _append_summary(_build_summary(pr, "skip", msg))
        _post_skip_comment_soft(repo, pr.number, msg)
        return 0
    title = build_retro_title(pr)
    body = build_retro_body(
        pr,
        commit_subjects,
        check_runs,
        verification_pairs,
        signals=signals,
    )
    labels = issue_labels(pr.layer_labels, tentative=tentative)

    created = create_issue(repo, title, body, labels)
    new_number = created.get("number")
    new_url = created.get("html_url") or ""

    back_link_status = "skipped"
    terminal_label_status = "skipped"
    if isinstance(new_number, int):
        if not _pr_comments_enabled():
            # Phase 1 of #1386: PR-thread comments are off by default. The
            # retro issue carries the audit trail and the terminal label
            # (applied below) is the quiet PR-side pointer, so the back-link
            # comment is skipped to avoid per-merge notification noise.
            back_link_status = "disabled"
        else:
            try:
                back_link_status = post_back_link_comment(
                    repo, pr.number, new_number
                )
            except subprocess.CalledProcessError as exc:
                # Fail-soft: the retro issue is already created. A failure to
                # post the PR-side back-link must NOT roll the retro back --
                # surface a warning and continue so the audit trail keeps the
                # retro that did land.
                print(
                    f"::warning::post_back_link_comment failed "
                    f"(exit {exc.returncode}); retro issue #{new_number} "
                    "created but source PR has no back-link comment",
                    file=sys.stderr,
                )
                back_link_status = "failed"

        try:
            apply_terminal_label(repo, pr.number)
            terminal_label_status = "applied"
        except subprocess.CalledProcessError as exc:
            # Fail-soft: the terminal label is a secondary signal layered on
            # top of the retro+back-link audit trail. A label-add failure
            # must NOT roll back the retro -- warn and continue so the
            # primary outputs remain intact.
            print(
                f"::warning::apply_terminal_label failed "
                f"(exit {exc.returncode}); retro issue #{new_number} created "
                f"but source PR was not labeled {_TERMINAL_LABEL!r}",
                file=sys.stderr,
            )
            terminal_label_status = "failed"

    msg = (
        f"created retro issue #{new_number} ({new_url}); "
        f"back-link={back_link_status}; "
        f"terminal-label={terminal_label_status}"
    )
    print(msg)
    _append_summary(_build_summary(pr, "created", msg))
    return 0


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with ``Z`` suffix.

    Wrapped so :func:`sentinel_run` can be tested with a monkeypatched
    clock without monkeypatching :mod:`datetime` directly.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_sentinel_summary(
    closed: list[int], skipped: list[tuple[int, str]], days: int
) -> str:
    """Render the GITHUB_STEP_SUMMARY block for one sentinel run.

    ``closed`` is the list of retro issue numbers that the sentinel
    closed on this tick; ``skipped`` is a list of ``(number, reason)``
    tuples for retros that did not qualify (still inside the inactivity
    window, operator-touched, or already sentinel-closed).
    """
    closed_block = (
        "\n".join(f"- #{n}" for n in closed) if closed else "- (none)"
    )
    skipped_block = (
        "\n".join(f"- #{n}: {reason}" for n, reason in skipped)
        if skipped
        else "- (none)"
    )
    return (
        "## auto-retro sentinel summary\n"
        "\n"
        f"Inactivity threshold: {days} days.\n"
        "\n"
        "### Closed\n"
        "\n"
        f"{closed_block}\n"
        "\n"
        "### Skipped\n"
        "\n"
        f"{skipped_block}\n"
    )


def sentinel_run(repo: str, now_iso: str, days: int) -> int:
    """Scan open retros and auto-close untouched ones older than *days*.

    Per-retro flow (each retro fails soft so one error does not block
    the rest of the cron tick):

    1. Skip when ``created_at`` is younger than the threshold.
    2. Skip when a prior sentinel comment marker is present (idempotent).
    3. Skip when the retro shows operator engagement
       (:func:`is_retro_untouched` returns False).
    4. Otherwise POST the sentinel comment, then PATCH the issue to
       ``closed`` / ``not_planned``.

    Returns 0 always; the step summary records the close / skip
    breakdown so an operator can audit the run.
    """
    try:
        items = search_open_retro_issues(repo)
    except subprocess.CalledProcessError as exc:
        print(
            f"::error::sentinel search failed (exit {exc.returncode}); "
            "no retros processed this tick",
            file=sys.stderr,
        )
        return 0

    closed: list[int] = []
    skipped: list[tuple[int, str]] = []

    for item in items:
        raw_number = item.get("number")
        if not isinstance(raw_number, int):
            continue
        number = raw_number
        created_at = str(item.get("created_at") or "")
        if not is_retro_age_exceeded(created_at, now_iso, days):
            skipped.append((number, "inside inactivity window"))
            continue
        try:
            comments = fetch_issue_comments(repo, number)
        except subprocess.CalledProcessError as exc:
            print(
                f"::warning::fetch_issue_comments failed for retro "
                f"#{number} (exit {exc.returncode}); skipping this "
                "retro on this tick",
                file=sys.stderr,
            )
            skipped.append((number, "comments fetch failed"))
            continue
        if has_sentinel_marker(comments):
            skipped.append((number, "already sentinel-closed marker present"))
            continue
        body = item.get("body") or ""
        if not is_retro_untouched(body, comments):
            skipped.append((number, "operator engagement detected"))
            continue
        try:
            post_sentinel_comment(repo, number, days)
        except subprocess.CalledProcessError as exc:
            print(
                f"::warning::post_sentinel_comment failed for retro "
                f"#{number} (exit {exc.returncode}); NOT closing to "
                "avoid silent close without operator-visible reason",
                file=sys.stderr,
            )
            skipped.append((number, "comment post failed"))
            continue
        try:
            close_issue_as_not_planned(repo, number)
        except subprocess.CalledProcessError as exc:
            print(
                f"::warning::close_issue_as_not_planned failed for retro "
                f"#{number} (exit {exc.returncode}); sentinel comment "
                "posted but issue remains open",
                file=sys.stderr,
            )
            skipped.append((number, "close patch failed after comment"))
            continue
        closed.append(number)
        print(f"closed retro #{number} as not_planned (sentinel)")

    _append_summary(_build_sentinel_summary(closed, skipped, days))
    return 0


# ---------------------------------------------------------------------------
# Post-merge re-scan (issue #421)
# ---------------------------------------------------------------------------

# Default lookback window (in hours) for the post-merge re-scan. PRs merged
# more recently than this may still have pending observation gates (the 24h
# no-follow-up window). 48h ensures the 24h gate has closed while keeping the
# scan window bounded. Overridable via AUTO_RETRO_RESCAN_HOURS.
_DEFAULT_RESCAN_HOURS: int = 48

# Minimum age (in hours) before a merged PR is eligible for re-scan. This
# ensures the "No follow-up fix(...) PR needed within 24h of merge" gate has
# had time to be observed. PRs merged less than this many hours ago are
# skipped.
_RESCAN_MIN_AGE_HOURS: int = 24

# Marker for the deferred Post-merge rescan comment posted to the retro issue
# so subsequent cron runs do not re-scan the same PR.
_RESCAN_MARKER = "<!-- auto-retro:post-merge-rescan -->"

# Per-page cap for the rescan's merged-PR search. Each cron tick processes
# at most this many recently merged PRs.
_RESCAN_SEARCH_PAGE_SIZE: int = 50


@dataclass(frozen=True)
class PostMergeGateResult:
    gate: str
    satisfied: bool
    detail: str


def _hours_between(iso_a: str, iso_b: str) -> float:
    """Return the number of hours between two ISO 8601 timestamps."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    a = datetime.strptime(iso_a[:20], fmt).replace(tzinfo=UTC)
    b = datetime.strptime(iso_b[:20], fmt).replace(tzinfo=UTC)
    return abs((b - a).total_seconds()) / 3600.0


def search_recently_merged_prs(
    repo: str, hours: int, now_iso: str
) -> list[dict[str, Any]]:
    """Return PRs merged in the last *hours* hours.

    Uses the GitHub search API with ``type:pr is:merged`` and a date
    filter. Returns the raw search items so the caller can read
    ``number``, ``title``, ``pull_request``, etc.
    """
    cutoff = datetime.strptime(
        now_iso[:20], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=UTC)
    since_ts = cutoff.timestamp() - (hours * 3600)
    since_dt = datetime.fromtimestamp(since_ts, tz=UTC)
    since_str = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    query = (
        f"repo:{repo} type:pr is:merged "
        f"merged:>={since_str}"
    )
    encoded = quote(query, safe="")
    raw = gh_api(
        "GET",
        f"/search/issues?q={encoded}&per_page={_RESCAN_SEARCH_PAGE_SIZE}",
    )
    data = json.loads(raw) if raw.strip() else {}
    return list(data.get("items") or [])


def fetch_issue_state(repo: str, number: int) -> str:
    """Return the state of issue ``<repo>#<number>`` (``open`` or ``closed``).

    Returns ``"unknown"`` on fetch failure.
    """
    try:
        raw = gh_api("GET", f"/repos/{repo}/issues/{number}")
    except subprocess.CalledProcessError:
        return "unknown"
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return "unknown"
    return str(data.get("state") or "unknown")


def search_fix_prs_since(
    repo: str, merged_at: str, now_iso: str
) -> list[dict[str, Any]]:
    """Return ``fix(...)`` PRs merged between *merged_at* and *now_iso*.

    Used to verify the "No follow-up fix(...) PR needed within 24h"
    gate. Filters client-side to titles starting with ``fix(``.
    """
    query = (
        f"repo:{repo} type:pr is:merged "
        f"merged:{merged_at}..{now_iso}"
    )
    encoded = quote(query, safe="")
    try:
        raw = gh_api(
            "GET",
            f"/search/issues?q={encoded}&per_page=50",
        )
    except subprocess.CalledProcessError:
        return []
    data = json.loads(raw) if raw.strip() else {}
    items = list(data.get("items") or [])
    return [
        item for item in items
        if (item.get("title") or "").lstrip().lower().startswith("fix(")
    ]


def fetch_pr_detail(repo: str, pr_number: int) -> dict[str, Any]:
    """Fetch full PR detail from the pulls endpoint (includes ``merged_at``).

    Returns ``{}`` on failure.
    """
    try:
        raw = gh_api("GET", f"/repos/{repo}/pulls/{pr_number}")
    except subprocess.CalledProcessError:
        return {}
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def verify_post_merge_gates(
    repo: str,
    pr_number: int,
    pr_body: str,
    merged_at: str,
    now_iso: str,
) -> list[PostMergeGateResult]:
    """Verify each Post-merge checklist gate for a merged PR.

    Returns a :class:`PostMergeGateResult` for every unchecked item.
    Checked items are omitted (they are already satisfied by operator
    observation).
    """
    items = extract_post_merge_checklist(pr_body)
    if not items:
        return []

    results: list[PostMergeGateResult] = []
    for text, checked in items:
        if checked:
            continue
        lower = text.lower()
        if "linked issue closed" in lower:
            body_no_comments = strip_html_comments(pr_body or "")
            refs = extract_refs(body_no_comments)
            if not refs:
                results.append(PostMergeGateResult(
                    gate="linked_issue_closed",
                    satisfied=True,
                    detail="no linked issues found in PR body (gate not applicable)",
                ))
                continue
            all_closed = True
            for ref in refs:
                state = fetch_issue_state(repo, ref)
                if state != "closed":
                    all_closed = False
                    break
            results.append(PostMergeGateResult(
                gate="linked_issue_closed",
                satisfied=all_closed,
                detail=(
                    f"linked issues {refs} all closed"
                    if all_closed
                    else f"issue #{ref} state={state}"
                ),
            ))
        elif "auto-retro issue opened" in lower:
            existing_items = search_retro_issues(repo, pr_number)
            existing = find_existing_retro(existing_items, pr_number)
            results.append(PostMergeGateResult(
                gate="retro_issue_opened",
                satisfied=existing is not None,
                detail=(
                    f"retro issue #{existing} exists"
                    if existing is not None
                    else f"no retro issue found for PR #{pr_number}"
                ),
            ))
        elif "follow-up" in lower and "fix" in lower:
            fix_prs = search_fix_prs_since(repo, merged_at, now_iso)
            has_followup = len(fix_prs) > 0
            results.append(PostMergeGateResult(
                gate="no_followup_fix",
                satisfied=not has_followup,
                detail=(
                    "no follow-up fix(...) PR found"
                    if not has_followup
                    else "follow-up fix PR(s) found: "
                    + ", ".join(
                        "#" + str(p.get("number", "?"))
                        for p in fix_prs
                    )
                ),
            ))
        else:
            results.append(PostMergeGateResult(
                gate="unknown",
                satisfied=True,
                detail=f"unrecognized gate text: {text!r}",
            ))

    return results


def _build_rescan_summary(
    appended: list[tuple[int, int]],
    skipped: list[tuple[int, str]],
    hours: int,
) -> str:
    """Render the GITHUB_STEP_SUMMARY block for one rescan run.

    ``appended`` is a list of ``(pr_number, retro_number)`` tuples for
    PRs whose unsatisfied gates were appended to their retro.
    ``skipped`` is a list of ``(pr_number, reason)`` tuples.
    """
    appended_block = (
        "\n".join(
            f"- PR #{pr}: appended to retro #{retro}"
            for pr, retro in appended
        )
        if appended
        else "- (none)"
    )
    skipped_block = (
        "\n".join(f"- PR #{pr}: {reason}" for pr, reason in skipped)
        if skipped
        else "- (none)"
    )
    return (
        "## auto-retro post-merge rescan summary\n"
        "\n"
        f"Lookback window: {hours} hours.\n"
        "\n"
        "### Appended\n"
        "\n"
        f"{appended_block}\n"
        "\n"
        "### Skipped\n"
        "\n"
        f"{skipped_block}\n"
    )


def post_merge_rescan_run(repo: str, now_iso: str, hours: int) -> int:
    """Re-scan Post-merge checklist gates on recently merged PRs.

    For each PR merged in the last *hours* hours (but at least
    :data:`_RESCAN_MIN_AGE_HOURS` old), parse the Post-merge
    checklist, verify each unchecked gate, and append a row to the
    existing retro issue for gates that did not fire.

    Returns 0 always; the step summary records the outcome so an
    operator can audit the run. Refs #421.
    """
    try:
        items = search_recently_merged_prs(repo, hours, now_iso)
    except subprocess.CalledProcessError as exc:
        print(
            f"::error::post-merge rescan search failed "
            f"(exit {exc.returncode}); no PRs processed this tick",
            file=sys.stderr,
        )
        _append_summary(_build_rescan_summary([], [], hours))
        return 0

    appended: list[tuple[int, int]] = []
    skipped: list[tuple[int, str]] = []

    for item in items:
        raw_number = item.get("number")
        if not isinstance(raw_number, int):
            continue
        pr_number = raw_number
        title = str(item.get("title") or "")

        if is_retro_pr(title):
            skipped.append((pr_number, "retro PR (skip)"))
            continue

        skip, reason = should_skip(
            MergedPR(
                number=pr_number,
                title=title,
                merged=True,
                merged_at="",
                merged_by_login=(
                    (item.get("user") or {}).get("login")
                ),
                user_login=(
                    (item.get("user") or {}).get("login")
                ),
                layer_labels=(),
                html_url="",
            )
        )
        if skip:
            skipped.append((pr_number, reason))
            continue

        pr_detail = fetch_pr_detail(repo, pr_number)
        if not pr_detail:
            skipped.append((pr_number, "could not fetch PR detail"))
            continue

        merged_at = str(pr_detail.get("merged_at") or "")
        if not merged_at:
            skipped.append((pr_number, "no merged_at in PR detail"))
            continue

        age_hours = _hours_between(merged_at, now_iso)
        if age_hours < _RESCAN_MIN_AGE_HOURS:
            skipped.append(
                (pr_number, f"too recent ({age_hours:.1f}h < {_RESCAN_MIN_AGE_HOURS}h)")
            )
            continue

        pr_body = str(pr_detail.get("body") or "")
        post_merge_items = extract_post_merge_checklist(pr_body)
        if not post_merge_items:
            skipped.append((pr_number, "no Post-merge checklist found"))
            continue

        all_checked = all(checked for _, checked in post_merge_items)
        if all_checked:
            skipped.append((pr_number, "all Post-merge items already checked"))
            continue

        existing_items = search_retro_issues(repo, pr_number)
        retro_number = find_existing_retro(existing_items, pr_number)
        if retro_number is None:
            skipped.append((pr_number, "no retro issue to append to"))
            continue

        retro_body = fetch_issue_body(repo, retro_number)
        if not retro_body:
            skipped.append(
                (pr_number, f"could not fetch retro #{retro_number} body")
            )
            continue

        if _RESCAN_MARKER in retro_body:
            skipped.append(
                (pr_number, f"retro #{retro_number} already rescan-marked")
            )
            continue

        gate_results = verify_post_merge_gates(
            repo, pr_number, pr_body, merged_at, now_iso,
        )
        unsatisfied = [g for g in gate_results if not g.satisfied]
        if not unsatisfied:
            skipped.append(
                (pr_number, "all Post-merge gates satisfied (no action)")
            )
            continue

        open_idx = retro_body.find(_AUTO_FILLED_OPEN)
        close_idx = retro_body.find(_AUTO_FILLED_CLOSE)
        if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
            skipped.append(
                (pr_number, f"retro #{retro_number} missing auto-filled markers")
            )
            continue

        block = retro_body[open_idx:close_idx]
        next_idx = _next_table_index(block)
        new_rows = ""
        for i, gate in enumerate(unsatisfied):
            row_idx = next_idx + i
            repair = _escape_table_cell(
                f"Post-merge gate: {gate.gate}"
            )
            detail = _escape_table_cell(gate.detail)
            new_rows += f"| {row_idx} | {repair} | {detail} |\n"

        new_body = (
            retro_body[:close_idx]
            + new_rows
            + retro_body[close_idx:]
        )

        rescan_comment = (
            f"\n\n{_RESCAN_MARKER}\n"
            f"_Deferred Post-merge re-scan appended "
            f"{len(unsatisfied)} row(s) for PR #{pr_number}. "
            f"Refs #421._\n"
        )
        new_body += rescan_comment

        try:
            patch_issue_body(repo, retro_number, new_body)
        except subprocess.CalledProcessError as exc:
            print(
                f"::warning::patch_issue_body failed for retro "
                f"#{retro_number} (exit {exc.returncode}); "
                "skipping this PR on this tick",
                file=sys.stderr,
            )
            skipped.append(
                (pr_number, f"PATCH retro #{retro_number} failed")
            )
            continue

        appended.append((pr_number, retro_number))
        print(
            f"appended {len(unsatisfied)} Post-merge gate row(s) "
            f"for PR #{pr_number} to retro #{retro_number}"
        )

    _append_summary(_build_rescan_summary(appended, skipped, hours))
    return 0


def _cmd_post_merge_rescan(args: argparse.Namespace) -> int:
    repo = (
        args.repo
        or os.environ.get("REPO")
        or os.environ.get("GITHUB_REPOSITORY")
    )
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY",
            file=sys.stderr,
        )
        return 1
    hours_raw = (
        args.hours
        if args.hours is not None
        else os.environ.get("AUTO_RETRO_RESCAN_HOURS")
    )
    if hours_raw is None:
        hours = _DEFAULT_RESCAN_HOURS
    else:
        try:
            hours = int(hours_raw)
        except (TypeError, ValueError):
            print(
                f"::error::invalid rescan hours value {hours_raw!r}; "
                f"must be a positive integer",
                file=sys.stderr,
            )
            return 1
        if hours <= 0:
            print(
                f"::error::rescan hours must be positive (got {hours})",
                file=sys.stderr,
            )
            return 1
    return post_merge_rescan_run(repo, _now_utc_iso(), hours)


def _cmd_sentinel(args: argparse.Namespace) -> int:
    repo = (
        args.repo or os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY")
    )
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY",
            file=sys.stderr,
        )
        return 1
    days_raw = (
        args.days
        if args.days is not None
        else os.environ.get("AUTO_RETRO_SENTINEL_DAYS")
    )
    if days_raw is None:
        days = _DEFAULT_SENTINEL_DAYS
    else:
        try:
            days = int(days_raw)
        except (TypeError, ValueError):
            print(
                f"::error::invalid sentinel days value {days_raw!r}; "
                f"must be a positive integer",
                file=sys.stderr,
            )
            return 1
        if days <= 0:
            print(
                f"::error::sentinel days must be positive (got {days})",
                file=sys.stderr,
            )
            return 1
    return sentinel_run(repo, _now_utc_iso(), days)


def _cmd_run(args: argparse.Namespace) -> int:
    event_path = args.event_file or os.environ.get("GITHUB_EVENT_PATH")
    repo = (
        args.repo or os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY")
    )

    if not event_path:
        print(
            "::error::missing --event-file / $GITHUB_EVENT_PATH", file=sys.stderr
        )
        return 1
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY", file=sys.stderr
        )
        return 1

    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"::error::cannot read event file {event_path}: {exc}",
            file=sys.stderr,
        )
        return 1

    return run(event, repo)


def _cmd_decision_tree(_args: argparse.Namespace) -> int:
    sys.stdout.write(render_decision_tree_mermaid())
    return 0


def _cmd_triage_report(args: argparse.Namespace) -> int:
    repo = (
        args.repo or os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY")
    )
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY",
            file=sys.stderr,
        )
        return 1
    past = fetch_past_retro_labels(repo, limit=args.limit)
    report = compute_triage_report(past)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_triage_report_markdown(report), encoding="utf-8")
    return 0


def _cmd_triage_report_pr(args: argparse.Namespace) -> int:
    """Publish the regenerated triage-report snapshot as a reuse-safe refresh PR.

    Reads the snapshot the preceding ``triage-report`` step wrote and upserts it
    onto the fixed refresh branch via :func:`pr_upsert.upsert_single_file_pr`,
    which creates a signed commit (createCommitOnBranch) instead of force-pushing
    -- the #1466 fix. The upsert is called with ``recreate=True``: on each drift
    the fixed branch is deleted and re-created off *base* with a single signed
    commit, so it never accumulates ancestry. Reusing-and-appending instead left a
    legacy unsigned ancestor on the branch that permanently violated the main
    ``required_signatures`` rule and ``non_fast_forward`` blocked rewriting it
    (#1560). A delete+create is not a force-push, so ``non_fast_forward`` is still
    honored. When the snapshot already matches *base*, there is no drift and the
    command is a no-op. Refs #1042, #1386, #1466, #1560.
    """
    repo = (
        args.repo or os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY")
    )
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY",
            file=sys.stderr,
        )
        return 1
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print(
            "::error::GH_TOKEN environment variable is required",
            file=sys.stderr,
        )
        return 1
    base = args.base or os.environ.get("GITHUB_REF_NAME") or "main"
    report_path = Path(args.report_file)
    try:
        content = report_path.read_bytes()
    except OSError as exc:
        print(
            f"::error::cannot read triage report {args.report_file}: {exc}",
            file=sys.stderr,
        )
        return 1
    try:
        result = upsert_single_file_pr(
            repo=repo,
            path=str(_TRIAGE_REPORT_DOC_PATH),
            content=content,
            base=base,
            branch=_TRIAGE_REPORT_PR_BRANCH,
            title=_TRIAGE_REPORT_PR_TITLE,
            body=_TRIAGE_REPORT_PR_BODY,
            commit_subject=_TRIAGE_REPORT_PR_TITLE,
            commit_body=_TRIAGE_REPORT_COMMIT_TRAILER,
            token=token,
            recreate=True,
        )
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"triage-report refresh: {result}")
    return 0


def _cmd_verify_retro_completeness(args: argparse.Namespace) -> int:
    """Gate a ``fix(auto-retro):`` PR on Repair history Cause/Next action.

    Skips (exit 0) for any PR that is not a retro-close PR, or whose body
    links no retro issue, or whose linked retro cannot be fetched -- the
    gate must never block an unrelated PR or a transient API failure. When
    the linked retro is readable, it fails (exit 1) only if a non-artifact
    repair row still carries an empty / sentinel Cause or Next action cell.
    """
    repo = (
        args.repo
        or os.environ.get("REPO")
        or os.environ.get("GITHUB_REPOSITORY")
    )
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY",
            file=sys.stderr,
        )
        return 1
    pr_title = args.pr_title or os.environ.get("TITLE") or ""
    if not is_retro_pr(pr_title):
        print("skip: not a retro-close PR")
        return 0
    if args.pr_body_file:
        try:
            pr_body = Path(args.pr_body_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"::error::cannot read --pr-body-file "
                f"{args.pr_body_file}: {exc}",
                file=sys.stderr,
            )
            return 1
    else:
        pr_body = os.environ.get("PR_BODY") or ""

    refs = extract_refs(strip_html_comments(pr_body))
    titles = fetch_issue_titles(repo, refs)
    target: int | None = None
    for number in refs:
        title = titles.get(number)
        if title is not None and is_retro_issue_title(title):
            target = number
            break
    if target is None:
        print("skip: no linked retro issue")
        return 0

    body = fetch_issue_body(repo, target)
    if not body:
        # fail-safe: a retro we cannot read must not block the PR.
        print(f"skip: retro issue #{target} body unavailable")
        return 0

    errors = verify_retro_repair_completeness(body)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(
        f"OK: retro issue #{target} repair history has Cause and "
        f"Next action filled for every non-artifact row."
    )
    return 0


def find_linked_retro_refs(
    pr_body: str, titles: Mapping[int, str]
) -> list[int]:
    """Return the linked issue numbers in *pr_body* that are retro issues.

    *titles* maps issue number to title (typically from
    :func:`fetch_issue_titles`). A ref counts as a retro issue when its
    fetched title satisfies :func:`is_retro_issue_title`. Refs whose title
    could not be fetched are skipped -- the caller must not block on a
    transient lookup failure (Refs #1069).
    """
    out: list[int] = []
    for number in extract_refs(strip_html_comments(pr_body)):
        title = titles.get(number)
        if title is not None and is_retro_issue_title(title):
            out.append(number)
    return out


def _cmd_verify_no_direct_retro_pr(args: argparse.Namespace) -> int:
    """Block a normal PR from closing an un-triaged retro issue.

    A retro issue is a triage signal, not a unit of work to implement
    directly. A PR that links (``Closes``/``Refs``) a retro issue must
    itself be a retro-close PR -- a title whose ``type(scope)`` token
    carries the ``auto-retro`` scope (:func:`is_retro_pr`). Any other PR
    that links a retro issue is rejected (exit 1) so direct PRs off
    un-triaged retros are blocked at CI (Refs #1069).

    Fail-open boundary (matches :func:`_cmd_verify_retro_completeness`):
    the gate skips (exit 0) when the PR is itself a retro-close PR, when no
    linked issue resolves to a retro title, or when the linked-title lookup
    cannot run -- it must never block an unrelated PR or a transient API
    failure.
    """
    repo = (
        args.repo
        or os.environ.get("REPO")
        or os.environ.get("GITHUB_REPOSITORY")
    )
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY",
            file=sys.stderr,
        )
        return 1
    pr_title = args.pr_title or os.environ.get("TITLE") or ""
    if is_retro_pr(pr_title):
        print("skip: PR is a retro-close PR")
        return 0
    if args.pr_body_file:
        try:
            pr_body = Path(args.pr_body_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"::error::cannot read --pr-body-file "
                f"{args.pr_body_file}: {exc}",
                file=sys.stderr,
            )
            return 1
    else:
        pr_body = os.environ.get("PR_BODY") or ""

    refs = extract_refs(strip_html_comments(pr_body))
    if not refs:
        print("skip: PR body links no issue")
        return 0
    titles = fetch_issue_titles(repo, refs)
    linked = find_linked_retro_refs(pr_body, titles)
    if not linked:
        print("skip: no linked retro issue")
        return 0

    joined = ", ".join(f"#{n}" for n in linked)
    print(
        f"::error::PR links retro issue {joined} but is not a retro-close "
        f"PR. Retro issues require triage and are not a unit of work to "
        f"implement directly: decide TP/FP, open a follow-up issue for any "
        f"confirmed repair loop, and let the retro be closed by a "
        f"retro-close PR (a 'type(auto-retro): ...' title). Refs #1069."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser(
        "run", help="Open a retrospective issue for a merged pull request."
    )
    p_run.add_argument(
        "--event-file", help="Override $GITHUB_EVENT_PATH (for tests)."
    )
    p_run.add_argument("--repo", help="Override $REPO (owner/name).")
    p_run.set_defaults(func=_cmd_run)

    p_sentinel = sub.add_parser(
        "sentinel",
        help=(
            "Auto-close open retro issues that have been untouched for "
            "more than --days days. Refs #414."
        ),
    )
    p_sentinel.add_argument("--repo", help="Override $REPO (owner/name).")
    p_sentinel.add_argument(
        "--days",
        type=int,
        default=None,
        help=(
            f"Inactivity threshold in days "
            f"(default {_DEFAULT_SENTINEL_DAYS}, env "
            "AUTO_RETRO_SENTINEL_DAYS)."
        ),
    )
    p_sentinel.set_defaults(func=_cmd_sentinel)

    p_rescan = sub.add_parser(
        "post-merge-rescan",
        help=(
            "Re-scan Post-merge checklist gates on recently merged PRs "
            "and append rows to existing retro issues for unsatisfied "
            "gates. Refs #421."
        ),
    )
    p_rescan.add_argument("--repo", help="Override $REPO (owner/name).")
    p_rescan.add_argument(
        "--hours",
        type=int,
        default=None,
        help=(
            f"Lookback window in hours "
            f"(default {_DEFAULT_RESCAN_HOURS}, env "
            "AUTO_RETRO_RESCAN_HOURS)."
        ),
    )
    p_rescan.set_defaults(func=_cmd_post_merge_rescan)

    p_decision_tree = sub.add_parser(
        "decision-tree",
        help="Render the auto-retro run decision tree as Mermaid (stdout preview).",
    )
    p_decision_tree.set_defaults(func=_cmd_decision_tree)

    p_triage = sub.add_parser(
        "triage-report",
        help=(
            "Aggregate past retro issues into a Markdown + Mermaid triage "
            "report (triage-status mix and per-signal FP rates). Refs #1042."
        ),
    )
    p_triage.add_argument("--repo", help="Override $REPO (owner/name).")
    p_triage.add_argument(
        "--limit",
        type=int,
        default=PRIOR_FETCH_LIMIT,
        help=(
            f"Maximum number of past retros to aggregate "
            f"(default {PRIOR_FETCH_LIMIT})."
        ),
    )
    p_triage.add_argument(
        "--output",
        default=str(_TRIAGE_REPORT_DOC_PATH),
        help=f"Markdown output path (default {_TRIAGE_REPORT_DOC_PATH}).",
    )
    p_triage.set_defaults(func=_cmd_triage_report)

    p_triage_pr = sub.add_parser(
        "triage-report-pr",
        help=(
            "Publish the regenerated triage-report snapshot as a refresh PR "
            "via a signed createCommitOnBranch append (no force-push). Reads "
            "the file the triage-report step wrote. Refs #1042, #1466."
        ),
    )
    p_triage_pr.add_argument("--repo", help="Override $REPO (owner/name).")
    p_triage_pr.add_argument(
        "--base",
        help="Base branch to open the PR against (default $GITHUB_REF_NAME or main).",
    )
    p_triage_pr.add_argument(
        "--report-file",
        default=str(_TRIAGE_REPORT_DOC_PATH),
        help=f"Path to the regenerated snapshot (default {_TRIAGE_REPORT_DOC_PATH}).",
    )
    p_triage_pr.set_defaults(func=_cmd_triage_report_pr)

    p_verify = sub.add_parser(
        "verify-retro-completeness",
        help=(
            "Gate a fix(auto-retro): PR on its linked retro issue having "
            "Cause + Next action filled for every non-artifact repair row. "
            "Skips (exit 0) for non-retro-close PRs. Refs #1058."
        ),
    )
    p_verify.add_argument("--repo", help="Override $REPO (owner/name).")
    p_verify.add_argument(
        "--pr-title", help="Override $TITLE (the PR title)."
    )
    p_verify.add_argument(
        "--pr-body-file",
        help="Path to a file holding the PR body (else env $PR_BODY).",
    )
    p_verify.set_defaults(func=_cmd_verify_retro_completeness)

    p_no_direct = sub.add_parser(
        "verify-no-direct-retro-pr",
        help=(
            "Block a normal PR from closing a retro issue: a PR that links "
            "a retro issue must itself be a retro-close PR. Skips (exit 0) "
            "for retro-close PRs and PRs with no linked retro. Refs #1069."
        ),
    )
    p_no_direct.add_argument("--repo", help="Override $REPO (owner/name).")
    p_no_direct.add_argument(
        "--pr-title", help="Override $TITLE (the PR title)."
    )
    p_no_direct.add_argument(
        "--pr-body-file",
        help="Path to a file holding the PR body (else env $PR_BODY).",
    )
    p_no_direct.set_defaults(func=_cmd_verify_no_direct_retro_pr)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"::error::gh api failed (exit {exc.returncode}): {exc.stderr}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
