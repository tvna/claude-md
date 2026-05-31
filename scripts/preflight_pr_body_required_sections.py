#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block PR bodies missing ``_PR_REQUIRED`` sections.

Bound in ``.claude/settings.json`` to
``mcp__github__(create_pull_request|update_pull_request)``. Reads the
PreToolUse event JSON from stdin and, when the drafted PR body would
fail the baseline H2/H3 heading existence check enforced by
``scripts/body_policy.py`` (the ``_PR_REQUIRED`` tuple: Facts /
Assumptions / Risk and blast radius / Rollback / Verification /
Checklist), emits a ``permissionDecision: "deny"`` JSON on stdout so
the operator can add the missing sections BEFORE the API call instead
of round-tripping through ``verify-body-policy.yml``.

Issue #382 motivation: a body that violates ``_PR_REQUIRED`` is only
caught after ``mcp__github__create_pull_request`` fires today; the
operator must then edit the body, which re-triggers every ``gate``
workflow on ``pull_request: edited``. Retro #356 row 1 records PR #355
running three trigger waves (13:04 / 13:07 / 13:10) on a single head
SHA because the initial body lacked the required sections. This
client-side mirror short-circuits that loop.

Architecture mirrors :mod:`preflight_pr_template_shape` (its sibling
that covers the post-2026-05-26 Verification command/result + Checklist
H3 subsection shape gate): pure decision function on top, a single
stdin/stdout boundary at the bottom (:func:`main`). The required-section
tuple is fetched via :func:`body_policy.required_sections` rather than
imported as ``_PR_REQUIRED`` so this hook and the server gate share the
same dispatch logic.

The two body-side preflights are complementary:

* This module covers the *baseline* H2/H3 heading existence check
  (`body_policy._verify` first branch, ``missing_sections``).
* :mod:`preflight_pr_template_shape` covers the *shape* check within
  the Verification and Checklist sections.

Failure modes (fail-open per CLAUDE.md section 4):

* off-target tool name, ``body`` absent or non-string, malformed stdin
  JSON, ``tool_input`` shape invalid -- exit 0 with no output. A hook
  bug must never wedge unrelated tool calls; the server gate
  (``verify-body-policy.yml``) remains as backstop.

The empty-string body (``"body": ""``) is treated as "all required
sections missing" and produces a deny that lists every entry of
``_PR_REQUIRED`` -- this matches the server gate, which would reject
the same empty body on opening the PR.

The hook deliberately ignores ``BODY_POLICY_CUTOFF``: any new PR opened
through MCP is expected to satisfy the current required-section list,
since the cutoff exists only to exempt the back-catalog at the server.
"""

from __future__ import annotations

import sys
from typing import Any

from _github_tool_names import canonical_github_tool
from _hook_runtime import emit_decision, read_event
from body_policy import (
    extract_headings,
    missing_sections,
    required_sections,
)

_TARGET_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request",
    }
)


def evaluate(body: str) -> list[str]:
    """Return list of missing ``_PR_REQUIRED`` section names; empty list means OK.

    Delegates to :func:`body_policy.required_sections` (with
    ``kind="pull_request"``) and :func:`body_policy.missing_sections`
    so this hook and the server gate share the same matching rules:
    case-sensitive heading text with ``&`` and ``and`` treated as
    interchangeable (see ``body_policy._normalize_heading``).
    """
    required = required_sections("pull_request", body=body)
    headings = extract_headings(body)
    return missing_sections(required, headings)


def build_deny_reason(tool_name: str, missing: list[str]) -> str:
    """Return the ASCII deny-reason text for a body missing required sections.

    Names every missing section so a single retry can fix them in one
    pass (rather than the body-edit feedback loop the issue documents).
    Cites the server-side authority so the agent gets the same
    remediation context it would get from a CI failure.
    """
    missing_csv = ", ".join(missing)
    return (
        f"Blocked by scripts/preflight_pr_body_required_sections.py "
        f"(client-side mirror of verify-body-policy.yml baseline gate): "
        f"`{tool_name}` body is missing required section(s): "
        f"{missing_csv}. The server-side gate scripts/body_policy.py "
        f"(verify-body-policy.yml) would reject this on `pull_request: "
        f"opened` and again on every `edited` event until fixed -- "
        f"adding the missing heading(s) before the API call avoids the "
        f"retrigger loop documented in retro #356.\n\n"
        f"Add an H2 (`## <name>`) or H3 (`### <name>`) heading for each "
        f"missing entry above. See .github/PULL_REQUEST_TEMPLATE.md for "
        f"the canonical shape and docs/standards/issue-pr-body-standard.md for "
        f"per-section guidance. Heading text is case-sensitive but the "
        f"server treats `Risk and blast radius` and `Risk & blast "
        f"radius` as equivalent."
    )


def decide(
    tool_name: str, tool_input: dict[str, Any]
) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed.

    Order:
      1. Off-target tool -> allow (None).
      2. ``body`` missing / non-string -> allow (other preflights or
         the server gate cover the no-body branch).
      3. All required sections present -> allow.
      4. One or more missing -> deny, listing every missing name.
    """
    if canonical_github_tool(tool_name) not in _TARGET_TOOLS:
        return None
    body = tool_input.get("body")
    if not isinstance(body, str):
        return None
    missing = evaluate(body)
    if not missing:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": build_deny_reason(tool_name, missing),
        }
    }


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write decision JSON to stdout.

    Fails open per CLAUDE.md section 4: any parse error or unexpected
    payload shape emits ``::error::...`` to stderr and exits 0 with no
    decision, so a hook bug never wedges the session. The server-side
    ``verify-body-policy.yml`` workflow remains as backstop.
    """
    del argv
    event = read_event("preflight_pr_body_required_sections")
    if event is None:
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            "::error::preflight_pr_body_required_sections: event missing "
            "tool_name/tool_input",
            file=sys.stderr,
        )
        return 0

    emit_decision(decide(tool_name, tool_input))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
