#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block PR bodies that would fail the server gate.

Bound in ``.claude/settings.json`` to
``mcp__github__(create_pull_request|update_pull_request)``. Reads the
PreToolUse event JSON from stdin and, when the tool input's PR body
would fail ``scripts/issue_link.py:_verify`` for the Refs-only
closing-keyword rule (PR #220, issue #222), emits a
``permissionDecision: "deny"`` JSON on stdout so the operator can fix
the body BEFORE the API call instead of round-tripping through
``verify-issue-link.yml``.

Architecture mirrors :mod:`preflight_non_ascii`: pure functions on top,
a single stdin/stdout boundary at the bottom (:func:`main`). Detection
constants, classification, and the deny-reason text are imported from
:mod:`_ref_classifier` so this hook and ``scripts/issue_link.py`` cannot
drift. Per issue #222, the old self-contained advisory file is removed.

Failure modes:

* Refs-only body, ``GH_TOKEN`` unset or label lookup fails: fail-closed
  (deny). The server gate also fails in this branch, so a hook block
  matches the server's strict semantics (#222 acceptance criterion 3).
* Off-target tool, body absent or non-string, ``tool_input`` shape
  invalid: fail-open (exit 0, no decision). A hook bug must never
  wedge unrelated tool calls; the server gate remains as backstop.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from typing import Any, Literal

from _github_api import apply_call
from _github_tool_names import canonical_github_tool
from _hook_runtime import emit_decision, read_event
from _ref_classifier import (
    TRACKING_LABEL,
    body_has_partial_marker,
    classify_refs,
    format_no_closing_keyword_msg,
    strip_html_comments,
)

_TARGET_TOOLS: frozenset[str] = frozenset({
    "mcp__github__create_pull_request",
    "mcp__github__update_pull_request",
})

Action = Literal["pass", "needs_label_check", "skip"]


def classify_action(body: str) -> tuple[Action, list[int]]:
    """Decide what the hook should do with *body*.

    Returns ``(action, refs_only_numbers)``:

    * ``"pass"`` -- the body satisfies the server gate (closing keyword
      present, or a partial-work opt-out marker present -- either the
      legacy ``<!-- partial -->`` HTML comment or the MCP-safe plain-text
      ``partial-pr`` line, #1035).
    * ``"needs_label_check"`` -- the body cites only ``Refs`` keywords;
      the hook must look up ``type:tracking`` labels to decide pass/deny.
    * ``"skip"`` -- the body has no recognized references at all; the
      server gate covers that branch (``_NO_REFS_MSG``) and is out of
      scope for this hook (per issue #222 plan).

    ``refs_only_numbers`` is the sorted-unique list of issue numbers in
    ``Refs`` references, populated only for ``needs_label_check``.
    """
    if body_has_partial_marker(body):
        return "pass", []
    cleaned = strip_html_comments(body)
    classified = classify_refs(cleaned)
    if not classified:
        return "skip", []
    if any(kw != "refs" for kw, _ in classified):
        return "pass", []
    refs_only = sorted({n for _, n in classified})
    return "needs_label_check", refs_only


def fetch_labels(
    owner: str,
    repo: str,
    number: int,
    *,
    token: str,
    opener: Callable[..., Any] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> list[str] | None:
    """Return label names on ``<owner>/<repo>#<number>``, or ``None`` on failure.

    Uses :func:`scripts._github_api.apply_call` so the urllib retry /
    Bearer-auth path is shared with the rest of the harness. ``None``
    means "could not determine"; callers must fail-closed.
    """
    kwargs: dict[str, Any] = {}
    if opener is not None:
        kwargs["opener"] = opener
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    try:
        status, body = apply_call(
            method="GET",
            url=f"https://api.github.com/repos/{owner}/{repo}/issues/{number}",
            payload=None,
            token=token,
            **kwargs,
        )
    except Exception:
        return None
    if not (200 <= status < 300):
        return None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None
    raw_labels = data.get("labels") if isinstance(data, dict) else None
    if not isinstance(raw_labels, list):
        return None
    out: list[str] = []
    for entry in raw_labels:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str):
                out.append(name)
        elif isinstance(entry, str):
            out.append(entry)
    return out


def all_tracking(labels_by_number: dict[int, list[str] | None]) -> bool:
    """True iff every number has labels and every list contains the carve-out."""
    if not labels_by_number:
        return False
    return all(labels is not None and TRACKING_LABEL in labels for labels in labels_by_number.values())


def _build_deny_reason(
    refs_only: list[int],
    *,
    token_present: bool,
    lookup_failed: bool,
) -> str:
    base = format_no_closing_keyword_msg(refs_only)
    if not token_present:
        suffix = (
            "\n\nNote: GH_TOKEN is not set in the hook environment, so "
            "this hook cannot consult issue labels to honor the "
            f"'{TRACKING_LABEL}' carve-out. Set GH_TOKEN (read scope on "
            "issues is enough) and retry, or use one of the two fixes "
            "above."
        )
    elif lookup_failed:
        suffix = (
            "\n\nNote: label lookup for one or more referenced issues "
            "failed (HTTP error or non-JSON response). Fail-closed per "
            "issue #222 acceptance criterion 3."
        )
    else:
        suffix = ""
    return base + suffix


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    token_getter: Callable[[], str | None],
    label_getter: Callable[[str, str, int], list[str] | None],
) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed.

    ``token_getter`` and ``label_getter`` are injected so :func:`main` can
    bind them to the real environment while tests can swap in mocks
    without touching urllib or :data:`os.environ`.
    """
    if canonical_github_tool(tool_name) not in _TARGET_TOOLS:
        return None
    body = tool_input.get("body")
    if not isinstance(body, str):
        return None

    action, refs_only = classify_action(body)
    if action in ("pass", "skip"):
        return None

    owner = tool_input.get("owner")
    repo = tool_input.get("repo")
    if not (isinstance(owner, str) and owner and isinstance(repo, str) and repo):
        return None

    token = token_getter()
    if not token:
        reason = _build_deny_reason(
            refs_only,
            token_present=False,
            lookup_failed=False,
        )
        return _deny(tool_name, reason)

    labels_by_number = {n: label_getter(owner, repo, n) for n in refs_only}
    if all_tracking(labels_by_number):
        return None

    lookup_failed = any(v is None for v in labels_by_number.values())
    reason = _build_deny_reason(
        refs_only,
        token_present=True,
        lookup_failed=lookup_failed,
    )
    return _deny(tool_name, reason)


def _deny(tool_name: str, reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked by scripts/pr_body_close_keyword_gate.py "
                f"(client-side mirror of verify-issue-link.yml gate): "
                f"`{tool_name}` would fail server-side. {reason}"
            ),
        }
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    event = read_event("pr_body_close_keyword_gate")
    if event is None:
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            "::error::pr_body_close_keyword_gate: event missing tool_name/tool_input",
            file=sys.stderr,
        )
        return 0

    def _token_getter() -> str | None:
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _label_getter(owner: str, repo: str, number: int) -> list[str] | None:
        token = _token_getter()
        if not token:
            return None
        return fetch_labels(owner, repo, number, token=token)

    emit_decision(
        decide(
            tool_name,
            tool_input,
            token_getter=_token_getter,
            label_getter=_label_getter,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
