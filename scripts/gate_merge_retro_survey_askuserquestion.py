#!/usr/bin/env python3
"""PreToolUse gate: require a pre-merge retro/satisfaction survey before merge.

Registered on ``mcp__github__merge_pull_request``. Just before a PR is
merged, the operator wants a structured retrospective survey presented
through the ``AskUserQuestion`` tool so the retro decision is captured by
inspection rather than left to operator memory. This gate is the
deterministic half of that contract: it blocks ``merge_pull_request``
until a survey marker has been recorded for the same PR number, and the
deny reason hands the agent the exact branching survey to run.

Why a Claude-only gate
----------------------
``AskUserQuestion`` is a Claude Code harness tool with no Codex / Devin
equivalent, so -- exactly like ``gate_decision_handoff_askuserquestion``
-- this gate lives only in ``.claude/settings.json`` and is recorded in
``scripts/scan_hook_coverage_drift.py``'s ``ALLOWLIST`` (PreToolUse is in
the parity scan scope, unlike the Stop event the handoff gate uses).

Survey shape (encoded in the deny reason)
-----------------------------------------
A hook cannot call ``AskUserQuestion`` itself; the only lever is to deny
the merge and feed the flow back to the agent, which then re-emits the
survey. The flow is satisfaction-first, then scenario-branched:

1. Ask satisfaction FIRST (single-select, 5..2).
2. Branch on the satisfaction answer:
   * high (4-5) -> ask whether any problem (rework / fix / surprise)
     occurred so retro necessity is *derived* from that answer
     (repair-free -> skip; minor -> note only; problem -> open retro);
   * low (2-3) -> ask the main pain points (multi-select) and recommend
     opening a retro, carrying the answers into the retro's seed rows.
3. After the survey, record completion via ``--record <pullNumber>`` and
   re-call ``merge_pull_request``; the marker lets this gate pass.

**Gate mode** (default): deny merge when no marker exists for the PR.
**Recorder mode** (``--record <pullNumber>``): write the marker so the
agent's next merge attempt proceeds.

Fail-open per CLAUDE.md section 4: any missing field, malformed stdin,
or unexpected exception exits 0 with no output. A gate bug must never
wedge the session -- the server-side merge protections remain as
backstop.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path
from typing import Any

from _github_tool_names import canonical_github_tool
from _hook_runtime import emit_decision, read_event

_SCRIPT_NAME = "gate_merge_retro_survey_askuserquestion"
_TARGET_TOOL = "mcp__github__merge_pull_request"
_MARKER_DIR = Path("/tmp/claude-merge-retro-survey")  # noqa: S108

_DENY_REASON = (
    "GATE DENY: PR #{pr} has no pre-merge retro survey recorded in this "
    "session. Before merging, run the AskUserQuestion tool with a "
    "satisfaction-first, scenario-branched flow:\n"
    "  1. Ask SATISFACTION first (single-select: 5 very satisfied / 4 "
    "satisfied / 3 neutral / 2 somewhat dissatisfied).\n"
    "  2. Branch on that answer:\n"
    "     - high (4-5): ask whether any problem (rework / fix / surprise) "
    "occurred, and DERIVE retro necessity from it -- repair-free means "
    "skip the retro, minor means a short note only, problem means open a "
    "retro issue.\n"
    "     - low (2-3): ask the main pain points (multi-select) and "
    "recommend opening a retro, carrying the answers into its seed rows.\n"
    "  3. After the survey, record it with "
    "'python3 scripts/gate_merge_retro_survey_askuserquestion.py "
    "--record {pr}', then re-call merge_pull_request."
)


def _marker_path(pr_number: int) -> Path:
    return _MARKER_DIR / str(pr_number)


def _coerce_pr_number(raw: object) -> int | None:
    """Return a positive PR number from *raw*, or ``None``."""
    if isinstance(raw, bool):  # bool is an int subclass; reject it explicitly
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, float) and raw > 0 and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and raw.isdecimal() and int(raw) > 0:
        return int(raw)
    return None


def _extract_pr_number(tool_name: str, tool_input: dict[str, Any]) -> int | None:
    """Return the PR number when *tool_name* is the merge tool, else ``None``."""
    if canonical_github_tool(tool_name) != _TARGET_TOOL:
        return None
    return _coerce_pr_number(tool_input.get("pullNumber"))


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return a ``permissionDecision: deny`` dict, or ``None`` to allow.

    Denies a merge attempt when no survey marker exists for the PR;
    allows once the marker is present or the call is off-target.
    """
    pr_number = _extract_pr_number(tool_name, tool_input)
    if pr_number is None:
        return None
    if _marker_path(pr_number).exists():
        return None
    return {
        "permissionDecision": "deny",
        "decisionReason": _DENY_REASON.format(pr=pr_number),
    }


def record(pr_number: int) -> bool:
    """Write the survey marker for *pr_number*; return ``True`` on success."""
    _MARKER_DIR.mkdir(parents=True, exist_ok=True)
    _marker_path(pr_number).touch()
    return True


def run_gate() -> int:
    event = read_event(_SCRIPT_NAME)
    if event is None:
        return 0
    if not isinstance(event, dict):
        return 0
    tool_name = event.get("tool_name", "")
    if not isinstance(tool_name, str):
        return 0
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    try:
        decision = decide(tool_name, tool_input)
    except Exception as exc:  # fail open: never wedge the session on a gate bug
        print(f"::error::{_SCRIPT_NAME}: {exc}", file=sys.stderr)
        return 0
    emit_decision(decision)
    return 0


def run_record(raw_pr: str | None) -> int:
    pr_number = _coerce_pr_number(raw_pr)
    if pr_number is None:
        print(
            f"::error::{_SCRIPT_NAME}: --record needs a positive PR number",
            file=sys.stderr,
        )
        return 0
    with contextlib.suppress(OSError):
        record(pr_number)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-merge retro/satisfaction survey gate and recorder.",
        add_help=True,
    )
    parser.add_argument(
        "--record",
        metavar="PR_NUMBER",
        help="Recorder mode: mark a PR's pre-merge survey as completed.",
    )
    args = parser.parse_args(argv)
    if args.record is not None:
        return run_record(args.record)
    return run_gate()


if __name__ == "__main__":
    raise SystemExit(main())
