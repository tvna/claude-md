#!/usr/bin/env python3
"""PreToolUse gate: allow mcp__github__resolve_review_thread.

``resolve_review_thread`` marks a PR review thread as resolved on GitHub.
It is a write operation but low blast-radius and reversible
(``mcp__github__unresolve_review_thread`` undoes it). No text content is
written and no notifications beyond the existing thread are triggered, so
no ASCII, secrets, or body-policy checks are required.

This gate exists to satisfy the ``gate_mcp_github_uncovered`` requirement
that every ``mcp__github__`` write tool has a dedicated PreToolUse hook
before it can be called. It performs no additional checks and passes
through unconditionally.

Wiring:
  PreToolUse matcher ``mcp__github__resolve_review_thread`` in
  ``.claude/settings.json``. Also listed in ``HOOK_COVERED_TOOLS`` in
  ``gate_mcp_github_uncovered.py`` so the catch-all passes it through
  to this dedicated gate.

Refs #887, #1932.
"""

from __future__ import annotations

import sys

from _hook_runtime import emit_decision, read_event

_SCRIPT_NAME = "preflight_resolve_review_thread"


def main() -> int:
    event = read_event(_SCRIPT_NAME)
    if event is None:
        return 0
    try:
        emit_decision(None, _SCRIPT_NAME)
    except Exception as exc:
        print(f"::error::{_SCRIPT_NAME}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
