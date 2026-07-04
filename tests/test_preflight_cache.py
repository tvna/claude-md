"""Tests for ``scripts/preflight_cache.py``.

Covers the content fingerprint (determinism, sensitivity to file content,
path, and the ``extra`` argv tokens), the per-clone cache path resolution
against a real temp git repo, the load / is_fresh / record round-trip, and the
read-only ``status`` CLI including its fail-open behaviour when git is
unavailable.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``. Refs #985.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import preflight_cache as pc
import pytest

pytestmark = pytest.mark.shard_preflight


def _init_repo(root: Path) -> None:
    """Initialise a minimal git repo covering the fingerprint input paths."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    # The host configures global commit signing against a signing server that
    # is unavailable for throwaway repos; disable it so the fixture commits.
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    (root / "scripts").mkdir()
    (root / "tests").mkdir()
    (root / "scripts" / "a.py").write_text("print('a')\n", encoding="utf-8")
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "docs.md").write_text("# docs\n", encoding="utf-8")  # tracked non-source data
    # A test-read data directory outside the old narrow allowlist. #2195: a
    # change here must bust the fingerprint because a test asserts its contents.
    (root / ".agents" / "skills" / "demo").mkdir(parents=True)
    (root / ".agents" / "skills" / "demo" / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)


# ---------------------------------------------------------------------------
# compute_fingerprint
# ---------------------------------------------------------------------------


