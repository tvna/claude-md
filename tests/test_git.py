"""Tests for ``scripts/_git.py``.

Verifies the shared git runner's plumbing without depending on a real
repository: that it resolves git from PATH, raises when git is absent, and
forwards cwd/check/timeout to ``subprocess.run`` while always capturing text
output.

Refs #1005.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import _git
import pytest

pytestmark = pytest.mark.shard_preflight


class TestRunGit:
    def test_raises_when_git_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_git.shutil, "which", lambda _name: None)
        with pytest.raises(RuntimeError, match="git executable not found"):
            _git.run_git(["status"])

    def test_invokes_resolved_git_with_captured_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")

        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        monkeypatch.setattr(_git.subprocess, "run", fake_run)
        result = _git.run_git(["rev-parse", "HEAD"], cwd=Path("/repo"), timeout=5)

        kwargs: dict[str, Any] = captured["kwargs"]
        assert captured["argv"] == ["/usr/bin/git", "rev-parse", "HEAD"]
        assert kwargs["cwd"] == Path("/repo")
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 5
        assert result.stdout == "ok"

    def test_check_true_is_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")

        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            seen.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setattr(_git.subprocess, "run", fake_run)
        _git.run_git(["fetch"], check=True)
        assert seen["check"] is True

    def test_returns_completed_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")
        sentinel = subprocess.CompletedProcess(["git"], 1, stdout="", stderr="boom")
        monkeypatch.setattr(_git.subprocess, "run", lambda *a, **k: sentinel)
        assert _git.run_git(["status"]) is sentinel


class TestMakeRunner:
    def test_binds_cwd_and_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")

        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            seen["argv"] = argv
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setattr(_git.subprocess, "run", fake_run)
        runner = _git.make_runner(cwd=Path("/repo"), timeout=7)
        runner(["rev-parse", "HEAD"])
        assert seen["argv"] == ["/usr/bin/git", "rev-parse", "HEAD"]
        assert seen["kwargs"]["cwd"] == Path("/repo")
        assert seen["kwargs"]["timeout"] == 7

    def test_defaults_to_no_cwd_no_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")
        monkeypatch.setattr(
            _git.subprocess,
            "run",
            lambda argv, **kwargs: seen.update(kwargs)
            or subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
        )
        _git.make_runner()(["status"])
        assert seen["cwd"] is None
        assert seen["timeout"] is None


class TestRevList:
    @staticmethod
    def _runner(
        result: subprocess.CompletedProcess[str] | Exception, calls: list[list[str]]
    ) -> _git.Runner:
        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if isinstance(result, Exception):
                raise result
            return result

        return run

    def test_prefixes_rev_list_and_strips_blanks(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner(
            subprocess.CompletedProcess(["git"], 0, stdout="a\n\n b \n", stderr=""), calls
        )
        assert _git.rev_list(runner, ["base..HEAD"]) == ["a", "b"]
        assert calls == [["rev-list", "base..HEAD"]]

    def test_empty_output_is_empty_list(self) -> None:
        runner = self._runner(subprocess.CompletedProcess(["git"], 0, stdout="\n", stderr=""), [])
        assert _git.rev_list(runner, ["base..HEAD"]) == []

    def test_nonzero_exit_returns_none(self) -> None:
        runner = self._runner(subprocess.CompletedProcess(["git"], 128, stdout="", stderr="no"), [])
        assert _git.rev_list(runner, ["bad..HEAD"]) is None

    def test_subprocess_error_returns_none(self) -> None:
        runner = self._runner(OSError("boom"), [])
        assert _git.rev_list(runner, ["base..HEAD"]) is None
