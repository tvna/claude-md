"""Tests for scripts/check_session_branch.py.

Refs #785. Verifies that the SessionStart hook surfaces the session push
target when running in a remote execution environment and is silent
otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import check_session_branch as subject
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# check() — environment gate
# ---------------------------------------------------------------------------


def test_check_returns_none_when_not_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    assert subject.check() is None


def test_check_returns_none_when_remote_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "false")
    assert subject.check() is None


def test_check_returns_none_when_branch_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    with patch("check_session_branch._current_branch", return_value=None):
        assert subject.check() is None


# ---------------------------------------------------------------------------
# check() — notice content
# ---------------------------------------------------------------------------


def test_check_returns_notice_with_branch_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    branch = "claude/stoic-johnson-ryJlF"
    with (
        patch("check_session_branch._current_branch", return_value=branch),
        patch.object(subject, "_SESSION_BRANCH_FILE", tmp_path / "CLAUDE_SESSION_BRANCH"),
    ):
        output = subject.check()
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert branch in msg
    assert "git push origin" in msg


def test_check_message_includes_refspec_example(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    branch = "claude/test-branch-abc123"
    with (
        patch("check_session_branch._current_branch", return_value=branch),
        patch.object(subject, "_SESSION_BRANCH_FILE", tmp_path / "CLAUDE_SESSION_BRANCH"),
    ):
        output = subject.check()
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert f"<local-branch>:{branch}" in msg


# ---------------------------------------------------------------------------
# check() — file write
# ---------------------------------------------------------------------------


def test_check_writes_session_branch_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    branch = "claude/session-xyz"
    branch_file = tmp_path / "CLAUDE_SESSION_BRANCH"
    with (
        patch("check_session_branch._current_branch", return_value=branch),
        patch.object(subject, "_SESSION_BRANCH_FILE", branch_file),
    ):
        subject.check()
    assert branch_file.read_text().splitlines() == [branch]


def test_check_appends_without_clobbering_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A second session in the same container (paired work / post-merge
    # follow-up) must ADD its branch, not overwrite the partner's entry.
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    branch_file = tmp_path / "CLAUDE_SESSION_BRANCH"
    branch_file.write_text("claude/partner-a\n")
    with (
        patch("check_session_branch._current_branch", return_value="claude/session-b"),
        patch.object(subject, "_SESSION_BRANCH_FILE", branch_file),
    ):
        subject.check()
    assert set(branch_file.read_text().splitlines()) == {
        "claude/partner-a",
        "claude/session-b",
    }


def test_check_append_is_deduped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Re-starting a session on a branch already recorded must not duplicate it.
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    branch = "claude/session-xyz"
    branch_file = tmp_path / "CLAUDE_SESSION_BRANCH"
    branch_file.write_text(f"{branch}\n")
    with (
        patch("check_session_branch._current_branch", return_value=branch),
        patch.object(subject, "_SESSION_BRANCH_FILE", branch_file),
    ):
        subject.check()
    assert branch_file.read_text().splitlines() == [branch]


def test_check_survives_unwritable_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    branch = "claude/session-xyz"
    # Point to a path whose parent does not exist → OSError on write
    bad_path = tmp_path / "nonexistent_dir" / "CLAUDE_SESSION_BRANCH"
    with (
        patch("check_session_branch._current_branch", return_value=branch),
        patch.object(subject, "_SESSION_BRANCH_FILE", bad_path),
    ):
        output = subject.check()
    # Still returns notice despite write failure
    assert output is not None
    assert branch in output["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_emits_json_when_remote(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    branch = "claude/test-main"
    with (
        patch("check_session_branch._current_branch", return_value=branch),
        patch.object(subject, "_SESSION_BRANCH_FILE", tmp_path / "CLAUDE_SESSION_BRANCH"),
    ):
        subject.main()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "hookSpecificOutput" in parsed
    assert branch in parsed["hookSpecificOutput"]["additionalContext"]


def test_main_silent_when_not_remote(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    subject.main()
    assert capsys.readouterr().out == ""


def test_main_exits_zero_when_check_raises() -> None:
    with (
        patch("check_session_branch.check", side_effect=RuntimeError("boom")),
        pytest.raises(SystemExit) as exc_info,
    ):
        subject.main()
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# _current_branch() — subprocess handling
# ---------------------------------------------------------------------------


class TestCurrentBranch:
    def test_returns_branch_name_on_success(self) -> None:
        import subprocess

        fake = subprocess.CompletedProcess(["git"], 0, stdout="main\n", stderr="")
        with patch("subprocess.run", return_value=fake):
            assert subject._current_branch() == "main"

    def test_returns_none_on_nonzero_exit(self) -> None:
        import subprocess

        fake = subprocess.CompletedProcess(["git"], 128, stdout="", stderr="not a repo")
        with patch("subprocess.run", return_value=fake):
            assert subject._current_branch() is None

    def test_returns_none_on_empty_output(self) -> None:
        import subprocess

        fake = subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")
        with patch("subprocess.run", return_value=fake):
            assert subject._current_branch() is None

    def test_returns_none_on_os_error(self) -> None:
        with patch("subprocess.run", side_effect=OSError("git not found")):
            assert subject._current_branch() is None
