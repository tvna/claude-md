"""Canonical mapping for GitHub MCP write tool names across agents.

Claude Code exposes GitHub write operations as ``mcp__github__<tool>``.
The Codex GitHub connector exposes the same operations under a different
naming shape, ``mcp__codex_apps__github._<tool>`` (note the ``codex_apps``
segment, the ``github.`` dot separator, and the leading underscore on the
verb). The client-side preflight hooks classify a call by its Claude-style
tool name, so connector names must be folded back onto that form before
the ``_TARGET_TOOLS`` membership checks run -- otherwise a Codex-shaped
PR/issue write slips past the preflight and is only caught after it has
already reached GitHub. Refs #740.

The mapping is intentionally explicit (no pattern rewriting): only the
connector tools whose Claude equivalent a preflight already gates are
listed, and any unknown name passes through unchanged so the hooks keep
their fail-open behavior (CLAUDE.md section 4) -- a name we do not
recognize is left alone for the server-side gate to handle.
"""

from __future__ import annotations

# Codex GitHub connector tool name -> Claude-style canonical tool name.
# Each entry mirrors an operation the client-side preflights already gate on
# the Claude side; keep this in sync with the connector matcher groups in
# ``.codex/hooks.json`` and ``.claude/settings.json``.
CODEX_GITHUB_TOOL_ALIASES: dict[str, str] = {
    "mcp__codex_apps__github._create_pull_request": "mcp__github__create_pull_request",
    "mcp__codex_apps__github._update_pull_request": "mcp__github__update_pull_request",
    "mcp__codex_apps__github._create_issue": "mcp__github__issue_write",
}


def canonical_github_tool(tool_name: str) -> str:
    """Return the Claude-style tool name for *tool_name*.

    Maps a known Codex GitHub connector name onto its Claude equivalent so
    the preflight ``_TARGET_TOOLS`` checks see one shape regardless of which
    agent fired the call. Any name that is not a recognized connector alias
    (including all native ``mcp__github__*`` names) is returned unchanged.
    """
    return CODEX_GITHUB_TOOL_ALIASES.get(tool_name, tool_name)
