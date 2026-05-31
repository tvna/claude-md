"""Shared PreToolUse/PostToolUse hook I/O runtime.

Every client-side gate under ``scripts/`` follows the same wire protocol with
the Claude Code hook harness: the event JSON arrives on stdin, and a decision
payload (or nothing) is written to stdout. Historically each gate's ``main()``
re-implemented that plumbing -- read stdin, parse JSON, emit a
``::error::<gate>: malformed stdin JSON`` line and exit 0 on a parse failure
(fail-open per CLAUDE.md section 4), then serialise the decision with
``json.dumps``. This module owns that plumbing once so each gate keeps only its
own ``decide(...)`` logic and deny-reason builders.

No decision rule lives here: deny-reason text, detection regexes,
classification, and tool-name extraction stay in the individual gates. Only the
stdin -> parse -> stdout contract moves in, byte-for-byte:

- :func:`read_event` reproduces the exact ``::error::<script>: malformed stdin
  JSON: <exc>`` stderr line and the empty-stdin -> ``{}`` behaviour.
- :func:`emit_decision` reproduces ``sys.stdout.write(json.dumps(decision))``
  and the "write nothing when the decision is ``None``" behaviour.

Both functions touch ``sys.stdin``/``sys.stdout``/``sys.stderr`` at call time so
the existing tests that monkeypatch those streams keep working unchanged.

Refs #1005.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any


def read_event(script_name: str) -> dict[str, Any] | None:
    """Read and parse the hook event JSON from stdin.

    Returns the parsed event dict on success. Empty (or whitespace-only) stdin
    yields an empty dict ``{}`` -- the same off-target pass-through the gates
    relied on. On malformed JSON the function logs

        ``::error::<script_name>: malformed stdin JSON: <exc>``

    to stderr and returns ``None`` so the caller can fail open (``return 0``).
    The ``None`` sentinel is distinct from the falsy-but-valid empty dict, so a
    caller can tell a parse failure apart from an empty event.
    """
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::{script_name}: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return None


def emit_decision(decision: Mapping[str, Any] | None) -> None:
    """Write *decision* to stdout as compact JSON, or nothing when ``None``.

    Mirrors the ``if decision is not None: sys.stdout.write(json.dumps(...))``
    tail every gate ended with -- no trailing newline, default ``json.dumps``
    separators -- so the bytes the harness reads are unchanged.
    """
    if decision is not None:
        sys.stdout.write(json.dumps(decision))
