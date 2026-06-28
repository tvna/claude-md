#!/usr/bin/env python3
"""PreToolUse gate: block create_pull_request / update_pull_request that
link a retro issue in their body.

Bound in ``.claude/settings.json`` to
``mcp__github__(create_pull_request|update_pull_request)``.  When the
PR body references an issue whose title satisfies
:func:`auto_retro.is_retro_issue_title` (i.e.
``chore(auto-retro): review PR #<N> repair loops`` or the legacy
``fix(auto-retro):`` prefix) and the PR title is not a retro-close PR
(i.e. :func:`auto_retro.is_retro_pr` is ``False``), the call is denied
with a block reason that names the offending issue and explains the
retro-close PR convention.

This is the client-side mirror of the server-side
``auto_retro.py verify-no-direct-retro-pr`` CI gate.  Both gates enforce
the same invariant and use the same title-based predicate
(:func:`auto_retro.is_retro_issue_title`), but the server gate fires after
push (costing a CI round-trip); this gate fires at PreToolUse time, before
the API call, so the operator is never blocked by a surprise CI failure
from an un-triaged retro link.

Fail-open (CLAUDE.md section 4)
---------------------------------
When the GH token is absent or a title lookup fails (HTTP error,
non-JSON response), the hook exits without emitting a decision so the
tool call proceeds.  The server-side ``verify-no-direct-retro-pr`` gate
remains the backstop.  Fail-closed would wedge sessions that lack a
token, or that run in environments where the GitHub API is unreachable.

Refs #1882.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from _github_api import apply_call
from _github_tool_names import canonical_github_tool
from _hook_runtime import build_deny, run_tool_hook
from auto_retro import is_retro_issue_title, is_retro_pr
from issue_link import extract_refs, strip_html_comments

_SCRIPT_NAME = "gate_pr_body_retro_issue_link"
_TARGET_TOOLS: frozenset[str] = frozenset({
    "mcp__github__create_pull_request",
    "mcp__github__update_pull_request",
})


def fetch_issue_title(
    owner: str,
    repo: str,
    number: int,
    *,
    token: str,
    opener: Any = None,
    sleeper: Any = None,
) -> str | None:
    """Return the title of ``<owner>/<repo>#<number>``, or ``None`` on failure.

    Uses the same urllib / Bearer-auth path as
    ``pr_body_close_keyword_gate.fetch_labels``.  ``None`` means the
    lookup failed; callers must fail-open.
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
    title = data.get("title") if isinstance(data, dict) else None
    return title if isinstance(title, str) else None


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
    title_getter: Callable[[str, str, int], str | None],
) -> dict[str, Any] | None:
    """Return a deny decision when the PR body links a retro issue, else ``None``.

    ``token_getter`` and ``title_getter`` are injected so :func:`main` can
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
        issue_title = title_getter(owner, repo, number)
        if issue_title is None:
            return None  # fail-open: lookup failed, CI gate is backstop
        if is_retro_issue_title(issue_title):
            retro_numbers.append(number)

    if not retro_numbers:
        return None

    return build_deny(_deny_reason(retro_numbers, tool_name))


def main(argv: list[str] | None = None) -> int:
    del argv

    def _token_getter() -> str | None:
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _title_getter(owner: str, repo: str, number: int) -> str | None:
        token = _token_getter()
        if not token:
            return None
        return fetch_issue_title(owner, repo, number, token=token)

    return run_tool_hook(
        _SCRIPT_NAME,
        lambda tool_name, tool_input: decide(
            tool_name,
            tool_input,
            token_getter=_token_getter,
            title_getter=_title_getter,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
