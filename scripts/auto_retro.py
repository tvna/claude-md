#!/usr/bin/env python3
"""Auto-open a retrospective issue when a pull request is merged.

Invoked from ``.github/workflows/auto-retro.yml`` as the single
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
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from _trusted_bots import _TRUSTED_BOT_LOGINS
from issue_link import extract_refs, strip_html_comments

FALLBACK_TYPE_SCOPE = "retro"

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
)


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
    return {
        "inline_review_comments": bool(has_inline_comments),
        "body_cites_refs": len(refs) > 0,
        "fix_typed_title": fix_typed,
        "multi_commit_pr": multi_commit,
    }


def render_repair_signals(signals: dict[str, bool]) -> str:
    """Render a one-line summary of the signal aggregate for log/summary use."""
    return ", ".join(f"{name}={str(fired).lower()}" for name, fired in signals.items())


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


def _escape_table_cell(text: str) -> str:
    """Escape a string for safe placement inside one markdown-table cell.

    Replaces ``|`` with ``\\|`` (so a commit subject containing a pipe
    does not split the row) and collapses any embedded newline or
    carriage return to a single space (so a multi-line value does not
    break out of the cell).
    """
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _build_repair_history_table(
    check_runs: list[dict[str, Any]] | None,
    commit_subjects: list[str],
    pr_commit_count: int,
) -> str:
    """Render the Repair history markdown table (header + rows, no surrounds).

    Walks four deterministic signal classes in fixed order: CI failures,
    fix-up commits, merge-from-main commits, multi-commit summary. Emits
    a sentinel row only when all four classes produced zero rows.

    Cells are run through :func:`_escape_table_cell` so commit subjects
    containing ``|`` cannot break the table. The shape mirrors the
    canonical hand-rewrites of #305, #307, #317, #333, #334, #336 on
    2026-05-25. Refs issue #343.
    """
    rows: list[tuple[str, str]] = []

    for entry in check_runs or []:
        conclusion = str(entry.get("conclusion") or "")
        if conclusion not in _CHECK_RUN_FAIL_CONCLUSIONS:
            continue
        name = str(entry.get("name") or "(unnamed)")
        completed = str(entry.get("completed_at") or "(no completed_at)")
        rows.append(
            (
                _escape_table_cell(f"CI fail: {name}"),
                _escape_table_cell(
                    f"conclusion={conclusion} at {completed}"
                ),
            )
        )

    for subject in commit_subjects:
        stripped = subject.strip()
        if (
            stripped.startswith("fix(")
            or stripped.startswith("fixup!")
            or stripped.startswith("squash!")
        ):
            rows.append(
                (
                    _escape_table_cell("Iteration commit"),
                    _escape_table_cell(
                        f"`{subject}` -- signals an earlier silent failure"
                    ),
                )
            )

    for subject in commit_subjects:
        stripped = subject.strip()
        if any(
            stripped.startswith(prefix) for prefix in _MERGE_FROM_MAIN_PREFIXES
        ):
            rows.append(
                (
                    _escape_table_cell("Merge from main"),
                    _escape_table_cell(
                        f"`{subject}` -- rebase debt before merge"
                    ),
                )
            )

    if pr_commit_count > 1:
        rows.append(
            (
                _escape_table_cell("Multi-commit PR"),
                _escape_table_cell(f"{pr_commit_count} commits squash-merged"),
            )
        )

    header = (
        "| # | Repair | What the reviewer / gate caught |\n"
        "|---|--------|----------------------------------|\n"
    )
    if not rows:
        return (
            header
            + "| -- | (no automated repair signals detected) "
            "| operator: investigate manually or mark `(none)` |\n"
        )
    body_rows = "".join(
        f"| {idx} | {left} | {right} |\n"
        for idx, (left, right) in enumerate(rows, start=1)
    )
    return header + body_rows


def build_retro_body(
    pr: MergedPR,
    commit_subjects: list[str],
    check_runs: list[dict[str, Any]] | None = None,
) -> str:
    """Return the markdown body. Contains every section in :data:`_REQUIRED_SECTIONS`.

    ``check_runs`` defaults to ``None`` so legacy two-arg callers keep
    working; in that case the Repair history table falls back to
    commit-subject signals only (and emits the sentinel row when those
    are also empty).
    """
    type_scope = extract_type_scope(pr.title)
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
        check_runs, commit_subjects, pr.commits
    )
    # Idempotent date stamp: derive from pr.merged_at (already an ISO
    # 8601 string from the event payload) rather than datetime.now() so
    # the body is byte-identical on re-run of the same event.
    triage_date = pr.merged_at[:10] if pr.merged_at else "YYYY-MM-DD"
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
        "\n"
        "## Verification\n"
        "\n"
        "- Every repair in the table has a classification from the "
        "section 3 taxonomy.\n"
        "- Every repair has a named earliest prevention point.\n"
        "- The no-repair reproduction path matches what would happen if "
        "the deterministic gates from this retrospective were in place.\n"
        "- The `## Follow-up issues` section (if any) is machine-parseable "
        "per the bullet convention above.\n"
        "\n"
        "## Acceptance criteria\n"
        "\n"
        "- [ ] Repair history table complete.\n"
        "- [ ] Each repair classified with the section 3 taxonomy.\n"
        "- [ ] Each repair has an earliest prevention point.\n"
        "- [ ] No-repair reproduction path stated.\n"
        "- [ ] `## Follow-up issues` filed (or explicitly stated `(none)`).\n"
        "\n"
        "## Parent\n"
        "\n"
        "Refs CLAUDE.md section 3 (\"After each merge, auto-open a "
        f"retrospective issue\"). Source PR: #{pr.number}.\n"
        "\n"
        "_Opened automatically by `.github/workflows/auto-retro.yml`. "
        f"Proposed work pre-filled by retro triage {triage_date} "
        "(auto-filled rows: check_runs + commit subjects; operator-filled "
        "rows: classification, prevention point, no-repair path, "
        "follow-ups)._\n"
    )


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


def issue_labels(layer_labels: tuple[str, ...]) -> list[str]:
    """Return the label list for the retro issue.

    Always ``type:docs`` + ``layer:meta``; appends any additional
    ``layer:*`` labels inherited from the source PR. Deduplicates while
    preserving order.
    """
    labels = ["type:docs", "layer:meta"]
    for lbl in layer_labels:
        if lbl and lbl not in labels:
            labels.append(lbl)
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


def fetch_check_runs(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Return failed check_run entries for the PR's merge commit.

    Two-step fetch:

    1. ``GET /repos/{repo}/pulls/{pr_number}`` to read
       ``merge_commit_sha``. Short-circuits to ``[]`` if the SHA is null
       (GitHub may not have computed it yet on
       ``pull_request_target.closed``).
    2. ``GET /repos/{repo}/commits/{sha}/check-runs?per_page=100`` to
       enumerate runs against that SHA.

    Returns only entries whose ``conclusion`` is in
    :data:`_CHECK_RUN_FAIL_CONCLUSIONS`. The ``per_page=100`` cap is
    sufficient for this repo today (each PR runs <30 checks); overflow
    is treated as best-effort and is not paginated. Refs issue #343.
    """
    raw = gh_api("GET", f"/repos/{repo}/pulls/{pr_number}")
    pr_detail = json.loads(raw) if raw.strip() else {}
    sha = pr_detail.get("merge_commit_sha")
    if not sha:
        return []
    raw = gh_api(
        "GET",
        f"/repos/{repo}/commits/{sha}/check-runs?per_page=100",
    )
    payload = json.loads(raw) if raw.strip() else {}
    all_runs = list(payload.get("check_runs") or [])
    return [
        run
        for run in all_runs
        if str(run.get("conclusion") or "") in _CHECK_RUN_FAIL_CONCLUSIONS
    ]


def search_retro_issues(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Search open + closed issues for an existing retro referencing pr_number."""
    query = f'repo:{repo} type:issue in:title "PR #{pr_number}" "retro"'
    encoded = quote(query, safe="")
    raw = gh_api("GET", f"/search/issues?q={encoded}&per_page=50")
    data = json.loads(raw) if raw.strip() else {}
    return list(data.get("items") or [])


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

    if commit_subjects is None:
        commit_subjects = fetch_pr_commits(repo, pr.number)
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
    title = build_retro_title(pr)
    body = build_retro_body(pr, commit_subjects, check_runs)
    labels = issue_labels(pr.layer_labels)

    created = create_issue(repo, title, body, labels)
    new_number = created.get("number")
    new_url = created.get("html_url") or ""

    back_link_status = "skipped"
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

    msg = (
        f"created retro issue #{new_number} ({new_url}); "
        f"back-link={back_link_status}"
    )
    print(msg)
    _append_summary(_build_summary(pr, "created", msg))
    return 0


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
