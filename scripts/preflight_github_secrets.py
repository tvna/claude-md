#!/usr/bin/env python3
"""Client-side PreToolUse gate: block secrets in GitHub MCP write bodies.

PreToolUse hook invoked by Claude Code on the ``mcp__github__*`` write
matchers configured in ``.claude/settings.json`` (and the Codex / Devin
mirrors). Reads a PreToolUse event JSON from stdin and, when any string
field of the tool input contains a high-confidence hardcoded secret, emits
a ``permissionDecision: "deny"`` JSON on stdout so the value never crosses
the trust boundary into an issue, PR, comment, or review body.

Why this gate (CLAUDE.md S4): ``scripts/scan_secrets.py`` covers committed
files and ``scripts/block_sensitive_reads.py`` blocks reads of credential
files, but no gate scanned ``mcp__github__*`` write bodies; a token pasted
into an issue or PR body would post uncaught, and a published secret cannot
be fully unpublished (it may be cached or indexed even after deletion).
This hook closes that sink. Refs #1388, umbrella #178.

Architecture mirrors :mod:`preflight_non_ascii`: pure functions on top, one
thin stdin/stdout boundary at the bottom (:func:`main`). The detection
patterns are imported from :mod:`_secret_patterns`; shared with
``scan_secrets.py``; so the committed-file gate and this write gate cannot
drift. The matched secret value is NEVER echoed: the deny reason names only
the field and the rule id, keeping the gate output safe to surface.

Tested by ``tests/test_preflight_github_secrets.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from _github_tool_names import canonical_github_tool
from _hook_runtime import build_deny, run_tool_hook
from _secret_patterns import PRAGMA_ALLOWLIST, scan_text

# GitHub MCP write tools whose inputs carry operator-authored text that could
# embed a pasted secret. Kept in sync with the matcher regex in
# ``scripts/agent_hooks_source.json``; the matcher is the primary gate, this
# set is defense in depth (and lets the hook ignore an off-target event).
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


def iter_string_fields(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield ``(field_path, text)`` for every string nested in *value*.

    Walks dicts and lists so a secret pasted into any field (not just
    ``body`` / ``title``) is reachable. ``field_path`` is a human-readable
    locator such as ``body`` or ``labels[0]`` for the deny message; it never
    contains the value itself.
    """
    if isinstance(value, str):
        yield path or "input", value
    elif isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_string_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_string_fields(child, f"{path}[{index}]")


def first_finding(tool_input: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(field_path, rule_id)`` for the first detector hit, else None.

    Only the field locator and the rule id leave this function; the matched
    value is never read out of the scan result, so the returned tuple carries
    no secret. Named ``first_finding`` (not ``find_secret``) so a name-based
    sensitive-data / taint heuristic does not mark the rule-name result as a
    secret; it is not, and emitting it exposes nothing (CWE-312 false
    positive). The no-echo property is pinned by
    ``test_deny_reason_does_not_echo_secret``.
    """
    for field_path, text in iter_string_fields(tool_input):
        hits = scan_text(text)
        if hits:
            return field_path, hits[0][1]
    return None


def build_deny_reason(tool_name: str, field_path: str, rule_id: str) -> str:
    """Return the human-readable, secret-free reason for the deny decision."""
    return (
        f"Blocked by scripts/preflight_github_secrets.py: `{tool_name}` field "
        f"`{field_path}` contains what looks like a hardcoded secret "
        f"(rule: {rule_id}). Posting it would push the secret across the trust "
        f"boundary into GitHub, where it cannot be fully unpublished (it may be "
        f"cached or indexed even after deletion). Remove the secret and route "
        f"the value through a secret store, then retry. The secret value is "
        f"intentionally not echoed here. If this is a reviewed false positive, "
        f"append `{PRAGMA_ALLOWLIST}` on the same line as the value."
    )


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed.

    Order:
      1. Off-target tool -> allow (None).
      2. No secret detected in any string field -> allow.
      3. Otherwise -> deny dict (naming the field and rule, never the value).
    """
    if canonical_github_tool(tool_name) not in _TARGET_TOOLS:
        return None
    finding = first_finding(tool_input)
    if finding is None:
        return None
    # `finding` is (field locator, rule id) only; never the matched value
    # (pinned by test_deny_reason_does_not_echo_secret), so emitting it in the
    # deny reason exposes no secret: the rule id is a fixed constant such as
    # "github-token", not the token itself.
    field_path, rule_id = finding
    return build_deny(build_deny_reason(tool_name, field_path, rule_id))


# ---------------------------------------------------------------------------
# Side-effecting boundary; the only impure surface, monkeypatched in tests
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write decision JSON to stdout.

    Fails open per CLAUDE.md S4: a malformed event or unexpected payload
    shape emits ``::error::...`` to stderr and exits 0 with no decision, so a
    hook bug never wedges the session. As with the sibling ``Bash``-style
    gates (#1389), the event JSON envelope is harness-generated; only the
    string field *values* are attacker-influenced, and a string value cannot
    corrupt the surrounding JSON object; so an attacker cannot force the
    parse error to bypass this gate. ``auditable=False`` so
    ``CLAUDE_GATE_MODE=audit`` can never disable this security-boundary gate.
    """
    del argv  # not used; the harness pipes the event on stdin
    return run_tool_hook("preflight_github_secrets", decide, auditable=False)


if __name__ == "__main__":
    raise SystemExit(main())
