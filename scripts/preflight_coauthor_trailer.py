#!/usr/bin/env python3
"""Fail before push when a commit carries a self-redundant Co-authored-by trailer.

Refs #2307, #2302. PR #2302 squash-merged to a body repeating
``Co-authored-by: Claude noreply@anthropic.com`` three times: GitHub's
squash-merge concatenates every commit body into the squash message (so an
inline ``Co-Authored-By:`` footer in each of the two commits survives
verbatim) and separately appends one deduplicated ``Co-authored-by:`` trailer
block after a ``---------`` separator; 2 inline + 1 aggregated = 3.

The git author of these commits is already ``Claude <noreply@anthropic.com>``
(``docs/standards/commit-signing.md``), so a ``Co-authored-by:`` trailer
naming that same identity adds no attribution the author line does not
already carry; it is pure redundancy that this squash duplication then
multiplies. This gate rejects exactly that redundant case: a
``Co-authored-by:``/``Co-Authored-By:`` trailer whose email matches (case
-insensitively) the email of the commit that carries it. A trailer naming a
genuinely different co-author is unaffected.

Range. Mirrors ``preflight_signed_commits.py`` (#2162): when the pre-push hook
bridges the actual to-be-updated refs through the environment
(``PREFLIGHT_PUSH_REFS`` / ``PREFLIGHT_PUSH_REMOTE``), the commits inspected
are exactly those the push would ship (via the shared
``_git.commits_for_pushed_refs``), so a non-HEAD branch push is checked and an
unrelated tag/non-HEAD push is not falsely blocked by a redundant trailer
reachable only from HEAD. With no such payload (a direct CLI ``verify`` run)
the range falls back to ``<base-ref>..HEAD`` (default ``origin/main``,
overridable with ``--base-ref``), read after ``preflight_branch_base`` has
fetched the live base so the remote-tracking ref is current.

Contract:
- Inputs: ``verify`` subcommand with optional ``--repo-root`` and
  ``--base-ref`` (default ``origin/main``). Reads ``PREFLIGHT_PUSH_REFS`` /
  ``PREFLIGHT_PUSH_REMOTE`` (the pushed refs the pre-push hook bridged from
  stdin; absent for a direct CLI run).
- Outputs: an ``OK:`` line and exit 0 when no commit in range carries a
  self-redundant trailer; a ``SKIP:`` line and exit 0 when the range cannot
  be resolved (the same fail-open posture as ``preflight_signed_commits.py``);
  ``::error::`` annotations naming each offending commit and exit 1
  otherwise; exit 64 on an unrecognised subcommand.
- Failure policy: fails loud (exit 1) only on a positively-shown redundant
  trailer; an unresolvable range or an uninspectable commit fails open
  (CLAUDE.md section 4), since a git/subprocess error here is an
  infrastructure problem, not evidence of a redundant trailer.

Tested by ``tests/test_preflight_coauthor_trailer.py``. Refs #2307, #2302.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from _git import (
    PushRef,
    Runner,
    commits_for_pushed_refs,
    commits_in_range,
    make_runner,
    read_push_refs,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

_GIT_TIMEOUT_SECONDS = 30

# Separates the author email from the raw message body in one `git log`
# call, using a byte that cannot appear in either field.
_FIELD_SEP = "\x1f"

# Matches a `Co-authored-by:` / `Co-Authored-By:` trailer line (git's own
# trailer key spelling is case-insensitive), capturing everything after the
# key rather than anchoring the email itself to end-of-line: a trailing
# annotation after the email (e.g. "(paired)") must not prevent a match. The
# emails are then extracted from the captured tail separately (see
# `_EMAIL_ANGLE_RE` / `_EMAIL_BARE_RE` below) so every bracketed/bare email on
# the line is checked, not only the last one a single greedy match would have
# captured. Anchored to a full line's start so a mention of the phrase in
# prose text does not false-positive.
_TRAILER_LINE_RE = re.compile(r"(?im)^co-authored-by:\s*(?P<rest>.*)$")

# Extracts every `<email>`-bracketed address from a trailer line's tail (the
# standard git trailer shape). Un-anchored and repeated via `finditer` so a
# single line listing more than one bracketed co-author (e.g.
# comma-separated) yields every email, not just the last.
_EMAIL_ANGLE_RE = re.compile(r"<(?P<email>[^<>]+)>")

# Falls back to a bare `user@host` address with no brackets (the shape PR
# #2302's manual footer actually used) when the trailer line's tail has no
# bracketed email at all.
_EMAIL_BARE_RE = re.compile(r"(?P<email>[\w.+-]+@[\w.-]+)")


@dataclass(frozen=True)
class Violation:
    """One commit whose Co-authored-by trailer names its own author."""

    sha: str
    author_email: str
    trailer_email: str


@dataclass(frozen=True)
class CoauthorTrailerResult:
    """Outcome of inspecting the push range for self-redundant trailers."""

    status: str  # "pass" | "fail" | "skip"
    detail: str
    violations: tuple[Violation, ...] = ()


def _commit_author_and_body(runner: Runner, sha: str) -> tuple[str, str] | None:
    """Return ``(author_email, message_body)`` for *sha*, or None on error."""
    try:
        result = runner(["log", "-1", f"--format=%ae{_FIELD_SEP}%B", sha])
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or _FIELD_SEP not in result.stdout:
        return None
    email, _, body = result.stdout.partition(_FIELD_SEP)
    return email.strip(), body


def find_redundant_trailers(runner: Runner, shas: list[str]) -> list[Violation]:
    """Return one :class:`Violation` per commit whose trailer names its author.

    A commit that cannot be read (a git/subprocess error) is skipped rather
    than treated as a violation, so an infrastructure failure never masquerades
    as a positive finding.
    """
    violations: list[Violation] = []
    for sha in shas:
        parsed = _commit_author_and_body(runner, sha)
        if parsed is None:
            continue
        author_email, body = parsed
        for line_match in _TRAILER_LINE_RE.finditer(body):
            rest = line_match.group("rest")
            angle_emails = [m.group("email").strip() for m in _EMAIL_ANGLE_RE.finditer(rest)]
            # A bare email can appear alongside a bracketed one on the same
            # line (e.g. a bracketed co-author followed by a bare self
            # email); scanning only the text outside `<...>` spans finds it
            # without re-matching an email already captured by the angle
            # branch (the bracket contents would otherwise also satisfy the
            # bare pattern, double-counting the same address).
            rest_outside_brackets = _EMAIL_ANGLE_RE.sub(" ", rest)
            bare_emails = [m.group("email") for m in _EMAIL_BARE_RE.finditer(rest_outside_brackets)]
            trailer_emails = angle_emails + bare_emails
            for trailer_email in trailer_emails:
                if trailer_email and trailer_email.casefold() == author_email.casefold():
                    violations.append(
                        Violation(sha=sha, author_email=author_email, trailer_email=trailer_email)
                    )
    return violations


def check_coauthor_trailers(*, runner: Runner, base_ref: str) -> CoauthorTrailerResult:
    """Inspect ``<base_ref>..HEAD`` and report any self-redundant trailer."""
    shas = commits_in_range(runner, base_ref)
    if shas is None:
        return CoauthorTrailerResult(
            status="skip",
            detail=f"range {base_ref}..HEAD could not be resolved",
        )
    violations = find_redundant_trailers(runner, shas)
    if violations:
        return CoauthorTrailerResult(
            status="fail",
            detail=f"{len(violations)} of {len(shas)} commit(s) in {base_ref}..HEAD carry a "
            "Co-authored-by trailer naming their own author",
            violations=tuple(violations),
        )
    return CoauthorTrailerResult(
        status="pass",
        detail=f"no self-redundant Co-authored-by trailer in {len(shas)} commit(s)",
    )


def check_pushed_refs(*, runner: Runner, refs: list[PushRef], remote: str) -> CoauthorTrailerResult:
    """Inspect the commits each pushed ref ships and report self-redundant trailers.

    Delegates the pushed-commit collection to the shared
    :func:`_git.commits_for_pushed_refs` (the same helper
    ``preflight_signed_commits.py`` uses for #2162), so a non-HEAD branch push
    is checked and an unrelated tag/non-HEAD push is not falsely blocked by a
    redundant trailer reachable only from HEAD.
    """
    commits, undeterminable = commits_for_pushed_refs(runner, refs, remote)
    if not commits and undeterminable:
        return CoauthorTrailerResult(
            status="skip",
            detail=f"no pushed ref range across {len(refs)} ref(s) could be resolved",
        )
    violations = find_redundant_trailers(runner, commits)
    scope = f"{len(commits)} pushed commit(s) across {len(refs)} ref(s)"
    if violations:
        return CoauthorTrailerResult(
            status="fail",
            detail=f"{len(violations)} of {scope} carry a Co-authored-by trailer naming their own author",
            violations=tuple(violations),
        )
    return CoauthorTrailerResult(
        status="pass",
        detail=f"no self-redundant Co-authored-by trailer in {scope}",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser(
        "verify", help="Reject a push whose range carries a self-redundant Co-authored-by trailer."
    )
    verify.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to check.")
    verify.add_argument("--base-ref", default="origin/main", help="Base ref; range is <base-ref>..HEAD.")
    return parser


def cmd_verify(args: argparse.Namespace, *, runner: Runner | None = None) -> int:
    if runner is None:
        runner = make_runner(cwd=Path(args.repo_root), timeout=_GIT_TIMEOUT_SECONDS)

    # When the pre-push hook bridged the actual to-be-updated refs through the
    # environment, inspect exactly those refs (issue #2333 review: a non-HEAD
    # branch push must be checked, and a tag/non-HEAD push must not be blocked
    # by a redundant trailer reachable only from HEAD). With no such payload (a
    # direct CLI ``verify``, not invoked via the hook) fall back to the
    # base-ref range so the manual invocation keeps working.
    refs, remote = read_push_refs()
    if refs:
        result = check_pushed_refs(runner=runner, refs=refs, remote=remote)
    else:
        result = check_coauthor_trailers(runner=runner, base_ref=args.base_ref)

    if result.status == "pass":
        print(f"OK: {result.detail}")
        return 0
    if result.status == "skip":
        print(
            f"SKIP: {result.detail}; deferring to preflight_branch_base.",
            file=sys.stderr,
        )
        return 0

    print("::error::A commit carries a self-redundant Co-authored-by trailer.", file=sys.stderr)
    print(f"reason: {result.detail}", file=sys.stderr)
    for violation in result.violations:
        print(
            f"  {violation.sha}: Co-authored-by names {violation.trailer_email!r}, "
            f"the same identity as the commit author {violation.author_email!r}",
            file=sys.stderr,
        )
    print(
        "repair: remove the redundant Co-authored-by trailer from the commit message "
        "(git commit --amend, or an interactive rebase for an earlier commit); the "
        "commit author already attributes it, and GitHub squash-merge re-aggregates "
        "one trailer per commit body on top of the inline copy, duplicating it "
        "further (Refs #2307, #2302).",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # `-h`/`--help` must fall through to argparse (which prints help and
    # exits 0) rather than being rejected as an unknown subcommand below; any
    # other unrecognised token keeps the existing exit-64 contract.
    command = argv[0] if argv else None
    if command not in ("verify", "-h", "--help"):
        print(
            f"::error::preflight_coauthor_trailer: unknown subcommand {command!r}; expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    args = _build_parser().parse_args(argv)
    return cmd_verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
