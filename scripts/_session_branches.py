#!/usr/bin/env python3
"""Shared format and authorization predicate for the session-branch set.

Refs #1513, #1181, #785. In remote execution environments the transport
layer restricts git pushes to branches that were checked out at a session
start. ``check_session_branch.py`` records those branches and the
``preflight_{push,commit}_session_branch.py`` gates enforce the limit.

The lock was originally a single overwritten branch name, which made the
workflow non-continuable whenever more than one branch was legitimately in
play -- paired work (codex/claude alternating across sessions) or a
post-merge follow-up branch. This module replaces the single value with a
governed, multi-entry *authorized set*: the gate decision becomes a
conjunction (member of the set AND not a protected branch), not a single
equality.

Entries are added through exactly one governed path -- a new session
starting on a branch (``check_session_branch.append_branch``) -- so an
arbitrary branch the agent never started a session on stays unauthorized.

The set is persisted at ``.git/CLAUDE_SESSION_BRANCH`` as a newline-
delimited list. A legacy single-line file is a valid one-element set, so no
migration is required. A missing or empty file is the empty set, which the
gates treat as fail-open (an unrecorded session is unconstrained; CI and
server-side branch protection remain the backstop).
"""

from __future__ import annotations

import contextlib
from pathlib import Path

# Protected branches must never be authorized for a direct commit/push,
# even if a stale entry names one. Server-side branch protection is the
# real guard; this keeps the gate from ever appearing to bless main.
PROTECTED: frozenset[str] = frozenset({"main", "master"})


def read_authorized_set(path: Path) -> set[str]:
    """Return the authorized branch names recorded at ``path``.

    The file is newline-delimited, one branch per line. A missing or
    unreadable file yields the empty set so the gates fail open. Blank
    lines are ignored.
    """
    try:
        text = path.read_text()
    except OSError:
        return set()
    return {line.strip() for line in text.splitlines() if line.strip()}


def append_branch(path: Path, branch: str) -> None:
    """Append ``branch`` to the authorized set, de-duplicating.

    Fails open (never raises) when the file cannot be written, mirroring
    the SessionStart writer's contract: a broken write must not wedge a
    session. A blank branch or one already present is a no-op.
    """
    branch = branch.strip()
    if not branch or branch in read_authorized_set(path):
        return
    # A SessionStart seed may lack a trailing newline. Appending blindly
    # would concatenate the new branch onto the last entry, collapsing two
    # members into one corrupted authorization string. Insert a separator
    # when the existing content does not already end in a newline.
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        existing = ""
    separator = "" if (not existing or existing.endswith("\n")) else "\n"
    with contextlib.suppress(OSError), path.open("a", encoding="utf-8") as handle:
        handle.write(separator + branch + "\n")


def is_authorized(branch: str | None, authorized: set[str]) -> bool:
    """Return True when ``branch`` may receive a direct commit/push.

    A conjunction of factors, not a single equality: the branch must be a
    member of the governed authorized set AND must not be a protected
    branch. A protected branch is rejected even if a stale entry names it.
    """
    if not branch:
        return False
    if branch in PROTECTED:
        return False
    return branch in authorized
