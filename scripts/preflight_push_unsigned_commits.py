#!/usr/bin/env python3
"""PreToolUse hook: deny a Bash ``git push`` that ships an unsigned commit.

Refs #2138. This repository configures ``commit.gpgsign=true`` with an ssh
signing key, and two layers aim to keep an unsigned commit from reaching
``main``:

- ``scripts/gate_unsigned_commit_bash.py`` denies a ``git`` command that
  *disables* signing for a single invocation (``-c commit.gpgsign=false`` /
  ``--no-gpg-sign``).
- ``.github/rulesets/main.json`` (``required_signatures``) refuses to merge an
  unsigned commit into ``main``.

A gap remained between them. The Bash gate inspects the command text for a
signing-bypass flag; it never checks whether the commit a push carries is
*actually signed*. The Codex Desktop worktree does not carry the SSH signing
key into the environment, so even with ``commit.gpgsign=true`` configured a
plain ``git commit`` produces an UNSIGNED commit (evidence: PR #1767 / #1766,
commits cbf2dbb / 4cad8d4 authored from the worktree's default git identity).
That commit then pushes cleanly, and the ruleset only refuses the eventual
merge; by then the branch base is unsigned and ruleset-unrewritable (force-push
and branch deletion are both blocked).

This gate closes that gap at the push boundary. It is the agent-Bash-push
sibling of ``scan_workflow_unsigned_commit.py`` (which guards the CI-side bot
``git push`` authoring path); together they cover both ways an unsigned commit
can reach a branch (the agent's Bash push here, and a workflow ``run:`` push
there) for the same unsigned-commit category (CLAUDE.md section 3).

Design (CLAUDE.md section 4: make wrong actions hard, right actions easy):

- The gate is active only in a remote session (``CLAUDE_CODE_REMOTE`` /
  ``CODEX_CODE_REMOTE``), where signing is the non-interactive signer-program
  path the Codex worktree breaks; outside a remote session it fails open
  unconditionally so a local-dev push is never gated by this hook.
- It resolves the commits a push would ship with ``git rev-list``: the range
  ``<remote-tracking-sha>..<local-sha>`` when the target branch already exists
  on the remote, or (a new branch whose remote sha is all-zeros) the commits
  reachable from the local tip but not from any remote ref. Each commit is
  classified by the PRESENCE of a ``gpgsig`` header in its raw object
  (``git cat-file commit``); a commit with no signature header is unsigned and
  the push is denied, naming the offending commits.

Why a header-presence check rather than ``git verify-commit`` (primary-source
finding; CLAUDE.md sections 1 and 2, live proof over plan-time intent). The
remote worktree this gate runs in does not configure
``gpg.ssh.allowedSignersFile``, so ``git verify-commit`` returns non-zero for a
perfectly-signed commit ("allowedSignersFile needs to be configured"), and
``git log --format=%G?`` collapses that same "cannot verify" outcome to ``N``,
indistinguishable from a genuinely unsigned commit. Either signal would
false-positive on every legitimate signed push in exactly the environment this
gate targets. The raw ``gpgsig`` header is present iff the committer produced a
signature, independent of whether this host can verify it, so it is the only
sound client-side signal for the Codex unsigned-commit failure (the same
signal ``check_commit_signing_ready.py`` inspects). Authenticity of a present
signature is left to GitHub's server-side ``required_signatures`` ruleset, the
backstop that can actually verify it.
- Escape hatch: append ``# unsigned-ack`` to the command when an unsigned push
  is genuinely intended and reviewed. The marker reuses the opt-in established
  by ``scan_workflow_unsigned_commit`` / ``gate_unsigned_commit_bash`` for the
  same category (CLAUDE.md section 4: one category, one control).
- Fail-open is wide and deliberate: a non-remote session, an unparseable push
  command, an inability to resolve the local or remote sha, an empty range, or
  any git/subprocess error all pass through (return None) so a hook bug never
  wedges a push; the ruleset stays as the backstop. The gate fails loud only by
  denying a push it has positively shown to carry an unsigned commit.

Contract:
- Inputs: a PreToolUse hook event as JSON on stdin (``tool_name`` plus
  ``tool_input.command`` for the Bash matcher). No flags.
- Outputs: a JSON deny decision on stdout when the push ships an unsigned
  commit; nothing on stdout on pass-through. Always exits 0.
- Failure policy: fail-open at every boundary except a demonstrated unsigned
  commit, which is denied (CLAUDE.md section 4).

Tested by ``tests/test_preflight_push_unsigned_commits.py``. Refs #2138, #1713.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Callable
from typing import Any

from _git import run_git
from _hook_runtime import build_deny, run_event_hook

# Both remote signals, mirroring check_commit_signing_ready.py so the gate is
# operative under Claude Code on the Web AND Codex/Devin cloud sessions; the
# Codex worktree is the environment whose missing signing key motivates it.
_REMOTE_ENV_VARS = ("CLAUDE_CODE_REMOTE", "CODEX_CODE_REMOTE")

# Opt-in marker for a reviewed, intentional unsigned push. Reuses the marker
# established by scan_workflow_unsigned_commit / gate_unsigned_commit_bash for
# the same unsigned-commit category.
_ACK_MARKER = "# unsigned-ack"

# Detect a leading ``git push``, optionally prefixed by ``rtk`` when the rtk
# auto-rewrite PreToolUse hook has rewritten ``git push`` -> ``rtk git push``
# (Refs #1199). Keeping the prefix optional means the gate fires on both forms.
_GIT_PUSH_RE = re.compile(r"(?m)^\s*(?:rtk\s+)?git\s+push\b")

# A new-branch push reports an all-zero remote sha in git's pre-push protocol;
# the same sentinel is produced here when the remote-tracking ref does not
# resolve. Either 40-hex (sha-1) or 64-hex (sha-256) all-zeros.
_ALL_ZEROS_RE = re.compile(r"^0{40}(?:0{24})?$")

_GIT_TIMEOUT_SECONDS = 30

# Flags consuming no extra token (mirrors preflight_push_session_branch).
_FLAGS_NO_VALUE: frozenset[str] = frozenset({
    "-f", "--force", "--force-with-lease", "-n", "--dry-run",
    "--tags", "--follow-tags", "--atomic", "--no-atomic",
    "-d", "--delete", "--prune", "--mirror", "--no-mirror",
    "-q", "--quiet", "-v", "--verbose", "--progress",
    "--all", "--verify", "--no-verify",
    "-u", "--set-upstream",
})

# Flags consuming one extra token as their value.
_FLAGS_WITH_VALUE: frozenset[str] = frozenset({
    "-o", "--push-option",
    "--receive-pack", "--exec", "--repo", "--recurse-submodules",
    "--signed",
})

# A runner takes a git argv (without the leading ``git``) and returns the
# completed process, mirroring _git.run_git's signature so it is the default.
_Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` with a bounded timeout (the production runner)."""
    return run_git(args, timeout=_GIT_TIMEOUT_SECONDS)


