#!/usr/bin/env python3
"""PreToolUse gate: deny a Bash ``git commit`` whose message closes a retro issue.

Bound in ``.claude/settings.json`` (and mirrored in ``.codex/hooks.json`` /
``.devin/hooks.v1.json`` via ``scripts/agent_hooks_source.json``) to the
``Bash`` matcher. When a ``git commit`` carries a GitHub auto-closing keyword
(``Closes`` / ``Fixes`` / ``Resolves`` followed by an issue number) in its
``-m`` / ``--message`` text for an issue whose title is a retrospective-issue
title (:func:`auto_retro.is_retro_issue_title`), the commit is denied.

This is the Bash-``git commit`` sibling of
``gate_pr_body_retro_issue_link.py`` (the PR-body surface) and of the
server-side ``auto_retro.py verify-no-direct-retro-pr`` CI gate. Those two
guard the PR body; neither inspects commit *messages*. The PR #2103 retro
(#2114) traced a real failure to exactly that gap: a content commit landed on
the session branch carrying a ``Closes #<retro>`` keyword in its message.
Because force-push and branch deletion are both blocked on a session branch,
the buried keyword could not be rewritten out, and on squash-merge GitHub
would concatenate the commit message into the squash body and auto-close the
retrospective issue. The squash mis-close is irreversible once pushed, so the
only place to stop it is before the commit is made (CLAUDE.md section 4: make
wrong actions hard, right actions easy).

Why retro issues specifically, not every closing keyword: a feature-branch
commit that closes its own implementation issue is the normal path, and the
PR body is where ``Closes`` belongs. The harm this gate prevents is the
mis-close of a *retrospective* issue, which the retro-scope governance
(#1882 / #1069) reserves for a separate retro-close PR. The retro-title
predicate is the same single source the PR-body gate and the CI gate use, so
this gate can never drift from them.

Fail-open (CLAUDE.md section 4): when the GH token is absent, the repo slug
cannot be resolved, a title lookup fails, or the stdin event is malformed, the
hook exits without a decision so the commit proceeds. The squash-time
mis-close is the only residual risk and a hook bug must never wedge a session.
An explicit, reviewed commit can still proceed by appending a
``# retro-close-ack`` comment to the command.

Contract:
- Inputs: a PreToolUse ``Bash`` event as JSON on stdin.
- Outputs: a JSON deny decision on stdout when the commit message closes a
  retro issue; nothing on pass-through. Always exits 0.
- Failure policy: fail-open at every I/O / lookup boundary; fail-loud-by-deny
  on a matched retro closing keyword.

Tested by ``tests/test_gate_retro_close_keyword_commit.py``. Refs #2114, #2103,
#2011, #1882.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Callable
from typing import Any

from _hook_runtime import build_deny, run_event_hook
from _ref_classifier import CLOSING_KEYWORDS
from auto_retro import is_retro_issue_title
from gate_pr_body_retro_issue_link import fetch_issue_title

_SCRIPT_NAME = "gate_retro_close_keyword_commit"

# Reviewed-commit opt-in. Distinct from the unsigned-commit ``# unsigned-ack``
# marker because this is a different category (a retro mis-close, not an
# unsigned object); one category, one control (CLAUDE.md section 4).
_ACK_MARKER = "# retro-close-ack"

# Git global options whose value is a SEPARATE following token (``git -C
# <path> commit``, ``git -c user.name=x commit``), so the token after them is
# the value, not the subcommand. Tokenizing past these is what lets the gate
# see a ``commit`` behind global options (Codex review on #2120).
_GIT_VALUE_OPTS = frozenset({"-c", "-C"})

# Shell separators that end a single git invocation in a command line.
_SHELL_OPS = frozenset({"&&", "||", "|", ";", "&"})

# A ``-m`` / ``-am`` short flag, capturing any attached value: ``-m`` (empty
# group, value is the next token) or ``-mmsg`` / ``-amsg`` (group is the value).
_MSG_FLAG_RE = re.compile(r"-[A-Za-z]*m(.*)")

# Auto-closing keyword followed by ``#N``, anywhere in the message (commit
# messages carry no line-anchored ``Closes #N`` convention, unlike PR bodies).
# Built from the single-source keyword set so it never drifts from the
# PR-body / CI gates.
_CLOSING_REF_RE = re.compile(
    r"\b(?:" + "|".join(sorted(CLOSING_KEYWORDS)) + r")\s+#(\d+)\b",
    re.IGNORECASE,
)

_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GIT_REMOTE_RE = re.compile(
    r"github\.com[/:]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?\s*$"
)


def _commit_message_values(command: str) -> list[str]:
    """Return every ``-m`` / ``--message`` value of each ``git commit`` in *command*.

    Tokenizes the whole command (so chains and global options are handled),
    finds each ``git`` invocation whose subcommand is ``commit`` even behind
    global options (``git -C <path> commit``, ``git -c k=v commit``), and
    collects that invocation's message values up to the next shell operator.
    Returns ``[]`` when the command cannot be tokenized (an unbalanced quote),
    so a malformed command fails open. ``commit-tree`` and other subcommands
    are not matched.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    n = len(tokens)
    out: list[str] = []
    i = 0
    while i < n:
        if tokens[i] != "git" and not tokens[i].endswith("/git"):
            i += 1
            continue
        j = i + 1
        while j < n and tokens[j].startswith("-"):
            j += 2 if tokens[j] in _GIT_VALUE_OPTS else 1
        if j < n and tokens[j].rstrip(";&|") == "commit":
            k = j + 1
            invocation: list[str] = []
            while k < n and tokens[k] not in _SHELL_OPS:
                invocation.append(tokens[k])
                k += 1
            out.extend(_message_values(invocation))
            i = k
            continue
        i = j + 1
    return out


