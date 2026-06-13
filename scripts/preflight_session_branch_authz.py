#!/usr/bin/env python3
"""PreToolUse hook: block work on an unauthorized branch BEFORE it begins.

Refs #1658, #1632, #1181, #785. In remote execution environments
(CLAUDE_CODE_REMOTE=true) the transport layer only permits pushes to the
branches recorded at session start (the authorized set in
.git/CLAUDE_SESSION_BRANCH, written by check_session_branch.py).
``preflight_commit_session_branch.py`` already enforces that -- but only at
*commit* time, which is the last moment before push. #1658 traced a real
near-miss to exactly that gap: an agent created an unauthorized branch for a
follow-up task, implemented the full change (7 files, 255 tests passing), and
only learned the branch was unauthorized when the commit was blocked. The work
could not be pushed and had to be redone. This is the same class of defect as
the late-rebase loop (#1632): a deterministic gate that fires *after* the work
is done instead of in front of the operation it guards.

This hook shifts the same constraint left to the earliest point it can prevent
the wasted effort, across two trigger surfaces backed by ONE authorized set:

* Bash ``git switch``/``git checkout`` that CREATES (``-c``/``-C``/``--create``/
  ``--orphan`` for switch, ``-b``/``-B``/``--orphan`` for checkout) or SWITCHES
  to a branch outside the authorized set -> deny at the switch, before any work.
* ``Edit``/``Write``/``MultiEdit``/``NotebookEdit`` on a file inside the repo
  while the checked-out branch is unauthorized -> deny at the first edit. This
  is the catch-all: it does not depend on enumerating every switch syntax, so a
  branch change made through a form the Bash matcher misses (e.g. a plain
  ``git checkout <branch>``, a worktree, or a tool the regex does not parse) is
  still caught the moment the agent tries to modify a tracked file.

The commit-time gate and the push-time gate remain as backstops; this is a
left-shift, not a replacement, so the defense-in-depth layers stay intact.

Single source: the authorized set and the ``is_authorized`` predicate come from
``_session_branches.py`` -- byte-for-byte the same source the commit/push gates
read -- so the gates cannot drift. The current branch is read from .git/HEAD
(no subprocess), so ``decide`` is unit-testable without a live repository.

Fail-open: a non-remote environment, an empty authorized set, a detached/unknown
HEAD, an unresolvable switch target, or an edit to a path outside the repo all
exit without a decision so the tool call proceeds and the commit/push gates plus
CI act as backstop.

Contract:
- Inputs: a PreToolUse event dict -- a Bash ``command`` string, or an
  Edit/Write/MultiEdit/NotebookEdit ``file_path``/``notebook_path``.
- Outputs: nothing (pass-through), or a PreToolUse deny payload (build_deny).
- Failure policy: fails open (any error or ambiguity exits without a decision).
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

from _hook_runtime import build_deny, run_event_hook
from _session_branches import PROTECTED, is_authorized, read_authorized_set

REPO_ROOT = Path(__file__).resolve().parent.parent
_SESSION_BRANCH_FILE = REPO_ROOT / ".git" / "CLAUDE_SESSION_BRANCH"
_HEAD_FILE = REPO_ROOT / ".git" / "HEAD"
_REMOTE_ENV_VAR = "CLAUDE_CODE_REMOTE"
_HEAD_REF_PREFIX = "ref: refs/heads/"

# Tools that modify working-tree files. NotebookEdit carries its target in
# ``notebook_path`` rather than ``file_path``; both are handled.
_EDIT_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

# Split a command line into simple-command segments on shell control operators
# (``&&``/``||``/``;``/``|``/newline/subshell parens). The switch/checkout match
# is then anchored to a *segment start*, so a ``git switch``/``git checkout``
# that appears inside an argument or a commit message body -- e.g.
# ``git commit -m "... git switch -c x ..."`` -- is not mistaken for a real
# branch operation. This mirrors the line-anchored detection in
# preflight_push_session_branch.py; chained forms like
# ``git fetch && git checkout -b foo`` still match because the checkout begins
# its own segment.
_SEGMENT_SPLIT_RE = re.compile(r"[\n;|&()]+")
# Anchored at the segment head. The optional ``rtk`` prefix mirrors
# preflight_push_session_branch.py: the rtk auto-rewrite PreToolUse hook can
# prepend ``rtk`` to git commands (Refs #1199). Group 2 is the remaining args.
_GIT_SWITCH_HEAD_RE = re.compile(
    r"^(?:rtk\s+)?git\s+(switch|checkout)(?![\w-])\s*(.*)$", re.DOTALL
)

# Flags whose value IS the new branch name (a create). The next token (or the
# ``=`` value) names the branch to create.
_CREATE_FLAGS_SWITCH: frozenset[str] = frozenset({"-c", "-C", "--create", "--force-create", "--orphan"})
_CREATE_FLAGS_CHECKOUT: frozenset[str] = frozenset({"-b", "-B", "--orphan"})

# Flags that put HEAD in a detached state -- no branch target, so fail open.
_DETACH_FLAGS: frozenset[str] = frozenset({"-d", "--detach"})


def _read_authorized_branches() -> set[str]:
    return read_authorized_set(_SESSION_BRANCH_FILE)


def _current_branch() -> str | None:
    """Return the checked-out branch from .git/HEAD, or None.

    Returns None on a detached HEAD (no ``ref:`` prefix) or any read error so
    the caller fails open. Mirrors preflight_commit_session_branch._current_branch.
    """
    try:
        head = _HEAD_FILE.read_text().strip()
    except OSError:
        return None
    if not head.startswith(_HEAD_REF_PREFIX):
        return None  # detached HEAD -- fail-open
    branch = head[len(_HEAD_REF_PREFIX):].strip()
    return branch or None


def _resolve_target(verb: str, tokens: list[str]) -> tuple[str, str] | None:
    """Resolve a ``switch``/``checkout`` token list to ``(mode, branch)`` or None.

    ``mode`` is ``"create"`` (a ``-c``/``-b``/``--orphan`` style new branch) or
    ``"switch"`` (an existing branch the command moves HEAD to). Returns None
    when the command names no branch we can confidently resolve -- a detach, a
    plain ``git checkout <pathspec>`` (ambiguous file-vs-branch; left to the
    Edit/Write surface and the commit-time backstop), or an unparseable form --
    so the caller fails open.
    """
    create_flags = _CREATE_FLAGS_SWITCH if verb == "switch" else _CREATE_FLAGS_CHECKOUT
    positional: str | None = None
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "--":
            break  # everything after -- is a pathspec, not a branch
        if tok.startswith("-") and tok != "-":
            if tok in _DETACH_FLAGS:
                return None  # detached HEAD -- no branch target
            if "=" in tok:
                flag, value = tok.split("=", 1)
                if flag in create_flags:
                    return ("create", value) if value else None
                i += 1
                continue
            if tok in create_flags:
                # The new branch name is the next token; if it is missing or is
                # itself a flag, we cannot resolve it -> fail open.
                if i + 1 < n and not tokens[i + 1].startswith("-"):
                    return ("create", tokens[i + 1])
                return None
            i += 1  # unknown flag -- skip conservatively (assume no value)
            continue
        if positional is None and tok != "-":
            positional = tok
        i += 1

    # A bare ``git switch <branch>`` moves HEAD to an existing branch. A plain
    # ``git checkout <arg>`` is ambiguous (branch vs pathspec) and is NOT gated
    # here -- the Edit/Write surface and the commit-time gate cover it.
    if verb == "switch" and positional:
        return ("switch", positional)
    return None


def _iter_branch_targets(command: str) -> list[tuple[str, str]]:
    """Return every ``(mode, branch)`` a switch/checkout in *command* resolves to.

    Each simple-command segment is matched only at its head, so a switch/checkout
    that is really an argument to another command (a commit message, an echo)
    does not register as a branch operation.
    """
    targets: list[tuple[str, str]] = []
    for segment in _SEGMENT_SPLIT_RE.split(command):
        match = _GIT_SWITCH_HEAD_RE.match(segment.strip())
        if match is None:
            continue
        verb = match.group(1)
        try:
            tokens = shlex.split(match.group(2))
        except ValueError:
            continue  # unbalanced quotes -- fail open for this segment
        resolved = _resolve_target(verb, tokens)
        if resolved is not None:
            targets.append(resolved)
    return targets


def _target_hint(authorized: set[str]) -> str:
    """Return a pushable branch to suggest switching back to.

    Prefers a non-protected member (a protected branch can never receive a
    commit/push here), falling back to any member if the set holds only
    protected names.
    """
    pushable = sorted(b for b in authorized if b not in PROTECTED)
    return pushable[0] if pushable else sorted(authorized)[0]


def _deny_switch(mode: str, branch: str, authorized: set[str]) -> dict[str, Any]:
    authorized_list = ", ".join(sorted(authorized))
    hint = _target_hint(authorized)
    action = "create" if mode == "create" else "switch to"
    return build_deny(
        f"Blocked by scripts/preflight_session_branch_authz.py: this remote "
        f"session can only push to an authorized branch ({authorized_list}), but "
        f"you are about to {action} '{branch}', which is not authorized. Work done "
        f"there could not be pushed and would have to be redone -- the commit-time "
        f"and push-time gates would refuse it (this gate just surfaces the limit "
        f"earlier, before the work).\n\n"
        f"Do one of the following:\n"
        f"  - Stay on / switch back to an authorized branch: git switch {hint}\n"
        f"  - To work on a different branch, start a NEW remote session on it so "
        f"SessionStart authorizes it; a protected branch (e.g. main) is never "
        f"authorized for commits/pushes here.\n\n"
        f"Refs #1658, #1632, #785."
    )


def _deny_edit(current: str, authorized: set[str], path: str) -> dict[str, Any]:
    authorized_list = ", ".join(sorted(authorized))
    hint = _target_hint(authorized)
    return build_deny(
        f"Blocked by scripts/preflight_session_branch_authz.py: you are about to "
        f"edit '{path}' while on branch '{current}', which is not in this remote "
        f"session's authorized set ({authorized_list}). Any work committed here "
        f"could not be pushed and would have to be redone (the commit-time and "
        f"push-time gates would refuse it).\n\n"
        f"Switch back to an authorized branch before editing: git switch {hint}\n"
        f"To work on a different branch, start a NEW remote session on it so "
        f"SessionStart authorizes it.\n\n"
        f"Refs #1658, #1632, #785."
    )


def _is_within_repo(resolved: Path) -> bool:
    """Return True when *resolved* (an absolute path) lives inside the repo root."""
    return resolved == REPO_ROOT or REPO_ROOT in resolved.parents


def _decide_bash(command: str) -> dict[str, Any] | None:
    authorized = _read_authorized_branches()
    if not authorized:
        return None  # fail-open: no session branch recorded yet
    for mode, branch in _iter_branch_targets(command):
        if not is_authorized(branch, authorized):
            return _deny_switch(mode, branch, authorized)
    return None


def _decide_edit(tool_input: dict[str, Any]) -> dict[str, Any] | None:
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw_path, str) or not raw_path:
        return None  # no target path -- fail open
    try:
        resolved = Path(raw_path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not _is_within_repo(resolved):
        return None  # edits outside the repo (e.g. /tmp plan files) are unconstrained

    authorized = _read_authorized_branches()
    if not authorized:
        return None  # fail-open: no session branch recorded yet
    current = _current_branch()
    if not current:
        return None  # detached HEAD / unknown -- fail-open
    if is_authorized(current, authorized):
        return None
    return _deny_edit(current, authorized, raw_path)


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny dict when work would begin on an unauthorized branch, else None."""
    if os.environ.get(_REMOTE_ENV_VAR, "").lower() != "true":
        return None

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None

    if tool_name == "Bash":
        return _decide_bash(str(tool_input.get("command") or ""))
    if tool_name in _EDIT_TOOLS:
        return _decide_edit(tool_input)
    return None


def main(argv: list[str] | None = None) -> int:
    del argv
    # auditable=False: a security/governance boundary gate, like the commit and
    # push session-branch gates -- CLAUDE_GATE_MODE=audit must not disable it.
    return run_event_hook("preflight_session_branch_authz", decide, auditable=False)


if __name__ == "__main__":
    raise SystemExit(main())
