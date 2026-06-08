#!/usr/bin/env python3
"""Open or update the devcontainer image-pin pull request.

Replaces the inline bash in the "Open pin update PR" step of
``.github/workflows/publish-devcontainer-images.yml``: detect whether the pin
update changed anything, create the pin branch and commit when needed, render
the PR body template, and upsert the PR. Keeping this logic in a tested script
(rather than YAML) lets the branch/PR decision flow be unit-tested and run
anywhere ``gh`` may be absent.

Usage::

    python3 scripts/devcontainer_pin_pr.py open \\
        --github-sha SHA --base main \\
        --title TITLE --commit-subject SUBJECT --commit-trailer "Refs #696" \\
        --template .github/pr-body-templates/devcontainer-image-pins.md \\
        --file PATH [--file PATH ...]

The ``refresh`` subcommand keeps an already-open pin PR mergeable. Once
``main`` advances the branch falls behind, because the ``main-protection``
ruleset requires the branch to be up to date
(``strict_required_status_checks_policy``) while ``required_linear_history``,
the ``gate_update_pr_branch.py`` hook, and the ``non_fast_forward`` rule on
all non-default branches (``.github/rulesets/all-branches.json``) all forbid
rebasing/force-pushing the branch in place. ``refresh``
detects the behind PR, cuts a fresh branch off the latest ``main``, re-applies
the same pin as a single commit, opens a new superseding PR, then supersedes
(comments, closes, deletes) the stale one. When the open PR is already up to
date it instead attempts a direct merge. This automates the #895 recovery
path for the generated pin PR. Refs #1137.

    python3 scripts/devcontainer_pin_pr.py refresh \\
        --base main --target-sha "$GITHUB_SHA" \\
        --title TITLE --commit-subject SUBJECT --commit-trailer "Refs #696" \\
        --template .github/pr-body-templates/devcontainer-image-pins.md \\
        --file PATH [--file PATH ...]

The ``merge`` subcommand completes the pin PR. The repository-level "Allow
auto-merge" toggle is intentionally OFF (so agents cannot enable native
auto-merge on arbitrary PRs), and native auto-merge cannot be scoped to a
single PR. Instead, ``merge`` finds the open pin PR by branch prefix and, when
it has reached ``mergeable_state == clean`` (all required checks green and the
branch up to date), squash-merges it via the REST merge API and deletes the
branch. Branch protection still gates the merge: a non-clean PR is left for the
next trigger. Driven by ``.github/workflows/devcontainer-pin-automerge.yml`` on
``check_suite: completed``. Refs #1352.

    python3 scripts/devcontainer_pin_pr.py merge

The pin commit is created through the GitHub API (GraphQL
``createCommitOnBranch``), not a local ``git commit``: API commits are signed by
GitHub and shown as Verified, with the App-bot token as author. A local runner
commit is always unsigned -- and an App bot cannot hold a GPG/SSH signing key --
so the ``required_signatures`` rule on ``main`` would block it. Refs #1437.

Environment variables:
    GH_TOKEN           Token with contents:write + pull-requests:write. The
                       workflows mint it at runtime from a GitHub App via
                       actions/create-github-app-token, so the generated PR's
                       author is the App bot rather than a human PAT owner, and
                       the API-created pin commit is authored by that same bot.
    REPO               Repository in ``owner/repo`` format.

Exit codes:
    0  PR opened/updated/merged, already up to date, already open, or not yet
       mergeable (left for the next trigger).
    1  Missing env var, git failure, or GitHub API error.
    2  Usage error.

Refs #696, #911, #1137, #1352.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import update_devcontainer_image_pins
from _git import run_git
from pr_upsert import (
    _close_pr,
    _comment_pr,
    _compare_behind,
    _create_branch_ref,
    _create_commit_on_branch,
    _delete_branch,
    _get_pr,
    _get_ref_sha,
    _list_open_prs,
    _list_open_prs_by_prefix,
    _merge_pr,
    _upsert_pr,
)

_DEFAULT_BRANCH_PREFIX = "devcontainer/image-pins-"

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


def _create_pin_branch(
    *, repo: str, base: str, branch: str, files: list[str], subject: str, trailer: str, token: str
) -> None:
    """Create *branch* off *base* and add a signed pin commit via the GitHub API.

    The commit is authored through GraphQL ``createCommitOnBranch`` rather than a
    local ``git commit``/``git push`` so GitHub signs it (Verified) with the App
    bot as author -- the only way to satisfy the ``required_signatures`` rule on
    ``main`` for an App-bot author, which cannot hold a signing key. The pin
    files are read from the working tree (already rewritten by the caller) and
    sent as base64 additions. Raises :class:`RuntimeError` on any API failure.
    Refs #1437.
    """
    base_sha = _get_ref_sha(repo=repo, ref=f"heads/{base}", token=token)
    _create_branch_ref(repo=repo, branch=branch, sha=base_sha, token=token)
    additions = [
        {"path": path, "contents": base64.b64encode(Path(path).read_bytes()).decode("ascii")} for path in files
    ]
    _create_commit_on_branch(
        repo=repo,
        branch=branch,
        expected_head_oid=base_sha,
        headline=subject,
        body=trailer,
        additions=additions,
        token=token,
    )


# Mergeability is computed asynchronously by GitHub, so the ``mergeable`` field
# is null for a short window after a push or check completes. Poll a bounded
# number of times before giving up and leaving the merge for the next trigger.
_MERGE_POLL_ATTEMPTS = 6
_MERGE_POLL_INTERVAL_SECONDS = 5.0


def _poll_pr_mergeability(
    *,
    repo: str,
    number: int,
    token: str,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Return the PR object once GitHub has computed ``mergeable`` (or the last poll)."""
    pr: dict[str, Any] = {}
    for attempt in range(_MERGE_POLL_ATTEMPTS):
        if attempt:
            sleeper(_MERGE_POLL_INTERVAL_SECONDS)
        pr = _get_pr(repo=repo, number=number, token=token)
        if pr.get("mergeable") is not None:
            break
    return pr


