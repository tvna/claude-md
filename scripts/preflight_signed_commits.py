#!/usr/bin/env python3
"""Fail before push when a commit in the push range is unsigned.

Refs #1959. This repository configures ``commit.gpgsign=true`` with an ssh
signing key and rejects unsigned commits at the ``main`` ruleset
(``required_signatures``). PRs #1744, #1766, #1767 were authored on macOS via
Codex Desktop with a broken signing setup: the operator skipped the repair and
pushed anyway, so the unsigned commits landed locally and were only blocked at
merge time by the server-side ruleset.

``scripts/preflight_push_unsigned_commits.py`` (#2138) closes one half of this
gap, but it is a PreToolUse Bash hook: it only sees a ``git push`` issued
through the agent's Bash tool. A Codex Desktop/GUI push never passes through
that tool. This step closes the residual half: a ``.githooks/pre-push``
preflight gate (registered in ``scripts/preflight_steps.py``) that inspects the
push range regardless of how the push was invoked.

Detection model (the gpgsig-header check, NOT git ``%G?``). Each commit is
unsigned iff its raw object carries no ``gpgsig`` header, decided by the shared
``_commit_signing.is_unsigned``. ``%G?`` / ``git verify-commit`` would
false-positive on every legitimate signed push in the remote worktrees these
gates run in, because those worktrees do not configure
``gpg.ssh.allowedSignersFile``; see ``_commit_signing`` for the full rationale.
The same shared helper backs #2138, so the signature rule has one definition.

Range. The commits inspected are ``origin/main..HEAD`` (``--base-ref`` overrides
the base, default ``origin/main``). This step runs AFTER ``preflight_branch_base``
in ``STEPS``, which fetches the live base, so the remote-tracking ref is already
current; a base ref that does not resolve is reported as a skip (that gate owns
base availability, and the server ruleset is the backstop) rather than failing
this gate on a condition another gate already covers.

Opt-in. An intentional, reviewed unsigned push opts out by setting
``PREFLIGHT_SIGNED_COMMITS_ACK`` to a value containing the marker ``# unsigned-ack``
on a line of its own. The match is anchored to a full line (never an unanchored
substring; the #1962 ACK bug, where a marker matched as a substring let an
unrelated string opt out) and reuses the ``# unsigned-ack`` convention #2138
established for the same unsigned-commit category (CLAUDE.md section 4: one
category, one control).

Contract:
- Inputs: no stdin. ``verify`` subcommand with optional ``--repo-root`` and
  ``--base-ref``. Reads ``PREFLIGHT_SIGNED_COMMITS_ACK`` for the opt-in.
- Outputs: exit 0 when every commit in range is signed (or the opt-in is set,
  or the range is undeterminable); exit 1 listing the unsigned commits.
- Failure policy: fail loud (exit 1) only on a positively-shown unsigned commit;
  an unresolvable range fails open (skip) so a transient git error never wedges
  a push when ``preflight_branch_base`` and the ruleset still guard the base.

Tested by ``tests/test_preflight_signed_commits.py``. Refs #1959, #2138.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from _commit_signing import is_unsigned
from _git import run_git

REPO_ROOT = Path(__file__).resolve().parent.parent

_GIT_TIMEOUT_SECONDS = 30

# Opt-in marker for a reviewed, intentional unsigned push, anchored to a full
# line so a substring can never opt out (the #1962 ACK bug). Reuses the
# ``# unsigned-ack`` marker #2138 established for the same category.
_ACK_ENV_VAR = "PREFLIGHT_SIGNED_COMMITS_ACK"
_ACK_MARKER_RE = re.compile(r"(?m)^# unsigned-ack$")

# A runner takes a git argv (without the leading ``git``) and returns the
# completed process, mirroring _git.run_git's signature so it is the default.
_Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class SignedCommitsResult:
    """Outcome of inspecting the push range for unsigned commits."""

    status: str  # "pass" | "fail" | "skip"
    detail: str
    unsigned: tuple[str, ...] = ()


def _make_runner(repo_root: Path) -> _Runner:
    """Return a git runner bound to *repo_root* with a bounded timeout."""

    def runner(git_args: list[str]) -> subprocess.CompletedProcess[str]:
        return run_git(git_args, cwd=repo_root, timeout=_GIT_TIMEOUT_SECONDS)

    return runner


def ack_present(env: Mapping[str, str] | None = None) -> bool:
    """Return True when the anchored ``# unsigned-ack`` opt-in marker is set.

    The marker must appear as a full line in ``PREFLIGHT_SIGNED_COMMITS_ACK``;
    an unanchored substring match (the #1962 bug) is deliberately not accepted.
    """
    value = (os.environ if env is None else env).get(_ACK_ENV_VAR, "")
    return _ACK_MARKER_RE.search(value) is not None


def commits_in_range(runner: _Runner, base_ref: str) -> list[str] | None:
    """Return the shas in ``<base_ref>..HEAD``, or None when undeterminable.

    None signals that the range could not be resolved (the base ref is missing,
    or a git error occurred); the caller treats it as a skip. An empty list
    means the range resolved with nothing to inspect (HEAD already contains the
    base), which is a pass.
    """
    try:
        result = runner(["rev-list", f"{base_ref}..HEAD"])
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_signed_commits(*, runner: _Runner, base_ref: str) -> SignedCommitsResult:
    """Inspect ``<base_ref>..HEAD`` and report whether every commit is signed."""
    commits = commits_in_range(runner, base_ref)
    if commits is None:
        return SignedCommitsResult(
            status="skip",
            detail=f"range {base_ref}..HEAD could not be resolved",
        )
    unsigned = tuple(sha for sha in commits if is_unsigned(runner, sha))
    if unsigned:
        return SignedCommitsResult(
            status="fail",
            detail=f"{len(unsigned)} of {len(commits)} commit(s) in {base_ref}..HEAD are unsigned",
            unsigned=unsigned,
        )
    return SignedCommitsResult(
        status="pass",
        detail=f"all {len(commits)} commit(s) in {base_ref}..HEAD are signed",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Reject a push whose range carries an unsigned commit.")
    verify.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to check.")
    verify.add_argument("--base-ref", default="origin/main", help="Base ref; range is <base-ref>..HEAD.")
    return parser


def cmd_verify(args: argparse.Namespace, *, runner: _Runner | None = None) -> int:
    if ack_present():
        print(f"OK: signed-commit check opted out via {_ACK_ENV_VAR} (# unsigned-ack).")
        return 0

    if runner is None:
        runner = _make_runner(Path(args.repo_root))
    result = check_signed_commits(runner=runner, base_ref=args.base_ref)

    if result.status == "pass":
        print(f"OK: {result.detail}")
        return 0
    if result.status == "skip":
        print(
            f"SKIP: {result.detail}; deferring to preflight_branch_base and the "
            "server-side required_signatures ruleset.",
            file=sys.stderr,
        )
        return 0

    print("::error::This push includes UNSIGNED commit(s).", file=sys.stderr)
    print(f"reason: {result.detail}", file=sys.stderr)
    for sha in result.unsigned:
        print(f"  unsigned: {sha}", file=sys.stderr)
    print(
        "repair: confirm signing works, then re-create the commits so they are "
        "signed (e.g. git rebase --exec 'git commit --amend --no-edit -S' "
        f"{args.base_ref}) and re-push. Verify readiness with:",
        file=sys.stderr,
    )
    print("  python3 scripts/check_commit_signing_ready.py check", file=sys.stderr)
    print(
        f"If an unsigned push is genuinely intended and reviewed, set "
        f"{_ACK_ENV_VAR} to a value containing a '# unsigned-ack' line to opt in.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "verify":
        return cmd_verify(args)
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
