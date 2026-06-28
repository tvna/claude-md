#!/usr/bin/env python3
"""Stop hook: force a paste-ready prompt when handing off to a new session.

#1291 surfaces a paste-ready new-session prompt after a *merge* that touched
session-affecting config. But not every handoff goes through a merge: work is
often parked on the session branch (a new PR cannot be opened in-session
because ``preflight_push_session_branch.py`` (#785) locks pushes to the one
session branch), so it must continue in a follow-up session WITHOUT a merge.

When the agent ends its turn describing such a handoff in prose but does NOT
include a verbatim, paste-ready prompt, the operator is left to ask "what do I
paste into the next session?". This hook removes that ask: it returns a Stop
``decision: block`` with a reason telling the agent to emit the paste-ready
prompt itself, so the handoff is self-serve.

Like ``gate_decision_handoff_askuserquestion.py`` this is a Claude-only Stop
hook: it is registered solely in ``.claude/settings.json`` and intentionally
absent from ``.codex/hooks.json`` / ``.devin/hooks.v1.json``. The ``Stop``
event is outside ``scan_hook_coverage_drift`` parity scope (which compares only
SessionStart / PreToolUse / PostToolUse), so the asymmetry is by design.

A hook cannot force a tool call or author text; the only lever is to block the
stop and feed a reason back to the agent, which then re-emits. Detection is a
deliberately conservative transcript heuristic (no network, no per-stop API
call):

* ``stop_hook_active`` true -> no-op. The harness sets this when the stop is
  already a continuation triggered by a prior block, so re-blocking would loop.
* The turn must NOT be a human/CI terminal wait (#1704). When the only
  remaining work is awaiting a GitHub-UI merge, a code-owner review, or CI,
  there is no agent work to hand to a follow-up session, so the paste-ready
  prompt is noise; such a turn no-ops even if it mentions a handoff.
* The turn must NOT be a terminal-done completion report (#1711). After a merge,
  a turn that frames the work as complete ("all done", "merged", "no follow-up")
  has nothing to hand off, so an RCA / status report that merely NAMES a handoff
  as a topic word must not trip a block; such a turn no-ops too.
* The final assistant turn must signal a handoff to a new / follow-up session,
  AFTER the mandatory pre-merge retro-survey vocabulary is stripped (#1704) --
  the survey gate names its own event a "session handoff", so merely reporting
  that REQUIRED survey must not count as a cue. A handoff is signalled only when
  a cue sits NEAR a forward-continuation directive (#1711): a bare topic mention
  with no directive (an RCA discussing this very hook) is not a handoff ...
* ... AND must NOT already carry a paste-ready prompt (a fenced code block or
  an explicit paste marker); otherwise the goal is already met.

Fails open per CLAUDE.md section 4: any missing field, unreadable transcript, or
parse error exits 0 with no output. A hook bug must never wedge the session.

Refs issue #1711. Refs #1704. Refs #1334. Refs #1291.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _hook_runtime import emit_decision, read_event

_SCRIPT_NAME = "stop_new_session_handoff_prompt"

# Cue substrings that mark a handoff to a fresh session (matched against the
# lowercased turn text; ja cues are unaffected by lowercasing, en cues are
# listed lowercase). Kept narrow on purpose, mirroring the conservative posture
# of gate_decision_handoff_askuserquestion.py. A cue ALONE is not enough (#1711):
# it must sit near a forward-continuation directive (HANDOFF_DIRECTIVES), so a
# turn that merely names a handoff as a topic word does not count.
HANDOFF_CUES: tuple[str, ...] = (
    "新規セッション",
    "新しいセッション",
    "別セッション",
    "別のセッション",
    "後続セッション",
    "次のセッション",
    "引き継",  # 引き継ぎ / 引き継いで / 引き継ぐ
    "new session",
    "fresh session",
    "follow-up session",
    "follow up session",
    "next session",
    "hand off",
    "handoff",
)

# A handoff cue is a real handoff only when an instruction to CARRY THE WORK
# FORWARD sits nearby (#1711). Without such a directive, a cue is just a topic
# word; an RCA of this very hook says "新規セッションのハンドオフプロンプト",
# naming the session but directing nothing. Listed lowercase (en) / verbatim
# (ja); matched against the lowercased, survey-stripped turn text. Kept to
# unambiguous forward verbs: completion- or negation-prone tokens (bare "対応",
# "残り") are deliberately excluded so a completion report is not misread as a
# directive; terminal-done (below) handles those.
HANDOFF_DIRECTIVES: tuple[str, ...] = (
    "続き",
    "続け",
    "継続",
    "引き継",
    "対応して",
    "お願い",
    "渡し",
    "退避",
    "進めて",
    "着手",
    "次の手",
    "次のステップ",
    "continue",
    "the rest",
    "parked",
    "pick up",
    "take over",
    "resume",
    "carry on",
    "carry forward",
    "next step",
    "proceed with",
    "remaining work",
)

# The maximum character gap between a handoff cue and a continuation directive
# for them to count as one handoff statement (#1711). Wide enough to span a
# natural clause ("Continue this in a new session"), narrow enough that a cue
# and an unrelated directive in different paragraphs of a long report do not pair.
PROXIMITY_WINDOW = 80

# If the turn already carries a paste-ready prompt, do not nag. A fenced code
# block is how such a prompt is normally delivered; the explicit markers cover
# a prompt delivered without a fence.
PROVIDED_MARKERS: tuple[str, ...] = (
    "```",
    "paste-ready",
    "貼り付け",
    "そのまま貼",
    "貼って",
)

# The mandatory pre-merge retro-survey gate
# (gate_handoff_retro_survey_askuserquestion.py) names its own event a "session
# handoff" / "引き継ぎサーベイ". Reporting compliance with that REQUIRED survey
# must not, by itself, trip the new-session cue (#1704): the survey compound is
# surgically removed before cue matching, so only a handoff cue OUTSIDE the
# survey vocabulary can fire. Listed lowercase (en) / verbatim (ja); matching is
# done on the lowercased turn text.
SURVEY_NEUTRALIZE: tuple[str, ...] = (
    "引き継ぎサーベイ",
    "ハンドオフサーベイ",
    "handoff survey",
    "session handoff survey",
    "session-handoff survey",
)

# A turn whose only remaining work is a human/CI terminal action; awaiting a
# GitHub-UI merge, a code-owner review, or CI; has NO agent work to hand to a
# follow-up session, so a paste-ready new-session prompt is noise (#1704).
# Presence of any cue suppresses the nag. Kept narrow and specific to the "work
# is done, waiting on a human or CI" framing so a genuine parked-work handoff is
# unaffected. Matched against the lowercased turn text (ja cues are unaffected
# by lowercasing; en cues are listed lowercase).
TERMINAL_WAIT_CUES: tuple[str, ...] = (
    "マージ直前",
    "ui 上でのマージ",
    "ui でのマージ",
    "ui でマージ",
    "マージをお任せ",
    "マージはお任せ",
    "マージはあなた",
    "オーナー承認待ち",
    "レビュー承認待ち",
    "just before merge",
    "awaiting merge",
    "await merge",
    "owner will merge",
    "owner to merge",
    "merge via the github ui",
)

# A turn that frames the WHOLE task as complete; merged and nothing left to do
#; has no agent work to hand to a follow-up session, so a paste-ready prompt is
# noise even when the turn names a handoff as a topic word (#1711). This is the
# residual case PR #1706 missed: a post-merge RCA / completion report. Cues are
# deliberately whole-task ("対応完了", "merged") rather than bare completion
# words ("完了") so that a genuine parked-work handoff which reports an unrelated
# subtask done is NOT suppressed. Matched against the lowercased turn text.
TERMINAL_DONE_CUES: tuple[str, ...] = (
    "対応完了",
    "対応は完了",
    "対応不要",
    "対応は不要",
    "作業完了",
    "作業は完了",
    "すべて完了",
    "全て完了",
    "追加対応なし",
    "追加対応は不要",
    "残作業なし",
    "残課題なし",
    "フォローアップ不要",
    "フォローアップは不要",
    "マージ済み",
    "マージ完了",
    "all done",
    "no follow-up",
    "no follow up",
    "no further action",
    "nothing to hand off",
    "no remaining work",
    "work is complete",
    "already merged",
    "has been merged",
)

_BLOCK_REASON = (
    "You ended the turn handing work off to a new / follow-up session but did "
    "not include a verbatim, paste-ready prompt for it. Emit one now, in the "
    "project owner's language and inside a fenced code block, so the operator "
    "does not have to ask. It must carry: the goal; the relevant "
    "issue / PR / branch / commit; what is already done; the next steps; and "
    "the key constraints (push-target branch lock, ASCII-only GitHub posts, "
    "owner-language output, measure-first). Do not summarize or act on it "
    "yourself; present it for the operator to copy."
)


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


def _entry_role(entry: object) -> str:
    """Return the role of a transcript entry ('user' / 'assistant' / '')."""
    if not isinstance(entry, dict):
        return ""
    message = entry.get("message")
    if isinstance(message, dict):
        role = message.get("role")
        if isinstance(role, str):
            return role
    entry_type = entry.get("type")
    return entry_type if isinstance(entry_type, str) else ""


def final_assistant_turn(entries: list[Any]) -> list[Any]:
    """Return the assistant entries that follow the last user message."""
    last_user = -1
    for idx, entry in enumerate(entries):
        if _entry_role(entry) == "user":
            last_user = idx
    return [entry for entry in entries[last_user + 1 :] if _entry_role(entry) == "assistant"]


def turn_text(turn: list[Any]) -> str:
    """Concatenate the text of every text block in *turn*."""
    parts: list[str] = []
    for entry in turn:
        for block in _content_blocks(entry):
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(parts)


def _strip_survey_vocab(lowered: str) -> str:
    """Remove retro-survey compounds so reporting the survey is not a cue."""
    for phrase in SURVEY_NEUTRALIZE:
        lowered = lowered.replace(phrase.lower(), " ")
    return lowered


def _find_all(text: str, needle: str) -> list[int]:
    """Return every start index of *needle* in *text* (overlapping-safe)."""
    out: list[int] = []
    start = 0
    while (i := text.find(needle, start)) != -1:
        out.append(i)
        start = i + 1
    return out


def _co_occurs_near(
    text: str, anchors: tuple[str, ...], partners: tuple[str, ...], window: int
) -> bool:
    """True when some *anchor* sits within *window* chars of some *partner*."""
    anchor_idx = [i for a in anchors for i in _find_all(text, a)]
    if not anchor_idx:
        return False
    partner_idx = [j for p in partners for j in _find_all(text, p)]
    return any(abs(a - p) <= window for a in anchor_idx for p in partner_idx)


def signals_handoff(text: str) -> bool:
    """True when *text* DIRECTS a handoff to a new / follow-up session.

    The mandatory pre-merge retro-survey vocabulary is stripped first (#1704)
    so merely reporting that survey does not, by itself, count as a handoff cue.
    A handoff cue must also sit near a forward-continuation directive (#1711):
    a bare topic mention with no directive (an RCA discussing this very hook)
    names a session but directs nothing, so it is not a handoff.
    """
    lowered = _strip_survey_vocab(text.lower())
    return _co_occurs_near(lowered, HANDOFF_CUES, HANDOFF_DIRECTIVES, PROXIMITY_WINDOW)


def signals_terminal_wait(text: str) -> bool:
    """True when *text*'s remaining work is a human/CI terminal wait (#1704)."""
    lowered = text.lower()
    return any(cue in lowered for cue in TERMINAL_WAIT_CUES)


def signals_terminal_done(text: str) -> bool:
    """True when *text* frames the whole task as complete; nothing to hand off (#1711)."""
    lowered = text.lower()
    return any(cue in lowered for cue in TERMINAL_DONE_CUES)


def already_provided(text: str) -> bool:
    """True when *text* already carries a paste-ready prompt."""
    lowered = text.lower()
    return any(marker in lowered for marker in PROVIDED_MARKERS)


def evaluate(event: dict[str, Any], entries: list[Any]) -> dict[str, Any] | None:
    """Return a Stop block decision, or None to let the stop proceed."""
    if event.get("hook_event_name") not in (None, "Stop"):
        return None
    if event.get("stop_hook_active"):
        return None
    turn = final_assistant_turn(entries)
    if not turn:
        return None
    text = turn_text(turn)
    # A pre-merge / human-CI terminal wait has no agent work to hand off (#1704):
    # the correct operator-facing status is "no agent work remaining", so the
    # paste-ready new-session prompt would be noise. Suppress before the cue check.
    if signals_terminal_wait(text):
        return None
    # A whole-task completion report (post-merge RCA / status) likewise has
    # nothing to hand off (#1711): suppress before the cue check so a handoff
    # mentioned only as a topic word does not trip a block.
    if signals_terminal_done(text):
        return None
    if not signals_handoff(text):
        return None
    if already_provided(text):
        return None
    return {"decision": "block", "reason": _BLOCK_REASON}


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
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def main() -> int:
    event = read_event(_SCRIPT_NAME)
    if event is None:
        return 0
    try:
        entries = load_transcript(event.get("transcript_path"))
        decision = evaluate(event, entries)
    except Exception as exc:  # fail open: never wedge the session on a hook bug
        print(f"::error::{_SCRIPT_NAME}: {exc}", file=sys.stderr)
        return 0
    emit_decision(decision, _SCRIPT_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
