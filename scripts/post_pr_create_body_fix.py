#!/usr/bin/env python3
"""PostToolUse hook: fix PR body corruption after mcp__github__create_pull_request.

mcp__github__create_pull_request has three defects that corrupt the stored body:
  1. HTML-encodes characters before storing (& -> &amp;, " -> &#34;,
     > -> &gt;, < -> &lt;).
  2. Drops angle-bracket tokens (e.g. the <sha> in `git revert <sha>`)
     entirely; this is content loss, not encoding.
  3. Appends a duplicate footer even when one already exists.

This hook normalizes the authored body deterministically via
``body_policy.normalize_pr_body`` (reversing defects 1 and 3) and emits
additionalContext instructing the agent to call
mcp__github__update_pull_request with that normalized body. Defect 2 is
unrecoverable from the stored body, so the hook compares the authored body
against the stored body and warns about each dropped <...> token so the
agent can rephrase (e.g. wrap it in backticks) rather than ship missing
content.

Footer carry-forward (Refs #1427, #1441): under the remote web harness
(``CLAUDE_CODE_REMOTE=true``) the create call auto-appends one session
footer to the *stored* body, but the agent's authored body carries none
(``preflight_pr_template_shape`` relaxes the footer on the create path
only). The mandated fix-up ``update_pull_request`` is NOT auto-appended and
its footer gate still requires one, so resending the footerless normalized
body would be denied.

The original carry-forward (#1427) lifted the footer out of the *stored*
body in ``tool_response``. That is inert under the web harness: the
``create_pull_request`` MCP response was observed to be ``{id, url}`` only,
with no ``body`` field (#1439), so there is nothing to lift. This hook
therefore reconstructs the canonical session footer from the harness session
id (``CLAUDE_CODE_REMOTE_SESSION_ID``; the harness footer URL is
``https://claude.ai/code/session_<token>`` where ``<token>`` is that env var
with its ``cse_`` prefix stripped) instead of depending on ``tool_response``.
The stored-body footer remains a secondary source for when one is actually
present there (e.g. a response shape that does echo the body). Outside the
web harness (local CLI, ``CLAUDE_CODE_REMOTE`` unset) no footer is
fabricated; the local path keeps requiring a manually authored footer. The
footer is appended only when the normalized body lacks a trailing footer, so
no duplicate is produced, and without relying on PreToolUse ``updatedInput``
(unreliable under the multiple-hook PR matcher; see
docs/runbooks/rtk-hook-verification.md).

Fail-open: malformed input, missing fields, or off-target tools exit 0 with
no output so a hook bug cannot wedge unrelated tool calls.

Refs: issue #892, #1361 (R1), #1427, #1441.
"""

from __future__ import annotations

import html
import os
import re
from collections.abc import Mapping
from typing import Any

from _hook_runtime import emit_decision, read_event

# Import the footer regex from body_policy (rather than recompiling it here)
# so the carry-forward detection and the reconstructed footer (#1441) cannot
# drift from the gate that enforces the footer. Refs #1427, #1441.
from body_policy import (
    _AGENT_ATTRIBUTION_FOOTER_RE,
    detect_dropped_angle_tokens,
    normalize_pr_body,
)

TARGET_TOOL = "mcp__github__create_pull_request"

# Refs #1441. The remote web harness signals itself with CLAUDE_CODE_REMOTE=true
# (the same env var preflight_push_session_branch.py and
# preflight_pr_template_shape.py key off) and exposes its session id as
# CLAUDE_CODE_REMOTE_SESSION_ID=cse_<token>. The footer URL the harness appends
# is https://claude.ai/code/session_<token>, i.e. the prefix below plus the
# token with its cse_ prefix stripped (observed in env, not the unrelated
# CLAUDE_CODE_SESSION_ID UUID that issue #1441 named).
_REMOTE_ENV_VAR = "CLAUDE_CODE_REMOTE"
_REMOTE_SESSION_ID_VAR = "CLAUDE_CODE_REMOTE_SESSION_ID"
_CSE_PREFIX = "cse_"
_SESSION_URL_PREFIX = "https://claude.ai/code/session_"
_AGENT_NAME = "Claude Code"


