"""Tests for scripts/check_hooks_path.py.

Refs #961, #760. Verifies that the session-start hook auto-configures
core.hooksPath to .githooks when missing or wrong, and falls back to a
warning when the git config write fails.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import check_hooks_path as subject
import pytest

pytestmark = pytest.mark.shard_preflight


def _run(returncode: int, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_check_returns_none_when_hooks_path_correct() -> None:
    with patch("check_hooks_path._git_config", return_value=".githooks"):
        assert subject.check() is None


def test_check_auto_configures_when_hooks_path_missing() -> None:
    with (
        patch("check_hooks_path._git_config", return_value=None),
        patch("check_hooks_path._git_config_set", return_value=True) as mock_set,
    ):
        output = subject.check()
    mock_set.assert_called_once_with("core.hooksPath", ".githooks")
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert "auto-configured" in msg
    assert ".githooks" in msg


def test_check_auto_configures_when_hooks_path_wrong() -> None:
    with (
        patch("check_hooks_path._git_config", return_value=".husky"),
        patch("check_hooks_path._git_config_set", return_value=True) as mock_set,
    ):
        output = subject.check()
    mock_set.assert_called_once_with("core.hooksPath", ".githooks")
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert "auto-configured" in msg
    assert ".githooks" in msg


def test_check_returns_warning_when_auto_config_fails() -> None:
    with (
        patch("check_hooks_path._git_config", return_value=None),
        patch("check_hooks_path._git_config_set", return_value=False),
    ):
        output = subject.check()
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert "WARNING" in msg
    assert "git config core.hooksPath .githooks" in msg


def test_check_output_is_valid_json_on_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("check_hooks_path._git_config", return_value=None),
        patch("check_hooks_path._git_config_set", return_value=True),
    ):
        subject.main()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "hookSpecificOutput" in parsed


def test_main_produces_no_output_when_path_correct(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("check_hooks_path._git_config", return_value=".githooks"):
        subject.main()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_exits_zero_when_check_raises() -> None:
    with patch("check_hooks_path.check", side_effect=RuntimeError("unexpected")), pytest.raises(SystemExit) as exc_info:
        subject.main()
    assert exc_info.value.code == 0


class TestGitConfig:
    def test_returns_none_when_git_not_found(self) -> None:
        import shutil
        with patch.object(shutil, "which", return_value=None):
            assert subject._git_config("core.hooksPath") is None

    def test_returns_none_when_git_returns_error(self) -> None:
        with patch("subprocess.run", return_value=_run(1, "")):
            assert subject._git_config("core.hooksPath") is None

    def test_returns_stripped_value_on_success(self) -> None:
        with patch("subprocess.run", return_value=_run(0, ".githooks\n")):
            assert subject._git_config("core.hooksPath") == ".githooks"


class TestGitConfigSet:
    def test_returns_false_when_git_not_found(self) -> None:
        import shutil
        with patch.object(shutil, "which", return_value=None):
            assert subject._git_config_set("core.hooksPath", ".githooks") is False

    def test_returns_false_when_git_returns_error(self) -> None:
        with patch("subprocess.run", return_value=_run(1, "")):
            assert subject._git_config_set("core.hooksPath", ".githooks") is False

    def test_returns_true_on_success(self) -> None:
        with patch("subprocess.run", return_value=_run(0, "")):
            assert subject._git_config_set("core.hooksPath", ".githooks") is True
