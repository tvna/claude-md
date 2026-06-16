#!/usr/bin/env python3
"""Stop hook: advise (never block) when a session's cache regime is inefficient.

Prompt caching is the dominant cost lever in Claude Code web sessions: cache
*writes* are billed at 1.25x base input, cache *reads* at 0.1x. The regime only
pays off when each written prefix is read back enough times to amortise the
write premium -- if a silent invalidator (a timestamp in the prompt prefix, a
reordered tool list, a per-turn id) breaks the prefix every turn, the session
keeps re-writing the cache and rarely reads it, paying the write premium for no
benefit. ``scripts/session_cost_structure.py`` (#1492) makes that structure
visible after the fact; this hook surfaces it *to the agent at end of turn* so a
thrashing regime is noticed in-session rather than in a post-mortem.

The signal is the **amortisation ratio** -- cache-read tokens divided by
cache-write tokens. A healthy session reads each written token back several
times: the session this gate was calibrated against measured ~5.3x
(cache_read 1.39M / cache_write 262k). The advisory floor is therefore 1.0:
below it the session is writing more cache than it ever reads back, which is the
fingerprint of a prefix that is being invalidated before it amortises (see the
silent-invalidator audit in the prompt-caching guidance). The floor is the
observed-healthy ratio rounded down to the break-even point, not an arbitrary
constant.

This gate is **advisory only and never blocks**. It mirrors the Claude-only Stop
registration of ``stop_new_session_handoff_prompt.py`` but, unlike that gate,
emits no ``decision: block`` -- it writes a single ``::warning::`` advisory to
stderr (visible in the hook log / verbose transcript) and exits 0. A caching
heuristic must never wedge a turn, and a regime warning is information, not a
gate.

Fails open per CLAUDE.md section 4: any missing field, unreadable transcript, no
cache writes yet, or parse error exits 0 with no advisory. Refs #1492.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from _hook_runtime import emit_decision, read_event
from session_cost_structure import aggregate_usages, load_transcript

_SCRIPT_NAME = "gate_cache_regime_advisor"

# Amortisation floor: cache_read / cache_write tokens. Calibrated against an
# observed healthy session (~5.3x); below 1.0 the session writes more cache than
# it reads back, the signature of a prefix invalidated before it amortises.
_MIN_AMORTIZATION_RATIO = 1.0

# Don't advise on a warm-up: a session with only a handful of cache-write tokens
# has not had a chance to read anything back yet, so its ratio is meaningless.
_MIN_WRITE_TOKENS = 50_000


def amortization_advice(read_tokens: int, write_tokens: int) -> str | None:
    """Return advisory text when the cache regime is under-amortised, else None.

    ``None`` when there are too few cache writes to judge (warm-up) or when the
    read/write ratio meets the floor. The returned text is ASCII so it is safe
    in any log sink.
    """
    if write_tokens < _MIN_WRITE_TOKENS:
        return None
    ratio = read_tokens / write_tokens if write_tokens else 0.0
    if ratio >= _MIN_AMORTIZATION_RATIO:
        return None
    return (
        f"cache regime advisory: cache-read/write token ratio is {ratio:.2f} "
        f"(read {read_tokens:,} / write {write_tokens:,}), below the {_MIN_AMORTIZATION_RATIO:.1f} "
        "amortisation floor. The session is writing more cache than it reads back "
        "-- check for a silent prefix invalidator (a timestamp, id, or reordered "
        "tool list in the cached prefix). Run scripts/session_cost_structure.py "
        "for the full breakdown."
    )


def evaluate(event: dict[str, Any]) -> str | None:
    """Return advisory text for a Stop *event*, or None to stay silent."""
    if event.get("hook_event_name") not in (None, "Stop"):
        return None
    if event.get("stop_hook_active"):
        return None
    transcript_path = event.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    entries = load_transcript(Path(transcript_path))
    tokens = aggregate_usages(entries)
    write_tokens = tokens.cache_write_5m + tokens.cache_write_1h
    return amortization_advice(tokens.cache_read, write_tokens)


def main() -> int:
    event = read_event(_SCRIPT_NAME)
    if event is None:
        return 0
    try:
        advice = evaluate(event)
    except Exception as exc:  # fail open: never wedge the session on a hook bug
        print(f"::error::{_SCRIPT_NAME}: {exc}", file=sys.stderr)
        return 0
    if advice is not None:
        print(f"::warning::{_SCRIPT_NAME}: {advice}", file=sys.stderr)
    # Advisory only: never emit a blocking decision.
    emit_decision(None, _SCRIPT_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
