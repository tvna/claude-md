#!/usr/bin/env python3
"""Stop hook: require a pre-merge retro/satisfaction survey at the handoff.

Registered on the ``Stop`` event. The repository UX is that a human
operator reviews and merges a PR through the GitHub UI, so the agent's
natural pre-merge moment is the *handoff*: it has opened a PR and is
ending its turn, advancing the PR to "ready for human merge". This gate
is the deterministic half of the retro contract: when the session's
transcript shows it created a pull request and no survey marker has been
recorded for that PR, it blocks the stop and hands the agent the exact
branching survey to run through the ``AskUserQuestion`` tool.

Why a Stop hook and not a merge-tool gate
-----------------------------------------
The earlier design (issue #1052 / PR #1053) gated
``mcp__github__merge_pull_request``. That only fires when the agent
itself merges through the tool; under the human-UI-merge UX the agent
never calls it, so the survey never appeared (observed on PR #1062).
The handoff -- the agent's ``Stop`` -- is the only in-session moment
that matches a human UI merge. Issue #1073 moves the trigger here.

Why a Claude-only gate
----------------------
``AskUserQuestion`` is a Claude Code harness tool with no Codex / Devin
equivalent, so -- exactly like ``gate_decision_handoff_askuserquestion``
-- this gate lives only in ``.claude/settings.json``. The ``Stop`` event
is outside the ``scan_hook_coverage_drift`` parity scope (SessionStart /
PreToolUse / PostToolUse), so it needs no allowlist entry.

Survey shape (encoded in the block reason)
------------------------------------------
A hook cannot call ``AskUserQuestion`` itself; the only lever is to
block the stop and feed the flow back to the agent, which then re-emits
the survey. The flow is satisfaction-first, then scenario-branched:

1. Ask satisfaction FIRST (single-select, 5..2).
2. Branch on the satisfaction answer:
   * high (4-5) -> ask whether any problem (rework / fix / surprise)
     occurred so retro necessity is *derived* from that answer
     (repair-free -> skip; minor -> note only; problem -> open retro);
   * low (2-3) -> ask the main pain points (multi-select) and recommend
     opening a retro, carrying the answers into the retro's seed rows.
3. After the survey, record completion via ``--record <pullNumber>`` and
   end the turn; the human merges the PR through the GitHub UI. The
   marker lets a later stop in the same session pass.

**Gate mode** (default): block the stop when a created PR has no marker.
**Recorder mode** (``--record <pullNumber>``): write the marker. Optional
``--satisfaction <2..5>`` and ``--problem <text>`` persist the survey answers
in the marker body -- the non-interactive fallback for when the interactive
``AskUserQuestion`` confirmation cannot be submitted (issue #1081).

Fail-open per CLAUDE.md section 4: any malformed event, unreadable
transcript, or unexpected exception exits 0 with no output. A gate bug
must never wedge the session -- the server-side post-merge retro
(``.github/workflows/post-merge.yml``) remains the backstop.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from _github_tool_names import canonical_github_tool
from _hook_runtime import emit_decision, read_event

_SCRIPT_NAME = "gate_handoff_retro_survey_askuserquestion"
_CREATE_PR_TOOL = "mcp__github__create_pull_request"
_MARKER_DIR = Path("/tmp/claude-pre-merge-retro-survey")  # noqa: S108
_PULL_URL_RE = re.compile(r"/pull/(\d+)")
_MIN_SATISFACTION = 2
_MAX_SATISFACTION = 5
# Lifecycle phase stamped into every survey marker (refs #1192) so a later
# reader knows which moment the satisfaction score measures.
_SURVEY_PHASE = "pre-merge-handoff"

_BLOCK_REASON = (
    "GATE BLOCK: this session opened PR #{pr} and is handing it off for a "
    "human GitHub-UI merge, but no pre-merge retro survey is recorded. "
    "Before ending your turn, run the AskUserQuestion tool with a "
    "satisfaction-first, scenario-branched flow. Present the questions "
    "CONSECUTIVELY, plan-mode style: emit the branched follow-up "
    "AskUserQuestion immediately after the satisfaction answer with no "
    "intervening prose, so the survey reads as one continuous flow.\n"
    "  1. Ask SATISFACTION first, anchored to an EXPLICIT timepoint: frame "
    "the question as 'satisfaction with the work as of the pre-merge handoff "
    "of PR #{pr} (state today's date, time, and timezone as "
    "YYYY-MM-DD HH:MM TZ -- e.g. JST and UTC together)' so the score's "
    "reference moment is unambiguous when the marker is read back later -- a "
    "date alone is ambiguous because a session can span hours and cross the "
    "day boundary (single-select: 5 very satisfied / 4 satisfied / 3 neutral "
    "/ 2 somewhat dissatisfied).\n"
    "  2. Branch on that answer (emit the next question right away):\n"
    "     - high (4-5): ask whether any problem (rework / fix / surprise) "
    "occurred, and DERIVE retro necessity from it -- repair-free means "
    "skip the retro, minor means a short note only, problem means open a "
    "retro issue.\n"
    "     - low (2-3): ask the main pain points (multi-select) and "
    "recommend opening a retro, carrying the answers into its seed rows.\n"
    "  3. After the survey, record it with "
    "'python3 scripts/gate_handoff_retro_survey_askuserquestion.py "
    "--record {pr}', then end your turn. Do NOT call merge_pull_request -- "
    "the human merges PR #{pr} through the GitHub UI."
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


def _coerce_satisfaction(raw: object) -> int | None:
    """Return an integer satisfaction score in ``2..5`` from *raw*, or ``None``.

    Accepts an int, an integral float, or a decimal string, mirroring
    ``_coerce_pr_number``. ``bool`` and out-of-range values are rejected so
    a bad ``--satisfaction`` never records a meaningless score.
    """
    if isinstance(raw, bool):  # bool is an int subclass; reject it explicitly
        return None
    value: int | None = None
    if isinstance(raw, int):
        value = raw
    elif (isinstance(raw, float) and raw.is_integer()) or (
        isinstance(raw, str) and raw.isdecimal()
    ):
        value = int(raw)
    if value is None or not (_MIN_SATISFACTION <= value <= _MAX_SATISFACTION):
        return None
    return value


def _content_blocks(entry: object) -> list[dict[str, Any]]:
    """Return the list of content blocks for a transcript entry, or []."""
    if not isinstance(entry, dict):
        return []
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _result_text(block: dict[str, Any]) -> str:
    """Return the text payload of a tool_result block (str or block list)."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            sub["text"]
            for sub in content
            if isinstance(sub, dict)
            and sub.get("type") == "text"
            and isinstance(sub.get("text"), str)
        ]
        return "\n".join(parts)
    return ""


