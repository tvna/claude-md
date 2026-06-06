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

The ``refresh`` subcommand keeps an already-open pin PR mergeable. Native
auto-merge stalls forever once ``main`` advances, because the
``main-protection`` ruleset requires the branch to be up to date
(``strict_required_status_checks_policy``) while ``required_linear_history``,
the ``gate_update_pr_branch.py`` hook, and the ``non_fast_forward`` rule on
all non-default branches (``.github/rulesets/all-branches.json``) all forbid
rebasing/force-pushing the branch in place. ``refresh``
detects the behind PR, cuts a fresh branch off the latest ``main``, re-applies
the same pin as a single commit, opens a new auto-merge PR, then supersedes
(comments, closes, deletes) the stale one. This automates the #895 recovery
path for the generated pin PR. Refs #1137.

    python3 scripts/devcontainer_pin_pr.py refresh \\
        --base main --target-sha "$GITHUB_SHA" \\
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

Refs #696, #911, #1137.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import update_devcontainer_image_pins
from _git import run_git
from dependabot_automerge import _enable_auto_merge
from pr_upsert import (
    _close_pr,
    _comment_pr,
    _compare_behind,
    _delete_branch,
    _list_open_prs,
    _list_open_prs_by_prefix,
    _upsert_pr,
)

_DEFAULT_BRANCH_PREFIX = "devcontainer/image-pins-"
_BOT_NAME = "github-actions[bot]"
_BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

# Original branches are ``<prefix><40-hex-sha>``; refreshed branches append
# ``-r-<main-short-sha>`` so each main advance yields a fresh, unique name (no
# force-push) while the published SHA stays recoverable for the next refresh.
_REFRESH_SEPARATOR = "-r-"
_PUBLISHED_SHA_RE = re.compile(
    rf"^{re.escape(_DEFAULT_BRANCH_PREFIX)}(?P<sha>[0-9a-f]{{7,40}})(?:{re.escape(_REFRESH_SEPARATOR)}[0-9a-f]+)?$"
)


def _parse_published_sha(branch: str) -> str | None:
    """Recover the published image SHA from a (possibly refreshed) pin branch name."""
    match = _PUBLISHED_SHA_RE.match(branch)
    return match.group("sha") if match else None


def _regenerate_pins(published_sha: str) -> int:
    """Rewrite the pin files for *published_sha* against the current working tree."""
    return update_devcontainer_image_pins.main([published_sha])


def render_pr_body(template_text: str, github_sha: str) -> str:
    """Substitute the ``__GITHUB_SHA__`` placeholder (replaces the workflow ``sed``)."""
    return template_text.replace("__GITHUB_SHA__", github_sha)


def _has_pin_changes() -> bool:
    """Return True when ``git diff --quiet`` exits non-zero (working tree changed)."""
    return run_git(["diff", "--quiet"]).returncode != 0


def _branch_exists_on_remote(branch: str) -> bool:
    """Return True when ``origin`` already has *branch*."""
    return run_git(["ls-remote", "--exit-code", "--heads", "origin", branch]).returncode == 0


def _git_error_detail(exc: subprocess.CalledProcessError) -> str:
    """Return git's captured stderr for an error message, or ``""`` when empty.

    ``run_git`` runs git with ``capture_output=True``, so a ``check=True``
    failure carries git's own diagnostic on the exception. ``str(exc)`` shows
    only the exit code (e.g. ``returned non-zero exit status 128``), hiding the
    concrete rejection reason -- the ruleset rule name or
    ``remote: Permission ...`` behind an exit-128 push failure. Surfacing the
    stderr makes a keeper auth/ruleset regression diagnosable from the run log;
    GitHub Actions masks registered secrets in step output, so the persisted
    token is not exposed. Refs #1229.
    """
    stderr = exc.stderr
    if isinstance(stderr, str) and stderr.strip():
        return f": {stderr.strip()}"
    return ""


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
            print(f"::error::git failed creating pin branch: {exc}{_git_error_detail(exc)}", file=sys.stderr)
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


