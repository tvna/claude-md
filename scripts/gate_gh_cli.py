#!/usr/bin/env python3
"""PreToolUse gate: block direct ``gh`` CLI and raw ``curl api.github.com`` calls.

Registered as a ``PreToolUse`` hook for the ``Bash`` matcher in
``.claude/settings.json``. Inspects every Bash command and denies:

- ``gh`` CLI invocations (any ``gh <subcommand>`` call).
- Direct ``curl`` calls to ``https://api.github.com/``.

Both surfaces bypass the MCP PreToolUse content-safety gates. The approved
alternatives are:

- **Read operations**: ``python3 scripts/github_api.py METHOD URL [--fields ...]``
  (reduces token consumption via response filtering).
- **Write operations**: use the appropriate ``mcp__github__*`` tool, which has
  a paired PreToolUse hook gate.

Fails open per CLAUDE.md section 4: parse errors log to stderr and exit 0
so a hook bug never wedges the session.

Refs #887.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# Matches: gh followed by a subcommand word at a word boundary,
# possibly preceded by whitespace, semicolon, pipe, or ampersand.
# Does NOT match paths like /usr/bin/gh or strings like "github".
_GH_CLI_RE = re.compile(
    r"(?:^|(?<=[\s;|&(]))gh\s+"
    r"(?:api|auth|browse|codespace|co|gist|gpg-key|issue|label|org|pr|"
    r"project|release|repo|ruleset|run|search|secret|ssh-key|status|variable|workflow)\b"
)

# Matches direct curl calls to the GitHub REST API.
_CURL_GITHUB_API_RE = re.compile(
    r"\bcurl\b[^\n]*https?://api\.github\.com/"
)

_APPROVED_PATH = "scripts/github_api.py"


def decide(tool_name: str, command: str) -> dict[str, Any] | None:
    """Return a deny decision if the command uses a prohibited GitHub path.

    Returns None to pass through if:
    - tool is not Bash
    - command does not invoke ``gh`` CLI or ``curl api.github.com``

    Returns a ``permissionDecision: "deny"`` dict otherwise.
    """
    if tool_name != "Bash":
        return None

    if _GH_CLI_RE.search(command):
        return {
            "permissionDecision": "deny",
            "decisionReason": (
                "Direct `gh` CLI calls are prohibited (no content-safety gate on writes; "
                "token overhead on reads).\n\n"
                "For READ operations, use:\n"
                f"  python3 {_APPROVED_PATH} GET https://api.github.com/... [--fields f1,f2]\n\n"
                "For WRITE operations, use the appropriate `mcp__github__*` tool "
                "(each write tool has a paired PreToolUse hook gate)."
            ),
        }

    if _CURL_GITHUB_API_RE.search(command):
        return {
            "permissionDecision": "deny",
            "decisionReason": (
                "Direct `curl api.github.com` calls are prohibited; "
                "use the approved wrapper instead:\n\n"
                f"  python3 {_APPROVED_PATH} GET https://api.github.com/... [--fields f1,f2]\n\n"
                "The wrapper handles auth, retry logic, and response filtering."
            ),
        }

    return None


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write deny decision to stdout if needed."""
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::gate_gh_cli: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str):
        print(
            "::error::gate_gh_cli: event missing tool_name",
            file=sys.stderr,
        )
        return 0

    command = str((event.get("tool_input") or {}).get("command") or "")
    decision = decide(tool_name, command)
    if decision is not None:
        sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