def _is_remote() -> bool:
    """Return True when either remote-session signal is set to ``true``."""
    return any(os.environ.get(var, "").lower() == "true" for var in _REMOTE_ENV_VARS)


def _parse_push_target(command: str) -> tuple[str, str, str] | None:
    """Return ``(remote, local_ref, remote_ref)`` for a push, or None.

    ``remote`` defaults to ``origin`` when the push names none. The refspec's
    local side defaults to ``HEAD`` (e.g. ``git push origin branch`` pushes
    ``HEAD`` to ``branch``); a ``local:remote`` refspec splits into its two
    sides. When no refspec is present (``git push`` / ``git push origin``) the
    remote ref is unknown from the command alone, so None is returned and the
    caller falls open. Examples::

        git push origin feat/x        -> ("origin", "HEAD", "feat/x")
        git push -u origin feat/x     -> ("origin", "HEAD", "feat/x")
        git push origin a:b           -> ("origin", "a", "b")
        git push origin HEAD:b        -> ("origin", "HEAD", "b")
        git push                      -> None
        git push origin               -> None
    """
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

    if len(positionals) < 2:
        return None  # no explicit refspec; fail-open

    remote = positionals[0]
    refspec = positionals[1]
    if refspec.startswith("+"):
        refspec = refspec[1:]

    if ":" in refspec:
        local_ref, remote_ref = refspec.split(":", 1)
        local_ref = local_ref or "HEAD"
    else:
        local_ref, remote_ref = "HEAD", refspec
    if not remote_ref:
        return None
    return remote, local_ref, remote_ref


