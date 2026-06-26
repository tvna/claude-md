"""Tests for ``scripts/preflight_merge_index_budget.py``.

Refs #2012. The central test reproduces the PR #2007 class with a real
``git merge-tree``: each side's ``docs/INDEX.md`` stays under budget while
their additive merge result crosses it. That is the direct demonstration that
this gate would have failed PR #2007's branch preflight before merge-time CI,
not an indirect signal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import preflight_merge_index_budget as gate
import pytest

pytestmark = pytest.mark.shard_preflight

# A small synthetic budget so the test fixtures stay tiny while exercising the
# exact same arithmetic the real MAX_INDEX_BYTES does.
TEST_BUDGET = 200

# Per-side additions sized so each side's INDEX stays under TEST_BUDGET while
# their additive merge union crosses it: base ~62 B + one ~100 B side each, so
# each side ~162 B (< 200) but the union ~265 B (> 200). This is the PR #2007
# arithmetic in miniature.
_OVERFLOW_BASE_EXTRA = "(rowA2_concurrent_" + "a" * 82 + ")"
_OVERFLOW_HEAD_EXTRA = "(rowC2_feature_" + "b" * 33 + ")\n(rowC3_feature_" + "c" * 31 + ")"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _commit_index(repo: Path, body: str, message: str) -> None:
    docs = repo / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "INDEX.md").write_text(body, encoding="utf-8")
    _git(repo, "add", "docs/INDEX.md")
    _git(repo, "commit", "-m", message)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    return repo


def _index_size(repo: Path, ref: str) -> int:
    out = _git(repo, "cat-file", "-s", f"{ref}:docs/INDEX.md")
    return int(out.stdout.strip())


def _make_divergent(tmp_path: Path, *, base_extra: str, head_extra: str) -> Path:
    """Build a repo whose base and feature add to DISTINCT lanes (clean merge).

    The shared base lists three lanes; base advances one lane, the feature
    advances a different lane, so the three-way merge is conflict-free and the
    merged INDEX is the additive union of both rows.
    """
    repo = _init_repo(tmp_path)
    base = (
        "# index\n\n"
        "## laneA\n(rowA1)\n\n"
        "## laneB\n(rowB1)\n\n"
        "## laneC\n(rowC1)\n"
    )
    _commit_index(repo, base, "base")
    _git(repo, "branch", "feature")
    # base side: concurrent docs PR adds a row to laneA
    _commit_index(repo, base.replace("(rowA1)\n", f"(rowA1)\n{base_extra}\n"), "base advance")
    # feature side: independently adds rows to laneC
    _git(repo, "switch", "feature")
    _commit_index(repo, base.replace("(rowC1)\n", f"(rowC1)\n{head_extra}\n"), "feature advance")
    _git(repo, "switch", "main")
    return repo


# ---------------------------------------------------------------------------
# PR #2007 reproduction: merge-only overflow
# ---------------------------------------------------------------------------


def test_merge_only_overflow_fails(tmp_path: Path) -> None:
    """Each side is under budget; only the clean merge result overflows."""
    # Sized so each side stays under TEST_BUDGET but their union exceeds it.
    repo = _make_divergent(
        tmp_path,
        base_extra=_OVERFLOW_BASE_EXTRA,
        head_extra=_OVERFLOW_HEAD_EXTRA,
    )

    base_size = _index_size(repo, "main")
    head_size = _index_size(repo, "feature")
    # Precondition of the #2007 class: neither side is over budget alone.
    assert base_size <= TEST_BUDGET
    assert head_size <= TEST_BUDGET

    result = gate.evaluate(repo, base_ref="main", head_ref="feature", max_bytes=TEST_BUDGET)

    assert result.status == "fail"
    assert result.size is not None and result.size > TEST_BUDGET
    assert "navigation budget" in result.detail


def test_cmd_verify_reports_merge_overflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI path fails (exit 1) and points at the per-lane split remediation."""
    repo = _make_divergent(
        tmp_path,
        base_extra=_OVERFLOW_BASE_EXTRA,
        head_extra=_OVERFLOW_HEAD_EXTRA,
    )
    monkeypatch.setattr(gate, "MAX_INDEX_BYTES", TEST_BUDGET)

    rc = gate.main(["verify", "--repo-root", str(repo), "--skip-fetch", "--base-ref", "main", "--head-ref", "feature"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "per-lane sub-indexes" in captured.err
    assert "rather than raising the budget" in captured.err


# ---------------------------------------------------------------------------
# Passing paths
# ---------------------------------------------------------------------------


def test_merge_under_budget_passes(tmp_path: Path) -> None:
    repo = _make_divergent(tmp_path, base_extra="(rowA2)", head_extra="(rowC2)")

    result = gate.evaluate(repo, base_ref="main", head_ref="feature", max_bytes=TEST_BUDGET)

    assert result.status == "pass"
    assert result.size is not None and result.size <= TEST_BUDGET


def test_clean_when_head_contains_base(tmp_path: Path) -> None:
    """When feature already contains base, the merge is feature's own tree."""
    repo = _make_divergent(tmp_path, base_extra="(rowA2)", head_extra="(rowC2)")
    _git(repo, "switch", "feature")
    _git(repo, "merge", "--no-edit", "main")
    head_own = _index_size(repo, "feature")

    result = gate.evaluate(repo, base_ref="main", head_ref="feature", max_bytes=TEST_BUDGET)

    assert result.status == "pass"
    assert result.size == head_own


def test_cmd_verify_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_divergent(tmp_path, base_extra="(rowA2)", head_extra="(rowC2)")

    rc = gate.main(["verify", "--repo-root", str(repo), "--skip-fetch", "--base-ref", "main", "--head-ref", "feature"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.startswith("OK:")


# ---------------------------------------------------------------------------
# Conflict and absent-index handling
# ---------------------------------------------------------------------------


def test_conflict_defers_to_branch_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A real merge conflict is not a budget failure; it defers with a warning."""
    repo = _init_repo(tmp_path)
    _commit_index(repo, "# index\nshared line\n", "base")
    _git(repo, "branch", "feature")
    _commit_index(repo, "# index\nbase version\n", "base edit")
    _git(repo, "switch", "feature")
    _commit_index(repo, "# index\nfeature version\n", "feature edit")
    _git(repo, "switch", "main")

    result = gate.evaluate(repo, base_ref="main", head_ref="feature", max_bytes=TEST_BUDGET)
    assert result.status == "conflict"

    rc = gate.main(["verify", "--repo-root", str(repo), "--skip-fetch", "--base-ref", "main", "--head-ref", "feature"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "conflicts with base" in captured.err


def test_absent_index_is_pass(tmp_path: Path) -> None:
    """A merge result with no docs/INDEX.md has nothing to budget."""
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("# repo\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "no index")
    _git(repo, "branch", "feature")

    result = gate.evaluate(repo, base_ref="main", head_ref="feature", max_bytes=TEST_BUDGET)

    assert result.status == "pass"
    assert result.size is None


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_bad_base_ref_hard_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_divergent(tmp_path, base_extra="(rowA2)", head_extra="(rowC2)")

    rc = gate.main(
        ["verify", "--repo-root", str(repo), "--skip-fetch", "--base-ref", "does-not-exist", "--head-ref", "feature"]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "::error::" in captured.err


def test_fetch_failure_hard_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _make_divergent(tmp_path, base_extra="(rowA2)", head_extra="(rowC2)")

    def _boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("git fetch origin main failed: offline")

    monkeypatch.setattr(gate, "fetch_base", _boom)

    rc = gate.main(["verify", "--repo-root", str(repo), "--head-ref", "feature"])
    assert rc == 1


def test_main_rejects_unknown_command(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        gate.main(["bogus"])


# ---------------------------------------------------------------------------
# fetch_base and the merge-tree abnormal-rc / fallback branches
# ---------------------------------------------------------------------------


def _fake_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_fetch_base_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gate, "run_git", lambda repo, args: _fake_completed(0))
    assert gate.fetch_base(tmp_path, remote="origin", base_branch="main") == "FETCH_HEAD"


def test_fetch_base_failure_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gate, "run_git", lambda repo, args: _fake_completed(128, stderr="no such remote"))
    with pytest.raises(RuntimeError, match="git fetch origin main failed"):
        gate.fetch_base(tmp_path, remote="origin", base_branch="main")


def test_merge_tree_abnormal_rc_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # rc not in (0, 1) is a git error, not a conflict: it must surface loudly.
    monkeypatch.setattr(gate, "run_git", lambda repo, args: _fake_completed(2, stderr="boom"))
    with pytest.raises(RuntimeError, match="git merge-tree .* failed"):
        gate.evaluate(tmp_path, base_ref="main", head_ref="feature", max_bytes=TEST_BUDGET)


def test_skip_fetch_without_base_ref_falls_back_to_remote_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # --skip-fetch with no --base-ref exercises the origin/<base> fallback; the
    # ref is absent in the temp repo, so the merge-tree error path returns 1.
    repo = _make_divergent(tmp_path, base_extra="(rowA2)", head_extra="(rowC2)")
    rc = gate.main(["verify", "--repo-root", str(repo), "--skip-fetch", "--head-ref", "feature"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "::error::" in captured.err
