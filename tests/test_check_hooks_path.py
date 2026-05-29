"""Tests for scripts/check_hooks_path.py.

Refs #760. Verifies that the session-start hook surfaces missing or wrong
core.hooksPath configuration.
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


def test_check_returns_warning_when_hooks_path_missing() -> None:
    with patch("check_hooks_path._git_config", return_value=None):
        output = subject.check()
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert "core.hooksPath is not set" in msg
    assert "git config core.hooksPath .githooks" in msg


def test_check_returns_warning_when_hooks_path_wrong() -> None:
    with patch("check_hooks_path._git_config", return_value=".husky"):
        output = subject.check()
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert ".husky" in msg
    assert "git config core.hooksPath .githooks" in msg


def test_check_output_is_valid_json_on_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("check_hooks_path._git_config", return_value=None):
        subject.main()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "hookSpecificOutput" in parsed


def test_main_produces_no_output_when_path_correct(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("check_hooks_path._git_config", return_value=".githooks"):
        subject.main()
    captured = capsys.readouterr()
    assert captured.out == ""
