#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block PR bodies that would fail the shape gate.

Bound in ``.claude/settings.json`` to
``mcp__github__(create_pull_request|update_pull_request)``. Reads the
PreToolUse event JSON from stdin and, when the PR body would fail the
post-2026-05-26 Verification + Checklist + agent-attribution footer
shape check enforced by ``scripts/body_policy.py``, emits a
``permissionDecision: "deny"`` JSON on stdout so the operator can fix
the body BEFORE the API call instead of round-tripping through
``verify-body-policy.yml``.

Architecture mirrors :mod:`pr_body_close_keyword_gate` and
:mod:`preflight_non_ascii`: pure decision function on top, a single
stdin/stdout boundary at the bottom (:func:`main`). The shape regexes
and required-subsection list are imported from :mod:`body_policy` so
the hook and the server gate cannot drift.

Failure modes (fail-open):

* off-target tool name, body absent or non-string, malformed stdin
  JSON, ``tool_input`` shape invalid -- exit 0 with no output. A hook
  bug must never wedge unrelated tool calls; the server gate
  (``verify-body-policy.yml``) remains as backstop.

The hook deliberately ignores the cutoff env var (``BODY_POLICY_SHAPE_CUTOFF``):
any new PR opened through MCP is expected to follow the new shape,
since the cutoff exists only to exempt the back-catalog at the server.
"""

from __future__ import annotations

import os
from typing import Any

from _github_tool_names import canonical_github_tool
from _hook_runtime import build_deny, run_tool_hook
from body_policy import (
    verify_pr_agent_attribution_footer,
    verify_pr_allowed_sections,
    verify_pr_checklist_subsections,
    verify_pr_verification_pairs,
)

_TARGET_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request",
    }
)

# Refs #1025. The remote Claude web harness (CLAUDE_CODE_REMOTE=true, the
# same signal preflight_push_session_branch.py keys off) auto-appends
# exactly one session footer when a PR is *created* via MCP. Only the
# create path is auto-appended -- update_pull_request is not (that is how
# the manual single-footer repair worked), so the footer relaxation below
# is deliberately create-only. Under those two conditions the agent must
# NOT pre-add a footer (the harness supplies it); any other invocation
# keeps requiring exactly one trailing footer.
#
# Discriminator note: CLAUDECODE=1 is set under BOTH the local Claude CLI
# and the remote web harness, so it cannot tell them apart. Only
# CLAUDE_CODE_REMOTE=true is remote-only, and only the remote harness
# auto-appends, so it is the correct (and sole) signal here. The local
# CLI leaves CLAUDE_CODE_REMOTE unset and keeps requiring a footer.
_REMOTE_ENV_VAR = "CLAUDE_CODE_REMOTE"
_HARNESS_FOOTER_APPEND_TOOL = "mcp__github__create_pull_request"


def _claude_web_harness(environ: dict[str, str] | None = None) -> bool:
    """Return True when running under the remote Claude web harness."""
    env = os.environ if environ is None else environ
    return env.get(_REMOTE_ENV_VAR, "").strip().lower() == "true"


def evaluate(body: str, *, harness_appends_footer: bool = False) -> list[str]:
    """Return list of ``::error::`` strings; empty list means OK."""
    return (
        verify_pr_verification_pairs(body)
        + verify_pr_checklist_subsections(body)
        + verify_pr_allowed_sections(body)
        + verify_pr_agent_attribution_footer(
            body, harness_appends_footer=harness_appends_footer
        )
    )


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed."""
    canonical = canonical_github_tool(tool_name)
    if canonical not in _TARGET_TOOLS:
        return None
    body = tool_input.get("body")
    if not isinstance(body, str):
        return None
    harness_appends_footer = (
        canonical == _HARNESS_FOOTER_APPEND_TOOL
        and _claude_web_harness(environ)
    )
    errors = evaluate(body, harness_appends_footer=harness_appends_footer)
    if not errors:
        return None
    joined = "\n".join(errors)
    reason = (
        f"Blocked by scripts/preflight_pr_template_shape.py (client-side "
        f"mirror of verify-body-policy.yml shape gate): `{tool_name}` "
        f"would fail server-side.\n\n{joined}\n\nFix the PR body to use "
        "the post-2026-05-26 shape: see "
        "docs/standards/issue-pr-body-standard.md and "
        ".github/PULL_REQUEST_TEMPLATE.md."
    )
    return build_deny(reason)


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_tool_hook("preflight_pr_template_shape", decide)


if __name__ == "__main__":
    raise SystemExit(main())
