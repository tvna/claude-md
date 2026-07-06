#!/usr/bin/env python3
"""Unified auto-merge keeper for App-bot (``tvna-bot[bot]``) authored PRs.

The repository-level "Allow auto-merge" toggle is intentionally OFF so agents
cannot enable GitHub native auto-merge on arbitrary PRs, and native auto-merge
is repo-wide rather than per-PR. This keeper provides the same outcome strictly
for PRs authored by the App bot: it lists every open PR whose author login is
``tvna-bot[bot]`` and, for each one that has reached ``mergeable_state == clean``
(all required checks green and the branch up to date), squash-merges it via the
REST merge API and deletes the head branch.

The bot PRs are considered in a fixed merge priority (``docs(generated)`` before
the triage-report series; see ``_pr_merge._BOT_PR_PRIORITY_BRANCHES``). While a
higher-priority bot PR is open and still in flight, the keeper holds the
lower-priority series for the next trigger instead of merging it, so the bot
series stop starving one another under ``strict_required_status_checks_policy``
(every merge to ``main`` re-stales the others and only a PR-churning
``--recreate`` can refresh them). Refs #2382.

Branch protection (``main`` ruleset) still gates the merge; a non-clean PR is
left for the next trigger. The merge method is fixed to ``squash`` so the keyless
commit-signature invariant on ``main`` documented in
``docs/standards/commit-signing.md`` is preserved: the squash commit GitHub
creates is signed with its web-flow key (``Verified``), satisfying
``required_signatures``.

This consolidates the earlier per-flow ``devcontainer_pin_pr.py merge`` keeper:
every bot PR flow that authors signed commits through ``createCommitOnBranch``
under the App installation token (devcontainer pin, generate-agents,
post-merge docs / triage, flake-pin, ...) is merged by this single keeper.

    python3 scripts/bot_pr_automerge.py merge

Environment variables:
    GH_TOKEN              GitHub App installation token with contents:write +
                          pull-requests:write. The workflow mints it at runtime
                          from a GitHub App via actions/create-github-app-token,
                          so the merge's push to ``main`` still triggers the
                          downstream push workflows.
    REPO                  Repository in ``owner/repo`` format.
    BOT_AUTHOR_LOGIN      Optional override of the matched author login
                          (default ``tvna-bot[bot]``); test/diagnostic only.

Contract:
- Inputs: the ``merge`` subcommand (no flags); ``GH_TOKEN`` (GitHub App
  installation token) and ``REPO`` env vars for the API boundary; optional
  ``BOT_AUTHOR_LOGIN`` override of the matched author login.
- Outputs: human-readable progress lines to stdout (the per-PR merge result
  and a final tally); a squash-merge plus branch deletion via the REST API for
  each clean PR. Exit 0 on success or no-op, exit 1 on a missing env var.
- Failure policy: fails loud per CLAUDE.md section 4. A missing token/repo
  exits 1 with an ``::error::`` annotation; a real GitHub API error propagates
  as a RuntimeError. A PR that is not yet clean is a deliberate no-op left for
  the next trigger, not a failure.

Exit codes:
    0  All clean bot PRs merged, or none were eligible (no-op).
    1  Missing env var or a real GitHub API error.
    2  Usage error.

Refs #1539, #1437, #1466, #1527, #32.
"""

from __future__ import annotations

import argparse
import os
import sys

from _pr_merge import (
    _list_open_prs_by_author,
    merge_bot_prs_in_priority_order,
)

# The App bot's PR author login. Commits it authors via ``createCommitOnBranch``
# under the installation token, and the PRs it opens, surface under this login.
_DEFAULT_BOT_AUTHOR_LOGIN = "tvna-bot[bot]"


def _cmd_merge(_args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN (GitHub App installation token) is required", file=sys.stderr)
        return 1
    repo = os.environ.get("REPO", "")
    if not repo:
        print("::error::REPO is not set", file=sys.stderr)
        return 1
    author_login = os.environ.get("BOT_AUTHOR_LOGIN") or _DEFAULT_BOT_AUTHOR_LOGIN

    prs = _list_open_prs_by_author(repo=repo, author_login=author_login, token=token)
    if not prs:
        print(f"no open PRs authored by {author_login}")
        return 0

    merged = merge_bot_prs_in_priority_order(prs=prs, repo=repo, token=token)
    print(f"merged {merged} of {len(prs)} open PR(s) authored by {author_login}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "merge",
        help="Squash-merge every open tvna-bot[bot] PR that has reached mergeable_state=clean",
    )

    args = parser.parse_args(argv)

    if args.cmd == "merge":
        return _cmd_merge(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
