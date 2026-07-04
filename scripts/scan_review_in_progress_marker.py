#!/usr/bin/env python3
"""CI gate: block merge while an automated reviewer's in-progress marker is
present on the PR.

Investigation (issue #2312): PR #2309 was merged 103s after creation while
required checks were still pending, and the owner suspected an automated
reviewer's status marker was misread as "done". Live observation on scratch
PR #2319 confirmed the actual mechanism: ``chatgpt-codex-connector[bot]``
(the OpenAI Codex GitHub review app, already carve-out'd in
``.github/trusted_bots.toml`` for #1731) adds an "eyes" reaction to the PR
6 seconds after creation, then removes it and adds either a "+1" reaction
(no suggestions) or posts a review comment starting "### Codex Review" with
a leading lightbulb emoji (has suggestions) once its review completes --
2m6s later in the observed sample. GitHub Copilot PR review is not
configured in this repository (no login in ``.github/trusted_bots.toml``),
so this gate only covers the Codex marker.

The "eyes" reaction is a genuine positive in-progress signal (unlike an
absence-based check, it cannot block forever on a PR the bot never reviews):
its presence means the review is actively running right now.

Contract:
- Inputs: the ``verify`` subcommand; ``--repo`` (default ``REPO`` env,
  ``owner/name``); ``--pr-number`` (default ``PR_NUMBER`` env); ``--token``
  (default ``GH_TOKEN`` then ``GITHUB_TOKEN`` env).
- Outputs: ``::error::`` on stderr and exit 1 when an "eyes" reaction from a
  ``review_in_progress_marker`` login (``.github/trusted_bots.toml``) is
  present on the PR; ``OK:`` on stderr and exit 0 otherwise; exit 64 on an
  unrecognised subcommand.
- Failure policy: fails open (exit 0, ``::warning::``) when the repo/PR
  number/token cannot be resolved or the GitHub API call fails, since a
  transient lookup failure must never wedge every merge in the repository;
  CLAUDE.md section 4 reserves fail-loud for cases where the check actually
  ran and found the marker.
- Caveat: the eyes-to-completion transition fires no PR webhook event this
  gate's own workflow trigger set listens to (no push, no edit), so once
  blocked, the required check re-runs only on a subsequent PR event (an
  edit, a new commit, a label change) or a manual workflow re-run. See
  ``docs/runbooks/review-in-progress-marker.md``.

Tested by ``tests/test_scan_review_in_progress_marker.py``. Refs #2312.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _github_api import GitHubApiError, paginate
from _trusted_bots import _REVIEW_MARKER_LOGINS

_SCRIPT = "scan_review_in_progress_marker"
_EYES_CONTENT = "eyes"


def has_in_progress_marker(
    reactions: list[dict[str, Any]],
    *,
    marker_logins: frozenset[str] = _REVIEW_MARKER_LOGINS,
) -> str | None:
    """Return the login of the first matching in-progress marker, or None.

    A marker is an "eyes" reaction authored by a login in *marker_logins*
    (case-insensitive, mirroring GitHub's own case-insensitive login rules).
    """
    lowered_logins = {login.lower() for login in marker_logins}
    for reaction in reactions:
        if not isinstance(reaction, dict):
            continue
        if reaction.get("content") != _EYES_CONTENT:
            continue
        user = reaction.get("user")
        if not isinstance(user, dict):
            continue
        login = user.get("login")
        if isinstance(login, str) and login.lower() in lowered_logins:
            return login
    return None


def fetch_reactions(
    repo: str,
    pr_number: str,
    *,
    token: str,
) -> list[dict[str, Any]]:
    """Return every one of the PR's issue-level reactions via the GitHub REST API.

    Paginated (GitHub defaults to 30 results per page, #2320 review comment):
    a PR with more than one page of reactions could otherwise leave an active
    "eyes" marker on a later page undetected, false-passing the gate.
    """
    return [item for item in paginate(f"/repos/{repo}/issues/{pr_number}/reactions", token=token) if isinstance(item, dict)]


def _warn_fail_open(message: str) -> int:
    print(f"::warning::{_SCRIPT}: {message}; failing open.", file=sys.stderr)
    return 0


def run_verify(*, repo: str | None, pr_number: str | None, token: str | None) -> int:
    if not repo:
        return _warn_fail_open("no --repo / $REPO available")
    if not pr_number:
        return _warn_fail_open("no --pr-number / $PR_NUMBER available")
    if not token:
        return _warn_fail_open("no --token / $GH_TOKEN / $GITHUB_TOKEN available")

    try:
        reactions = fetch_reactions(repo, pr_number, token=token)
    except GitHubApiError as exc:
        return _warn_fail_open(f"GitHub API call failed: {exc}")

    marker_login = has_in_progress_marker(reactions)
    if marker_login is not None:
        print(
            f"::error::{_SCRIPT}: {repo}#{pr_number} carries an active "
            f"review-in-progress marker (an 'eyes' reaction from {marker_login!r}). "
            "The automated reviewer has not finished yet; wait for it to remove "
            "the reaction and post its completion marker (a '+1' reaction or a "
            "'Codex Review' comment), then re-run this check (edit the PR or "
            "re-run the workflow job; the marker's removal fires no webhook "
            "event this gate listens to). "
            "See docs/runbooks/review-in-progress-marker.md.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {_SCRIPT}: no review-in-progress marker on {repo}#{pr_number}.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Check the subcommand before argparse so an unrecognised command returns
    # exit 64 (EX_USAGE) rather than argparse's exit 2.
    command = argv[0] if argv else None
    if command != "verify":
        print(
            f"::error::{_SCRIPT}: unknown subcommand {command!r}; expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    parser = argparse.ArgumentParser(
        description="Block merge while an automated reviewer's in-progress marker is present."
    )
    parser.add_argument("command", help="Must be 'verify'.")
    parser.add_argument(
        "--repo",
        default=os.environ.get("REPO"),
        help="owner/name (default: REPO env).",
    )
    parser.add_argument(
        "--pr-number",
        default=os.environ.get("PR_NUMBER"),
        help="Pull request number (default: PR_NUMBER env).",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"),
        help="GitHub token (default: GH_TOKEN then GITHUB_TOKEN env).",
    )
    args = parser.parse_args(argv)

    return run_verify(repo=args.repo, pr_number=args.pr_number, token=args.token)


if __name__ == "__main__":
    raise SystemExit(main())
