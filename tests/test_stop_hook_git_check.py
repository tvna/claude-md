"""Smoke tests for the CCR Stop hook ``stop-hook-git-check.sh``.

The hook (deployed at ``~/.claude/stop-hook-git-check.sh`` in a Claude Code on
the web container) warns when a branch carries commits that GitHub would show as
Unverified, or commits that have not been pushed. A copy of the corrected script
lives at ``tests/fixtures/stop-hook-git-check.sh`` so the behaviour is exercised
hermetically in CI; that fixture is the single source the SessionStart deploy
hook installs into the container.

What these tests pin:

* The unverified-commit inspection is scoped to commits UNIQUE to the current
  branch (``origin/main..HEAD``). Before the fix the hook ranged from
  ``origin/<branch>`` (or a stale ``origin/HEAD``) to ``HEAD`` and flagged
  squash-merge commits that already live on the default branch (commits authored
  by the repo owner or a GitHub merge bot), then proposed a
  ``git rebase --exec '... --reset-author'`` that would rewrite their authorship.
* The unpushed-commit check uses the genuine ``origin/<branch>..HEAD`` range so a
  commit that is also reachable from the default branch is still counted.
* Detection of a real branch-unique unsigned commit is pinned to the branch
  commit, not the upstream base.

Assertions check for the hook's own marker strings rather than total stderr
emptiness, so an incidental git warning (e.g. a ``safe.directory`` "dubious
ownership" notice when the temp repo is owned differently than the test user)
does not fail a "silent" case spuriously.
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
ANTHROPIC = ("Claude", "noreply@anthropic.com")
# A Claude-authored-but-unsigned commit whose committer email is not the signing
# identity; %ce is what the hook inspects.
CLAUDE_UNSIGNED = ("Claude", "noreply@github.com")

# Marker substrings the hook emits on each failure path. A "silent" run must
# contain none of these; incidental git stderr (safe.directory warnings, etc.)
# is ignored.
HOOK_MARKERS = (
    "uncommitted changes",
    "untracked files",
    "Unverified",
    "unpushed commit",
    "no remote branch",
)


def _env(author=OWNER, committer=OWNER) -> dict[str, str]:
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": author[0],
        "GIT_AUTHOR_EMAIL": author[1],
        "GIT_COMMITTER_NAME": committer[0],
        "GIT_COMMITTER_EMAIL": committer[1],
    }


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, env=_env(), check=True, capture_output=True, text=True)
    return out.stdout.strip()


def _commit(repo: Path, fname: str, msg: str, *, author=OWNER, committer=OWNER) -> str:
    (repo / fname).write_text(msg + "\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", fname],
        cwd=repo,
        env=_env(author, committer),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", msg],
        cwd=repo,
        env=_env(author, committer),
        check=True,
        capture_output=True,
        text=True,
    )
    return _git(repo, "rev-parse", "--short", "HEAD")


def _run_hook(repo: Path, *, gpgsign: bool = True) -> subprocess.CompletedProcess[str]:
    if gpgsign:
        _git(repo, "config", "commit.gpgsign", "true")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=repo,
        env=env,
        input='{"stop_hook_active": false}',
        capture_output=True,
        text=True,
    )


def _assert_silent(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}: {result.stderr!r}"
    present = [m for m in HOOK_MARKERS if m in result.stderr]
    assert not present, f"hook should be silent, but emitted markers {present}: {result.stderr!r}"


def _bare_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main", ".")
    return origin


def _clone(origin: Path, dest: Path) -> Path:
    _git(dest.parent, "clone", str(origin), dest.name)
    return dest


def test_signing_check_ignores_upstream_merge_commits(tmp_path: Path) -> None:
    """Regression: merge commits already on origin/main are never flagged as
    Unverified, and the destructive ``--reset-author`` remediation is not
    proposed, even when the branch's own remote ref lags behind them.

    The pre-fix hook ranged origin/feat..HEAD and emitted the Unverified warning
    for the two merge-bot commits. The branch is genuinely ahead of origin/feat
    here, so the (benign, non-rewriting) unpushed notice is expected; only the
    signing false-positive must be gone.
    """
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")
    _commit(seed, "base.txt", "C0 base commit")
    _git(seed, "push", "origin", "main")
    _git(seed, "branch", "feat")
    _git(seed, "push", "origin", "feat")  # origin/feat pinned at the fork point
    _commit(seed, "m1.txt", "M1 squash-merge of PR", committer=MERGE_BOT)
    _commit(seed, "m2.txt", "M2 squash-merge of PR", committer=MERGE_BOT)
    _git(seed, "push", "origin", "main")

    work = _clone(origin, tmp_path / "work")
    _git(work, "checkout", "feat")
    _git(work, "reset", "--hard", "origin/main")
    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "0"

    result = _run_hook(work)
    assert "Unverified" not in result.stderr, result.stderr
    assert "--reset-author" not in result.stderr, result.stderr


def test_silent_when_branch_pushed_and_synced(tmp_path: Path) -> None:
    """Realistic reported scenario: branch tip == origin/main == origin/feat
    (no commits of its own, remote in sync) -> fully silent."""
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")
    _commit(seed, "base.txt", "C0 base commit")
    _commit(seed, "m1.txt", "M1 squash-merge", committer=MERGE_BOT)
    _git(seed, "push", "origin", "main")
    _git(seed, "branch", "feat")
    _git(seed, "push", "origin", "feat")  # origin/feat == origin/main tip

    work = _clone(origin, tmp_path / "work")
    _git(work, "checkout", "feat")
    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "0"

    _assert_silent(_run_hook(work))


def test_silent_for_brand_new_branch_on_default_tip(tmp_path: Path) -> None:
    """A never-pushed branch sitting exactly on origin/main is fully silent
    (the literal ``git log origin/main..HEAD`` empty verification case)."""
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")
    _commit(seed, "base.txt", "C0 base commit")
    _git(seed, "push", "origin", "main")

    work = _clone(origin, tmp_path / "work")
    _git(work, "checkout", "-b", "claude/fresh")  # never pushed, tip == origin/main
    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "0"

    _assert_silent(_run_hook(work))


def test_detects_unsigned_unique_commit_scoped_to_branch(tmp_path: Path) -> None:
    """A branch-unique unsigned commit is flagged, and detection is pinned to
    that commit: the upstream base commit's SHA must not appear, and the
    remediation must target the default branch."""
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")
    base_sha = _commit(seed, "base.txt", "C0 base commit")
    _git(seed, "push", "origin", "main")

    work = _clone(origin, tmp_path / "work")
    _git(work, "checkout", "-b", "claude/feature")
    feature_sha = _commit(work, "feature.txt", "Claude work", committer=CLAUDE_UNSIGNED)
    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "1"

    result = _run_hook(work)
    assert result.returncode == 2
    assert "Unverified" in result.stderr
    assert feature_sha in result.stderr, "the branch-unique commit must be reported"
    assert base_sha not in result.stderr, "the upstream base commit must NOT be inspected"
    assert "origin/main' for earlier commits" in result.stderr


def test_reports_unpushed_commit_reachable_from_default_branch(tmp_path: Path) -> None:
    """F4: a commit on HEAD that is absent from origin/<branch> but also
    reachable from origin/main is still counted as unpushed (the pre-fix
    ``--not origin/<branch>`` scoping undercounted it to zero).

    Signing is left disabled so only the unpushed path is exercised.
    """
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")
    _commit(seed, "base.txt", "C0 base commit")
    _git(seed, "push", "origin", "main")
    _git(seed, "branch", "feat")
    _git(seed, "push", "origin", "feat")  # origin/feat at C0

    work = _clone(origin, tmp_path / "work")
    _git(work, "checkout", "feat")
    _commit(work, "x.txt", "X local work", committer=ANTHROPIC)
    # Simulate origin/main advancing to include X (X is now reachable from the
    # default branch) while origin/feat still lags at C0.
    _git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "0"
    assert _git(work, "rev-list", "origin/feat..HEAD", "--count") == "1"

    result = _run_hook(work, gpgsign=False)
    assert result.returncode == 2
    assert "unpushed commit" in result.stderr


def test_uses_configured_upstream_for_differently_named_branch(tmp_path: Path) -> None:
    """The unpushed check honours a configured upstream whose name differs from
    the local branch (localwork tracking origin/remote-name), instead of
    assuming origin/<branch> and falsely reporting 'no remote branch'.

    Signing is left disabled so only the unpushed path is exercised.
    """
    origin = _bare_origin(tmp_path)
    seed = _clone(origin, tmp_path / "seed")
    _commit(seed, "base.txt", "C0 base commit")
    _git(seed, "push", "origin", "main")
    _git(seed, "checkout", "-b", "remote-name")
    _commit(seed, "f.txt", "feature work", committer=ANTHROPIC)
    _git(seed, "push", "origin", "remote-name")  # origin/remote-name = C0 + feature

    work = _clone(origin, tmp_path / "work")
    # localwork tracks origin/remote-name (a differently-named upstream), in sync.
    _git(work, "checkout", "-b", "localwork", "origin/remote-name")
    assert _git(work, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}") == ("origin/remote-name")
    assert _git(work, "rev-list", "origin/remote-name..HEAD", "--count") == "0"
    # The commit is beyond origin/main, so the same-name logic would have
    # reported it as unpushed with no remote branch.
    assert _git(work, "rev-list", "origin/main..HEAD", "--count") == "1"

    result = _run_hook(work, gpgsign=False)
    assert result.returncode == 0, result.stderr
    assert "no remote branch" not in result.stderr
    assert "unpushed commit" not in result.stderr