def build_harness_session_footer(env: Mapping[str, str]) -> str | None:
    """Return the agent footer the web harness auto-appends, or None.

    Reconstructs the footer deterministically from the harness session id so
    the mandated ``update_pull_request`` body carries it even when the create
    MCP response omits the stored body (the ``{id, url}``-only shape observed
    on #1439). Returns None when not under the remote web harness
    (``CLAUDE_CODE_REMOTE`` not truthy); so the local CLI never has a footer
    fabricated for it; and None when the session id is absent or empty; so
    a malformed ``.../session_`` URL is never produced.

    The constructed line is asserted against ``_AGENT_ATTRIBUTION_FOOTER_RE``
    (the very regex ``body_policy.verify_pr_agent_attribution_footer`` uses) so
    the reconstruction cannot drift from the gate that enforces the footer;
    any mismatch returns None rather than emitting a footer the gate rejects.
    """
    if env.get(_REMOTE_ENV_VAR, "").strip().lower() != "true":
        return None
    raw = env.get(_REMOTE_SESSION_ID_VAR, "").strip()
    if not raw:
        return None
    token = raw[len(_CSE_PREFIX):] if raw.startswith(_CSE_PREFIX) else raw
    if not token:
        return None
    footer = f"_Generated by [{_AGENT_NAME}]({_SESSION_URL_PREFIX}{token})_"
    if not _AGENT_ATTRIBUTION_FOOTER_RE.fullmatch(footer):
        return None
    return footer


def has_trailing_agent_footer(body: str) -> bool:
    """Return True when *body*'s last non-empty line is an agent footer."""
    lines = body.replace("\r", "").rstrip().splitlines()
    return bool(lines and _AGENT_ATTRIBUTION_FOOTER_RE.fullmatch(lines[-1].strip()))


def extract_trailing_agent_footer(body: str) -> str | None:
    """Return the last agent-attribution footer line in *body*, or None.

    HTML entities are unescaped first so a footer the MCP write tool stored
    as ``&amp;`` is returned in authored form; the *last* match is returned
    because the remote web harness appends its session footer last.
    """
    found: str | None = None
    for line in html.unescape(body.replace("\r", "")).splitlines():
        stripped = line.strip()
        if _AGENT_ATTRIBUTION_FOOTER_RE.fullmatch(stripped):
            found = stripped
    return found

_PR_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)")
_NUMBER_KEYS = frozenset({"number", "pullRequestNumber", "pull_request_number", "pr_number"})
_MAX_BODY_PREVIEW = 4000  # characters; truncated beyond this to avoid excessive context


def _walk(value: Any) -> list[Any]:
    out: list[Any] = []
    stack = [value]
    while stack and len(out) < 200:
        node = stack.pop()
        out.append(node)
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def extract_pr_coords(
    tool_input: dict[str, Any], tool_response: Any
) -> tuple[str | None, str | None, str | None]:
    """Return (owner, repo, pr_number) from event fields.

    Prefers a PR URL in tool_response (most reliable); falls back to
    structured number fields combined with owner/repo from tool_input.
    """
    for node in _walk(tool_response):
        if isinstance(node, str):
            m = _PR_URL_RE.search(node)
            if m:
                return m.group(1), m.group(2), m.group(3)

    owner = tool_input.get("owner") if isinstance(tool_input, dict) else None
    repo = tool_input.get("repo") if isinstance(tool_input, dict) else None

    for node in _walk(tool_response):
        if not isinstance(node, dict):
            continue
        for key in _NUMBER_KEYS:
            val = node.get(key)
            if isinstance(val, int) and val > 0:
                return owner, repo, str(val)
            if isinstance(val, str) and val.isdecimal():
                return owner, repo, val

    return None, None, None


