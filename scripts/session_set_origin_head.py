#!/usr/bin/env python3
"""SessionStart hook: make ``refs/remotes/origin/HEAD`` resolvable.

Refs #2080. Remote-execution sessions clone the repository fresh, and the
clone does not populate the ``refs/remotes/origin/HEAD`` symbolic ref
(``git symbolic-ref refs/remotes/origin/HEAD`` exits 128). Tooling that
derives a review range from ``origin/HEAD`` (for example the
``/security-review`` and ``/code-review`` slash commands, whose default
diff command is ``git diff origin/HEAD...HEAD``) then fails on every such
session with::

    fatal: ambiguous argument 'origin/HEAD...': unknown revision or path

Per CLAUDE.md section 3 ("Push deterministic work into hooks ... never
substitute agent memory for an absent gate"), this hook establishes the
ref once, deterministically, instead of the per-session manual workaround
(re-running the diff against ``origin/main`` by hand).

Mechanism (offline, network-free, deterministic): the fetch refspec
``+refs/heads/*:refs/remotes/origin/*`` already populates
``refs/remotes/origin/main`` after clone, and the repository default branch
is ``main``. So when ``origin/HEAD`` is absent but ``origin/main`` exists,
point the symbolic ref at it::

    git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main

The chosen tradeoff (issue #2080) is the offline ``symbolic-ref`` rather
than ``git remote set-head origin --auto``: it is deterministic and adds no
per-session network round-trip, at the cost of assuming the default branch
is ``main`` (which the rulesets and workflows already encode). If a future
rename moves the default branch, ``set-head --auto`` is the documented
fallback; this hook stays offline and simply warns when ``origin/main`` is
absent.

Idempotent: a no-op when ``origin/HEAD`` already *resolves to a commit*.
The probe is ``git rev-parse --verify`` rather than ``git symbolic-ref``
on purpose: a symbolic ref left dangling by a pruned target (e.g. a stale
``refs/remotes/origin/master`` after a default-branch rename) satisfies
``symbolic-ref`` yet still makes ``git diff origin/HEAD...HEAD`` fail, so
treating "is a symref" as "is repaired" would no-op over a broken ref.
``rev-parse --verify`` is true only when the ref resolves to an object, so
an absent *or* dangling ``origin/HEAD`` is repaired by re-pointing it at
``origin/main`` (``symbolic-ref`` overwrites the stale target).

Fail-soft: a missing ``origin/main``, a non-git directory, or any git
error warns and exits 0 so session start is never aborted.

Tested by ``tests/test_session_set_origin_head.py``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any, Protocol

from _git import run_git

_ORIGIN_HEAD = "refs/remotes/origin/HEAD"
_ORIGIN_MAIN = "refs/remotes/origin/main"


class _CompletedLike(Protocol):
    returncode: int


# A git runner takes an argv list (no leading "git") and returns an object
# exposing ``returncode``. ``_git.run_git`` satisfies this; tests inject a
# fake so the branch logic is exercised without a real repository.
GitRunner = Callable[[list[str]], _CompletedLike]


def origin_head_resolves(run: GitRunner) -> bool:
    """Return True when ``refs/remotes/origin/HEAD`` resolves to a commit.

    Uses ``git rev-parse --verify`` rather than ``git symbolic-ref`` so a
    dangling symref (one whose target was pruned) reads as unresolved and
    gets repaired, instead of being mistaken for an already-good ref.
    """
    try:
        return run(["rev-parse", "--verify", "--quiet", _ORIGIN_HEAD]).returncode == 0
    except RuntimeError:
        return False


def origin_main_exists(run: GitRunner) -> bool:
    """Return True when ``refs/remotes/origin/main`` exists."""
    try:
        return run(["show-ref", "--verify", "--quiet", _ORIGIN_MAIN]).returncode == 0
    except RuntimeError:
        return False


def set_origin_head(run: GitRunner) -> bool:
    """Point ``origin/HEAD`` at ``origin/main``; return True on success."""
    try:
        return run(["symbolic-ref", _ORIGIN_HEAD, _ORIGIN_MAIN]).returncode == 0
    except RuntimeError:
        return False


def configure(run: GitRunner) -> dict[str, Any] | None:
    """Ensure ``origin/HEAD`` resolves; return hook output dict or None.

    Returns None on the idempotent no-op (already resolves) so a settled
    session stays silent. Otherwise returns a ``hookSpecificOutput`` dict
    carrying an ``additionalContext`` message: a confirmation when the ref
    was set, or a soft-fail warning when ``origin/main`` is absent or the
    ``symbolic-ref`` write fails. Never raises and never signals abort.
    """
    if origin_head_resolves(run):
        return None

    if not origin_main_exists(run):
        message = (
            f"WARNING: {_ORIGIN_HEAD} is unset and {_ORIGIN_MAIN} is absent "
            f"(or this is not a git repository); leaving origin/HEAD unset. "
            f"'git diff origin/HEAD...HEAD' will not resolve until origin/main "
            f"is fetched. Fallback if the default branch was renamed: "
            f"git remote set-head origin --auto"
        )
        return _context(message)

    if set_origin_head(run):
        message = (
            f"{_ORIGIN_HEAD} did not resolve; pointed it at {_ORIGIN_MAIN} so "
            f"'git diff origin/HEAD...HEAD' resolves this session."
        )
    else:
        message = (
            f"WARNING: could not set {_ORIGIN_HEAD}. Fix manually: "
            f"git symbolic-ref {_ORIGIN_HEAD} {_ORIGIN_MAIN}"
        )
    return _context(message)


def _context(message: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"additionalContext": message}}


def main() -> None:
    try:
        output = configure(run_git)
    except Exception:
        # Fail-soft: a broken git install must never wedge session start.
        sys.exit(0)

    if output is not None:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