def created_pr_numbers(entries: list[Any]) -> list[int]:
    """Return PR numbers this session created, oldest first, de-duplicated.

    A PR is "created" when an assistant ``tool_use`` of
    ``create_pull_request`` has a matching ``tool_result`` that did NOT
    error and whose body carries a ``/pull/<n>`` URL.

    A failed ``create_pull_request`` call is marked ``is_error: true`` by
    the harness regardless of its body, and a common failure -- "A pull
    request already exists for owner:branch .../pull/<n>" -- carries a
    ``/pull/<n>`` URL pointing at the *existing* PR. Counting that as a
    creation would fire the handoff survey for a PR this session never
    opened (#1374), so error results are skipped.
    """
    create_ids: set[str] = set()
    for entry in entries:
        for block in _content_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if canonical_github_tool(str(block.get("name", ""))) != _CREATE_PR_TOOL:
                continue
            tool_id = block.get("id")
            if isinstance(tool_id, str) and tool_id:
                create_ids.add(tool_id)

    numbers: list[int] = []
    for entry in entries:
        for block in _content_blocks(entry):
            if block.get("type") != "tool_result":
                continue
            if block.get("tool_use_id") not in create_ids:
                continue
            if block.get("is_error"):  # failed creation: not a real PR (#1374)
                continue
            match = _PULL_URL_RE.search(_result_text(block))
            if not match:
                continue
            number = int(match.group(1))
            if number > 0 and number not in numbers:
                numbers.append(number)
    return numbers


def evaluate(event: dict[str, Any], entries: list[Any]) -> dict[str, Any] | None:
    """Return a Stop block decision, or None to let the stop proceed."""
    if event.get("hook_event_name") not in (None, "Stop"):
        return None
    if event.get("stop_hook_active"):
        return None
    for pr_number in created_pr_numbers(entries):
        if not _marker_path(pr_number).exists():
            return {
                "decision": "block",
                "reason": _BLOCK_REASON.format(pr=pr_number),
            }
    return None


