#!/usr/bin/env python3
"""Client-side preflight for PR title rules (Layer 2.5).

PreToolUse hook invoked by Claude Code on the matcher configured in
``.claude/settings.json``. Reads a PreToolUse event JSON from stdin and,
when ``mcp__github__create_pull_request`` or
``mcp__github__update_pull_request`` carries a ``title`` that violates
any of the rules the server-side gate ``scripts/title_policy.py`` would
reject, emits a ``permissionDecision: "deny"`` JSON on stdout that asks
Claude to fix the title before retrying.

Three rules are mirrored from ``scripts/title_policy.py``:

* ASCII-only (:func:`title_policy.is_ascii_title`). Server-side rationale:
  prompt-injection defense per #155.
* Conventional-commit type (:func:`title_policy.follows_naming_convention`,
  backed by ``_CONVENTIONAL_TYPES``). Server-side rationale: predictable
  title shape for triage queues, agent summaries, and CI commit logs.
* No ``(#NNN)`` issue-reference token
  (:func:`title_policy.pr_title_has_issue_ref`). Server-side rationale per
  #167 / #214: the PR body's ``Closes #NNN`` / ``Refs #NNN`` line,
  validated by ``.github/workflows/verify-issue-link.yml``, is the
  single source of truth for the issue link, so the title must not
  duplicate it.

The hook evaluates the three rules in the order above; the first
violation wins so the deny reason stays focused. The script name still
mentions ``issue_ref`` only for backward compatibility -- renaming would
churn the ``.claude/settings.json`` matcher and downstream consumers.
Tracked in #348 (extension that added the two extra rules); original
issue-ref behavior is #292.

Architecture mirrors :mod:`preflight_non_ascii`: pure functions on top,
one thin stdin/stdout boundary at the bottom (:func:`main`). The main
function fails open on parse / shape errors so a hook bug cannot wedge
the session -- the server-side gate remains as backstop.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from title_policy import (
    describe_non_ascii,
    follows_naming_convention,
    naming_convention_hint,
)

# Tools whose ``title`` field the server-side title-policy gate enforces
# its rules on. Kept in sync with the matcher regex in
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


def find_non_ascii_codepoints(title: str) -> list[str]:
    """Return human-readable descriptions of non-ASCII code points in *title*.

    Thin wrapper around :func:`title_policy.describe_non_ascii` so the
    hook and the server-side gate produce identical messages. Empty list
    when *title* is ASCII-only.
    """
    return describe_non_ascii(title)


def find_invalid_type(title: str) -> str | None:
    """Return the offending type prefix when *title* breaks naming convention.

    Returns ``None`` when *title* matches the conventional-commit shape
    enforced by :func:`title_policy.follows_naming_convention` for PRs.
    When the title does not match, returns the substring up to the first
    ``(`` or ``:`` so the deny reason can quote it back. Returns the
    full title (trimmed to a sensible length) when no separator is
    present so the operator can still see what the hook saw.
    """
    if follows_naming_convention(title, kind="pull_request"):
        return None
    # Quote whatever the operator likely meant as the type; stop at the
    # first separator that conventional-commits uses.
    head = re.split(r"[(:]", title, maxsplit=1)[0].strip()
    if not head:
        return title.strip()[:40]
    return head


def suggest_fix(title: str) -> str:
    """Return *title* with every ``(#NNN)`` token removed.

    Adjacent whitespace is collapsed to a single space and the result is
    stripped so a title like ``"feat: foo (#1)"`` becomes ``"feat: foo"``
    rather than ``"feat: foo "``.
    """
    stripped = _ISSUE_REF_RE.sub("", title)
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def build_issue_ref_deny_reason(tool_name: str, title: str, refs: list[str]) -> str:
    """Return the deny reason text for the issue-ref rule."""
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


def build_non_ascii_deny_reason(tool_name: str, title: str, findings: list[str]) -> str:
    """Return the deny reason text for the ASCII-only rule."""
    details = ", ".join(findings)
    return (
        f"Blocked by scripts/preflight_pr_title_issue_ref.py (Layer "
        f"2.5): `{tool_name}` title contains non-ASCII code points "
        f"({details}). The server-side gate scripts/title_policy.py "
        f"(verify-title-policy.yml) rejects this per #155: titles are "
        f"prompt-injection surface (notifications, triage queues, agent "
        f"summaries) and must stay ASCII-only so zero-width marks, RTL "
        f"controls, emoji, and homoglyphs cannot smuggle instructions "
        f"through the header layer.\n\n"
        f"  Offending title: {title!r}"
    )


def build_invalid_type_deny_reason(tool_name: str, title: str, offending: str) -> str:
    """Return the deny reason text for the conventional-type rule."""
    hint = naming_convention_hint("pull_request")
    types_csv = "build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test, tracking"
    return (
        f"Blocked by scripts/preflight_pr_title_issue_ref.py (Layer "
        f"2.5): `{tool_name}` title does not follow the conventional-"
        f"commit shape required by scripts/title_policy.py "
        f"(verify-title-policy.yml). Offending prefix: {offending!r}. "
        f"Expected: {hint} where the type is one of: {types_csv}.\n\n"
        f"  Offending title: {title!r}\n\n"
        f"If the change is security-flavored, use `feat(<scope>): ...` "
        f"and put the security context in the body. If it adds or "
        f"changes a CI gate, `ci(<scope>): ...` also fits."
    )


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed.

    Order:
      1. Off-target tool -> allow (None).
      2. No title (missing / wrong type / empty) -> allow.
      3. Title contains non-ASCII code points -> deny.
      4. Title does not match the conventional-commit shape -> deny.
      5. Title carries a ``(#NNN)`` token -> deny.
      6. Otherwise -> allow.

    The three deny rules are evaluated in the order the operator most
    likely needs to fix them (encoding -> overall shape -> ref smell);
    the first violation wins so the deny reason stays focused.
    """
    if tool_name not in _TARGET_TOOLS:
        return None
    title = extract_title(tool_input)
    if not title:
        return None

    non_ascii = find_non_ascii_codepoints(title)
    if non_ascii:
        return _build_deny_dict(build_non_ascii_deny_reason(tool_name, title, non_ascii))

    invalid_type = find_invalid_type(title)
    if invalid_type is not None:
        return _build_deny_dict(build_invalid_type_deny_reason(tool_name, title, invalid_type))

    refs = find_issue_refs(title)
    if refs:
        return _build_deny_dict(build_issue_ref_deny_reason(tool_name, title, refs))

    return None


def _build_deny_dict(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
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
