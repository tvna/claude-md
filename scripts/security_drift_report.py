#!/usr/bin/env python3
"""Aggregate security-control drift signals into one deterministic report.

The workflow `.github/workflows/weekly-maintenance.yml` invokes
this module. It does not duplicate any detector: it consumes the read-only
output of existing scripts (`ruleset_drift.py detect`, `labels_apply.py
plan`, `uv_pin.py drift`, `uv_pin.py stale`) and the portable-pr-policy.yml
compile-then-diff recipe, then assembles a single Markdown table and a
rolling comment body for the parent tracking issue (#178).

Contract:
- Inputs (aggregate): captured exit codes and stdout/summary files from
  the upstream detector steps; required input shapes are validated and
  malformed values raise ValueError (M4).
- Outputs (aggregate): Markdown table to --summary-file, rolling-comment
  body to --report-file, `families_with_drift=N` and `report_date=` lines
  appended to --github-output.
- Outputs (post-comment): GET issue comments via
  `scripts/_github_api.apply_call`, find the marker, PATCH (update) or
  POST (new). Honours --dry-run.

Failure policy: fails LOUD per CLAUDE.md section 4 on malformed REQUIRED
inputs (this is a gate). Per-family detector failures are recorded as a
`status=error` row in the report and the aggregator still exits 0 -- drift
itself is reported, not gated; each per-family detector keeps its own
gate semantics independently (e.g. `weekly-maintenance.yml` keeps filing its
own per-family issues on the existing weekly cron).

Tested by `tests/test_security_drift_report.py`. Refs #180, parent #178.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from collections.abc import Callable
from pathlib import Path

import issue_anchors
from _github_api import apply_call as github_apply_call

# Static per-family catalog and the shared FamilyRow shape split out to keep this
# module within its size budget (#1488); re-imported so sdr.* names stay stable
# for callers/tests.
from _security_drift_families import (
    FAMILY_ISSUE_SPEC,  # noqa: F401  re-exported for callers/tests
    ISSUE_LABELS,  # noqa: F401  re-exported for callers/tests
    STATUS_COVERED,
    STATUS_DRIFT,
    STATUS_ERROR,
    STATUS_PENDING,
    TARGET_FAMILIES,
    FamilyRow,
)

# Rolling per-family drift-issue reconcile IO split out to keep this module within
# its size budget (#1726); re-imported so sdr.* names stay stable for callers/tests.
from _security_drift_issues import (  # noqa: F401  re-exported for callers/tests
    is_family_issue_title,
    reconcile_family_issues,
    render_family_issue_body,
    render_family_issue_title,
)

API_ROOT = "https://api.github.com"
# Anchor table (#1640): a renumbering is a one-file diff to the TOML.
DEFAULT_TRACKING_ISSUE = issue_anchors.resolve("security-tracking")
DEFAULT_MARKER = "<!-- security-control-drift-report -->"

# ---------------------------------------------------------------------------
# Input parsers (pure)
# ---------------------------------------------------------------------------

def parse_dry_run(raw: str) -> bool:
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"Invalid dry_run value: {raw!r}")


def parse_int_flag(raw: str, name: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer; got {raw!r}") from exc


def parse_detect_output(text: str) -> dict[str, str]:
    """Parse `ruleset_drift.py detect` stdout into a dict.

    The detect subcommand prints three lines `key=value` (run_date,
    drift_count, unknown_count). Other lines are ignored so the parser
    is tolerant of harmless extra output (warnings, etc.).
    """
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in ("run_date", "drift_count", "unknown_count"):
            result[key] = value.strip()
    return result


def labels_plan_has_drift(summary_text: str) -> bool:
    """Return True when the labels_apply.py plan summary shows any non-noop row.

    The plan-mode summary renders one row per SoT label plus one per live
    label not in SoT. Drift rows contain `plan-only (POST|PATCH|DELETE)`
    or `report-only`. No-op rows contain `no-op`. The detector matrix
    treats any non-empty plan as drift.
    """
    return any("plan-only" in line or "report-only" in line for line in summary_text.splitlines())


def uv_stale_has_warning(stale_text: str) -> bool:
    """Return True when uv_pin.py stale emitted a `::warning::` line."""
    return "::warning::" in stale_text


# ---------------------------------------------------------------------------
# Family classifiers (pure)
# ---------------------------------------------------------------------------

def classify_rulesets(*, rc: int, detect_output: str) -> FamilyRow:
    evidence = ".github/workflows/weekly-maintenance.yml"
    if rc != 0:
        return FamilyRow(
            family="rulesets",
            detector="scripts/ruleset_drift.py detect",
            status=STATUS_ERROR,
            evidence=evidence,
            action=f"detector exit rc={rc}; investigate the ruleset-drift step log",
        )
    parsed = parse_detect_output(detect_output)
    drift_count = int(parsed.get("drift_count", "0") or "0")
    unknown_count = int(parsed.get("unknown_count", "0") or "0")
    if drift_count == 0 and unknown_count == 0:
        return FamilyRow(
            family="rulesets",
            detector="scripts/ruleset_drift.py detect",
            status=STATUS_COVERED,
            evidence=evidence,
            action="no action -- live vs SoT in sync",
        )
    parts: list[str] = []
    if drift_count > 0:
        parts.append(f"{drift_count} SoT-vs-live drift row(s)")
    if unknown_count > 0:
        parts.append(f"{unknown_count} unknown ruleset(s) live but not in SoT")
    return FamilyRow(
        family="rulesets",
        detector="scripts/ruleset_drift.py detect",
        status=STATUS_DRIFT,
        evidence=evidence,
        action=(
            f"{'; '.join(parts)} -- see issues filed by weekly-maintenance.yml and "
            "docs/runbooks/rulesets.md for remediation"
        ),
    )


def classify_labels(*, rc: int, summary_text: str) -> FamilyRow:
    evidence = ".github/labels.json"
    if rc != 0:
        return FamilyRow(
            family="labels",
            detector="scripts/labels_apply.py plan",
            status=STATUS_ERROR,
            evidence=evidence,
            action=f"detector exit rc={rc}; investigate the labels plan step log",
        )
    if labels_plan_has_drift(summary_text):
        return FamilyRow(
            family="labels",
            detector="scripts/labels_apply.py plan",
            status=STATUS_DRIFT,
            evidence=evidence,
            action=(
                "plan shows POST/PATCH/DELETE or report-only rows -- dispatch "
                "apply-labels.yml with dry_run=false after review (docs/runbooks/issue-triage.md)"
            ),
        )
    return FamilyRow(
        family="labels",
        detector="scripts/labels_apply.py plan",
        status=STATUS_COVERED,
        evidence=evidence,
        action="no action -- live labels match SoT",
    )


def classify_apm(*, rc: int) -> FamilyRow:
    evidence = ".github/workflows/portable-pr-policy.yml"
    detector = "apm compile + git diff --exit-code -- CLAUDE.md AGENTS.md"
    if rc == 0:
        return FamilyRow(
            family="apm-instructions",
            detector=detector,
            status=STATUS_COVERED,
            evidence=evidence,
            action="no action -- compiled outputs match APM source",
        )
    if rc == 1:
        return FamilyRow(
            family="apm-instructions",
            detector=detector,
            status=STATUS_DRIFT,
            evidence=evidence,
            action=(
                "CLAUDE.md / AGENTS.md drift vs .apm/instructions/master.instructions.md "
                "-- run `uv run --with apm-cli==<pin> --exclude-newer \"14 days\" apm compile` "
                "and commit"
            ),
        )
    return FamilyRow(
        family="apm-instructions",
        detector=detector,
        status=STATUS_ERROR,
        evidence=evidence,
        action=f"detector exit rc={rc}; investigate the apm compile step log",
    )


def classify_uv_pin_literal(*, rc: int) -> FamilyRow:
    evidence = "pyproject.toml [tool.uv].required-version"
    if rc == 0:
        return FamilyRow(
            family="uv-pin-literal",
            detector="scripts/uv_pin.py drift",
            status=STATUS_COVERED,
            evidence=evidence,
            action="no action -- pin literal only in pyproject.toml",
        )
    if rc == 1:
        return FamilyRow(
            family="uv-pin-literal",
            detector="scripts/uv_pin.py drift",
            status=STATUS_DRIFT,
            evidence=evidence,
            action=(
                "uv pin literal appears outside pyproject.toml -- remove the "
                "offending literal or update pyproject.toml (docs/standards/remote-environment.md)"
            ),
        )
    return FamilyRow(
        family="uv-pin-literal",
        detector="scripts/uv_pin.py drift",
        status=STATUS_ERROR,
        evidence=evidence,
        action=f"detector exit rc={rc}; investigate the uv_pin drift step log",
    )


def classify_workflow_permissions(*, rc: int) -> FamilyRow:
    evidence = ".github/actions-permissions/workflow.json"
    detector = "scripts/rulesets_apply.py workflow-permissions --mode drift"
    if rc == 0:
        return FamilyRow(
            family="workflow-permissions",
            detector=detector,
            status=STATUS_COVERED,
            evidence=evidence,
            action="no action -- live default workflow permissions match SoT",
        )
    if rc == 1:
        return FamilyRow(
            family="workflow-permissions",
            detector=detector,
            status=STATUS_DRIFT,
            evidence=evidence,
            action=(
                "live default workflow permissions diverge from SoT -- dispatch "
                "apply-rulesets.yml with enable_workflow_permissions=true and "
                "dry_run=false after review (docs/runbooks/workflow-permissions.md)"
            ),
        )
    return FamilyRow(
        family="workflow-permissions",
        detector=detector,
        status=STATUS_ERROR,
        evidence=evidence,
        action=f"detector exit rc={rc}; investigate the workflow-permissions step log",
    )


def classify_owasp_asi(*, rc: int) -> FamilyRow:
    if rc == 0:
        status, action = STATUS_COVERED, "no action -- every ASI01-ASI10 item carries a status row"
    elif rc == 1:
        status, action = STATUS_DRIFT, (
            "an ASI item lost its status row -- restore the ASI01-ASI10 mapping in "
            "docs/prd/security-control-inventory.md (PR-time lint-scripts-static normally blocks this)"
        )
    else:
        status, action = STATUS_ERROR, f"detector exit rc={rc}; investigate the owasp-asi-mapping step log"
    return FamilyRow(
        family="owasp-asi-mapping",
        detector="scripts/owasp_asi_mapping.py verify",
        status=status,
        evidence="docs/prd/security-control-inventory.md (ASI01-ASI10 section)",
        action=action,
    )


def classify_uv_pin_staleness(*, rc: int, stale_text: str) -> FamilyRow:
    evidence = "pyproject.toml [tool.uv].required-version vs astral-sh/uv latest release"
    if rc != 0:
        return FamilyRow(
            family="uv-pin-staleness",
            detector="scripts/uv_pin.py stale",
            status=STATUS_ERROR,
            evidence=evidence,
            action=f"detector exit rc={rc}; investigate the uv_pin stale step log",
        )
    if uv_stale_has_warning(stale_text):
        return FamilyRow(
            family="uv-pin-staleness",
            detector="scripts/uv_pin.py stale",
            status=STATUS_DRIFT,
            evidence=evidence,
            action=(
                "uv pin trails upstream latest (informational) -- bump "
                "[tool.uv].required-version in pyproject.toml when ready"
            ),
        )
    return FamilyRow(
        family="uv-pin-staleness",
        detector="scripts/uv_pin.py stale",
        status=STATUS_COVERED,
        evidence=evidence,
        action="no action -- pin matches upstream latest",
    )


def pr_gate_only_row(*, family: str, detector: str, evidence: str) -> FamilyRow:
    return FamilyRow(
        family=family,
        detector=detector,
        status=STATUS_PENDING,
        evidence=evidence,
        action="PR-gate only; not scheduled (no drift surface beyond PR review)",
    )


def out_of_scope_row(
    *, family: str, detector: str, evidence: str, message: str
) -> FamilyRow:
    return FamilyRow(
        family=family,
        detector=detector,
        status=STATUS_PENDING,
        evidence=evidence,
        action=message,
    )


# ---------------------------------------------------------------------------
# Report builder (pure)
# ---------------------------------------------------------------------------

def _escape_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _render_table(families: list[FamilyRow]) -> str:
    header = (
        "| Control family | Detector | Status | Evidence | Action |\n"
        "|---|---|---|---|---|\n"
    )
    rows = "".join(
        f"| `{_escape_cell(row.family)}` "
        f"| `{_escape_cell(row.detector)}` "
        f"| {_escape_cell(row.status)} "
        f"| `{_escape_cell(row.evidence)}` "
        f"| {_escape_cell(row.action)} |\n"
        for row in families
    )
    return header + rows


def build_report(
    families: list[FamilyRow],
    *,
    run_url: str,
    run_date: str,
    marker: str = DEFAULT_MARKER,
) -> tuple[str, str, int]:
    """Render summary Markdown, rolling-comment body, and drift count.

    Returns (summary_md, report_body_md, families_with_drift). The
    ``report_body_md`` begins with the marker on its own line so
    ``find_existing_comment`` can locate the rolling comment next run.
    """
    if not families:
        raise ValueError("build_report requires at least one FamilyRow")
    families_with_drift = sum(1 for row in families if row.status == STATUS_DRIFT)
    families_with_error = sum(1 for row in families if row.status == STATUS_ERROR)

    summary = (
        f"## Security control drift report -- {run_date}\n"
        "\n"
        f"- Run: {run_url}\n"
        f"- Families with drift: {families_with_drift}\n"
        f"- Families with detector error: {families_with_error}\n"
        "\n"
        + _render_table(families)
    )

    # Body = marker + `summary` + note; built from `summary` so the two cannot diverge.
    note = (
        "Detector workflows file their own per-family issues when drift is "
        "actionable (see `weekly-maintenance.yml`); this rolling comment is a "
        "single-glance status across all families for the parent #178 tracking issue.\n"
    )
    report_body = f"{marker}\n\n{summary}\n{note}"

    return summary, report_body, families_with_drift


# ---------------------------------------------------------------------------
# Per-family issue helpers (pure)
# ---------------------------------------------------------------------------

def target_families_with_drift(families: list[FamilyRow]) -> list[str]:
    """Return the target families currently in drift, in table order.

    Only families in :data:`TARGET_FAMILIES` are returned, so `rulesets`
    (filed by its own job) and advisory signals never appear here.
    """
    return [
        row.family
        for row in families
        if row.family in TARGET_FAMILIES and row.status == STATUS_DRIFT
    ]


def target_families_covered(families: list[FamilyRow]) -> list[str]:
    """Return the target families with an EXPLICIT clean (`covered`) status.

    A detector that errored is :data:`STATUS_ERROR`, not covered, so it is
    omitted here. The reconcile step closes a rolling issue only for families
    in this list -- never on a bare absence from the drift list -- so a transient
    detector failure cannot auto-close (and thereby hide) an active drift issue.
    """
    return [
        row.family
        for row in families
        if row.family in TARGET_FAMILIES and row.status == STATUS_COVERED
    ]


# render_family_issue_title / is_family_issue_title / render_family_issue_body now
# live in _security_drift_issues (#1726) and are re-imported above.


# ---------------------------------------------------------------------------
# Comment-side pure helpers
# ---------------------------------------------------------------------------

def find_existing_comment(
    comments_json: list[dict], marker: str = DEFAULT_MARKER
) -> int | None:
    """Return the id of the first comment whose body contains the marker."""
    for entry in comments_json:
        body = entry.get("body")
        if isinstance(body, str) and marker in body:
            comment_id = entry.get("id")
            if isinstance(comment_id, int):
                return comment_id
    return None


# ---------------------------------------------------------------------------
# IO boundary (thin)
# ---------------------------------------------------------------------------

def _utc_today() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _append_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def _assemble_families(args: argparse.Namespace) -> list[FamilyRow]:
    ruleset_text = _read_text(Path(args.ruleset_detect_output))
    labels_text = _read_text(Path(args.labels_summary_file))
    uv_stale_text = _read_text(Path(args.uv_stale_output))

    return [
        classify_rulesets(
            rc=parse_int_flag(args.ruleset_detect_rc, "--ruleset-detect-rc"),
            detect_output=ruleset_text,
        ),
        classify_labels(
            rc=parse_int_flag(args.labels_plan_rc, "--labels-plan-rc"),
            summary_text=labels_text,
        ),
        classify_apm(rc=parse_int_flag(args.apm_diff_rc, "--apm-diff-rc")),
        classify_uv_pin_literal(
            rc=parse_int_flag(args.uv_drift_rc, "--uv-drift-rc")
        ),
        classify_workflow_permissions(
            rc=parse_int_flag(
                args.workflow_permissions_drift_rc,
                "--workflow-permissions-drift-rc",
            )
        ),
        classify_uv_pin_staleness(
            rc=parse_int_flag(args.uv_stale_rc, "--uv-stale-rc"),
            stale_text=uv_stale_text,
        ),
        classify_owasp_asi(rc=parse_int_flag(args.owasp_asi_verify_rc, "--owasp-asi-verify-rc")),
        pr_gate_only_row(
            family="title-policy",
            detector=".github/workflows/portable-pr-policy.yml",
            evidence="scripts/title_policy.py",
        ),
        pr_gate_only_row(
            family="non-ascii",
            detector=".github/workflows/issue-pr-triage.yml / scan",
            evidence="scripts/scan_non_ascii.py + scripts/preflight_non_ascii.py",
        ),
        pr_gate_only_row(
            family="dependabot-labels",
            detector=".github/workflows/verify-dependabot-labels.yml",
            evidence="scripts/dependabot_labels.py",
        ),
        out_of_scope_row(
            family="required-checks",
            detector="(tracked separately)",
            evidence=".github/rulesets/main.json",
            message="tracked by #120 -- out of scope for this report path",
        ),
    ]


def _cmd_aggregate(args: argparse.Namespace) -> int:
    run_date = args.run_date or _utc_today()
    families = _assemble_families(args)
    summary, report_body, families_with_drift = build_report(
        families, run_url=args.run_url, run_date=run_date, marker=args.marker
    )

    drift_families = target_families_with_drift(families)
    covered_families = target_families_covered(families)

    _append_text(Path(args.summary_file), summary)
    _write_text(Path(args.report_file), report_body)
    _append_text(
        Path(args.github_output),
        f"families_with_drift={families_with_drift}\n"
        f"report_date={run_date}\n"
        f"drift_families={','.join(drift_families)}\n"
        f"covered_families={','.join(covered_families)}\n",
    )
    return 0


def _cmd_file_family_issues(args: argparse.Namespace) -> int:
    """Reconcile ONE rolling issue per target family (create / dedupe / close).

    Despite the historical subcommand name, this no longer floods a fresh issue
    per run (#1726): it delegates to
    :func:`_security_drift_issues.reconcile_family_issues`. ``--families`` is the
    comma-separated ``drift_families`` output of ``aggregate`` (families in drift),
    and ``--resolved-families`` is the ``covered_families`` output (families with an
    EXPLICIT clean status). Only a `covered` family is auto-closed; a family in
    neither list -- e.g. its detector errored -- is left untouched so a transient
    failure cannot hide an active drift issue. Each name must be in
    :data:`TARGET_FAMILIES`; an unexpected name fails loud. Honours ``--dry-run``.
    """
    dry_run = parse_dry_run(args.dry_run)
    run_date = args.run_date or _utc_today()
    drifting = [name.strip() for name in args.families.split(",") if name.strip()]
    resolved = [name.strip() for name in args.resolved_families.split(",") if name.strip()]

    unknown = [name for name in (*drifting, *resolved) if name not in TARGET_FAMILIES]
    if unknown:
        raise ValueError(
            f"--families/--resolved-families contains non-target families {unknown}; "
            f"allowed: {sorted(TARGET_FAMILIES)}"
        )

    return reconcile_family_issues(
        apply=args.apply_call,  # injected via tests; main() wires github_apply_call.
        repo=args.repo,
        run_url=args.run_url,
        run_date=run_date,
        drifting=drifting,
        resolved=resolved,
        dry_run=dry_run,
    )


def _cmd_post_comment(args: argparse.Namespace) -> int:
    dry_run = parse_dry_run(args.dry_run)
    body = _read_text(Path(args.report_file))
    if not body.strip():
        print("::error::Report body is empty; nothing to post.", file=sys.stderr)
        return 1
    if args.marker not in body:
        print(
            f"::error::Report body is missing required marker {args.marker!r}.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(
            f"[dry-run] Would post/update rolling comment on "
            f"{args.repo}#{args.issue} (marker={args.marker!r})."
        )
        return 0

    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN is not set.", file=sys.stderr)
        return 1

    apply = args.apply_call  # injected via tests; main() wires this to github_apply_call.
    code, response = apply(
        method="GET",
        url=f"{API_ROOT}/repos/{args.repo}/issues/{args.issue}/comments?per_page=100",
        payload=None,
        token=token,
    )
    if not 200 <= code < 300:
        print(
            f"::error::GET comments failed (HTTP {code}); body: {response[:200]}",
            file=sys.stderr,
        )
        return 1

    import json as _json
    try:
        comments = _json.loads(response)
    except _json.JSONDecodeError as exc:
        print(f"::error::Could not parse comments JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(comments, list):
        print("::error::Comments response was not a JSON array.", file=sys.stderr)
        return 1

    comment_id = find_existing_comment(comments, args.marker)
    if comment_id is None:
        code, response = apply(
            method="POST",
            url=f"{API_ROOT}/repos/{args.repo}/issues/{args.issue}/comments",
            payload={"body": body},
            token=token,
        )
        if not 200 <= code < 300:
            print(
                f"::error::POST comment failed (HTTP {code}); body: {response[:200]}",
                file=sys.stderr,
            )
            return 1
        print(f"Posted new rolling comment on {args.repo}#{args.issue}.")
        return 0

    code, response = apply(
        method="PATCH",
        url=f"{API_ROOT}/repos/{args.repo}/issues/comments/{comment_id}",
        payload={"body": body},
        token=token,
    )
    if not 200 <= code < 300:
        print(
            f"::error::PATCH comment {comment_id} failed (HTTP {code}); body: {response[:200]}",
            file=sys.stderr,
        )
        return 1
    print(f"Updated rolling comment {comment_id} on {args.repo}#{args.issue}.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser(
    apply_call: Callable[..., tuple[int, str]] = github_apply_call,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_agg = sub.add_parser("aggregate", help="Aggregate detector outputs into one report.")
    p_agg.add_argument("--ruleset-detect-output", required=True)
    p_agg.add_argument("--ruleset-detect-rc", required=True)
    p_agg.add_argument("--labels-plan-rc", required=True)
    p_agg.add_argument("--labels-summary-file", required=True)
    p_agg.add_argument("--apm-diff-rc", required=True)
    p_agg.add_argument("--uv-drift-rc", required=True)
    p_agg.add_argument("--workflow-permissions-drift-rc", required=True)
    p_agg.add_argument("--uv-stale-rc", required=True)
    p_agg.add_argument("--uv-stale-output", required=True)
    p_agg.add_argument("--owasp-asi-verify-rc", required=True)
    p_agg.add_argument("--run-url", required=True)
    p_agg.add_argument("--run-date", default="")
    p_agg.add_argument(
        "--summary-file",
        default=os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"),
    )
    p_agg.add_argument("--report-file", required=True)
    p_agg.add_argument(
        "--github-output",
        default=os.environ.get("GITHUB_OUTPUT", "/dev/null"),
    )
    p_agg.add_argument("--marker", default=DEFAULT_MARKER)
    p_agg.set_defaults(func=_cmd_aggregate)

    p_post = sub.add_parser(
        "post-comment", help="Post or update the rolling comment on the tracking issue."
    )
    p_post.add_argument("--repo", required=True)
    p_post.add_argument("--issue", type=int, default=DEFAULT_TRACKING_ISSUE)
    p_post.add_argument("--report-file", required=True)
    p_post.add_argument("--marker", default=DEFAULT_MARKER)
    p_post.add_argument("--dry-run", default="true")
    p_post.set_defaults(func=_cmd_post_comment, apply_call=apply_call)

    p_file = sub.add_parser(
        "file-family-issues",
        help="Reconcile one rolling issue per target family (create / dedupe / close).",
    )
    p_file.add_argument("--repo", required=True)
    p_file.add_argument("--run-url", required=True)
    p_file.add_argument("--run-date", default="")
    p_file.add_argument(
        "--families",
        required=True,
        help="Comma-separated drift_families output from the aggregate subcommand.",
    )
    p_file.add_argument(
        "--resolved-families",
        default="",
        help=(
            "Comma-separated covered_families output from the aggregate subcommand "
            "(families with an EXPLICIT clean status). Only these are auto-closed; "
            "a family in neither list (e.g. a detector error) is left untouched. "
            "Defaults to empty so a missing value never auto-closes."
        ),
    )
    p_file.add_argument("--dry-run", default="true")
    p_file.set_defaults(func=_cmd_file_family_issues, apply_call=apply_call)

    return parser


def main(
    argv: list[str] | None = None,
    *,
    apply_call: Callable[..., tuple[int, str]] = github_apply_call,
) -> int:
    parser = _build_parser(apply_call=apply_call)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