def extract_stored_body(tool_response: Any) -> str | None:
    """Return the stored PR body from a create_pull_request response, or None.

    The MCP response echoes the created PR object; its ``body`` field holds
    the corrupted, stored body. Returns the first string ``body`` value
    found while walking the response, so the hook can diff it against the
    authored body to detect dropped ``<...>`` tokens.
    """
    for node in _walk(tool_response):
        if isinstance(node, dict):
            val = node.get("body")
            if isinstance(val, str):
                return val
    return None


def _build_context(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return hook output for a PostToolUse event, or None if no action needed."""
    if event.get("tool_name") != TARGET_TOOL:
        return None

    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response")

    body = tool_input.get("body") if isinstance(tool_input, dict) else None
    if not isinstance(body, str) or not body.strip():
        return _build_context(
            "PR body fix skipped: original authored body not found in tool_input. "
            "Verify the stored PR body for HTML-entity encoding (&amp;/&#34;/&gt;), "
            "dropped <...> tokens, and a duplicate footer; call "
            "mcp__github__update_pull_request to rewrite if any defect is present."
        )

    owner, repo, pr_number = extract_pr_coords(tool_input, tool_response)
    if pr_number is None:
        return _build_context(
            "PR body fix skipped: could not extract PR number from tool response. "
            "Verify the stored PR body for HTML-entity encoding (&amp;/&#34;/&gt;), "
            "dropped <...> tokens, and a duplicate footer; call "
            "mcp__github__update_pull_request to rewrite if any defect is present."
        )

    pr_label = f"{owner}/{repo}#{pr_number}" if owner and repo else f"PR #{pr_number}"
    normalized = normalize_pr_body(body)

    stored = extract_stored_body(tool_response)
    # Refs #1427, #1441: ensure the mandated update_pull_request (whose footer
    # gate is NOT relaxed) is not denied for a missing footer. Append only when
    # the normalized body lacks one, so no duplicate is produced. Reconstruct
    # the harness session footer from the session id (the create MCP response
    # omits the body under the web harness, #1439, so lifting it from the
    # stored body is inert); fall back to the stored-body footer when one is
    # actually present there, and to nothing outside the harness so the local
    # CLI is never given a fabricated footer.
    if not has_trailing_agent_footer(normalized):
        carried_footer = build_harness_session_footer(os.environ)
        if carried_footer is None and stored is not None:
            carried_footer = extract_trailing_agent_footer(stored)
        if carried_footer is not None:
            normalized = f"{normalized.rstrip()}\n\n{carried_footer}"

    body_repr = (
        normalized if len(normalized) <= _MAX_BODY_PREVIEW
        else normalized[:_MAX_BODY_PREVIEW] + "\n…(truncated)"
    )

    dropped = detect_dropped_angle_tokens(body, stored) if stored is not None else []
    warning = ""
    if dropped:
        tokens = ", ".join(dropped)
        warning = (
            f"\n\nWARNING: the stored body dropped these angle-bracket tokens "
            f"(content loss, not recoverable by re-encoding): {tokens}. The "
            f"normalized body above keeps them, but the MCP tool will drop them "
            f"again on update; rephrase each (e.g. wrap in backticks) so it "
            f"survives, then verify the stored body."
        )

    return _build_context(
        f"MANDATORY BODY FIX: mcp__github__create_pull_request corrupts stored PR "
        f"bodies (HTML-encodes &/\"/>, drops <...> tokens, and appends a duplicate "
        f"footer). The normalized body below was computed deterministically "
        f"(body_policy.normalize_pr_body). Call mcp__github__update_pull_request for "
        f"{pr_label} with it before taking any other action. "
        f"owner={owner or '(see tool_input)'}, repo={repo or '(see tool_input)'}, "
        f"pullNumber={pr_number}.{warning}\n\n"
        f"--- NORMALIZED BODY ---\n{body_repr}\n--- END BODY ---"
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    event = read_event("post_pr_create_body_fix")
    if event is None:
        return 0
    if not isinstance(event, dict):
        return 0
    emit_decision(decide(event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