class TestComputeFingerprint:
    def test_deterministic_for_same_tree(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        assert pc.compute_fingerprint(tmp_path) == pc.compute_fingerprint(tmp_path)

    def test_changes_when_tracked_content_changes(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        before = pc.compute_fingerprint(tmp_path)
        (tmp_path / "scripts" / "a.py").write_text("print('b')\n", encoding="utf-8")
        # No commit needed: the fingerprint hashes working-tree bytes.
        assert pc.compute_fingerprint(tmp_path) != before

    def test_stable_when_untracked_file_changes(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        before = pc.compute_fingerprint(tmp_path)
        # An untracked scratch file cannot affect a committed test run, so it
        # must not bust the cache (git ls-files never lists it).
        (tmp_path / "scratch.tmp").write_text("junk\n", encoding="utf-8")
        assert pc.compute_fingerprint(tmp_path) == before

    def test_changes_when_tracked_data_file_changes(self, tmp_path: Path) -> None:
        # #2195 regression guard: a tracked data file outside the old allowlist
        # (scripts/tests/pyproject.toml/uv.lock), here a docs page, must bust the
        # fingerprint, because tests read such files and assert their bytes.
        _init_repo(tmp_path)
        before = pc.compute_fingerprint(tmp_path)
        (tmp_path / "docs.md").write_text("# changed\n", encoding="utf-8")
        assert pc.compute_fingerprint(tmp_path) != before

    def test_changes_when_skills_data_file_changes(self, tmp_path: Path) -> None:
        # Acceptance criterion #2195: editing a file under .agents/skills/ must
        # invalidate the cached green. Under the old narrow allowlist this path
        # was invisible to the fingerprint, so a skills-only commit reused a
        # cached pass and the failure surfaced only in CI (retro #1577).
        _init_repo(tmp_path)
        before = pc.compute_fingerprint(tmp_path)
        skill = tmp_path / ".agents" / "skills" / "demo" / "SKILL.md"
        skill.write_text("# demo (edited)\n", encoding="utf-8")
        assert pc.compute_fingerprint(tmp_path) != before

    def test_excluded_pathspec_is_dropped_from_fingerprint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The denylist mechanism (EXCLUDED_PATHSPECS) must subtract a path from
        # the fingerprint so a change under it no longer busts the cache. The
        # shipped denylist is empty (nothing is provably test-irrelevant); this
        # exercises the :(exclude) plumbing that a future entry would rely on.
        _init_repo(tmp_path)
        monkeypatch.setattr(pc, "EXCLUDED_PATHSPECS", ("docs.md",))
        before = pc.compute_fingerprint(tmp_path)
        (tmp_path / "docs.md").write_text("# changed\n", encoding="utf-8")
        assert pc.compute_fingerprint(tmp_path) == before

    def test_extra_tokens_affect_digest(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        base = pc.compute_fingerprint(tmp_path, extra=())
        with_n = pc.compute_fingerprint(tmp_path, extra=("pytest", "-n", "auto"))
        assert base != with_n

    def test_path_rename_changes_digest(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        before = pc.compute_fingerprint(tmp_path)
        subprocess.run(["git", "mv", "scripts/a.py", "scripts/renamed.py"], cwd=tmp_path, check=True)
        assert pc.compute_fingerprint(tmp_path) != before

    def test_skips_listed_but_deleted_file(self, tmp_path: Path) -> None:
        # git ls-files can name a tracked path removed from the working tree
        # mid-rebase; hashing must not raise.
        _init_repo(tmp_path)
        (tmp_path / "scripts" / "a.py").unlink()
        # Should not raise even though git still tracks scripts/a.py.
        assert isinstance(pc.compute_fingerprint(tmp_path), str)


# ---------------------------------------------------------------------------
# cache_path / _git_dir
# ---------------------------------------------------------------------------


class TestCachePath:
    def test_cache_path_inside_git_dir(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        path = pc.cache_path(tmp_path)
        assert path.name == pc._CACHE_BASENAME
        assert path.parent.resolve() == (tmp_path / ".git").resolve()


# ---------------------------------------------------------------------------
# load / is_fresh / record
# ---------------------------------------------------------------------------


class TestLoad:
    def test_absent_returns_none(self, tmp_path: Path) -> None:
        assert pc.load(tmp_path / "nope.json") is None

    def test_malformed_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "c.json"
        p.write_text("{not json", encoding="utf-8")
        assert pc.load(p) is None

    def test_non_dict_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "c.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        assert pc.load(p) is None

    def test_valid_returns_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "c.json"
        p.write_text('{"fingerprint": "x", "status": "pass"}', encoding="utf-8")
        assert pc.load(p) == {"fingerprint": "x", "status": "pass"}


class TestIsFresh:
    def test_none_cache(self) -> None:
        assert pc.is_fresh(None, "x") is False

    def test_match_and_pass(self) -> None:
        assert pc.is_fresh({"fingerprint": "x", "status": "pass"}, "x") is True

    def test_match_but_not_pass(self) -> None:
        assert pc.is_fresh({"fingerprint": "x", "status": "fail"}, "x") is False

    def test_fingerprint_mismatch(self) -> None:
        assert pc.is_fresh({"fingerprint": "y", "status": "pass"}, "x") is False


class TestRecord:
    def test_round_trip(self, tmp_path: Path) -> None:
        p = tmp_path / "c.json"
        pc.record(p, "deadbeef")
        loaded = pc.load(p)
        assert loaded is not None
        assert loaded["fingerprint"] == "deadbeef"
        assert loaded["status"] == "pass"
        assert "recorded_at" in loaded
        assert pc.is_fresh(loaded, "deadbeef") is True

    def test_write_failure_is_swallowed(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # A directory path cannot be written as a file -> OSError, swallowed.
        target = tmp_path / "adir"
        target.mkdir()
        pc.record(target, "x")
        assert "could not write cache" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cache_disabled
# ---------------------------------------------------------------------------


class TestCacheDisabled:
    def test_default_enabled(self) -> None:
        assert pc.cache_disabled({}) is False

    def test_explicit_disable(self) -> None:
        assert pc.cache_disabled({"PREFLIGHT_NO_CACHE": "1"}) is True

    def test_other_value_enabled(self) -> None:
        assert pc.cache_disabled({"PREFLIGHT_NO_CACHE": "0"}) is False


# ---------------------------------------------------------------------------
# _format_status
# ---------------------------------------------------------------------------


class TestFormatStatus:
    def test_miss(self) -> None:
        assert "miss" in pc._format_status(None, "x")

    def test_fresh(self) -> None:
        cache: dict[str, object] = {
            "fingerprint": "x",
            "status": "pass",
            "recorded_at": "2026-05-31T00:00:00Z",
        }
        msg = pc._format_status(cache, "x")
        assert "fresh" in msg and "2026-05-31T00:00:00Z" in msg

    def test_stale(self) -> None:
        cache: dict[str, object] = {"fingerprint": "y", "status": "pass"}
        assert "stale" in pc._format_status(cache, "x")


# ---------------------------------------------------------------------------
# main (status CLI)
# ---------------------------------------------------------------------------


class TestMainStatus:
    def test_status_miss(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_repo(tmp_path)
        monkeypatch.setattr(pc, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(pc, "compute_fingerprint", lambda *a, **k: "fp")
        monkeypatch.setattr(pc, "cache_path", lambda *a, **k: tmp_path / "absent.json")
        assert pc.main(["status"]) == 0
        assert "miss" in capsys.readouterr().out

    def test_status_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cache_file = tmp_path / "c.json"
        pc.record(cache_file, "fp")
        monkeypatch.setattr(pc, "compute_fingerprint", lambda *a, **k: "fp")
        monkeypatch.setattr(pc, "cache_path", lambda *a, **k: cache_file)
        assert pc.main(["status"]) == 0
        assert "fresh" in capsys.readouterr().out

    def test_status_unavailable_on_git_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def boom(*_a: object, **_k: object) -> str:
            raise subprocess.CalledProcessError(128, ["git"])

        monkeypatch.setattr(pc, "compute_fingerprint", boom)
        assert pc.main(["status"]) == 0
        assert "unavailable" in capsys.readouterr().out
