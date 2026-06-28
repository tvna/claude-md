#!/usr/bin/env python3
"""Shared client-side commit-signature detection (the gpgsig-header model).

Refs #2138, #1959. This repository configures ``commit.gpgsign=true`` with an
ssh signing key and rejects unsigned commits at the ``main`` ruleset
(``required_signatures``). Two client-side gates aim to surface an unsigned
commit before the merge-time block:

- ``scripts/preflight_push_unsigned_commits.py`` (#2138): a PreToolUse Bash hook
  that denies a ``git push`` whose range carries an unsigned commit, but only
  when the push is issued through the agent's Bash tool.
- ``scripts/preflight_signed_commits.py`` (#1959): a ``.githooks/pre-push``
  preflight step that inspects ``origin/main..HEAD`` regardless of how the push
  was invoked (it catches the Codex Desktop/GUI push that never passes through
  the Bash tool).

Both need the same answer to one question ("is this commit signed?"), so the
rule lives here once rather than being defined twice and drifting (the #1962
class: a second copy that missed the ``gpgsig-sha256`` spelling).

Why a header-presence check rather than ``git verify-commit`` / ``git log
--format=%G?`` (primary-source finding; CLAUDE.md sections 1 and 2, live proof
over plan-time intent). The remote worktrees these gates run in do not configure
``gpg.ssh.allowedSignersFile``, so ``git verify-commit`` returns non-zero for a
perfectly-signed commit ("allowedSignersFile needs to be configured"), and
``%G?`` collapses that same "cannot verify" outcome to ``N``, indistinguishable
from a genuinely unsigned commit. Either signal would false-positive on every
legitimate signed push in exactly the environment these gates target. The raw
``gpgsig`` header is present iff the committer produced a signature, independent
of whether this host can verify it, so it is the only sound client-side signal
for the unsigned-commit failure. Authenticity of a present signature is left to
GitHub's server-side ``required_signatures`` ruleset, the backstop that can
actually verify it.

Tested by ``tests/test_commit_signing.py``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

# A runner takes a git argv (without the leading ``git``) and returns the
# completed process, mirroring _git.run_git's signature so it is interchangeable.
Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def is_unsigned(runner: Runner, sha: str) -> bool:
    """Return True when *sha*'s raw object carries no ``gpgsig`` header.

    Reads the commit object with ``git cat-file commit`` and scans only its
    header section (the lines before the first blank line, which separates the
    headers from the commit message) for a line beginning ``gpgsig`` (the
    header git writes when a commit is signed, covering both ``gpgsig`` and the
    sha-256 ``gpgsig-sha256`` spelling). Stopping at the blank line keeps a
    commit MESSAGE that merely mentions ``gpgsig`` from masking an unsigned
    commit. A subprocess error or a non-zero exit is reported as "not unsigned"
    so an infrastructure failure fails open rather than denying a push it could
    not actually evaluate (CLAUDE.md section 4).
    """
    try:
        result = runner(["cat-file", "commit", sha])
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        if not line:
            break  # the empty line ends the header section; the message follows
        if line.startswith("gpgsig"):
            return False  # a signature header is present
    return True
