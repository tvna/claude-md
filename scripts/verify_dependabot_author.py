#!/usr/bin/env python3
"""Deterministic gate: a ``dependabot/*`` PR must be authored by a trusted bot.

Background (#1014, parent #273): the dedicated ``non_fast_forward`` ruleset on
``refs/heads/dependabot/*`` was removed so ``@dependabot rebase`` can force-push
in place again instead of falling back to close-and-reopen. ``non_fast_forward``
never gated *who* could create a ``dependabot/*`` branch, so removing it does not
widen branch-creation scope; but it also means the branch name alone is no
longer behind any ruleset. Auto-merge trust was always anchored on the author
login (``scripts/dependabot_automerge.py`` requires the author in
``_TRUSTED_BOT_LOGINS``), not the branch name. This gate makes that anchor
explicit at PR time: any pull request whose head branch matches ``dependabot/*``
while the author login is not in ``_trusted_bots._TRUSTED_BOT_LOGINS`` fails
loudly, so a non-bot actor cannot pose as Dependabot by pushing a
``dependabot/<x>`` branch and inheriting the dependency-update trust posture.

The check is intentionally narrow: it only fires when the head ref matches
``dependabot/*``. PRs on any other branch are out of scope and pass through.

Contract:
- Inputs: the ``verify`` subcommand; the PR head ref and author login
  from ``--head-ref`` / ``--author`` (or their env-var fallbacks); the
  trusted-bot allowlist ``_trusted_bots._TRUSTED_BOT_LOGINS``.
- Outputs: a ``::error::`` annotation on stderr when an untrusted author
  poses as Dependabot; exit 0 when in scope and trusted (or out of
  scope), exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (gate: an untrusted
  ``dependabot/*`` author exits non-zero).

Exit codes:
* ``0``; head ref is not ``dependabot/*``, or it is and the author is trusted.
* ``1``; head ref is ``dependabot/*`` and the author login is not trusted.

Invoked from ``.github/workflows/issue-pr-triage.yml``. Tested by
``tests/test_verify_dependabot_author.py``.
"""

from __future__ import annotations

import argparse
import sys

from _trusted_bots import _TRUSTED_BOT_LOGINS

_DEPENDABOT_PREFIX = "dependabot/"


def is_violation(head_ref: str, author: str) -> bool:
    """Return True when a ``dependabot/*`` head ref has an untrusted author.

    A non-``dependabot/*`` head ref is never a violation (returns False); the
    gate only governs branches that claim the Dependabot namespace.
    """
    if not head_ref.startswith(_DEPENDABOT_PREFIX):
        return False
    return author not in _TRUSTED_BOT_LOGINS


def cmd_verify(args: argparse.Namespace) -> int:
    head_ref = args.head_ref or ""
    author = args.author or ""
    if is_violation(head_ref, author):
        print(
            f"::error::PR head branch '{head_ref}' is in the dependabot/* "
            f"namespace but author '{author or '<missing>'}' is not a trusted "
            "bot login. Trusted logins are defined in .github/trusted_bots.toml "
            "(see scripts/_trusted_bots.py). A dependabot/* branch authored by a "
            "non-bot actor cannot inherit the dependency-update trust posture; "
            "rename the branch or open the PR from a trusted account.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    verify = sub.add_parser(
        "verify",
        help="Fail when a dependabot/* PR is authored by a non-trusted login.",
    )
    verify.add_argument(
        "--head-ref",
        required=True,
        help="The PR head branch name (github.event.pull_request.head.ref).",
    )
    verify.add_argument(
        "--author",
        required=True,
        help="The PR author login (github.event.pull_request.user.login).",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
