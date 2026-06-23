#!/usr/bin/env python3
"""PreToolUse hook: block git push to non-session branches in remote sessions.

Refs #785. In remote execution environments (CLAUDE_CODE_REMOTE=true) the
transport layer only permits pushes to the branch that was checked out at
session start.  A push to any other remote ref returns HTTP 403 with no
diagnostic, giving the agent no signal about which branch is permitted.

This hook intercepts every Bash ``git push`` command, parses the explicit
remote-side refspec, and denies the push when the target is not in the
authorized branch set recorded in .git/CLAUDE_SESSION_BRANCH by
check_session_branch.py. The decision is a conjunction (member of the set
AND not a protected branch), not a single equality, so paired work and
post-merge follow-up branches stay continuable without re-opening a path
to a prior session's branch (Refs #1513).

Fail-open: any hook error, an empty authorized set, or a push without an
explicit refspec exits 0 so the push proceeds and CI acts as backstop.

Architecture mirrors preflight_push_base.py:
* Pure decide() surface plus a thin main() entry.
* Injected runner for subprocess calls enables unit testing without I/O.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

from _hook_runtime import build_deny, run_event_hook
from _session_branches import is_authorized, read_authorized_set

REPO_ROOT = Path(__file__).resolve().parent.parent
_SESSION_BRANCH_FILE = REPO_ROOT / ".git" / "CLAUDE_SESSION_BRANCH"
# Optional ``rtk`` prefix: the rtk auto-rewrite PreToolUse hook rewrites
# ``git push`` -> ``rtk git push`` (Refs #1199), so the gate must fire on both.
_GIT_PUSH_RE = re.compile(r"(?m)^\s*(?:rtk\s+)?git\s+push\b")
_REMOTE_ENV_VAR = "CLAUDE_CODE_REMOTE"

# Flags that consume no additional token.
_FLAGS_NO_VALUE: frozenset[str] = frozenset({
    "-f", "--force", "--force-with-lease", "-n", "--dry-run",
    "--tags", "--follow-tags", "--atomic", "--no-atomic",
    "-d", "--delete", "--prune", "--mirror", "--no-mirror",
    "-q", "--quiet", "-v", "--verbose", "--progress",
    "--all", "--verify", "--no-verify",
    # -u/--set-upstream records the upstream relationship but does not
    # consume a separate value token; it is a boolean flag.
    "-u", "--set-upstream",
})

# Flags that consume one additional token as their value.
_FLAGS_WITH_VALUE: frozenset[str] = frozenset({
    "-o", "--push-option",
    "--receive-pack", "--exec", "--repo", "--recurse-submodules",
    "--signed",
})


def _read_authorized_branches() -> set[str]:
    return read_authorized_set(_SESSION_BRANCH_FILE)


def _extract_push_remote_ref(command: str) -> str | None:
    """Return the explicit remote-side ref of a git push command, or None.

    Returns None when no explicit refspec is present (fail-open).

    Examples::

        git push origin feat/x          -> "feat/x"
        git push -u origin feat/x       -> "feat/x"
        git push origin local:remote    -> "remote"
        git push origin HEAD:session/b  -> "session/b"
        git push                        -> None  (fail-open)
        git push origin                 -> None  (fail-open)
    """
    # Capture the push sub-command up to a shell operator or newline.
    m = re.search(r"git\s+push\b([^&;|\n]*)", command)
    if not m:
        return None

    try:
        tokens = shlex.split(m.group(1))
    except ValueError:
        return None

    positionals: list[str] = []
    i = 0
    end_of_opts = False
    while i < len(tokens):
        tok = tokens[i]
        if not end_of_opts and tok == "--":
            end_of_opts = True
            i += 1
            continue
        if not end_of_opts and tok.startswith("-"):
            if "=" in tok or tok in _FLAGS_NO_VALUE:
                i += 1
            elif tok in _FLAGS_WITH_VALUE:
                i += 2
            else:
                i += 1  # unknown flag; skip conservatively
            continue
        positionals.append(tok)
        i += 1

    # positionals layout: [<remote>] [<refspec>...]
    # We need at least 2 positionals (remote + refspec) to have an explicit target.
    if len(positionals) < 2:
        return None

    refspec = positionals[1]
    if refspec.startswith("+"):
        refspec = refspec[1:]

    # local:remote form; return remote side.
    if ":" in refspec:
        return refspec.split(":", 1)[1]

    return refspec


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny dict when a push targets a non-session branch, else None."""
    if os.environ.get(_REMOTE_ENV_VAR, "").lower() != "true":
        return None

    if event.get("tool_name") != "Bash":
        return None

    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_PUSH_RE.search(command):
        return None

    authorized = _read_authorized_branches()
    if not authorized:
        return None  # fail-open: no session branch recorded yet

    remote_ref = _extract_push_remote_ref(command)
    if not remote_ref:
        return None  # no explicit refspec; fail-open

    if remote_ref == "HEAD" or is_authorized(remote_ref, authorized):
        return None

    authorized_list = ", ".join(sorted(authorized))
    target_hint = sorted(authorized)[0]
    return build_deny(
        f"Blocked by scripts/preflight_push_session_branch.py: "
        f"this remote session only permits pushes to an authorized branch "
        f"({authorized_list}). The push targets '{remote_ref}'.\n\n"
        f"Map your local branch onto an authorized branch with a refspec:\n"
        f"  git push origin <local-branch>:{target_hint}\n\n"
        f"To authorize a different branch, start a new remote session on it "
        f"(SessionStart records it); a protected branch (e.g. main) is never "
        f"authorized here.\n\n"
        "Refs #1513, #785."
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_event_hook("preflight_push_session_branch", decide, auditable=False)


if __name__ == "__main__":
    raise SystemExit(main())
