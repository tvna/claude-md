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

Range. The commits inspected are the ones the push actually ships. When the
``.githooks/pre-push`` hook bridges git's pre-push stdin into the environment
(``PREFLIGHT_PUSH_REFS``, plus the remote name in ``PREFLIGHT_PUSH_REMOTE``),
each updated ref is inspected over its own ``remote-oid..local-oid`` range, with
new-branch (all-zeros remote oid) and delete (all-zeros local oid) handling
shared with ``preflight_push_unsigned_commits.py`` (#2138) through
``_git.commits_to_push``. This closes the #2162 gaps the fixed range left: a
``git push origin other-branch`` while ``HEAD`` is on a signed branch is now
inspected, and a tag or non-HEAD push is no longer falsely blocked by unsigned
commits reachable only from ``HEAD``. Why the environment and not stdin: a
preflight ``verify`` step is dispatched by ``preflight_all.py`` with a fixed
argv and no stdin routed to it (the same reason the opt-in below is an env var),
so the hook is the only place that can read git's stdin, and it forwards it.

Fallback. With no ``PREFLIGHT_PUSH_REFS`` payload (a direct CLI ``verify`` run,
not via the hook) the commits inspected are ``origin/main..HEAD`` (``--base-ref``
overrides the base, default ``origin/main``). This step runs AFTER
``preflight_branch_base`` in ``STEPS``, which fetches the live base, so the
remote-tracking ref is already current; a base ref that does not resolve is
reported as a skip (that gate owns base availability, and the server ruleset is
the backstop) rather than failing this gate on a condition another gate already
covers.

Opt-in. A preflight ``verify`` step sees no Bash command line (unlike the
PreToolUse Bash gate #2138, which scans the command text for a ``# unsigned-ack``
comment), so an intentional, reviewed unsigned push opts out here through the
environment instead: set ``PREFLIGHT_SIGNED_COMMITS_ACK`` to a value carrying a
``# unsigned-ack`` line. The marker STRING matches #2138's, but the SURFACE
differs (an env var, not command text), so this is a sibling control for the
same unsigned-commit category, not literally the same control. The match is
anchored to a full line (tolerating a trailing CR), never an unanchored
substring (the #1962 ACK bug, where a substring match let an unrelated string
opt out). Because an exported env var persists across a session (wider than a
per-command marker), the opt-in is consulted ONLY when an unsigned commit is
actually found, and each bypass is logged as a loud ``::warning::`` so the wide
scope can never suppress a block silently (CLAUDE.md section 4: escape hatches
are loud). The opt-in stays session-scoped (an env var) even with the per-push
ref inspection added in #2162, since the surface is still an env var, not the
command text.

Contract:
- Inputs: ``verify`` subcommand with optional ``--repo-root`` and ``--base-ref``.
  Reads ``PREFLIGHT_PUSH_REFS`` / ``PREFLIGHT_PUSH_REMOTE`` (the pushed refs the
  pre-push hook bridged from stdin; absent for a direct CLI run) and
  ``PREFLIGHT_SIGNED_COMMITS_ACK`` for the opt-in. No stdin is read directly.
- Outputs: exit 0 when every commit in range is signed, when the range is
  undeterminable (skip), or when an unsigned commit is present but the opt-in
  bypasses it (logged loudly); exit 1 listing the unsigned commits otherwise.
- Failure policy: fail loud (exit 1) only on a positively-shown unsigned commit
  with no opt-in; an unresolvable range fails open (skip) so a transient git
  error never wedges a push when ``preflight_branch_base`` and the ruleset still
  guard the base.

Tested by ``tests/test_preflight_signed_commits.py``. Refs #1959, #2138, #2162.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from _commit_signing import is_unsigned
from _git import (
    _PUSH_REFS_ENV_VAR,  # noqa: F401  re-exported for tests (subject._PUSH_REFS_ENV_VAR)
    _PUSH_REMOTE_ENV_VAR,  # noqa: F401  re-exported for tests (subject._PUSH_REMOTE_ENV_VAR)
    PushRef,
    Runner,
    commits_for_pushed_refs,
    commits_in_range,
    make_runner,
    read_push_refs,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

_GIT_TIMEOUT_SECONDS = 30

# Opt-in marker for a reviewed, intentional unsigned push, anchored to a full
# line (a trailing CR tolerated) so a substring can never opt out (the #1962 ACK
# bug). Same marker STRING as #2138, but matched against an env var, not command
# text (a sibling control for the same category; see the module docstring).
_ACK_ENV_VAR = "PREFLIGHT_SIGNED_COMMITS_ACK"
_ACK_MARKER_RE = re.compile(r"(?m)^# unsigned-ack\r?$")


@dataclass(frozen=True)
class SignedCommitsResult:
    """Outcome of inspecting the push range for unsigned commits."""

    status: str  # "pass" | "fail" | "skip"
    detail: str
    unsigned: tuple[str, ...] = ()


def ack_present(env: Mapping[str, str] | None = None) -> bool:
    """Return True when the anchored ``# unsigned-ack`` opt-in marker is set.

    The marker must appear as a full line (a trailing CR tolerated) in
    ``PREFLIGHT_SIGNED_COMMITS_ACK``; an unanchored substring match (the #1962
    bug) is deliberately not accepted.
    """
    value = (os.environ if env is None else env).get(_ACK_ENV_VAR, "")
    return _ACK_MARKER_RE.search(value) is not None


def check_signed_commits(*, runner: Runner, base_ref: str) -> SignedCommitsResult:
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


def check_pushed_refs(
    *, runner: Runner, refs: list[PushRef], remote: str
) -> SignedCommitsResult:
    """Inspect the commits each pushed ref ships and report unsigned ones.

    Delegates the pushed-commit collection to the shared
    :func:`_git.commits_for_pushed_refs` (the same helper #2307's coauthor-
    trailer gate uses), then classifies each collected commit as signed or not.
    A ref whose range cannot be resolved is skipped (fail-open for that ref)
    rather than failing the whole push, matching the #2138 union model; if NO
    ref range could be resolved the result is a skip so a transient git error
    defers to the server-side ruleset instead of wedging the push.
    """
    commits, undeterminable = commits_for_pushed_refs(runner, refs, remote)
    unsigned = [sha for sha in commits if is_unsigned(runner, sha)]

    scope = f"{len(commits)} pushed commit(s) across {len(refs)} ref(s)"
    if unsigned:
        return SignedCommitsResult(
            status="fail",
            detail=f"{len(unsigned)} of {scope} are unsigned",
            unsigned=tuple(unsigned),
        )
    if not commits and undeterminable:
        return SignedCommitsResult(
            status="skip",
            detail=f"no pushed ref range across {len(refs)} ref(s) could be resolved",
        )
    return SignedCommitsResult(status="pass", detail=f"all {scope} are signed")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Reject a push whose range carries an unsigned commit.")
    verify.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to check.")
    verify.add_argument("--base-ref", default="origin/main", help="Base ref; range is <base-ref>..HEAD.")
    return parser


def cmd_verify(args: argparse.Namespace, *, runner: Runner | None = None) -> int:
    if runner is None:
        runner = make_runner(cwd=Path(args.repo_root), timeout=_GIT_TIMEOUT_SECONDS)

    # When the pre-push hook bridged the actual to-be-updated refs through the
    # environment, inspect exactly those refs (issue #2162: a non-HEAD branch
    # push must be checked, and a tag/non-HEAD push must not be blocked by
    # HEAD-only unsigned commits). With no such payload (a direct CLI ``verify``,
    # not invoked via the hook) fall back to the origin/main..HEAD range so the
    # manual invocation and the existing tests keep working.
    refs, remote = read_push_refs()
    if refs:
        result = check_pushed_refs(runner=runner, refs=refs, remote=remote)
    else:
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

    # result.status == "fail": unsigned commits are present. The env-var opt-in is
    # consulted only here (not before the range is resolved) so it can suppress a
    # block ONLY when there is a real one, and every bypass is logged loudly so
    # the env var's session-wide scope cannot silently pass an unsigned push.
    if ack_present():
        print(
            f"::warning::{_ACK_ENV_VAR} opt-in bypassed {len(result.unsigned)} "
            f"UNSIGNED commit(s): {', '.join(result.unsigned)}",
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