def _merge_pin_pr_if_clean(*, repo: str, number: int, head_ref: str, token: str) -> bool:
    """Squash-merge pin PR *number* iff it is ``mergeable_state == clean``.

    Returns True when the PR was merged. A PR that is not yet clean (required
    checks pending, branch behind, conflicts) or that loses the merge race is a
    no-op left for the next trigger; only an API error raises.
    """
    pr = _poll_pr_mergeability(repo=repo, number=number, token=token)
    state = str(pr.get("mergeable_state") or "unknown").lower()
    if state != "clean":
        print(f"pin PR #{number} not mergeable yet (mergeable_state={state}); leaving for the next trigger")
        return False
    head_sha = pr.get("head", {}).get("sha", "") if isinstance(pr.get("head"), dict) else ""
    if not head_sha:
        raise RuntimeError(f"pin PR #{number} is clean but has no head sha")
    if not _merge_pr(repo=repo, number=number, sha=head_sha, merge_method="squash", token=token):
        print(f"pin PR #{number} was not mergeable at merge time; leaving for the next trigger")
        return False
    print(f"merged pin PR #{number}")
    if head_ref:
        try:
            _delete_branch(repo=repo, branch=head_ref, token=token)
        except RuntimeError as exc:
            print(f"::warning::merged PR #{number} but branch cleanup failed: {exc}", file=sys.stderr)
    return True


def _cmd_open(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN (GitHub App installation token) is required", file=sys.stderr)
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
            return 0
        print(f"pin update branch already exists without an open PR; retrying PR creation: {branch}")
    else:
        try:
            _create_pin_branch(
                repo=repo,
                base=args.base,
                branch=branch,
                files=args.file,
                subject=args.commit_subject,
                trailer=args.commit_trailer,
                token=token,
            )
        except RuntimeError as exc:
            print(f"::error::failed creating pin branch: {exc}", file=sys.stderr)
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
    print(f"PR #{pr_number} {action}. The pin auto-merge keeper merges it once checks pass.")
    return 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN (GitHub App installation token) is required", file=sys.stderr)
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
        print(f"pin PR #{old_number} is up to date with {args.base}; attempting merge")
        try:
            _merge_pin_pr_if_clean(repo=repo, number=old_number, head_ref=head_ref, token=token)
        except RuntimeError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1
        return 0

    target_short = args.target_sha[:12]
    new_branch = f"{prefix}{published_sha}{_REFRESH_SEPARATOR}{target_short}"
    if new_branch == head_ref:
        print(f"pin PR #{old_number} already refreshed onto {target_short}; attempting merge")
        try:
            _merge_pin_pr_if_clean(repo=repo, number=old_number, head_ref=head_ref, token=token)
        except RuntimeError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1
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
                repo=repo,
                base=args.base,
                branch=new_branch,
                files=args.file,
                subject=args.commit_subject,
                trailer=args.commit_trailer,
                token=token,
            )
        except RuntimeError as exc:
            print(f"::error::failed creating refresh branch: {exc}", file=sys.stderr)
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
    print(f"refresh PR #{new_number} {action} from {new_branch}; the pin auto-merge keeper merges it once checks pass")

    # Supersede the stale PR only after the replacement exists, so a failure here
    # never leaves the repository without an open pin PR. Cleanup is best-effort.
    if new_number != old_number:
        try:
            _comment_pr(
                repo=repo,
                number=old_number,
                body=(
                    f"Superseded by #{new_number}: refreshed onto {args.base} so the pin auto-merge "
                    "keeper can complete (the branch was behind and cannot be rebased in place). "
                    "Closing this stale pin PR."
                ),
                token=token,
            )
            _close_pr(repo=repo, number=old_number, token=token)
            _delete_branch(repo=repo, branch=head_ref, token=token)
        except RuntimeError as exc:
            print(f"::warning::failed to fully supersede PR #{old_number}: {exc}", file=sys.stderr)
    return 0


def _cmd_merge(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN (GitHub App installation token) is required", file=sys.stderr)
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
        print("no open devcontainer pin PR; nothing to merge")
        return 0

    # At most one pin PR is expected; if several exist, merge the newest and let
    # the refresh keeper supersede the rest.
    pr = max(open_prs, key=lambda p: int(p["number"]))
    number = int(pr["number"])
    head_ref = pr.get("head", {}).get("ref", "") if isinstance(pr.get("head"), dict) else ""
    try:
        _merge_pin_pr_if_clean(repo=repo, number=number, head_ref=head_ref, token=token)
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
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

    merge_p = sub.add_parser(
        "merge",
        help="Squash-merge the open pin PR once it has reached mergeable_state=clean",
    )
    merge_p.add_argument(
        "--branch-prefix",
        default=_DEFAULT_BRANCH_PREFIX,
        dest="branch_prefix",
        help="Branch name prefix shared with the open command",
    )

    args = parser.parse_args(argv)

    if args.cmd == "open":
        return _cmd_open(args)
    if args.cmd == "refresh":
        return _cmd_refresh(args)
    if args.cmd == "merge":
        return _cmd_merge(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
