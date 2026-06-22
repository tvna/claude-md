#!/usr/bin/env python3
"""PreToolUse gate: block create_pull_request / update_pull_request that
link a retro issue in their body.

Bound in ``.claude/settings.json`` to
``mcp__github__(create_pull_request|update_pull_request)``.  When the
PR body references an issue that carries a ``type:retrospective`` or
``auto-retro`` label and the PR title is not a retro-close PR (i.e.
:func:`auto_retro.is_retro_pr` is ``False``), the call is denied with a
block reason that names the offending issue and explains the retro-close
PR convention.

This is the client-side mirror of the server-side
``auto_retro.py verify-no-direct-retro-pr`` CI gate.  Both gates enforce
the same invariant, but the server gate fires after push (costing a CI
round-trip); this gate fires at PreToolUse time, before the API call,
so the operator is never blocked by a surprise CI failure from an
un-triaged retro link.

Fail-open (CLAUDE.md section 4)
---------------------------------
When the GH token is absent or a label lookup fails (HTTP error,
non-JSON response), the hook exits without emitting a decision so the
tool call proceeds.  The server-side ``verify-no-direct-retro-pr`` gate
remains the backstop.  Fail-closed would wedge sessions that lack a
token, or that run in environments where the GitHub API is unreachable.

Refs #1882.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from _github_tool_names import canonical_github_tool
from _hook_runtime import build_deny, run_tool_hook
from auto_retro import is_retro_pr
from issue_link import extract_refs, strip_html_comments
from pr_body_close_keyword_gate import fetch_labels

_SCRIPT_NAME = "gate_pr_body_retro_issue_link"
_TARGET_TOOLS: frozenset[str] = frozenset({
    "mcp__github__create_pull_request",
    "mcp__github__update_pull_request",
})
# Labels that identify a retro issue; either is sufficient.
_RETRO_ISSUE_LABELS: frozenset[str] = frozenset({"type:retrospective", "auto-retro"})


def has_retro_label(labels: list[str]) -> bool:
    """Return ``True`` when *labels* marks an issue as a retrospective."""
    return bool(_RETRO_ISSUE_LABELS & set(labels))


def _deny_reason(retro_numbers: list[int], tool_name: str) -> str:
    joined = ", ".join(f"#{n}" for n in retro_numbers)
    return (
        f"Blocked by scripts/{_SCRIPT_NAME}.py (client-side mirror of "
        f"verify-no-direct-retro-pr): `{tool_name}` links retro issue(s) "
        f"{joined} but is not a retro-close PR.\n\n"
        "Retro issues are triage signals, not units of work to implement "
        "directly. To resolve:\n"
        "  1. Open a new implementation issue that describes the work.\n"
        "  2. Target this PR at the new issue (`Closes #<new-issue>`).\n"
        "  3. Reference the retro as prose in the Facts section instead "
        "(e.g. \"(retro #N)\"), not via a `Closes` / `Refs` line.\n\n"
        "The retro issue will be closed by a separate retro-close PR "
        "(`chore(auto-retro): ...` title) once the follow-up work lands. "
        "Refs #1882."
    )


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    token_getter: Callable[[], str | None],
    label_getter: Callable[[str, str, int], list[str] | None],
) -> dict[str, Any] | None:
    """Return a deny decision when the PR body links a retro issue, else ``None``.

    ``token_getter`` and ``label_getter`` are injected so :func:`main` can
    bind them to the real environment while tests swap in mocks without
    touching urllib or :data:`os.environ`.
    """
    if canonical_github_tool(tool_name) not in _TARGET_TOOLS:
        return None

    body = tool_input.get("body")
    if not isinstance(body, str):
        return None

    title = tool_input.get("title", "")
    if isinstance(title, str) and is_retro_pr(title):
        return None  # retro-close PR is permitted to link retro issues

    refs = extract_refs(strip_html_comments(body))
    if not refs:
        return None

    owner = tool_input.get("owner")
    repo = tool_input.get("repo")
    if not (isinstance(owner, str) and owner and isinstance(repo, str) and repo):
        return None

    token = token_getter()
    if not token:
        return None  # fail-open: CI gate is backstop

    retro_numbers: list[int] = []
    for number in refs:
        labels = label_getter(owner, repo, number)
        if labels is None:
            return None  # fail-open: lookup failed, CI gate is backstop
        if has_retro_label(labels):
            retro_numbers.append(number)

    if not retro_numbers:
        return None

    return build_deny(_deny_reason(retro_numbers, tool_name))


def main(argv: list[str] | None = None) -> int:
    del argv

    def _token_getter() -> str | None:
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _label_getter(owner: str, repo: str, number: int) -> list[str] | None:
        token = _token_getter()
        if not token:
            return None
        return fetch_labels(owner, repo, number, token=token)

    return run_tool_hook(
        _SCRIPT_NAME,
        lambda tool_name, tool_input: decide(
            tool_name,
            tool_input,
            token_getter=_token_getter,
            label_getter=_label_getter,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