def load_transcript(path_value: object) -> list[Any]:
    """Read a JSONL transcript into a list of entries; [] on any failure."""
    if not isinstance(path_value, str) or not path_value:
        return []
    path = Path(path_value)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[Any] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def record(
    pr_number: int,
    *,
    satisfaction: int | None = None,
    problem: str | None = None,
) -> bool:
    """Write the survey marker for *pr_number*; return ``True`` on success.

    The marker's *existence* is all the gate checks, so a bare ``--record``
    stays valid. When ``satisfaction`` and/or ``problem`` answers are given
    (the non-interactive fallback for when ``AskUserQuestion`` cannot be
    confirmed -- issue #1081), they are persisted as JSON in the marker body
    so a real signal is captured instead of an empty file.

    Every marker also records *when* and *at what lifecycle phase* the score
    was taken (refs #1192): ``recorded_at`` (ISO-8601 UTC) and ``phase``
    (``pre-merge-handoff``). Without them a later reader cannot tell which
    moment a satisfaction score measures.
    """
    _MARKER_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "pr": pr_number,
        "phase": _SURVEY_PHASE,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    if satisfaction is not None:
        payload["satisfaction"] = satisfaction
    if problem is not None:
        payload["problem"] = problem
    _marker_path(pr_number).write_text(
        json.dumps(payload, sort_keys=True), encoding="utf-8"
    )
    return True


def run_gate() -> int:
    event = read_event(_SCRIPT_NAME)
    if event is None:
        return 0
    if not isinstance(event, dict):
        return 0
    try:
        entries = load_transcript(event.get("transcript_path"))
        decision = evaluate(event, entries)
    except Exception as exc:  # fail open: never wedge the session on a gate bug
        print(f"::error::{_SCRIPT_NAME}: {exc}", file=sys.stderr)
        return 0
    emit_decision(decision, _SCRIPT_NAME)
    return 0


def run_record(
    raw_pr: str | None,
    raw_satisfaction: str | None = None,
    raw_problem: str | None = None,
) -> int:
    pr_number = _coerce_pr_number(raw_pr)
    if pr_number is None:
        print(
            f"::error::{_SCRIPT_NAME}: --record needs a positive PR number",
            file=sys.stderr,
        )
        return 0
    satisfaction: int | None = None
    if raw_satisfaction is not None:
        satisfaction = _coerce_satisfaction(raw_satisfaction)
        if satisfaction is None:
            # Reject loudly and leave the marker unwritten so the gate stays
            # blocked rather than recording the handoff as done with bad data.
            print(
                f"::error::{_SCRIPT_NAME}: --satisfaction must be an integer "
                f"{_MIN_SATISFACTION}..{_MAX_SATISFACTION}",
                file=sys.stderr,
            )
            return 0
    try:
        record(pr_number, satisfaction=satisfaction, problem=raw_problem)
    except OSError as exc:
        # Refs #1140: a swallowed marker-write failure used to exit 0 as if the
        # survey were recorded, but with no marker the next Stop re-blocks and
        # the survey double-fires for the same PR. Surface the failure loudly
        # (CLAUDE.md section 4: never a silent default) and exit non-zero so the
        # caller knows the handoff is NOT recorded and can fix the marker dir
        # and retry, instead of looping on a phantom success.
        print(
            f"::error::{_SCRIPT_NAME}: failed to write survey marker for "
            f"PR #{pr_number}: {exc}. The handoff survey is NOT recorded and "
            "the Stop gate will re-block; fix the marker directory and rerun "
            "--record.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-merge retro/satisfaction survey handoff gate and recorder.",
        add_help=True,
    )
    parser.add_argument(
        "--record",
        metavar="PR_NUMBER",
        help="Recorder mode: mark a PR's pre-merge survey as completed.",
    )
    parser.add_argument(
        "--satisfaction",
        metavar="SCORE",
        help=(
            "Optional non-interactive answer: satisfaction score "
            f"{_MIN_SATISFACTION}..{_MAX_SATISFACTION}, persisted with --record."
        ),
    )
    parser.add_argument(
        "--problem",
        metavar="TEXT",
        help=(
            "Optional non-interactive answer: problem / pain-point note, "
            "persisted with --record."
        ),
    )
    args = parser.parse_args(argv)
    if args.record is not None:
        return run_record(args.record, args.satisfaction, args.problem)
    return run_gate()


if __name__ == "__main__":
    raise SystemExit(main())