def _message_values(tokens: list[str]) -> list[str]:
    """Return every ``-m`` / ``--message`` value in a commit's argument *tokens*.

    Handles the separate-token (``-m msg``), attached (``-mmsg``), combined
    short-flag (``-am msg``), long (``--message msg``), and ``=``
    (``--message=msg``) spellings. ``-F`` / ``--file`` (a file) and the editor
    path carry no inspectable text, so their refs stay invisible and the gate
    fails open on them.
    """
    values: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in ("-m", "--message"):
            if i + 1 < n:
                values.append(tokens[i + 1])
                i += 2
                continue
        elif tok.startswith("--message="):
            values.append(tok[len("--message="):])
        elif (match := _MSG_FLAG_RE.fullmatch(tok)) is not None:
            attached = match.group(1)
            if attached:
                values.append(attached)
            elif i + 1 < n:
                values.append(tokens[i + 1])
                i += 2
                continue
        i += 1
    return values


def _closing_refs(command: str) -> list[int]:
    """Return sorted-unique issue numbers closed by the commit message, or []."""
    message = "\n".join(_commit_message_values(command))
    found = {int(m.group(1)) for m in _CLOSING_REF_RE.finditer(message)}
    return sorted(found)


def _detect_repo() -> str | None:
    """Return ``owner/repo`` from ``GITHUB_REPOSITORY`` or git remote origin."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo and _OWNER_REPO_RE.match(repo):
        return repo
    try:
        result = subprocess.run(  # noqa: S603 -- fixed args, not user input
            ["git", "remote", "get-url", "origin"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    match = _GIT_REMOTE_RE.search(result.stdout.strip())
    return match.group(1) if match else None


def _deny_reason(retro_numbers: list[int]) -> str:
    joined = ", ".join(f"#{n}" for n in retro_numbers)
    return (
        f"Blocked by scripts/{_SCRIPT_NAME}.py: this `git commit` message "
        f"carries a closing keyword (Closes / Fixes / Resolves) for "
        f"retrospective issue(s) {joined}.\n\n"
        "A closing keyword in a commit message is concatenated into the "
        "squash-merge body and auto-closes the issue on merge. On a "
        "force-push-protected session branch the commit cannot be rewritten "
        "out afterward, so a retro issue would be mis-closed irreversibly "
        "(the PR #2103 failure). Retro issues are triage signals closed only "
        "by a separate retro-close PR (`chore(auto-retro): ...` title), never "
        "by an implementation commit.\n\n"
        "To resolve:\n"
        "  1. Remove the closing keyword from the commit message; reference "
        "the retro as prose instead (e.g. \"(retro #N)\").\n"
        "  2. Put any `Closes #<implementation-issue>` line in the PR body, "
        "not the commit message.\n\n"
        "If this commit is genuinely intended and reviewed, append a "
        f"'{_ACK_MARKER}' comment to the command to opt in. Refs #2114, #1882."
    )


def decide(
    event: dict[str, Any],
    *,
    repo_getter: Callable[[], str | None],
    token_getter: Callable[[], str | None],
    title_getter: Callable[[str, str, int], str | None],
) -> dict[str, Any] | None:
    """Return a deny decision when a commit message closes a retro issue, else None.

    ``repo_getter`` / ``token_getter`` / ``title_getter`` are injected so
    :func:`main` binds the real environment while tests swap in mocks without
    touching subprocess, urllib, or :data:`os.environ`.
    """
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not command.strip():
        return None
    if _ACK_MARKER in command:
        return None
    if not token_getter():
        return None  # fail-open early: CI / PR-body gate path is the backstop

    refs = _closing_refs(command)
    if not refs:
        return None

    repo = repo_getter()
    if not repo or "/" not in repo:
        return None  # fail-open: cannot resolve repo slug
    owner, _, name = repo.partition("/")
    if not (owner and name):
        return None

    retro_numbers: list[int] = []
    for number in refs:
        title = title_getter(owner, name, number)
        if title is None:
            return None  # fail-open: lookup failed
        if is_retro_issue_title(title):
            retro_numbers.append(number)

    if not retro_numbers:
        return None
    return build_deny(_deny_reason(retro_numbers))


def main(argv: list[str] | None = None) -> int:
    del argv

    def _token_getter() -> str | None:
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _title_getter(owner: str, repo: str, number: int) -> str | None:
        token = _token_getter()
        if not token:
            return None
        return fetch_issue_title(owner, repo, number, token=token)

    return run_event_hook(
        _SCRIPT_NAME,
        lambda event: decide(
            event,
            repo_getter=_detect_repo,
            token_getter=_token_getter,
            title_getter=_title_getter,
        ),
        auditable=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
