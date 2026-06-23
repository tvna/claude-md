#!/usr/bin/env python3
"""Client-side preflight that blocks MCP-write bodies with bare <...> tokens.

PreToolUse hook invoked by Claude Code on the matchers configured in
``.claude/settings.json``. Reads a PreToolUse event JSON from stdin and, when a
GitHub MCP write tool's ``title`` or ``body`` carries a bare angle-bracket
placeholder token (e.g. ``<sha>``, ``<issue-number>``), emits a
``permissionDecision: "deny"`` JSON on stdout so the author fixes the body
BEFORE the write.

Why a forward-looking gate: the GitHub MCP write tools corrupt
angle-bracket-delimited tokens on write; dropping them entirely or
HTML-encoding them; even inside backticks (observed in retro #1593 R2; see
``body_policy.detect_dropped_angle_tokens`` / ``normalize_pr_body``). The
existing detector diffs an authored body against the stored body, but that only
runs PostToolUse, after the corruption has shipped. This hook runs PreToolUse,
where only the authored body exists, so :func:`find_angle_tokens` scans that
body with the same ``body_policy._ANGLE_TOKEN_RE`` the diff detector uses to
detect the at-risk tokens up front and reject loudly (CLAUDE.md section 4: fail
loudly, no silent
default). Auto-rewrite is deliberately NOT done: stripping the angle brackets
(``<sha>`` -> ``sha``) changes author intent, and the concrete value the
placeholder stands for is known only to the author.

Architecture mirrors :mod:`preflight_non_ascii`: pure functions on top, a single
stdin/stdout boundary at the bottom (:func:`main`). The detection regex lives in
:mod:`body_policy` so this client-side gate and the post-write detector cannot
drift.

Failure modes (fail-open): off-target tool name, body/title absent or
non-string, malformed stdin JSON, ``tool_input`` shape invalid; exit 0 with no
output. A hook bug must never wedge unrelated tool calls.

Refs #1673, #1593 (R2).
"""

from __future__ import annotations

from typing import Any

from _github_tool_names import canonical_github_tool
from _hook_runtime import build_deny, run_tool_hook

# Reuse the single-source detection regex from body_policy (same pattern its
# post-write diff detect_dropped_angle_tokens uses) so the predictive preflight
# and the post-write diff cannot drift. The private import mirrors
# post_pr_create_body_fix importing _AGENT_ATTRIBUTION_FOOTER_RE from the same
# module. The function lives here rather than in body_policy because that module
# is at its line-size budget (scripts/preflight_all.py module-size gate).
from body_policy import _ANGLE_TOKEN_RE
from issue_link import strip_html_comments

# Tools whose inputs carry author-written prose (title/body) that the MCP write
# tools would corrupt. Kept in sync with the matcher regex in
# ``.claude/settings.json``; the matcher is the primary gate, this set is
# defense in depth. Codex connector names are folded onto these via
# :func:`canonical_github_tool` so a Codex-shaped write is gated too.
_TARGET_TOOLS: frozenset[str] = frozenset({
    "mcp__github__issue_write",
    "mcp__github__add_issue_comment",
    "mcp__github__create_pull_request",
    "mcp__github__update_pull_request",
    "mcp__github__add_reply_to_pull_request_comment",
    "mcp__github__pull_request_review_write",
    "mcp__github__add_comment_to_pending_review",
    "mcp__github__sub_issue_write",
})


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def find_angle_tokens(text: str) -> list[str]:
    """Return distinct ``<...>`` tokens in *text* at risk of MCP-write drop.

    The GitHub MCP write tools corrupt angle-bracket-delimited tokens on write
   ; dropping them entirely (e.g. the ``<sha>`` in ``git revert <sha>``,
    observed in retro #1593 R2) or HTML-encoding them; even when the token is
    wrapped in backticks (see ``tests/test_body_policy.py`` ``test_detects_dropped_token``,
    where a backtick-wrapped ``<sha>`` is still lost). A PreToolUse gate has only
    the outgoing/authored body, with no stored body yet to diff against, so this
    scans a single body (or title) and returns each distinct token in document
    order so a loud reject can name them.

    HTML comments are stripped first (via :func:`strip_html_comments`) so the
    established ``<!-- ... -->`` markers (e.g. the ``<!-- non-ascii-ack -->``
    opt-out) are not flagged. Refs #1673, #1593 (R2).
    """
    cleaned = strip_html_comments(text.replace("\r", ""))
    seen: set[str] = set()
    out: list[str] = []
    for token in _ANGLE_TOKEN_RE.findall(cleaned):
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def extract_text_fields(tool_input: dict[str, Any]) -> tuple[str, str]:
    """Return ``(title, body)`` from a tool input payload.

    Missing or non-string fields collapse to ``""`` so downstream detection
    sees a uniform shape regardless of which write tool fired.
    """
    title = tool_input.get("title") or ""
    body = tool_input.get("body") or ""
    if not isinstance(title, str):
        title = ""
    if not isinstance(body, str):
        body = ""
    return title, body


def offending_tokens(title: str, body: str) -> dict[str, list[str]]:
    """Return ``{field: tokens}`` for fields carrying bare ``<...>`` tokens.

    Only fields with at least one token are included; a clean field is
    omitted, so an empty dict means the input is clean.
    """
    out: dict[str, list[str]] = {}
    for field, text in (("title", title), ("body", body)):
        if not text:
            continue
        tokens = find_angle_tokens(text)
        if tokens:
            out[field] = tokens
    return out


def build_deny_reason(tool_name: str, offending: dict[str, list[str]]) -> str:
    """Return the human-readable reason text for the deny decision.

    Names which fields carry tokens, lists the tokens verbatim, and explains
    the only safe remediation (replace with the concrete value or remove the
    angle brackets; NOT backticks, which do not protect the token).
    """
    where = " and ".join(offending)
    listed = "; ".join(
        f"{field}: {', '.join(tokens)}" for field, tokens in offending.items()
    )
    return (
        f"Blocked by scripts/preflight_angle_token_drop.py: `{tool_name}` "
        f"{where} contains bare angle-bracket placeholder token(s) that the "
        f"GitHub MCP write tools corrupt on write (dropped entirely or "
        f"HTML-encoded, even inside backticks). Offending tokens -> {listed}.\n"
        f"Fix before retrying: replace each placeholder with the concrete "
        f"value it stands for, or remove the angle brackets. Wrapping the "
        f"token in backticks does NOT protect it (the token is still dropped). "
        f"If the angle brackets are an intentional HTML comment, use the "
        f"`<!-- ... -->` form, which is exempt."
    )


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed.

    Order:
      1. Off-target tool -> allow (None).
      2. No bare angle-bracket tokens detected -> allow.
      3. Otherwise -> deny dict.
    """
    if canonical_github_tool(tool_name) not in _TARGET_TOOLS:
        return None
    title, body = extract_text_fields(tool_input)
    offending = offending_tokens(title, body)
    if not offending:
        return None
    return build_deny(build_deny_reason(tool_name, offending))


# ---------------------------------------------------------------------------
# Side-effecting boundary; the only impure surface, monkeypatched in tests
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write decision JSON to stdout.

    Fails open per CLAUDE.md section 4: any parse error or unexpected payload
    shape emits ``::error::...`` to stderr and exits 0 with no decision, so a
    hook bug never wedges the session. The PostToolUse detector
    (``post_pr_create_body_fix.py``) remains as backstop.
    """
    del argv  # not used; the harness pipes the event on stdin
    return run_tool_hook("preflight_angle_token_drop", decide)


if __name__ == "__main__":
    raise SystemExit(main())
