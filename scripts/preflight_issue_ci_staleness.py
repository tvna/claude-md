#!/usr/bin/env python3
"""PreToolUse gate: block issue creation for CI failures without verifying current main.

When mcp__github__issue_write creates an issue whose title or body references
a GitHub Actions run URL or CI-failure keywords, the agent must have confirmed
the failure is still present on current main HEAD before opening the issue.
Otherwise a post-merge automated fix (e.g. chore/update-generated-docs) may
have already resolved the failure, and the issue would be unnecessary.

Why a PreToolUse hook (CLAUDE.md S3): issue creation is an outward-facing,
hard-to-retract operation; a confirmatory gate prevents unnecessary issues
that require a follow-up close (as happened with #1943). The gate is
advisory-style: it blocks and requests verification, but the agent can
satisfy it by first running 'git fetch origin main' and documenting that the
failure still exists in the issue body (FRESH_MAIN_CHECK_PHRASE). Refs #1944.

Detection heuristics
---------------------
* Actions run URL pattern: github.com/.../actions/runs/<id>
* CI-failure keywords (title + body): "stale", "docs/generated/ is stale",
  "post-merge", "CI fail", "CI failure", "failing CI", "job failed".
* Keywords are case-insensitive and intentionally broad; false positives
  (e.g. a doc issue that mentions "post-merge") are cleared by adding
  FRESH_MAIN_CHECK_PHRASE to the body.

Opt-out mechanism
-----------------
Adding the literal phrase FRESH_MAIN_CHECK_PHRASE anywhere in the issue body
signals that the agent has already verified current main and the failure
persists. The hook allows the call.

Tested by tests/test_preflight_issue_ci_staleness.py. Refs #1944, #1943.
"""

from __future__ import annotations

import re
from typing import Any

from _hook_runtime import build_deny, run_tool_hook

# Only intercept issue creation calls.
_TARGET_TOOL = "mcp__github__issue_write"
_TARGET_METHOD = "create"

# Phrase the agent adds to the issue body to certify it verified main HEAD.
FRESH_MAIN_CHECK_PHRASE = "Verified: failure still present on current main HEAD"

# GitHub Actions run URL pattern.
_ACTIONS_RUN_RE = re.compile(
    r"github\.com/[^/\s]+/[^/\s]+/actions/runs/\d+", re.IGNORECASE
)

# CI-failure keywords in title or body.
_CI_KEYWORDS: tuple[str, ...] = (
    "stale",
    "docs/generated",
    "post-merge",
    "ci fail",
    "ci failure",
    "failing ci",
    "job failed",
    "jobs failed",
    "workflow failed",
    "check failed",
    "post merge",
)

_DENY_REASON = (
    "Blocked by scripts/preflight_issue_ci_staleness.py: this "
    "mcp__github__issue_write create call looks like it is opening an issue "
    "for a CI failure, but the issue body does not contain the verification "
    "phrase that confirms the failure is still present on current main HEAD. "
    "Before creating the issue: (1) run `git fetch origin main`, (2) "
    "reproduce the failing check against the current HEAD, (3) confirm the "
    "failure is still present. Then add the following exact phrase anywhere "
    "in the issue body and retry: "
    f'"{FRESH_MAIN_CHECK_PHRASE}". '
    "If the failure is already fixed on main, do not create the issue. "
    "Refs #1944, #1943."
)


def _looks_like_ci_failure(title: str, body: str) -> bool:
    """Return True when title or body contains a CI-failure signal."""
    text = (title + " " + body).lower()
    if _ACTIONS_RUN_RE.search(text):
        return True
    return any(kw in text for kw in _CI_KEYWORDS)


def _has_verification_phrase(body: str) -> bool:
    """Return True when the agent has certified a current-main check."""
    return FRESH_MAIN_CHECK_PHRASE.lower() in body.lower()


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny decision, or None to allow the call.

    Only fires on mcp__github__issue_write with method=create. Off-target
    tools and update calls are allowed immediately. Fails open on any
    unexpected payload shape (CLAUDE.md S4).
    """
    if tool_name != _TARGET_TOOL:
        return None
    if tool_input.get("method") != _TARGET_METHOD:
        return None

    title = tool_input.get("title", "")
    body = tool_input.get("body", "")
    if not isinstance(title, str):
        title = ""
    if not isinstance(body, str):
        body = ""

    if not _looks_like_ci_failure(title, body):
        return None
    if _has_verification_phrase(body):
        return None
    return build_deny(_DENY_REASON)


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write decision JSON to stdout.

    Fails open: a malformed event or unexpected payload shape exits 0 with
    no decision so a hook bug never wedges the session. Refs #1944.
    """
    del argv
    return run_tool_hook(
        script_name="preflight_issue_ci_staleness",
        decide=decide,
        auditable=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
