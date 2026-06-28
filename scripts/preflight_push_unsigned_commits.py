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
- It finds every ``git push`` in the command, including one chained after
  another command (``git commit -m x && git push ...``), by splitting the
  command at shell command-position boundaries, and inspects EVERY refspec each
  push ships (``[<repository> [<refspec>...]]``), resolving each refspec's local
  SOURCE ref the way git does (``a:b`` -> local ``a``; a bare ``b`` -> local
  ``b``, the same-named local ref, NOT ``HEAD``; ``HEAD:b`` -> local ``HEAD``; a
  ``:b`` deletion ships nothing and is skipped).
- It resolves the commits each refspec would ship with ``git rev-list``: the
  range ``<remote-tracking-sha>..<local-sha>`` when the target branch already
  exists on the remote, or (a new branch whose remote sha is all-zeros) the
  commits reachable from the local tip but not from any remote ref. Each commit
  is classified by the PRESENCE of a ``gpgsig`` header in its raw object
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
from pathlib import PurePosixPath
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

# Cheap pre-filter: only commands that mention a git push are worth segmenting
# and tokenizing. A false hit (e.g. the words inside a quoted string) is harmless
# because the command-position-aware segment parser then finds no push spec.
_PUSH_MENTION_RE = re.compile(r"\bgit\s+push\b")

# Shell separators that begin a new command position, so a ``git push`` chained
# after another command (``git commit -m x && git push ...``) is still detected
# (Codex review on #2140: the gate must fire on the chained remote-session flow,
# not only when ``git push`` leads the line).
_SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n&]")

