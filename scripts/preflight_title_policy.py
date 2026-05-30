#!/usr/bin/env python3
"""Client-side preflight for issue and PR title rules.

PreToolUse hook invoked by Claude Code on the matcher configured in
``.claude/settings.json``. Reads a PreToolUse event JSON from stdin and,
when ``mcp__github__issue_write``, ``mcp__github__create_pull_request``,
or ``mcp__github__update_pull_request`` carries a ``title`` that
violates any of the rules the server-side gate ``scripts/title_policy.py``
would reject, emits a ``permissionDecision: "deny"`` JSON on stdout that
asks Claude to fix the title before retrying.

Three rules are mirrored from :mod:`title_policy`:

* ASCII-only (:func:`title_policy.is_ascii_title`). Server-side rationale:
  prompt-injection defense per #155.
* Conventional-commit type (:func:`title_policy.follows_naming_convention`,
  backed by ``.github/title-policy.toml``). Server-side rationale: predictable
  title shape for triage queues, agent summaries, and CI commit logs.
* No ``(#NNN)`` issue-reference token, PRs only
  (:func:`title_policy.pr_title_has_issue_ref`). Server-side rationale per
  #167 / #214: the PR body's ``Closes #NNN`` / ``Refs #NNN`` line,
  validated by ``.github/workflows/verify-issue-link.yml``, is the
  single source of truth for the issue link, so the title must not
  duplicate it.

The hook evaluates the three rules in the order above; the first
violation wins so the deny reason stays focused. Issue titles are gated
on the first two rules only -- the ``(#NNN)`` rule is PR-specific because
the issue link is enforced on the PR body, not the issue body.

Architecture mirrors :mod:`preflight_non_ascii`: pure functions on top,
one thin stdin/stdout boundary at the bottom (:func:`main`). The main
function fails open on parse / shape errors so a hook bug cannot wedge
the session -- the server-side gate (``verify-title-policy.yml``)
remains as backstop.

Refs #496. Supersedes ``scripts/preflight_pr_title_issue_ref.py``
(extended issue-write coverage to close the gap surfaced by triage
2026-05-27, tracking #491 / #492 / #493).
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from _github_tool_names import canonical_github_tool
from title_policy import (
    allowed_types_csv,
    describe_non_ascii,
    follows_naming_convention,
    format_type_fit_finding,
    is_ascii_title,
    naming_convention_hint,
    pr_title_has_issue_ref,
    pr_title_issue_refs,
    pr_title_strip_issue_refs,
    type_fit_findings,
)

# Tools whose ``title`` field the server-side title-policy gate enforces
# its rules on. Kept in sync with the matcher regex in
# ``.claude/settings.json``; the matcher is the primary gate, this set
# is defense in depth.
_TARGET_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__issue_write",
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request",
    }
)

_PR_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request",
    }
)

# Same separators conventional-commits uses; helps quote the offending
# prefix back when the type is unknown.
_TYPE_SEPARATOR_RE = re.compile(r"[(:]")


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def extract_title(tool_input: dict[str, Any]) -> str:
    """Return the ``title`` field as a string, or ``""`` if absent / wrong type.

    Mirrors :func:`preflight_non_ascii.extract_text_fields` shape so the
    client-side preflight hooks behave consistently on missing payload keys.
    ``issue_write`` with ``method="update"`` and no title change goes
    through this branch and is allowed.
    """
    title = tool_input.get("title") or ""
    if not isinstance(title, str):
        return ""
    return title


def extract_body(tool_input: dict[str, Any]) -> str:
    """Return the optional body/description field as a string."""
    body = tool_input.get("body") or tool_input.get("description") or ""
    if not isinstance(body, str):
        return ""
    return body


def kind_for_tool(tool_name: str) -> str | None:
    """Return the :mod:`title_policy` ``kind`` for *tool_name*.

    ``"issue"`` for ``mcp__github__issue_write`` and ``"pull_request"``
    for the two PR-write tools. ``None`` for any off-target tool.

    Codex GitHub connector tool names are folded onto their Claude
    equivalents first (Refs #740) so a connector-shaped PR/issue write is
    classified the same as the native call.
    """
    canonical = canonical_github_tool(tool_name)
    if canonical == "mcp__github__issue_write":
        return "issue"
    if canonical in _PR_TOOLS:
        return "pull_request"
    return None


def find_invalid_type(title: str, *, kind: str) -> str | None:
    """Return the offending type prefix when *title* breaks naming convention.

    Returns ``None`` when *title* matches the conventional-commit shape
    enforced by :func:`title_policy.follows_naming_convention` for
    *kind*. When the title does not match, returns the substring up to
    the first ``(`` or ``:`` so the deny reason can quote it back.
    Returns the trimmed full title (capped to 40 chars) when no
    separator is present so the operator can still see what the hook
    saw.
    """
    if follows_naming_convention(title, kind=kind):
        return None
    head = _TYPE_SEPARATOR_RE.split(title, maxsplit=1)[0].strip()
    if not head:
        return title.strip()[:40]
    return head


def build_non_ascii_deny_reason(tool_name: str, kind: str, title: str, findings: list[str]) -> str:
    """Return the deny reason text for the ASCII-only rule."""
    details = ", ".join(findings)
    return (
        f"Blocked by scripts/preflight_title_policy.py "
        f"(client-side preflight): "
        f"`{tool_name}` {kind} title contains non-ASCII code points "
        f"({details}). The server-side gate scripts/title_policy.py "
        f"(verify-title-policy.yml) rejects this per #155: titles are "
        f"prompt-injection surface (notifications, triage queues, agent "
        f"summaries) and must stay ASCII-only so zero-width marks, RTL "
        f"controls, emoji, and homoglyphs cannot smuggle instructions "
        f"through the header layer.\n\n"
        f"  Offending title: {title!r}"
    )


def build_invalid_type_deny_reason(tool_name: str, kind: str, title: str, offending: str) -> str:
    """Return the deny reason text for the conventional-type rule."""
    hint = naming_convention_hint(kind)
    types_csv = allowed_types_csv()
    return (
        f"Blocked by scripts/preflight_title_policy.py "
        f"(client-side preflight): "
        f"`{tool_name}` {kind} title does not follow the conventional-"
        f"commit shape required by scripts/title_policy.py "
        f"(verify-title-policy.yml). Offending prefix: {offending!r}. "
        f"Expected: {hint} where the type is one of: {types_csv}.\n\n"
        f"  Offending title: {title!r}\n\n"
        f"If the change is security-flavored, use `feat(<scope>): ...` "
        f"and put the security context in the body. If it adds or "
        f"changes a CI gate, `ci(<scope>): ...` also fits. For "
        f"operational tracking issues, `tracking: ...` or "
        f"`ci(ops): ...` are the conventional fits (the 2026-05-27 "
        f"triage round repaired three `ops:` issues to `ci(ops): ...`)."
    )


def build_issue_ref_deny_reason(tool_name: str, title: str, refs: list[str], suggested: str) -> str:
    """Return the deny reason text for the issue-ref rule (PRs only)."""
    refs_csv = ", ".join(refs)
    return (
        f"Blocked by scripts/preflight_title_policy.py "
        f"(client-side preflight): "
        f"`{tool_name}` pull_request title contains issue-reference "
        f"token(s) {refs_csv}. The server-side gate "
        f"scripts/title_policy.py (verify-title-policy.yml) rejects "
        f"this per #167 / #214: the PR body's `Closes #NNN` / `Refs "
        f"#NNN` line, validated by verify-issue-link.yml, is the "
        f"single source of truth for the issue link, so the title must "
        f"not duplicate it.\n\n"
        f"Retry with the issue ref removed:\n"
        f"  Offending title: {title!r}\n"
        f"  Suggested fix:   {suggested!r}\n\n"
        f"If the bracketed token is intentional and not an issue "
        f"reference, reword it so it does not match the regex "
        f"\\(#\\d+\\)."
    )


def build_type_fit_deny_reason(tool_name: str, kind: str, title: str, finding_text: str) -> str:
    """Return the deny reason text for semantic type/title mismatch."""
    return (
        f"Blocked by scripts/preflight_title_policy.py "
        f"(client-side preflight): "
        f"`{tool_name}` {kind} title uses a Conventional Commit type "
        f"that does not fit the detected work category. "
        f"{finding_text}\n\n"
        f"  Offending title: {title!r}\n\n"
        f"Use `perf(<scope>): ...` for runtime, cache, latency, throughput, "
        f"startup, memory, or resource improvements. DevContainer work is "
        f"a valid scope; choose `perf(devcontainer): ...` for performance "
        f"work, `fix(devcontainer): ...` for a demonstrated defect, "
        f"`ci(devcontainer): ...` for workflow-only changes, and "
        f"`build(devcontainer): ...` for build/package mechanics."
    )


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed.

    Order:
      1. Off-target tool -> allow (None).
      2. No title (missing / wrong type / empty) -> allow.
      3. Title contains non-ASCII code points -> deny.
      4. Title does not match the conventional-commit shape -> deny.
      5. (PR only) Title carries a ``(#NNN)`` token -> deny.
      6. Otherwise -> allow.

    The three deny rules are evaluated in the order the operator most
    likely needs to fix them (encoding -> overall shape -> ref smell);
    the first violation wins so the deny reason stays focused.
    """
    kind = kind_for_tool(tool_name)
    if kind is None:
        return None
    title = extract_title(tool_input)
    if not title:
        return None
    body = extract_body(tool_input)

    if not is_ascii_title(title):
        findings = describe_non_ascii(title)
        return _build_deny_dict(build_non_ascii_deny_reason(tool_name, kind, title, findings))

    invalid_type = find_invalid_type(title, kind=kind)
    if invalid_type is not None:
        return _build_deny_dict(build_invalid_type_deny_reason(tool_name, kind, title, invalid_type))

    fit_findings = type_fit_findings(title, kind=kind, body=body)
    if fit_findings:
        return _build_deny_dict(
            build_type_fit_deny_reason(
                tool_name,
                kind,
                title,
                format_type_fit_finding(fit_findings[0]),
            )
        )

    if kind == "pull_request" and pr_title_has_issue_ref(title):
        refs = pr_title_issue_refs(title)
        suggested = pr_title_strip_issue_refs(title)
        return _build_deny_dict(build_issue_ref_deny_reason(tool_name, title, refs, suggested))

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
            f"::error::preflight_title_policy: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            "::error::preflight_title_policy: event missing tool_name/tool_input",
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