def _rev_parse(runner: _Runner, ref: str) -> str | None:
    """Return the resolved sha of *ref*, or None when it does not resolve."""
    try:
        result = runner(["rev-parse", "--verify", "--quiet", ref])
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _commits_in_push(runner: _Runner, command: str) -> list[str] | None:
    """Return the shas a push would ship, or None when undeterminable.

    Resolves the push target from *command*, the local tip sha, and the
    remote-tracking sha. When the remote-tracking ref resolves, the range is
    ``<remote>..<local>``; when it does not (a new branch, all-zeros remote
    sha) the range is the commits reachable from the local tip but not from any
    remote ref. None signals "could not determine" (fail-open); an empty list
    means "nothing new to ship" (also a pass-through, distinct from a failure).
    """
    target = _parse_push_target(command)
    if target is None:
        return None
    remote, local_ref, remote_ref = target

    local_sha = _rev_parse(runner, local_ref)
    if local_sha is None:
        return None

    remote_sha = _rev_parse(runner, f"refs/remotes/{remote}/{remote_ref}")
    if remote_sha is not None and _ALL_ZEROS_RE.match(remote_sha):
        remote_sha = None

    if remote_sha is not None:
        rev_args = ["rev-list", f"{remote_sha}..{local_sha}"]
    else:
        # New branch: every commit reachable from the local tip that is not
        # already on a remote ref. This bounds the scan to the new work rather
        # than re-verifying the whole history.
        rev_args = ["rev-list", local_sha, "--not", "--remotes"]

    try:
        result = runner(rev_args)
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_unsigned(runner: _Runner, sha: str) -> bool:
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
        if not line.strip():
            break  # end of header section; the message follows
        if line.startswith("gpgsig"):
            return False  # a signature header is present
    return True


def _deny(unsigned: list[str]) -> dict[str, Any]:
    shown = ", ".join(s[:12] for s in unsigned[:10])
    more = "" if len(unsigned) <= 10 else f" (and {len(unsigned) - 10} more)"
    return build_deny(
        "Blocked by scripts/preflight_push_unsigned_commits.py: this push ships "
        f"{len(unsigned)} UNSIGNED commit(s): {shown}{more}.\n\n"
        "This repository requires signed commits (commit.gpgsign=true with an ssh "
        "signing key) and rejects unsigned commits at the main ruleset. A commit "
        "lands unsigned most often because the worktree has no signing key (the "
        "Codex Desktop environment does not carry one in), so commit.gpgsign=true "
        "cannot actually produce a signature.\n\n"
        "Repair: confirm signing works, then re-create the commits so they are "
        "signed (for example `git rebase --exec 'git commit --amend --no-edit -S' "
        "<base>` while signing is healthy), and re-push. Verify readiness with:\n"
        "  python3 scripts/check_commit_signing_ready.py check\n\n"
        "If an unsigned push is genuinely intended and reviewed, append an "
        f"'{_ACK_MARKER}' comment to the command to opt in. Refs #2138, #1713."
    )


def decide(
    event: dict[str, Any],
    *,
    runner: _Runner = _default_runner,
) -> dict[str, Any] | None:
    """Return a deny dict when a push ships an unsigned commit, else None."""
    if not _is_remote():
        return None
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_PUSH_RE.search(command):
        return None
    if _ACK_MARKER in command:
        return None

    commits = _commits_in_push(runner, command)
    if not commits:
        return None  # undeterminable or nothing new to ship; fail-open

    unsigned = [sha for sha in commits if _is_unsigned(runner, sha)]
    if not unsigned:
        return None
    return _deny(unsigned)


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_event_hook("preflight_push_unsigned_commits", decide, auditable=False)


if __name__ == "__main__":
    raise SystemExit(main())
