#!/usr/bin/env python3
"""Client-side preflight for PR title issue references (Layer 2.5).

PreToolUse hook invoked by Claude Code on the matcher configured in
``.claude/settings.json``. Reads a PreToolUse event JSON from stdin and,
when ``mcp__github__create_pull_request`` or
``mcp__github__update_pull_request`` carries a ``title`` containing a
``(#NNN)`` issue-reference token, emits a ``permissionDecision: "deny"``
JSON on stdout that asks Claude to remove the token before retrying.

The server-side authority is ``scripts/title_policy.py``
(``pr_title_has_issue_ref``) backed by
``.github/workflows/verify-title-policy.yml`` and rooted in #167 / #214:
the PR body's ``Closes #NNN`` / ``Refs #NNN`` line, validated by
``.github/workflows/verify-issue-link.yml``, is the single source of
truth for the issue link, so the title must not duplicate it.

Architecture mirrors :mod:`preflight_non_ascii`: pure functions on top,
one thin stdin/stdout boundary at the bottom (:func:`main`). The main
function fails open on parse / shape errors so a hook bug cannot wedge
the session -- the server-side gate remains as backstop. Refs #292.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# Tools whose ``title`` field the server-side title-policy gate enforces
# the no-issue-ref rule on. Kept in sync with the matcher regex in
# ``.claude/settings.json``; the matcher is the primary gate, this set
# is defense in depth.
_TARGET_TOOLS: frozenset[str] = frozenset({
    "mcp__github__create_pull_request",
    "mcp__github__update_pull_request",
})

# Single-source of the regex shared with ``scripts/title_policy.py``
# (_PR_ISSUE_REF_RE). Kept in sync by spec: both modules look for the
# literal ``(#NNN)`` token.
_ISSUE_REF_RE = re.compile(r"\(#\d+\)")

# Collapses runs of whitespace left behind after stripping the ref token
# so the suggested fix in the deny reason reads naturally.
_WHITESPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def extract_title(tool_input: dict[str, Any]) -> str:
    """Return the ``title`` field as a string, or ``""`` if absent / wrong type.

    Mirrors :func:`preflight_non_ascii.extract_text_fields` shape so the
    two Layer 2.5 hooks behave consistently on missing payload keys.
    """
    title = tool_input.get("title") or ""
    if not isinstance(title, str):
        return ""
    return title


def find_issue_refs(title: str) -> list[str]:
    """Return every ``(#NNN)`` token in *title* in source order.

    Empty list when *title* is clean. Used both for the deny decision
    and to populate the deny reason message.
    """
    return _ISSUE_REF_RE.findall(title)


def suggest_fix(title: str) -> str:
    """Return *title* with every ``(#NNN)`` token removed.

    Adjacent whitespace is collapsed to a single space and the result is
    stripped so a title like ``"feat: foo (#1)"`` becomes ``"feat: foo"``
    rather than ``"feat: foo "``.
    """
    stripped = _ISSUE_REF_RE.sub("", title)
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def build_deny_reason(tool_name: str, title: str, refs: list[str]) -> str:
    """Return the human-readable reason text for the deny decision.

    Names every offending token, shows the canonical fix, and points at
    the server-side rule + workflow so the model gets the same context
    it would receive from a CI failure -- only earlier.
    """
    refs_csv = ", ".join(refs)
    return (
        f"Blocked by scripts/preflight_pr_title_issue_ref.py (Layer "
        f"2.5): `{tool_name}` title contains issue-reference token(s) "
        f"{refs_csv}. The server-side gate scripts/title_policy.py "
        f"(verify-title-policy.yml) rejects this per #167 / #214: the "
        f"PR body's `Closes #NNN` / `Refs #NNN` line, validated by "
        f"verify-issue-link.yml, is the single source of truth for the "
        f"issue link, so the title must not duplicate it.\n\n"
        f"Retry with the issue ref removed:\n"
        f"  Offending title: {title!r}\n"
        f"  Suggested fix:   {suggest_fix(title)!r}\n\n"
        f"If the bracketed token is intentional and not an issue "
        f"reference, reword it so it does not match the regex "
        f"\\(#\\d+\\)."
    )


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed.

    Order:
      1. Off-target tool -> allow (None).
      2. No title (missing / wrong type / empty) -> allow.
      3. Title carries no ``(#NNN)`` token -> allow.
      4. Otherwise -> deny dict naming every offending token.
    """
    if tool_name not in _TARGET_TOOLS:
        return None
    title = extract_title(tool_input)
    if not title:
        return None
    refs = find_issue_refs(title)
    if not refs:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": build_deny_reason(
                tool_name, title, refs
            ),
        }
    }


# ---------------------------------------------------------------------------
# Side-effecting boundary -- the only impure surface, monkeypatched in tests
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write decision JSON to stdout.

    Fails open per CLAUDE.md section 4: any parse error or unexpected
    payload shape emits ``::error::...`` to stderr and exits 0 with no
    decision, so a hook bug never wedges the session. The server-side
    ``verify-title-policy.yml`` workflow remains as backstop.
    """
    del argv  # not used; the harness pipes the event on stdin
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::preflight_pr_title_issue_ref: malformed "
            f"stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            "::error::preflight_pr_title_issue_ref: event missing "
            "tool_name/tool_input",
            file=sys.stderr,
        )
        return 0

    decision = decide(tool_name, tool_input)
    if decision is None:
        return 0

    sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