# A leading ``NAME=value`` environment assignment to skip before the command.
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Git global options taking a separate value token (``git -c k=v push``,
# ``git -C path push``); the token after them is the value, not the subcommand.
_GIT_VALUE_OPTS: frozenset[str] = frozenset({"-c", "-C"})

# A new-branch push reports an all-zero remote sha in git's pre-push protocol;
# the same sentinel is produced here when the remote-tracking ref does not
# resolve. Either 40-hex (sha-1) or 64-hex (sha-256) all-zeros.
_ALL_ZEROS_RE = re.compile(r"^0{40}(?:0{24})?$")

# Command surface this hook acts on, read by scan_hook_predicate_surface_drift.py
# to verify the Bash(*git push*) if: predicate admits it (a narrower predicate
# would silently skip a command the script handles, the PR #2120 class). Refs #2133.
HOOK_GIT_SUBCOMMANDS = frozenset({"push"})

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


def _basename(token: str) -> str:
    """Return the command basename so ``/usr/bin/git`` classifies as ``git``."""
    return PurePosixPath(token.strip().strip("'\"")).name


def _push_args_in_segment(segment: str) -> list[str] | None:
    """Return the args after ``push`` when *segment* is a ``git push``, else None.

    Tokenizes one shell segment and recognizes a push even behind a leading
    ``VAR=value`` env assignment, an optional ``rtk`` wrapper (the rtk
    auto-rewrite prefix, Refs #1199), and git global options
    (``git -c k=v push``, ``git -C path push``). A segment whose leading command
    is not ``git``, or whose first non-option token is not ``push``, returns None
    so a non-push segment is skipped.
    """
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return None
    idx = 0
    while idx < len(tokens) and _ASSIGN_RE.match(tokens[idx]):
        idx += 1
    if idx < len(tokens) and _basename(tokens[idx]) == "rtk":
        idx += 1
    if idx >= len(tokens) or _basename(tokens[idx]) != "git":
        return None
    rest = tokens[idx + 1 :]
    j = 0
    while j < len(rest) and rest[j].startswith("-"):
        j += 2 if rest[j] in _GIT_VALUE_OPTS else 1
    if j >= len(rest) or rest[j] != "push":
        return None
    return rest[j + 1 :]


def _specs_from_push_args(args: list[str]) -> list[tuple[str, str, str]]:
    """Return ``(remote, local_ref, remote_ref)`` for EVERY refspec in *args*.

    A push accepts ``[<repository> [<refspec>...]]`` (Codex review on #2140:
    inspect every refspec, not only the first). Each refspec resolves its local
    SOURCE ref the way git does:

    - ``a:b``      -> local ``a``, remote ``b``
    - ``b`` (bare) -> local ``b``, remote ``b`` (git pushes the local ref of the
      same name, NOT ``HEAD``; Codex review on #2140)
    - ``HEAD:b``   -> local ``HEAD``, remote ``b`` (only an explicit HEAD source
      uses HEAD)
    - ``:b``       -> a deletion; ships no commit, so it is skipped
    - a leading ``+`` (force) is stripped before splitting

    Returns an empty list when no explicit refspec is present (``git push`` /
    ``git push origin``); the remote ref is then unknown from the command alone
    and the caller falls open.
    """
    positionals: list[str] = []
    i = 0
    end_of_opts = False
    while i < len(args):
        tok = args[i]
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
        return []  # no explicit refspec

    remote = positionals[0]
    specs: list[tuple[str, str, str]] = []
    for raw in positionals[1:]:
        refspec = raw[1:] if raw.startswith("+") else raw
        if ":" in refspec:
            local_ref, remote_ref = refspec.split(":", 1)
            if not local_ref:
                continue  # deletion (:dst); ships nothing
        else:
            local_ref = remote_ref = refspec
        if not remote_ref:
            continue
        specs.append((remote, local_ref, remote_ref))
    return specs


def _iter_push_specs(command: str) -> list[tuple[str, str, str]]:
    """Return every ``(remote, local_ref, remote_ref)`` the *command* would push.

    Splits *command* at shell command-position boundaries so a ``git push``
    chained after another command is still found, and unions the refspecs of
    every push segment. An empty list means no inspectable push target.
    """
    specs: list[tuple[str, str, str]] = []
    for segment in _SEGMENT_SPLIT.split(command):
        segment = segment.strip()
        if "push" not in segment:
            continue  # skip the shlex tokenization for a non-push segment
        push_args = _push_args_in_segment(segment)
        if push_args is None:
            continue
        specs.extend(_specs_from_push_args(push_args))
    return specs


def _rev_parse(runner: _Runner, ref: str) -> str | None:
    """Return the resolved sha of *ref*, or None when it does not resolve."""
    try:
        result = runner(["rev-parse", "--verify", "--quiet", ref])
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _commits_for_spec(
    runner: _Runner, remote: str, local_ref: str, remote_ref: str
) -> list[str] | None:
    """Return the shas one refspec would ship, or None when undeterminable.

    Resolves the local SOURCE sha and the remote-tracking sha. When the
    remote-tracking ref resolves, the range is ``<remote>..<local>``; when it
    does not (a new branch, all-zeros remote sha) the range is the commits
    reachable from the local tip but not from the target remote's refs. None signals
    "could not determine" (the caller skips this spec, fail-open); an empty list
    means "nothing new to ship".
    """
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
        # already on the TARGET remote's refs. Scoping to ``--remotes=<remote>``
        # (not the bare ``--remotes``, which excludes commits on ANY remote)
        # keeps an unsigned commit that exists on a different remote but is new
        # to this push's target from being silently skipped, and matches the
        # target-remote scope of the existing-branch range above.
        rev_args = ["rev-list", local_sha, "--not", f"--remotes={remote}"]

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
        if not line:
            break  # the empty line ends the header section; the message follows
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
    if not _PUSH_MENTION_RE.search(command):
        return None
    if _ACK_MARKER in command:
        return None

    specs = _iter_push_specs(command)
    if not specs:
        return None  # no inspectable push target; fail-open

    # Union the commits across every refspec, de-duplicating shared shas so each
    # commit is verified once. A spec that cannot be resolved is skipped (it
    # contributes no commits, fail-open for that spec) rather than failing the
    # whole push open, so a determinable unsigned refspec is still caught.
    unsigned: list[str] = []
    seen: set[str] = set()
    for remote, local_ref, remote_ref in specs:
        commits = _commits_for_spec(runner, remote, local_ref, remote_ref)
        if not commits:
            continue
        for sha in commits:
            if sha in seen:
                continue
            seen.add(sha)
            if _is_unsigned(runner, sha):
                unsigned.append(sha)
    if not unsigned:
        return None
    return _deny(unsigned)


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_event_hook("preflight_push_unsigned_commits", decide, auditable=False)


if __name__ == "__main__":
    raise SystemExit(main())
