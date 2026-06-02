#!/usr/bin/env python3
"""Open or update the devcontainer image-pin pull request.

Replaces the inline bash in the "Open pin update PR" step of
``.github/workflows/publish-devcontainer-images.yml``: detect whether the pin
update changed anything, create the pin branch and commit when needed, render
the PR body template, upsert the PR, and request auto-merge. Keeping this logic
in a tested script (rather than YAML) lets the branch/PR decision flow be
unit-tested and run anywhere ``gh`` may be absent.

Usage::

    python3 scripts/devcontainer_pin_pr.py open \\
        --github-sha SHA --base main \\
        --title TITLE --commit-subject SUBJECT --commit-trailer "Refs #696" \\
        --template .github/pr-body-templates/devcontainer-image-pins.md \\
        --file PATH [--file PATH ...]

Environment variables:
    GH_TOKEN  Token with contents:write + pull-requests:write
              (DEVCONTAINER_PIN_PR_TOKEN).
    REPO      Repository in ``owner/repo`` format.

Exit codes:
    0  PR opened/updated, already up to date, or already open.
    1  Missing env var, git failure, or GitHub API error.
    2  Usage error.

Refs #696, #911.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from _git import run_git
from dependabot_automerge import _enable_auto_merge
from pr_upsert import _list_open_prs, _upsert_pr

_DEFAULT_BRANCH_PREFIX = "codex/devcontainer-image-pins-"
_BOT_NAME = "github-actions[bot]"
_BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def render_pr_body(template_text: str, github_sha: str) -> str:
    """Substitute the ``__GITHUB_SHA__`` placeholder (replaces the workflow ``sed``)."""
    return template_text.replace("__GITHUB_SHA__", github_sha)


def _has_pin_changes() -> bool:
    """Return True when ``git diff --quiet`` exits non-zero (working tree changed)."""
    return run_git(["diff", "--quiet"]).returncode != 0


def _branch_exists_on_remote(branch: str) -> bool:
    """Return True when ``origin`` already has *branch*."""
    return run_git(["ls-remote", "--exit-code", "--heads", "origin", branch]).returncode == 0


def _create_pin_branch(*, branch: str, files: list[str], subject: str, trailer: str) -> None:
    """Configure the bot identity, branch off, commit the pin files, and push.

    Raises :class:`subprocess.CalledProcessError` if any git step fails.
    """
    run_git(["config", "user.name", _BOT_NAME], check=True)
    run_git(["config", "user.email", _BOT_EMAIL], check=True)
    run_git(["checkout", "-b", branch], check=True)
    run_git(["add", *files], check=True)
    run_git(["commit", "-m", subject, "-m", trailer], check=True)
    run_git(["push", "origin", branch], check=True)


def _request_auto_merge_soft(*, repo: str, pr_number: int, token: str) -> None:
    """Request auto-merge, downgrading any failure to a warning (matches prior bash)."""
    try:
        _enable_auto_merge(repo=repo, pr_number=pr_number, merge_method="SQUASH", token=token)
    except RuntimeError as exc:
        print(
            f"::warning::auto-merge request failed for PR #{pr_number}; enable it manually if needed ({exc})",
            file=sys.stderr,
        )


def _cmd_open(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN (DEVCONTAINER_PIN_PR_TOKEN) is required", file=sys.stderr)
        return 1
    repo = os.environ.get("REPO", "")
    if not repo:
        print("::error::REPO is not set", file=sys.stderr)
        return 1

    sha = args.github_sha
    branch = f"{args.branch_prefix}{sha}"

    if not _has_pin_changes():
        print(f"devcontainer image pins already match {sha}")
        return 0

    if _branch_exists_on_remote(branch):
        try:
            prs = _list_open_prs(repo=repo, head=branch, token=token)
        except RuntimeError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1
        if prs:
            existing = int(prs[0]["number"])
            print(f"pin update PR already exists: #{existing}")
            _request_auto_merge_soft(repo=repo, pr_number=existing, token=token)
            return 0
        print(f"pin update branch already exists without an open PR; retrying PR creation: {branch}")
    else:
        try:
            _create_pin_branch(
                branch=branch,
                files=args.file,
                subject=args.commit_subject,
                trailer=args.commit_trailer,
            )
        except subprocess.CalledProcessError as exc:
            print(f"::error::git failed creating pin branch: {exc}", file=sys.stderr)
            return 1

    try:
        template_text = Path(args.template).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::cannot read template {args.template}: {exc}", file=sys.stderr)
        return 1
    body = render_pr_body(template_text, sha)

    try:
        action, pr_number = _upsert_pr(
            repo=repo, head=branch, base=args.base, title=args.title, body=body, token=token
        )
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"PR #{pr_number} {action}.")
    _request_auto_merge_soft(repo=repo, pr_number=pr_number, token=token)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open or update the devcontainer image-pin pull request.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    open_p = sub.add_parser("open", help="Create the pin branch/commit if needed and upsert the PR")
    open_p.add_argument("--github-sha", required=True, dest="github_sha", help="Published commit SHA")
    open_p.add_argument("--base", default="main", help="Base branch to merge into")
    open_p.add_argument("--title", required=True, help="PR title")
    open_p.add_argument("--template", required=True, help="Path to the PR body template")
    open_p.add_argument("--commit-subject", required=True, dest="commit_subject", help="Commit subject line")
    open_p.add_argument("--commit-trailer", required=True, dest="commit_trailer", help="Commit trailer line")
    open_p.add_argument(
        "--branch-prefix",
        default=_DEFAULT_BRANCH_PREFIX,
        dest="branch_prefix",
        help="Branch name prefix; the github-sha is appended",
    )
    open_p.add_argument("--file", action="append", default=[], required=True, help="File to commit (repeatable)")

    args = parser.parse_args(argv)

    if args.cmd == "open":
        return _cmd_open(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
