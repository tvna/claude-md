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

* the merged PR is itself a retrospective. Detected when the title
  starts with ``retro(`` or ``retro:``, OR when the title's
  ``type(scope)`` token contains the literal ``(retro)`` scope (e.g.
  ``docs(retro):``, ``feat(retro):``). The second branch covers
  retro-closing PRs that the title policy forces to use a non-``retro``
  Conventional Commit type. Avoids recursion.
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
import ast
import inspect
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from _retro_labels import (
    PRIOR_FETCH_LIMIT,
    PRIOR_MIN_SAMPLE_SIZE,
    PRIOR_SKIP_THRESHOLD,
    PRIOR_TENTATIVE_THRESHOLD,
    RETRO_FP,
    RETRO_TENTATIVE,
)
from _trusted_bots import _TRUSTED_BOT_LOGINS
from issue_link import extract_refs, strip_html_comments

FALLBACK_TYPE_SCOPE = "retro"
_DECISION_TREE_DOC_PATH = Path("docs/generated/auto-retro-decision-tree.md")

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
# parenthetic scope. Non-matching titles fall back to FALLBACK_TYPE_SCOPE
# and the retro body records the fallback in its Facts section.
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

# Explicit failure-count marker that must NOT be treated as passing even
# if the rest of the string smells like a pass (`0 passed, 3 failed`).
# Refs #453.
_RESULT_FAILING_COUNT_RE = re.compile(r"\b\d+\s+failed\b", re.IGNORECASE)

# Append-to-existing-retro markers used by append_repair_history_row.
_AUTO_FILLED_OPEN = "<!-- auto-filled:repair-history -->"
_AUTO_FILLED_CLOSE = "<!-- /auto-filled:repair-history -->"
_APPENDED_OPEN = "<!-- appended-follow-up-fixes -->"
_APPENDED_CLOSE = "<!-- /appended-follow-up-fixes -->"


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

    Returns ``""`` when the title does not match; callers should fall
    back to :data:`FALLBACK_TYPE_SCOPE`.
    """
    match = _TYPE_SCOPE_RE.match(pr_title)
    if match is None:
        return ""
    return match.group(1)


def is_retro_pr(pr_title: str) -> bool:
    """True if the PR is itself a retrospective (skip to avoid recursion).

    Matches in two ways: (a) title starts with ``retro(`` or ``retro:``
    (case-insensitive, leading whitespace stripped); (b) the title's
    ``type(scope)`` token literally contains ``(retro)``. The second
    branch covers retro-closing PRs like ``docs(retro): ...`` that the
    title policy forces to use a non-``retro`` Conventional Commit type.
    """
    stripped = pr_title.lstrip().lower()
    if stripped.startswith("retro(") or stripped.startswith("retro:"):
        return True
    token = extract_type_scope(stripped) or ""
    return "(retro)" in token


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

    Anything else (including ``exit 1``, ``failed``, free-form prose) is
    treated as a failure signal. Refs #411, #417, #453.
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

    Signals returned:

    - ``inline_review_comments``: at least one comment on the PR's
      review thread (the legacy gate).
    - ``body_cites_refs``: PR body has at least one line-anchored
      ``Refs|Closes|Fixes|Resolves #N``. Reuses
      :func:`issue_link.extract_refs`.
    - ``fix_typed_title``: PR title starts with ``fix(`` (Conventional
      Commit `fix` type).
    - ``multi_commit_pr``: source branch had more than one commit before
      the merge. When *commit_subjects* is supplied, merge-from-main
      commits (see :data:`_MERGE_FROM_MAIN_PREFIXES`) are subtracted
      from the count so rebase debt created by the squash-only,
      linear-history merge policy does not fire the gate on its own.
      When *commit_subjects* is ``None`` (the legacy two-arg call shape,
      retained for tests that do not exercise the gate ordering in
      :func:`run`) the gate falls back to ``pr.commits > 1``.
    """
    body_without_comments = strip_html_comments(pr.body or "")
    refs = extract_refs(body_without_comments)
    fix_typed = pr.title.lstrip().lower().startswith("fix(")
    if commit_subjects is None:
        multi_commit = pr.commits > 1
    else:
        pure_commits = pr.commits - _count_merge_from_main(commit_subjects)
        multi_commit = pure_commits > 1
    verification_pairs = extract_verification_pairs(pr.body or "")
    # `post_merge_unchecked` was removed in #418: the Post-merge subsection
    # is documented to be checked by the operator AFTER observing the merge,
    # so it is structurally unchecked at merge time. Re-scanning the subsection
    # is deferred to the workflow tracked in #421.
    return {
        "inline_review_comments": bool(has_inline_comments),
        "body_cites_refs": len(refs) > 0,
        "fix_typed_title": fix_typed,
        "multi_commit_pr": multi_commit,
        "verification_pairs_failed": any(
            not p.passed for p in verification_pairs
        ),
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
    "body_cites_refs",
    "fix_typed_title",
    "multi_commit_pr",
    "verification_pairs_failed",
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
    """

    number: int
    signals: frozenset[str]
    labels: frozenset[str]


@dataclass(frozen=True)
class DecisionTreeEdge:
    """One renderable edge in the auto-retro decision tree."""

    source: str
    target: str
    label: str


@dataclass(frozen=True)
class DecisionTreeNode:
    """One renderable node in the auto-retro decision tree."""

    node_id: str
    label: str


def compute_prior_from_labels(
    past_retros: list[PastRetro],
    signal_names: tuple[str, ...] = _SIGNAL_NAMES,
) -> dict[str, tuple[float, int]]:
    """For each signal name, return ``(fp_rate, sample_size)``.

    ``fp_rate`` is

        |{r in past_retros : signal in r.signals and RETRO_FP in r.labels}|
        / max(1, |{r in past_retros : signal in r.signals}|)

    and ``sample_size`` is the denominator (un-floored). Empty input
    yields ``(0.0, 0)`` for every signal -- the consumer
    (:func:`should_skip_by_prior`) gates on ``sample_size >=
    PRIOR_MIN_SAMPLE_SIZE`` so the empty-prior case degrades to
    "open normally" rather than to a silent skip. Refs #582.
    """
    prior: dict[str, tuple[float, int]] = {}
    for name in signal_names:
        denom = sum(1 for r in past_retros if name in r.signals)
        if denom == 0:
            prior[name] = (0.0, 0)
            continue
        numer = sum(
            1 for r in past_retros if name in r.signals and RETRO_FP in r.labels
        )
        prior[name] = (numer / denom, denom)
    return prior


def _mermaid_text(text: str) -> str:
    return text.replace('"', '\\"')


def _ast_text(node: ast.AST) -> str:
    """Return deterministic source text for one AST node."""
    return ast.unparse(node).strip()


def _called_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
    return None


def _stmt_label(stmt: ast.stmt) -> str:
    if isinstance(stmt, ast.Assign):
        targets = ", ".join(_ast_text(t) for t in stmt.targets)
        called = _called_name(stmt.value)
        if called is not None:
            return f"{targets} = {called}(...)"
        return f"{targets} = {_ast_text(stmt.value)}"
    if isinstance(stmt, ast.AnnAssign):
        target = _ast_text(stmt.target)
        if stmt.value is None:
            return target
        called = _called_name(stmt.value)
        if called is not None:
            return f"{target} = {called}(...)"
        return f"{target} = {_ast_text(stmt.value)}"
    if isinstance(stmt, ast.Expr):
        called = _called_name(stmt.value)
        if called is not None:
            return f"{called}(...)"
        return _ast_text(stmt.value)
    if isinstance(stmt, ast.Return):
        return f"return {_ast_text(stmt.value)}" if stmt.value else "return"
    if isinstance(stmt, ast.Raise):
        return f"raise {_ast_text(stmt.exc)}" if stmt.exc else "raise"
    if isinstance(stmt, ast.If):
        return f"if {_ast_text(stmt.test)}"
    if isinstance(stmt, ast.Try):
        return "try"
    return _ast_text(stmt)


class _AstDecisionTreeBuilder:
    def __init__(self) -> None:
        self._next_id = 0
        self.nodes: list[DecisionTreeNode] = []
        self.edges: list[DecisionTreeEdge] = []

    def _new_node(self, label: str) -> str:
        self._next_id += 1
        node_id = f"N{self._next_id:03d}"
        self.nodes.append(DecisionTreeNode(node_id=node_id, label=label))
        return node_id

    def _connect(
        self, incoming: list[tuple[str, str]], target: str
    ) -> None:
        for source, label in incoming:
            self.edges.append(DecisionTreeEdge(source, target, label))

    def build_function(
        self, func: Callable[..., Any]
    ) -> tuple[tuple[DecisionTreeNode, ...], tuple[DecisionTreeEdge, ...]]:
        source = textwrap.dedent(inspect.getsource(func))
        module = ast.parse(source)
        function = module.body[0]
        if not isinstance(function, ast.FunctionDef):
            raise ValueError("decision tree source did not parse to a function")
        start = self._new_node(f"{function.name}(...)")
        statements = list(function.body)
        if (
            statements
            and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)
        ):
            statements = statements[1:]
        exits = self._build_block(statements, [(start, "start")])
        if exits:
            done = self._new_node("end")
            self._connect(exits, done)
        return tuple(self.nodes), tuple(self.edges)

    def _build_block(
        self, statements: list[ast.stmt], incoming: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        exits = incoming
        for stmt in statements:
            if not exits:
                break
            if isinstance(stmt, ast.If):
                exits = self._build_if(stmt, exits)
            elif isinstance(stmt, ast.Try):
                exits = self._build_try(stmt, exits)
            else:
                exits = self._build_plain(stmt, exits)
        return exits

    def _build_plain(
        self, stmt: ast.stmt, incoming: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        node_id = self._new_node(_stmt_label(stmt))
        self._connect(incoming, node_id)
        if isinstance(stmt, ast.Return | ast.Raise):
            return []
        return [(node_id, "")]

    def _build_if(
        self, stmt: ast.If, incoming: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        node_id = self._new_node(_stmt_label(stmt))
        self._connect(incoming, node_id)
        body_exits = self._build_block(stmt.body, [(node_id, "true")])
        if stmt.orelse:
            orelse_exits = self._build_block(stmt.orelse, [(node_id, "false")])
        else:
            orelse_exits = [(node_id, "false")]
        return body_exits + orelse_exits

    def _build_try(
        self, stmt: ast.Try, incoming: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        node_id = self._new_node(_stmt_label(stmt))
        self._connect(incoming, node_id)
        exits = self._build_block(stmt.body, [(node_id, "try")])
        for handler in stmt.handlers:
            if handler.type is None:
                label = "except"
            else:
                label = f"except {_ast_text(handler.type)}"
            handler_id = self._new_node(label)
            self.edges.append(DecisionTreeEdge(node_id, handler_id, "raises"))
            exits.extend(self._build_block(handler.body, [(handler_id, "")]))
        if stmt.orelse:
            exits = self._build_block(stmt.orelse, exits)
        if stmt.finalbody:
            exits = self._build_block(stmt.finalbody, exits)
        return exits


def auto_retro_decision_tree() -> tuple[
    tuple[DecisionTreeNode, ...], tuple[DecisionTreeEdge, ...]
]:
    """Extract the current ``run`` control-flow tree from Python AST."""
    return _AstDecisionTreeBuilder().build_function(run)


def auto_retro_decision_tree_edges() -> tuple[DecisionTreeEdge, ...]:
    """Return AST-derived Mermaid edges for compatibility with tests."""
    _nodes, edges = auto_retro_decision_tree()
    return edges


def render_decision_tree_mermaid() -> str:
    """Render the AST-derived auto-retro decision tree as Mermaid."""
    nodes, edges = auto_retro_decision_tree()
    lines = ["flowchart TD"]
    for node in nodes:
        lines.append(
            f'    {node.node_id}["{_mermaid_text(node.label)}"]'
        )
    for edge in edges:
        if edge.label:
            lines.append(
                f'    {edge.source} -->|"{_mermaid_text(edge.label)}"| '
                f"{edge.target}"
            )
        else:
            lines.append(f"    {edge.source} --> {edge.target}")
    return "\n".join(lines) + "\n"


def render_decision_tree_markdown() -> str:
    """Render the checked-in auto-retro decision tree document."""
    return (
        "# Auto-retro decision tree\n"
        "\n"
        "This file is generated from `scripts/auto_retro.py::run` by "
        "`python3 scripts/auto_retro.py decision-tree-doc`. Do not edit it "
        "by hand; update `run()` and regenerate instead.\n"
        "\n"
        "```mermaid\n"
        f"{render_decision_tree_mermaid()}"
        "```\n"
    )


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
    """``retro(<type>): review PR #<N> repair loops``.

    Strips the optional ``(scope)`` from the source ``type(scope)`` token
    to keep the generated title at a single nesting level. Without this,
    a source PR titled ``docs(retro): ...`` would produce
    ``retro(docs(retro)): ...`` -- nested parens that break the
    Conventional Commit shape of the auto-opened retro title.
    """
    token = extract_type_scope(pr.title) or FALLBACK_TYPE_SCOPE
    type_only = token.split("(", 1)[0]
    return f"retro({type_only}): review PR #{pr.number} repair loops"


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
        rows.append(RepairHistoryRow(f"CI fail: {name}", "; ".join(parts)))

    overflow = total_failed - _CHECK_RUN_DISPLAY_CAP
    if overflow > 0:
        rows.append(
            RepairHistoryRow(
                f"CI fail: + {overflow} more failures",
                "see PR check-run list (truncated)",
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
                )
            )

    if pr_commit_count > 1:
        rows.append(
            RepairHistoryRow(
                "Multi-commit PR",
                f"{_POLICY_ARTIFACT_MARKER} {pr_commit_count} "
                "commits squash-merged",
                policy_artifact=True,
            )
        )

    for pair in verification_pairs or []:
        if pair.passed:
            continue
        rows.append(
            RepairHistoryRow(
                f"Verification fail: {pair.command}",
                f"observed: {pair.result}",
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
        "| # | Repair | What the reviewer / gate caught |\n"
        "|---|--------|----------------------------------|\n"
    )
    if not rows:
        return (
            header
            + "| -- | (no automated repair signals detected) "
            "| positive-control: no repair taxonomy classification requested |\n"
        )
    body_rows = "".join(
        f"| {idx} | {_escape_table_cell(row.repair)} "
        f"| {_escape_table_cell(row.detail)} |\n"
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
    # _build_repair_history_table. Mirrors build_retro_title's split.
    pr_type = type_scope.split("(", 1)[0] if type_scope else ""
    fallback_note = ""
    if not type_scope:
        fallback_note = (
            "\n- Note: source PR title did not parse as a Conventional "
            "Commit-style `type(scope): subject`; retro title falls back to "
            f"`{FALLBACK_TYPE_SCOPE}`.\n"
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
        "- Every repair has a named earliest prevention point.\n"
        "- The no-repair reproduction path matches what would happen if "
        "the deterministic gates from this retrospective were in place.\n"
        "- The `## Follow-up issues` section (if any) is machine-parseable "
        "per the bullet convention above.\n"
    )
    acceptance_block = (
        "- [ ] Repair history table complete.\n"
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
        "check_runs + commit subjects. Edit only to add missed repairs.\n"
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
      Resolves #N`` whose target issue title starts with ``retro(`` or
      ``retro:`` (case-insensitive after lstrip).

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
        stripped = title.lstrip().lower()
        if stripped.startswith("retro(") or stripped.startswith("retro:"):
            return number
    return None


def render_appended_row(pr: MergedPR) -> tuple[str, str]:
    """Render the (left, right) markdown cells for a follow-up fix row."""
    return (
        _escape_table_cell(f"Follow-up fix PR: #{pr.number}"),
        _escape_table_cell(f"`{pr.title}` merged at {pr.merged_at}"),
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
    body: str, row: tuple[str, str], pr_number: int
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
    new_line = f"| {next_idx} | {row[0]} | {row[1]} |\n"
    new_body = body[:close_idx] + new_line + body[close_idx:]
    return new_body, True


def find_existing_retro(
    search_items: list[dict[str, Any]], pr_number: int
) -> int | None:
    """Return the matching retro issue number from search results, or None.

    Match heuristic: title begins with ``retro(`` or ``retro:`` (case-
    insensitive after lstrip) AND contains ``PR #<N>`` not followed by
    another digit. The trailing ``(?!\\d)`` lookahead prevents PR-number
    prefix collisions (e.g. a lookup for #249 must not match a retro for
    #2490). The prefix guard avoids matching an unrelated retro that
    happens to share a type-scope token.
    """
    needle = re.compile(rf"PR #{pr_number}(?!\d)")
    for item in search_items:
        title = item.get("title") or ""
        stripped = title.lstrip().lower()
        if not (stripped.startswith("retro(") or stripped.startswith("retro:")):
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
        created = created.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
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
    sleeper: Callable[[float], None] = time.sleep,
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
        out.append(
            PastRetro(number=number, signals=signals, labels=frozenset(names))
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


# ---------------------------------------------------------------------------
# Retro sentinel I/O boundary (issue #414)
# ---------------------------------------------------------------------------


def search_open_retro_issues(repo: str) -> list[dict[str, Any]]:
    """Return open retro issues for *repo* (paginated to one page).

    Filter: ``layer:meta`` + ``type:docs`` labels (the two labels every
    auto-opened retro carries per :func:`issue_labels`) AND title prefix
    ``retro(`` / ``retro:`` (filtered client-side because the GitHub
    search API does not honor leading parens in ``in:title``).

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
        stripped = title.lstrip().lower()
        if stripped.startswith("retro(") or stripped.startswith("retro:"):
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
        return 0

    # Label-derived prior (refs #582): short the gate when the active
    # signal mix historically produced false positives. Evaluated AFTER
    # signal computation because the prior is irrelevant when no signal
    # fires. Fail-soft: a transient search-API error degrades the
    # prior to empty, which routes through the empty-prior safety
    # net (open normally).
    past_retros = fetch_past_retro_labels(repo)
    prior = compute_prior_from_labels(past_retros)
    prior_skip, prior_reason = should_skip_by_prior(signals, prior)
    if prior_skip:
        print(f"skip: {prior_reason}")
        _append_summary(_build_summary(pr, "skip", prior_reason))
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
        try:
            back_link_status = post_back_link_comment(repo, pr.number, new_number)
        except subprocess.CalledProcessError as exc:
            # Fail-soft: the retro issue is already created. A failure to
            # post the PR-side back-link must NOT roll the retro back --
            # surface a warning and continue so the audit trail keeps the
            # retro that did land.
            print(
                f"::warning::post_back_link_comment failed "
                f"(exit {exc.returncode}); retro issue #{new_number} created "
                "but source PR has no back-link comment",
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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    a = datetime.strptime(iso_a[:20], fmt).replace(tzinfo=timezone.utc)
    b = datetime.strptime(iso_b[:20], fmt).replace(tzinfo=timezone.utc)
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
    ).replace(tzinfo=timezone.utc)
    since_ts = cutoff.timestamp() - (hours * 3600)
    since_dt = datetime.fromtimestamp(since_ts, tz=timezone.utc)
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


def _cmd_decision_tree_doc(args: argparse.Namespace) -> int:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_decision_tree_markdown(), encoding="utf-8")
    return 0


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
        help="Render the auto-retro run decision tree as Mermaid.",
    )
    p_decision_tree.set_defaults(func=_cmd_decision_tree)

    p_decision_tree_doc = sub.add_parser(
        "decision-tree-doc",
        help="Write the checked-in auto-retro decision tree document.",
    )
    p_decision_tree_doc.add_argument(
        "--output",
        default=str(_DECISION_TREE_DOC_PATH),
        help=f"Markdown output path (default {_DECISION_TREE_DOC_PATH}).",
    )
    p_decision_tree_doc.set_defaults(func=_cmd_decision_tree_doc)

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
