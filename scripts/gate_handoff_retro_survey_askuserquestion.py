#!/usr/bin/env python3
"""Stop hook: require a pre-merge retro/satisfaction survey at the handoff.

Registered on the ``Stop`` event. The repository UX is that a human
operator reviews and merges a PR through the GitHub UI, so the agent's
natural pre-merge moment is the *handoff*: it has opened a PR and is
ending its turn, advancing the PR to "ready for human merge". This gate
is the deterministic half of the retro contract: when the session's
transcript shows it created a pull request and no survey marker has been
recorded for the session yet, it blocks the stop and hands the agent the
exact branching survey to run through the ``AskUserQuestion`` tool.

Once per session, not once per PR
---------------------------------
The survey is a session-handoff quality signal, so it fires once per
*session*, aggregating every PR opened in the session -- not once per PR.
``created_pr_numbers`` reads the current session's transcript only (a new
session uses a fresh transcript), so it already returns just this session's
PRs; ``evaluate`` blocks only when NONE of them carries a marker yet.
Recording any one PR's survey covers the whole session, so a session that
opens N PRs in a burst fires the gate once, not N times (#1594) -- repeated
per-PR surveys added friction without proportional signal (CLAUDE.md
section 5).

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

When the survey derives "open a retro" (problem at high satisfaction, or any
low-satisfaction handoff), the Stop-hook path -- not CI -- owns opening it
(Refs #1581 / responsibility-separation design D1). The agent first checks for
an existing CI retro for the PR: it comments the local-specific repair detail
(the process repairs CI cannot see) on that retro if one exists, otherwise it
creates the canonical retro issue directly. Either way it records the issue
number with ``--needs-retro --retro-issue <N>``; the recorder refuses to write
the marker (so the Stop gate re-blocks) until that issue number is supplied.

**Gate mode** (default): block the stop when a created PR has no marker.
**Recorder mode** (``--record <pullNumber>``): write the marker. Optional
``--satisfaction <2..5>`` and ``--problem <text>`` persist the survey answers
in the marker body -- the non-interactive fallback for when the interactive
``AskUserQuestion`` confirmation cannot be submitted (issue #1081).
``--needs-retro`` (with the required ``--retro-issue <N>``) records that the
survey derived a retro and which issue captured it.

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
    "GATE BLOCK: this session opened {pr_list} and is handing the work off "
    "for a human GitHub-UI merge, but no pre-merge retro survey is recorded "
    "for this session yet. Run the survey ONCE for the whole session handoff "
    "-- it covers every PR opened this session ({pr_list}), not one survey "
    "per PR (#1594). Use the AskUserQuestion tool with a satisfaction-first, "
    "scenario-branched flow. Present the questions CONSECUTIVELY, plan-mode "
    "style: emit the branched follow-up AskUserQuestion immediately after the "
    "satisfaction answer with no intervening prose, so the survey reads as "
    "one continuous flow.\n"
    "  1. Ask SATISFACTION first, anchored to an EXPLICIT timepoint: frame "
    "the question as 'satisfaction with the work as of the pre-merge handoff "
    "of this session (covering {pr_list}), stating today's date, time, and "
    "timezone as YYYY-MM-DD HH:MM TZ -- e.g. JST and UTC together)' so the "
    "score's reference moment is unambiguous when the marker is read back "
    "later -- a date alone is ambiguous because a session can span hours and "
    "cross the day boundary (single-select: 5 very satisfied / 4 satisfied / "
    "3 neutral / 2 somewhat dissatisfied).\n"
    "  2. Branch on that answer (emit the next question right away):\n"
    "     - high (4-5): ask whether any problem (rework / fix / surprise) "
    "occurred, and DERIVE retro necessity from it -- repair-free means "
    "skip the retro, minor means a short note only, problem means open a "
    "retro issue.\n"
    "     - low (2-3): ask the main pain points (multi-select) and "
    "recommend opening a retro, carrying the answers into its seed rows.\n"
    "  3. If the survey derived 'open a retro' (a problem at high "
    "satisfaction, or any low-satisfaction handoff), open it IN-SESSION now "
    "-- this path, not CI, owns it, because process repairs (e.g. a "
    "wrong-branch re-placement, a discarded-drift cleanup) leave no PR-diff / "
    "CI / review trace for the post-merge detector to see. First search for "
    "an existing retro issue for PR #{primary} (title "
    "'chore(auto-retro): review PR #{primary} repair loops'):\n"
    "     - if one EXISTS: add a comment capturing the local-specific repair "
    "detail (the pain points / process repairs from the survey).\n"
    "     - if NONE exists: create it via mcp__github__issue_write with that "
    "EXACT title and an issue body carrying the H2 sections '## Scope', "
    "'## Facts', '## Proposed work', '## Verification', '## Acceptance "
    "criteria' (seed Facts with the survey pain points).\n"
    "  4. Record the handoff ONCE for the session. For a repair-free / minor "
    "outcome run 'python3 scripts/gate_handoff_retro_survey_askuserquestion.py "
    "--record {primary}'. For a retro outcome run it with "
    "'--record {primary} --needs-retro --retro-issue <N>' where <N> is the "
    "issue you created or commented on -- the recorder refuses the marker "
    "(the Stop gate re-blocks) until that number is supplied. Recording any "
    "one of this session's PRs satisfies the gate for all of them. Then end "
    "your turn. Do NOT call merge_pull_request -- the human merges {pr_list} "
    "through the GitHub UI."
)


def _build_block_reason(created: list[int]) -> str:
    """Render the block reason for the session's created PRs.

    *created* is oldest-first (``created_pr_numbers``). The whole list is
    enumerated so the single survey is understood to cover the session's batch
    of PRs, and the oldest PR is the stable ``--record`` / retro-title target.
    """
    pr_list = ", ".join(f"#{number}" for number in created)
    return _BLOCK_REASON.format(pr_list=pr_list, primary=created[0])


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


def session_surveyed(created: list[int]) -> bool:
    """Return True when any PR created this session already carries a marker.

    The marker dir is the gate's per-session memory: ``created_pr_numbers``
    only ever returns PRs opened in the current session (a fresh session uses a
    fresh transcript), so a single existing marker means the session's handoff
    survey is already done. The gate must then NOT re-fire for the sibling PRs
    opened in the same multi-PR burst -- that double/triple-firing is #1594.
    """
    return any(_marker_path(pr_number).exists() for pr_number in created)


def evaluate(event: dict[str, Any], entries: list[Any]) -> dict[str, Any] | None:
    """Return a Stop block decision, or None to let the stop proceed.

    Survey ONCE per session: block only when the session opened PRs and none of
    them carries a survey marker yet. Recording any one PR's survey then covers
    the whole session, so a session that opens N PRs fires the gate once, not N
    times (#1594).
    """
    if event.get("hook_event_name") not in (None, "Stop"):
        return None
    if event.get("stop_hook_active"):
        return None
    created = created_pr_numbers(entries)
    if not created:
        return None
    if session_surveyed(created):
        return None
    return {"decision": "block", "reason": _build_block_reason(created)}


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
    needs_retro: bool = False,
    retro_issue: int | None = None,
) -> bool:
    """Write the survey marker for *pr_number*; return ``True`` on success.

    The marker's *existence* is all the gate checks, so a bare ``--record``
    stays valid. When ``satisfaction`` and/or ``problem`` answers are given
    (the non-interactive fallback for when ``AskUserQuestion`` cannot be
    confirmed -- issue #1081), they are persisted as JSON in the marker body
    so a real signal is captured instead of an empty file.

    When the survey derives that a retrospective is needed (a problem at high
    satisfaction, or any low-satisfaction handoff), the responsibility for
    opening it is the in-session Stop-hook path's, not CI's: process repairs
    such as a wrong-branch re-placement or a discarded-drift cleanup leave no
    PR-diff / CI / review trace, so the deterministic post-merge detector
    (``scripts/auto_retro.py``) structurally cannot see them (Refs #1581 / D1).
    ``needs_retro`` records that derivation and ``retro_issue`` records the
    issue number the agent created OR commented on (append-or-create against an
    existing CI retro), so the marker carries durable proof the human-observed
    retro landed.

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
    if needs_retro:
        payload["needs_retro"] = True
    if retro_issue is not None:
        payload["retro_issue"] = retro_issue
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
    raw_needs_retro: bool = False,
    raw_retro_issue: str | None = None,
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
    retro_issue: int | None = None
    if raw_retro_issue is not None:
        retro_issue = _coerce_pr_number(raw_retro_issue)
        if retro_issue is None:
            # A malformed issue number is bad data: refuse loudly and leave
            # the marker unwritten so the gate stays blocked (#1140 semantics).
            print(
                f"::error::{_SCRIPT_NAME}: --retro-issue must be a positive "
                "issue number",
                file=sys.stderr,
            )
            return 1
    if raw_needs_retro and retro_issue is None:
        # The survey derived "open a retro" but no retro issue was supplied.
        # The Stop-hook path owns the human-observed retro (Refs #1581 / D1),
        # so refuse to record the handoff as done and exit non-zero: with no
        # marker the Stop gate re-blocks until the agent opens (or comments on)
        # the retro and re-records with --retro-issue.
        print(
            f"::error::{_SCRIPT_NAME}: --needs-retro requires --retro-issue "
            "<N>. The pre-merge survey found a problem, so a retro must be "
            "opened in-session (comment on an existing CI retro for the PR, "
            "or create one titled 'chore(auto-retro): review PR #<PR> repair "
            "loops') before recording. The handoff is NOT recorded and the "
            "Stop gate will re-block.",
            file=sys.stderr,
        )
        return 1
    try:
        record(
            pr_number,
            satisfaction=satisfaction,
            problem=raw_problem,
            needs_retro=raw_needs_retro,
            retro_issue=retro_issue,
        )
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
    parser.add_argument(
        "--needs-retro",
        action="store_true",
        help=(
            "Declare that the survey derived 'open a retro'. Requires "
            "--retro-issue: the recorder refuses to write the marker (the "
            "Stop gate stays blocked) until a retro issue is recorded."
        ),
    )
    parser.add_argument(
        "--retro-issue",
        metavar="ISSUE_NUMBER",
        help=(
            "The retro issue number the agent created OR commented on at the "
            "handoff (append-or-create against an existing CI retro), "
            "persisted with --record."
        ),
    )
    args = parser.parse_args(argv)
    if args.record is not None:
        return run_record(
            args.record,
            args.satisfaction,
            args.problem,
            args.needs_retro,
            args.retro_issue,
        )
    return run_gate()


if __name__ == "__main__":
    raise SystemExit(main())