def _cmd_refresh(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN (DEVCONTAINER_PIN_PR_TOKEN) is required", file=sys.stderr)
        return 1
    repo = os.environ.get("REPO", "")
    if not repo:
        print("::error::REPO is not set", file=sys.stderr)
        return 1

    prefix = args.branch_prefix
    try:
        open_prs = _list_open_prs_by_prefix(repo=repo, prefix=prefix, token=token)
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    if not open_prs:
        print("no open devcontainer pin PR; nothing to refresh")
        return 0

    # At most one pin PR is expected; if several exist, refresh the newest and
    # let later runs supersede the rest.
    pr = max(open_prs, key=lambda p: int(p["number"]))
    old_number = int(pr["number"])
    head_ref = pr.get("head", {}).get("ref", "")
    published_sha = _parse_published_sha(head_ref)
    if published_sha is None:
        print(f"::error::cannot parse published SHA from branch {head_ref!r}", file=sys.stderr)
        return 1

    try:
        behind = _compare_behind(repo=repo, base=args.base, head=head_ref, token=token)
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    if behind <= 0:
        print(f"pin PR #{old_number} is up to date with {args.base}; re-requesting auto-merge")
        _request_auto_merge_soft(repo=repo, pr_number=old_number, token=token)
        return 0

    target_short = args.target_sha[:12]
    new_branch = f"{prefix}{published_sha}{_REFRESH_SEPARATOR}{target_short}"
    if new_branch == head_ref:
        print(f"pin PR #{old_number} already refreshed onto {target_short}; re-requesting auto-merge")
        _request_auto_merge_soft(repo=repo, pr_number=old_number, token=token)
        return 0

    # Working tree is a fresh checkout of the latest base; rewrite the pins for
    # the same published image and confirm the rebased change is non-empty.
    rc = _regenerate_pins(published_sha)
    if rc != 0:
        print(f"::error::update_devcontainer_image_pins failed (rc={rc})", file=sys.stderr)
        return 1
    if not _has_pin_changes():
        print(f"pins for {published_sha} already match {args.base}; closing redundant PR #{old_number}")
        try:
            _comment_pr(
                repo=repo,
                number=old_number,
                body=(
                    f"Devcontainer image pins for {published_sha} already match {args.base}; "
                    "closing this superseded pin PR."
                ),
                token=token,
            )
            _close_pr(repo=repo, number=old_number, token=token)
            _delete_branch(repo=repo, branch=head_ref, token=token)
        except RuntimeError as exc:
            print(f"::warning::failed to close redundant PR #{old_number}: {exc}", file=sys.stderr)
        return 0

    if not _branch_exists_on_remote(new_branch):
        try:
            _create_pin_branch(
                branch=new_branch,
                files=args.file,
                subject=args.commit_subject,
                trailer=args.commit_trailer,
            )
        except subprocess.CalledProcessError as exc:
            print(f"::error::git failed creating refresh branch: {exc}{_git_error_detail(exc)}", file=sys.stderr)
            return 1

    try:
        template_text = Path(args.template).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::cannot read template {args.template}: {exc}", file=sys.stderr)
        return 1
    body = render_pr_body(template_text, published_sha)

    try:
        action, new_number = _upsert_pr(
            repo=repo, head=new_branch, base=args.base, title=args.title, body=body, token=token
        )
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"refresh PR #{new_number} {action} from {new_branch}")
    _request_auto_merge_soft(repo=repo, pr_number=new_number, token=token)

    # Supersede the stale PR only after the replacement exists, so a failure here
    # never leaves the repository without an open pin PR. Cleanup is best-effort.
    if new_number != old_number:
        try:
            _comment_pr(
                repo=repo,
                number=old_number,
                body=(
                    f"Superseded by #{new_number}: refreshed onto {args.base} so native auto-merge "
                    "can complete (the branch was behind and cannot be rebased in place). "
                    "Closing this stale pin PR."
                ),
                token=token,
            )
            _close_pr(repo=repo, number=old_number, token=token)
            _delete_branch(repo=repo, branch=head_ref, token=token)
        except RuntimeError as exc:
            print(f"::warning::failed to fully supersede PR #{old_number}: {exc}", file=sys.stderr)
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

    refresh_p = sub.add_parser(
        "refresh",
        help="Rebase a behind, open pin PR onto the latest base via a fresh superseding PR",
    )
    refresh_p.add_argument("--base", default="main", help="Base branch to merge into")
    refresh_p.add_argument(
        "--target-sha",
        required=True,
        dest="target_sha",
        help="Current base HEAD SHA; its short form names the refreshed branch",
    )
    refresh_p.add_argument("--title", required=True, help="PR title")
    refresh_p.add_argument("--template", required=True, help="Path to the PR body template")
    refresh_p.add_argument("--commit-subject", required=True, dest="commit_subject", help="Commit subject line")
    refresh_p.add_argument("--commit-trailer", required=True, dest="commit_trailer", help="Commit trailer line")
    refresh_p.add_argument(
        "--branch-prefix",
        default=_DEFAULT_BRANCH_PREFIX,
        dest="branch_prefix",
        help="Branch name prefix shared with the open command",
    )
    refresh_p.add_argument("--file", action="append", default=[], required=True, help="File to commit (repeatable)")

    args = parser.parse_args(argv)

    if args.cmd == "open":
        return _cmd_open(args)
    if args.cmd == "refresh":
        return _cmd_refresh(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
