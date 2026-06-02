"""Tests for ``scripts/devcontainer_pin_pr.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import devcontainer_pin_pr as dpp
import pytest

pytestmark = pytest.mark.shard_ci_ops


class _FakeGit:
    """Stand-in for ``run_git``: returns a configurable returncode per subcommand.

    ``rc_map`` maps the first git arg (e.g. ``"diff"``) to a returncode;
    unmapped subcommands return 0. When ``raise_on`` matches a subcommand and
    ``check`` is set, a CalledProcessError is raised (mirrors ``check=True``).
    """

    def __init__(self, rc_map: dict[str, int] | None = None, raise_on: str | None = None) -> None:
        self.rc_map = rc_map or {}
        self.raise_on = raise_on
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], *, check: bool = False, **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        sub = args[0]
        if check and self.raise_on == sub:
            raise subprocess.CalledProcessError(1, ["git", *args])
        return subprocess.CompletedProcess(["git", *args], self.rc_map.get(sub, 0))

    def ran(self, sub: str) -> bool:
        return any(c[0] == sub for c in self.calls)


def _template(tmp_path: Path) -> Path:
    p = tmp_path / "tmpl.md"
    p.write_text("Pinned to __GITHUB_SHA__ now.\n", encoding="utf-8")
    return p


def _open_argv(tmp_path: Path, *, sha: str = "abc123") -> list[str]:
    return [
        "open",
        "--github-sha",
        sha,
        "--base",
        "main",
        "--title",
        "fix(devcontainer): pin published agent images",
        "--commit-subject",
        "fix(devcontainer): pin published agent images",
        "--commit-trailer",
        "Refs #696",
        "--template",
        str(_template(tmp_path)),
        "--file",
        ".devcontainer/claude/devcontainer.json",
        "--file",
        "docs/runbooks/devcontainers.md",
    ]


@pytest.fixture
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")


# ---------------------------------------------------------------------------
# render_pr_body
# ---------------------------------------------------------------------------


class TestRenderPrBody:
    def test_substitutes_all_occurrences(self) -> None:
        out = dpp.render_pr_body("a __GITHUB_SHA__ b __GITHUB_SHA__", "deadbeef")
        assert out == "a deadbeef b deadbeef"

    def test_no_placeholder_is_passthrough(self) -> None:
        assert dpp.render_pr_body("no marker", "x") == "no marker"


# ---------------------------------------------------------------------------
# _cmd_open guards
# ---------------------------------------------------------------------------


class TestGuards:
    def test_missing_token_returns_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        assert dpp.main(_open_argv(tmp_path)) == 1

    def test_missing_repo_returns_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.delenv("REPO", raising=False)
        assert dpp.main(_open_argv(tmp_path)) == 1


# ---------------------------------------------------------------------------
# _cmd_open flow
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_env")
class TestOpenFlow:
    def test_no_changes_returns_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 0}))
        rc = dpp.main(_open_argv(tmp_path, sha="sha1"))
        assert rc == 0
        assert "already match sha1" in capsys.readouterr().out

    def test_branch_exists_with_open_pr_enables_and_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [{"number": 5}])
        enabled: list[int] = []
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: enabled.append(kw["pr_number"]))
        upserted: list[Any] = []

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            upserted.append(kw)
            return ("created", 99)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert enabled == [5]
        assert upserted == []  # existing PR short-circuits before upsert

    def test_branch_exists_without_pr_falls_through_to_upsert(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = _FakeGit({"diff": 1, "ls-remote": 0})
        monkeypatch.setattr(dpp, "run_git", git)
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])
        monkeypatch.setattr(dpp, "_upsert_pr", lambda **kw: ("created", 7))
        enabled: list[int] = []
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: enabled.append(kw["pr_number"]))
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert enabled == [7]
        assert not git.ran("commit")  # branch already existed; no new commit

    def test_branch_absent_creates_branch_then_upserts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = _FakeGit({"diff": 1, "ls-remote": 2})  # ls-remote --exit-code: 2 == no match
        monkeypatch.setattr(dpp, "run_git", git)
        captured: dict[str, Any] = {}

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            captured.update(kw)
            return ("created", 8)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: None)
        rc = dpp.main(_open_argv(tmp_path, sha="zz"))
        assert rc == 0
        assert git.ran("commit") and git.ran("push") and git.ran("checkout")
        assert captured["head"] == "codex/devcontainer-image-pins-zz"
        assert "zz" in captured["body"]  # template placeholder substituted

    def test_create_branch_git_failure_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 2}, raise_on="commit"))
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 1

    def test_list_open_prs_error_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))

        def _boom(**kw: Any) -> list[dict[str, Any]]:
            raise RuntimeError("List PRs failed")

        monkeypatch.setattr(dpp, "_list_open_prs", _boom)
        assert dpp.main(_open_argv(tmp_path)) == 1

    def test_unreadable_template_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])
        argv = _open_argv(tmp_path)
        argv[argv.index("--template") + 1] = str(tmp_path / "missing.md")
        assert dpp.main(argv) == 1

    def test_upsert_error_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])

        def _boom(**kw: Any) -> tuple[str, int]:
            raise RuntimeError("Create PR failed")

        monkeypatch.setattr(dpp, "_upsert_pr", _boom)
        assert dpp.main(_open_argv(tmp_path)) == 1

    def test_auto_merge_failure_is_a_warning_not_fatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])
        monkeypatch.setattr(dpp, "_upsert_pr", lambda **kw: ("created", 12))

        def _boom(**kw: Any) -> None:
            raise RuntimeError("automerge denied")

        monkeypatch.setattr(dpp, "_enable_auto_merge", _boom)
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert "auto-merge request failed for PR #12" in capsys.readouterr().err
