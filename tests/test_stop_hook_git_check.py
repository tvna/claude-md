"""Smoke tests for the CCR Stop hook ``stop-hook-git-check.sh``.

The hook (deployed at ``~/.claude/stop-hook-git-check.sh`` in a Claude Code on
the web container) warns when a branch carries commits that GitHub would show as
Unverified, or commits that have not been pushed. A vendored copy of the
corrected script lives at ``tests/fixtures/stop-hook-git-check.sh`` so the
behaviour is exercised hermetically in CI.

These tests pin the false-positive fix: the commit inspections must be scoped to
commits UNIQUE to the current branch (``origin/main..HEAD``). Before the fix the
hook ranged from ``origin/<branch>`` (or a stale ``origin/HEAD``) to ``HEAD`` and
flagged squash-merge commits that already live on the default branch (commits
authored by the repo owner or a GitHub merge bot), then proposed a
``git rebase --exec '... --reset-author'`` that would rewrite their authorship.

Covered cases:

* AC1 (silent): a branch whose tip equals ``origin/main`` (no commits of its
  own) produces no output and exits 0, even when the default branch's recent
  history is merge-bot commits and the branch's own remote ref lags behind them.
* AC2 (detect): a branch carrying one unsigned, non-Anthropic commit is still
  flagged with the remediation steps.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight

HOOK = Path(__file__).resolve().parent / "fixtures" / "stop-hook-git-check.sh"

OWNER = ("Repo Owner", "owner@users.noreply.github.com")
MERGE_BOT = ("GitHub", "noreply@github.com")
# A Claude-authored-but-unsigned commit: committer email is not the signing
# identity (noreply@anthropic.com) and the commit carries no signature.
CLAUDE_UNSIGNED = ("Claude", "noreply@github.com")


def _git(cwd: Path, *args: str) -> str:
    """Run git in an environment isolated from global/system config and signing."""
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": OWNER[0],
        "GIT_AUTHOR_EMAIL": OWNER[1],
        "GIT_COMMITTER_NAME": OWNER[0],
        "GIT_COMMITTER_EMAIL": OWNER[1],
    }
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _commit(repo: Path, fname: str, msg: str, *, author=OWNER, committer=OWNER) -> None:
    (repo / fname).write_text(msg + "\n", encoding="utf-8")
    _git(repo, "add", fname)
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": author[0],
        "GIT_AUTHOR_EMAIL": author[1],
        "GIT_COMMITTER_NAME": committer[0],
        "GIT_COMMITTER_EMAIL": committer[1],
    }
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", msg],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=repo,
        env=env,
        input='{"stop_hook_active": false}',
        capture_output=True,
        text=True,
    )


def _bare_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main", ".")
    return origin


def _clone(origin: Path, dest: Path) -> Path:
    _git(dest.parent, "clone", str(origin), dest.name)
    # The hook only inspects commits when signing is configured; mirror the CCR
    # container where commit.gpgsign=true. Commits are created --no-gpg-sign, so
    # they remain genuinely unsigned (%G? == N) regardless of this flag.
    _git(dest, "config", "commit.gpgsign", "true")
    return dest


def test_silent_when_branch_sits_on_default_branch(tmp_path: Path) -> None:
    """AC1: branch tip == origin/main, no unique commits -> hook is silent.

    The default branch's recent history is merge-bot commits (committer
    noreply@github.com), and the branch's own remote ref (origin/feat) lags
    behind them. The pre-fix logic ranged origin/feat..HEAD and flagged the
    merge-bot commits; the corrected logic ranges origin/main..HEAD (empty) and
    says nothing.
    """
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")

    _commit(seed, "base.txt", "C0 base commit")
    _git(seed, "push", "origin", "main")
    # Publish feat pointing at the fork point, then advance main with merge-bot
    # commits so origin/feat lags origin/main.
    _git(seed, "branch", "feat")
    _git(seed, "push", "origin", "feat")
    _commit(seed, "m1.txt", "M1 squash-merge of PR", committer=MERGE_BOT)
    _commit(seed, "m2.txt", "M2 squash-merge of PR", committer=MERGE_BOT)
    _git(seed, "push", "origin", "main")

    work = _clone(origin, tmp_path / "work")
    _git(work, "checkout", "feat")
    # Fast-forward feat to the current default branch tip (no commits of its own).
    _git(work, "reset", "--hard", "origin/main")

    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "0"

    result = _run_hook(work)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", f"hook should be silent, got: {result.stderr!r}"


def test_detects_unsigned_claude_commit(tmp_path: Path) -> None:
    """AC2: a branch-unique unsigned commit is flagged with remediation steps."""
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")
    _commit(seed, "base.txt", "C0 base commit")
    _git(seed, "push", "origin", "main")

    work = _clone(origin, tmp_path / "work")
    _git(work, "checkout", "-b", "claude/feature")
    _commit(work, "feature.txt", "Claude work", committer=CLAUDE_UNSIGNED)

    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "1"

    result = _run_hook(work)
    assert result.returncode == 2
    assert "Unverified" in result.stderr
    # Remediation must target the default branch, never the upstream ref.
    assert "origin/main' for earlier commits" in result.stderr


def test_silent_for_brand_new_branch_on_default_tip(tmp_path: Path) -> None:
    """AC1 variant: a never-pushed branch sitting exactly on origin/main.

    This is the literal verification case from the report: with
    ``git log origin/main..HEAD`` empty the hook must produce no output, and the
    unpushed check must not fire either (no commits of its own to push).
    """
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")
    _commit(seed, "base.txt", "C0 base commit")
    _git(seed, "push", "origin", "main")

    work = _clone(origin, tmp_path / "work")
    _git(work, "checkout", "-b", "claude/fresh")  # never pushed, tip == origin/main

    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "0"

    result = _run_hook(work)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == ""
