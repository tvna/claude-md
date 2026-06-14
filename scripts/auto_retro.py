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
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

# Pure layers extracted into sibling helper modules (Refs #1725, a
# precondition for #1702). auto_retro.py retains the GitHub IO fetchers and
# the run / sentinel / post-merge-rescan orchestration; the parser, triage,
# and renderer layers below are pure and are re-exported here so existing
# ``import auto_retro as ar; ar.<X>`` callers and tests keep resolving every
# moved name (public and underscore-prefixed) on this module. The names are
# also consumed directly by the retained IO code, which calls them as
# module-level symbols.
from _auto_retro_parse import (
    _APPENDED_CLOSE,
    _APPENDED_OPEN,
    _AUTO_FILLED_CLOSE,
    _AUTO_FILLED_OPEN,
    _MERGE_FROM_MAIN_PREFIXES,
    _POLICY_ARTIFACT_MARKER,
    _REPAIR_CAUSE_FILL,
    _REPAIR_NEXT_ACTION_FILL,
    _REQUIRED_SECTIONS,
    _RESULT_ENV_SKIP_RE,
    _RESULT_FAILING_COUNT_RE,
    _RESULT_PASSING_ALL_UNIT_RE,
    _RESULT_PASSING_COUNT_RE,
    _RESULT_PASSING_EXIT_ZERO_RE,
    _RESULT_PASSING_GREP_N_RE,
    _RESULT_PASSING_HEX_HASH_RE,
    _RESULT_PASSING_NIX_QUOTED_RE,
    _RESULT_PASSING_NIX_TOOL_RE,
    _RESULT_PASSING_NON_ASCII_ZERO_RE,
    _RESULT_PASSING_NUMERIC_RE,
    _RESULT_PASSING_OBSERVATION_PHRASES,
    _RESULT_PASSING_PKG_VERSION_RE,
    _RESULT_PASSING_PREFIXES,
    _RESULT_PASSING_SHASUM_RE,
    _RESULT_PASSING_TRAILING_OK_RE,
    _REVERT_CONVENTIONAL_RE,
    _REVERT_PREFIXES,
    _SENTINEL_IGNORED_COMMENT_LOGINS,
    _SIGNAL_NAMES,
    _SIGNALS_FIRED_LINE_RE,
    _TYPE_SCOPE_RE,
    _VERIFICATION_COMMAND_RE,
    _VERIFICATION_RESULT_RE,
    MergedPR,
    RepairHistoryRow,
    VerificationPair,
    _count_merge_from_main,
    _count_revert,
    _is_revert_subject,
    _result_is_passing,
    _slice_section,
    compute_repair_signals,
    extract_post_merge_checklist,
    extract_type_scope,
    extract_verification_pairs,
    is_retro_issue_title,
    is_retro_pr,
    parse_event,
    parse_signals_from_retro_body,
    render_repair_signals,
    render_signals_fired_line,
    should_skip,
)
from _auto_retro_render import (
    _ACCEPTANCE_CHECKBOX_RE,
    _ANNOTATION_FETCH_LIMIT,
    _ANNOTATION_SUMMARY_MAX,
    _CANONICAL_RETRO_TITLE_RE,
    _CHECK_RUN_DISPLAY_CAP,
    _CHECK_RUN_FAIL_CONCLUSIONS,
    _build_repair_history_table,
    _escape_table_cell,
    _has_only_exempt_policy_artifact_rows,
    _insert_appended_row,
    _next_table_index,
    _repair_history_rows,
    build_retro_body,
    build_retro_title,
    find_existing_retro,
    find_target_retro_from_refs,
    is_canonical_handoff_retro_title,
    is_retro_age_exceeded,
    is_retro_untouched,
    issue_labels,
    render_appended_row,
    verify_retro_repair_completeness,
)
from _auto_retro_triage import (
    _FP_TREND_WINDOW,
    _RECENT_RETRO_COUNT,
    _TRIAGE_LABELS,
    _UNLABELLED_KEY,
    PastRetro,
    RecentRetro,
    SignalStat,
    TriageReport,
    _max_active_fp,
    _render_fp_trend,
    _render_recent_retros,
    _retro_fp_rate,
    _retro_status,
    compute_prior_from_labels,
    compute_triage_report,
    is_tentative_by_prior,
    render_triage_report_markdown,
    should_skip_by_prior,
)
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

