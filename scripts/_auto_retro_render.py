"""Pure renderer/body layer for ``scripts/auto_retro.py``.

The top pure layer of the auto-retro refactor (Refs #1725, a precondition
for #1702): building the retro issue title and body, rendering the Repair
history table, the completeness verifier, the dedup / append helpers, and
the sentinel age/untouched predicates. Every function here is pure; it
turns parsed inputs (a :class:`_auto_retro_parse.MergedPR`, fetched
check_runs / commit subjects, an existing issue body) into Markdown or a
verdict; with no GitHub API calls or filesystem access. The IO layer in
``auto_retro.py`` fetches the inputs and posts the rendered output.

Depends on :mod:`_auto_retro_parse` for the shared dataclasses, the
``type(scope)`` parser, the signal-line renderer, the revert/merge-from-main
predicates, and the auto-filled / repair-fill marker constants, plus the
constants-only ``_retro_labels`` and ``issue_link`` helpers. It never
imports ``auto_retro`` or ``_auto_retro_triage``, keeping the dependency
graph acyclic.

``scripts/auto_retro.py`` re-exports every public and underscore-prefixed
name defined here so existing ``import auto_retro as ar; ar.<X>`` callers
and tests keep working unchanged.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from _auto_retro_parse import (
    _AUTO_FILLED_CLOSE,
    _AUTO_FILLED_OPEN,
    _MERGE_FROM_MAIN_PREFIXES,
    _POLICY_ARTIFACT_MARKER,
    _REPAIR_CAUSE_FILL,
    _REPAIR_NEXT_ACTION_FILL,
    _SENTINEL_IGNORED_COMMENT_LOGINS,
    MergedPR,
    RepairHistoryRow,
    VerificationPair,
    _is_revert_subject,
    _slice_section,
    extract_type_scope,
    is_per_pr_retro_title,
    is_retro_issue_title,
    render_signals_fired_line,
)
from _retro_labels import RETRO_TENTATIVE
from issue_link import extract_refs, strip_html_comments


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


# Exact canonical retro-title shape produced by :func:`build_retro_title`.
# Anchored and fully literal so the match is the *single* title an agent is
# permitted to mint under the otherwise-reserved ``auto-retro`` scope (the
# pre-merge handoff survey opens this retro in-session when a problem is
# found; Refs #1581 / D1). Kept deliberately narrow: only the colon form
# ``chore(auto-retro): review PR #<N> repair loops`` matches, so every other
# ``auto-retro``-scoped title stays denied by gate_reserved_retro_scope, and
# CI dedup (:func:`find_existing_retro`) still recognises the in-session retro
# to suppress the post-merge duplicate. The alignment with build_retro_title
# is asserted by tests so the predicate can never drift from the producer.
_CANONICAL_RETRO_TITLE_RE = re.compile(
    r"^chore\(auto-retro\): review PR #\d+ repair loops$"
)


def is_canonical_handoff_retro_title(title: str) -> bool:
    """True iff *title* is exactly the canonical auto-retro retro title.

    The match is exact (anchored, literal) against the shape
    :func:`build_retro_title` emits, so it is the one permitted exception to
    the reserved-``auto-retro``-scope deny in
    :mod:`gate_reserved_retro_scope`. Surrounding whitespace is tolerated;
    the legacy no-colon prefix and any other ``auto-retro`` title do NOT
    match. Refs #1581.
    """
    return bool(_CANONICAL_RETRO_TITLE_RE.fullmatch(title.strip()))


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
    distinct ``Fix commit`` row; see #413), merge-from-main commits,
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
                    f"{_POLICY_ARTIFACT_MARKER} `{subject}`; "
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
                    f"{_POLICY_ARTIFACT_MARKER} `{subject}`; "
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
                    f"{_POLICY_ARTIFACT_MARKER} `{subject}`; "
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
                    f"{_POLICY_ARTIFACT_MARKER} `{subject}`; rollback; "
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
    # skips a verification-only PR; mirroring the `Revert commit` row.
    for pair in verification_pairs or []:
        if pair.passed:
            continue
        rows.append(
            RepairHistoryRow(
                f"Verification fail: {pair.command}",
                f"{_POLICY_ARTIFACT_MARKER} observed: {pair.result}; "
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
            + "| n/a | (no automated repair signals detected) "
            "| positive-control: no repair taxonomy classification requested "
            "| n/a |\n"
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
    the line is rendered as ``- Signals fired: (none)``; contributing
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
        "2. Classification; (operator) tag each repair above as one of: "
        "`missing deterministic gate` / `unclear agent instruction` / "
        "`external or human decision that cannot be automated`.\n"
        "3. Earliest prevention point; (operator) per repair, name the "
        "deterministic gate that should have caught it (workflow, hook, "
        "ruleset, label, preflight).\n"
        "4. No-repair reproduction path; (operator) numbered steps the next "
        "similar PR should follow to land in one shot.\n"
        "5. Follow-up issues; (operator) list deferred gates as "
        "`- [ ] type(scope): TITLE; RATIONALE` or write `(none)`.\n"
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
            "2. Positive-control outcome; no automated repair signals were "
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
        f"- Source PR: #{pr.number}; {pr.title}\n"
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
        "1. Repair history; the table below is pre-filled from "
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

    Match heuristic: title is a per-PR retro title (auto-retro shape via
    :func:`is_retro_issue_title` OR hand-authored ``chore(retro)`` via
    :func:`is_per_pr_retro_title`; additive OR so both creation paths dedup,
    Refs #1995) AND contains ``PR #<N>`` not followed by another digit. The
    trailing ``(?!\\d)`` lookahead prevents PR-number prefix collisions (e.g. a
    lookup for #249 must not match a retro for #2490).
    """
    needle = re.compile(rf"PR #{pr_number}(?!\d)")
    for item in search_items:
        title = item.get("title") or ""
        if not (is_retro_issue_title(title) or is_per_pr_retro_title(title)):
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
