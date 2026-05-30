#!/usr/bin/env python3
"""PreToolUse hook: block git push to non-session branches in remote sessions.

Refs #785. In remote execution environments (CLAUDE_CODE_REMOTE=true) the
transport layer only permits pushes to the branch that was checked out at
session start.  A push to any other remote ref returns HTTP 403 with no
diagnostic, giving the agent no signal about which branch is permitted.

This hook intercepts every Bash ``git push`` command, parses the explicit
remote-side refspec, and denies the push when it targets a branch other
than the session branch stored in .git/CLAUDE_SESSION_BRANCH by
check_session_branch.py.

Fail-open: any hook error, missing session-branch file, or push without
an explicit refspec exits 0 so the push proceeds and CI acts as backstop.

Architecture mirrors preflight_push_base.py:
* Pure decide() surface plus a thin main() entry.
* Injected runner for subprocess calls enables unit testing without I/O.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
_SESSION_BRANCH_FILE = REPO_ROOT / ".git" / "CLAUDE_SESSION_BRANCH"
_GIT_PUSH_RE = re.compile(r"(?m)^\s*git\s+push\b")
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


def _read_session_branch() -> str | None:
    try:
        branch = _SESSION_BRANCH_FILE.read_text().strip()
        return branch if branch else None
    except OSError:
        return None


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
                i += 1  # unknown flag — skip conservatively
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

    # local:remote form — return remote side.
    if ":" in refspec:
        return refspec.split(":", 1)[1]

    return refspec


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny dict when a push targets a non-session branch, else None."""
    if os.environ.get(_REMOTE_ENV_VAR, "").lower() != "true":
        return None

    if event.get("tool_name") != "Bash":
        return None

    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_PUSH_RE.search(command):
        return None

    session_branch = _read_session_branch()
    if not session_branch:
        return None  # fail-open: session branch not recorded yet

    remote_ref = _extract_push_remote_ref(command)
    if not remote_ref:
        return None  # no explicit refspec — fail-open

    if remote_ref in (session_branch, "HEAD"):
        return None

    return _deny(
        f"Blocked by scripts/preflight_push_session_branch.py: "
        f"this remote session only permits pushes to '{session_branch}'. "
        f"The push targets '{remote_ref}'.\n\n"
        f"Use the refspec syntax to map your local branch to the session branch:\n"
        f"  git push origin <local-branch>:{session_branch}\n\n"
        "Refs #785."
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::preflight_push_session_branch: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0
    if not isinstance(event, dict):
        return 0
    output = decide(event)
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