# Re-export every moved pure symbol (public and underscore-prefixed) so
# ``auto_retro.<name>`` keeps resolving for callers and tests. Ruff's F401
# unused-import check is satisfied by listing the re-exports in ``__all__``.
__all__ = [
    "ALL_RETRO_LABELS",
    "PRIOR_MIN_SAMPLE_SIZE",
    "PRIOR_SKIP_THRESHOLD",
    "PRIOR_TENTATIVE_THRESHOLD",
    "RETRO_FP",
    "RETRO_FP_CANDIDATE",
    "RETRO_TENTATIVE",
    "RETRO_TP",
    "_ACCEPTANCE_CHECKBOX_RE",
    "_ANNOTATION_FETCH_LIMIT",
    "_ANNOTATION_SUMMARY_MAX",
    "_APPENDED_CLOSE",
    "_APPENDED_OPEN",
    "_AUTO_FILLED_CLOSE",
    "_AUTO_FILLED_OPEN",
    "_CANONICAL_RETRO_TITLE_RE",
    "_CHECK_RUN_DISPLAY_CAP",
    "_CHECK_RUN_FAIL_CONCLUSIONS",
    "_FP_TREND_WINDOW",
    "_MERGE_FROM_MAIN_PREFIXES",
    "_POLICY_ARTIFACT_MARKER",
    "_RECENT_RETRO_COUNT",
    "_REPAIR_CAUSE_FILL",
    "_REPAIR_NEXT_ACTION_FILL",
    "_REQUIRED_SECTIONS",
    "_RESULT_ENV_SKIP_RE",
    "_RESULT_FAILING_COUNT_RE",
    "_RESULT_PASSING_ALL_UNIT_RE",
    "_RESULT_PASSING_COUNT_RE",
    "_RESULT_PASSING_EXIT_ZERO_RE",
    "_RESULT_PASSING_GREP_N_RE",
    "_RESULT_PASSING_HEX_HASH_RE",
    "_RESULT_PASSING_NIX_QUOTED_RE",
    "_RESULT_PASSING_NIX_TOOL_RE",
    "_RESULT_PASSING_NON_ASCII_ZERO_RE",
    "_RESULT_PASSING_NUMERIC_RE",
    "_RESULT_PASSING_OBSERVATION_PHRASES",
    "_RESULT_PASSING_PKG_VERSION_RE",
    "_RESULT_PASSING_PREFIXES",
    "_RESULT_PASSING_SHASUM_RE",
    "_RESULT_PASSING_TRAILING_OK_RE",
    "_REVERT_CONVENTIONAL_RE",
    "_REVERT_PREFIXES",
    "_SENTINEL_IGNORED_COMMENT_LOGINS",
    "_SIGNALS_FIRED_LINE_RE",
    "_SIGNAL_NAMES",
    "_TRIAGE_LABELS",
    "_TRUSTED_BOT_LOGINS",
    "_TYPE_SCOPE_RE",
    "_UNLABELLED_KEY",
    "_VERIFICATION_COMMAND_RE",
    "_VERIFICATION_RESULT_RE",
    "MergedPR",
    # triage layer (_auto_retro_triage)
    "PastRetro",
    "RecentRetro",
    "RepairHistoryRow",
    "SignalStat",
    "TriageReport",
    # parser layer (_auto_retro_parse)
    "VerificationPair",
    "_build_repair_history_table",
    "_count_merge_from_main",
    "_count_revert",
    "_escape_table_cell",
    "_has_only_exempt_policy_artifact_rows",
    "_insert_appended_row",
    "_is_revert_subject",
    "_max_active_fp",
    "_next_table_index",
    "_render_fp_trend",
    "_render_recent_retros",
    "_repair_history_rows",
    "_result_is_passing",
    "_retro_fp_rate",
    "_retro_status",
    "_slice_section",
    "build_retro_body",
    # renderer layer (_auto_retro_render)
    "build_retro_title",
    "compute_prior_from_labels",
    "compute_repair_signals",
    "compute_triage_report",
    "extract_post_merge_checklist",
    "extract_type_scope",
    "extract_verification_pairs",
    "find_existing_retro",
    "find_target_retro_from_refs",
    "is_canonical_handoff_retro_title",
    "is_retro_age_exceeded",
    "is_retro_issue_title",
    "is_retro_pr",
    "is_retro_untouched",
    "is_tentative_by_prior",
    "issue_labels",
    "parse_event",
    "parse_signals_from_retro_body",
    "render_appended_row",
    "render_repair_signals",
    "render_signals_fired_line",
    "render_triage_report_markdown",
    "should_skip",
    "should_skip_by_prior",
    "verify_retro_repair_completeness",
]

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

# ``_SENTINEL_IGNORED_COMMENT_LOGINS`` is defined in ``_auto_retro_parse``
# (consumed by both the moved ``is_retro_untouched`` predicate and the
# sentinel orchestration retained below) and re-exported at the top of this
# module.

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
