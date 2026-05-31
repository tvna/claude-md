"""Tests for ``scripts/preflight_main_freshness.py``.

Covers the stamp read/write helpers, freshness check logic, hook decision
function, and the stdin/stdout boundary of :func:`main`.

Refs #654.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import preflight_main_freshness as gate
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# read_stamp
# ---------------------------------------------------------------------------


class TestReadStamp:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert gate.read_stamp(tmp_path / "missing") is None

    def test_parses_valid_stamp(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
        p.write_text(f"sha=abc123\nfetched_at={now.isoformat()}\n", encoding="utf-8")
        stamp = gate.read_stamp(p)
        assert stamp is not None
        assert stamp.sha == "abc123"
        assert stamp.fetched_at == now

    def test_malformed_file_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        p.write_text("garbage\n", encoding="utf-8")
        assert gate.read_stamp(p) is None

    def test_missing_sha_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        p.write_text("fetched_at=2026-05-30T12:00:00+00:00\n", encoding="utf-8")
        assert gate.read_stamp(p) is None

    def test_missing_fetched_at_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        p.write_text("sha=abc\n", encoding="utf-8")
        assert gate.read_stamp(p) is None

    def test_invalid_timestamp_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        p.write_text("sha=abc\nfetched_at=not-a-date\n", encoding="utf-8")
        assert gate.read_stamp(p) is None

    def test_naive_datetime_gets_utc_tzinfo(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        p.write_text("sha=abc\nfetched_at=2026-05-30T12:00:00\n", encoding="utf-8")
        stamp = gate.read_stamp(p)
        assert stamp is not None
        assert stamp.fetched_at.tzinfo is not None


# ---------------------------------------------------------------------------
# write_stamp
# ---------------------------------------------------------------------------


class TestWriteStamp:
    def test_writes_and_returns_stamp(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        stamp = gate.write_stamp("deadbeef", path=p)
        assert stamp.sha == "deadbeef"
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "sha=deadbeef" in text
        assert "fetched_at=" in text

    def test_stamp_is_readable_back(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        written = gate.write_stamp("cafe1234", path=p)
        read_back = gate.read_stamp(p)
        assert read_back is not None
        assert read_back.sha == written.sha


# ---------------------------------------------------------------------------
# check_freshness
# ---------------------------------------------------------------------------


class TestCheckFreshness:
    def test_missing_stamp_returns_missing(self, tmp_path: Path) -> None:
        result = gate.check_freshness(path=tmp_path / "missing", ttl_seconds=3600)
        assert result.status == "missing"
        assert "record" in result.detail

    def test_fresh_stamp_returns_fresh(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        gate.write_stamp("abc", path=p)
        result = gate.check_freshness(path=p, ttl_seconds=3600)
        assert result.status == "fresh"
        assert result.stamp is not None

    def test_stale_stamp_returns_stale(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        stale_time = datetime.now(UTC) - timedelta(hours=2)
        p.write_text(f"sha=oldsha\nfetched_at={stale_time.isoformat()}\n", encoding="utf-8")
        result = gate.check_freshness(path=p, ttl_seconds=3600)
        assert result.status == "stale"
        assert "record" in result.detail

    def test_just_within_ttl_is_fresh(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        almost_stale = datetime.now(UTC) - timedelta(seconds=3599)
        p.write_text(f"sha=abc\nfetched_at={almost_stale.isoformat()}\n", encoding="utf-8")
        result = gate.check_freshness(path=p, ttl_seconds=3600)
        assert result.status == "fresh"

    def test_exactly_over_ttl_is_stale(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        just_stale = datetime.now(UTC) - timedelta(seconds=3601)
        p.write_text(f"sha=abc\nfetched_at={just_stale.isoformat()}\n", encoding="utf-8")
        result = gate.check_freshness(path=p, ttl_seconds=3600)
        assert result.status == "stale"


# ---------------------------------------------------------------------------
# decide (PreToolUse hook decision function)
# ---------------------------------------------------------------------------


class TestDecide:
    def test_off_target_tool_allows_regardless_of_stamp(self, tmp_path: Path) -> None:
        with patch.object(gate, "STAMP_FILE", tmp_path / "missing"):
            result = gate.decide("mcp__github__list_branches", {})
        assert result is None

    def test_off_target_bash_allows(self, tmp_path: Path) -> None:
        with patch.object(gate, "STAMP_FILE", tmp_path / "missing"):
            result = gate.decide("Bash", {"command": "git commit -m msg"})
        assert result is None

    def test_create_branch_without_stamp_denies(self, tmp_path: Path) -> None:
        with patch.object(gate, "STAMP_FILE", tmp_path / "missing"):
            result = gate.decide("mcp__github__create_branch", {})
        assert result is not None
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "record" in reason
        assert "preflight_main_freshness.py" in reason

    def test_create_branch_with_fresh_stamp_allows(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        gate.write_stamp("abc123", path=p)
        with patch.object(gate, "STAMP_FILE", p):
            result = gate.decide("mcp__github__create_branch", {})
        assert result is None

    def test_create_branch_with_stale_stamp_denies(self, tmp_path: Path) -> None:
        p = tmp_path / "stamp"
        stale = datetime.now(UTC) - timedelta(hours=2)
        p.write_text(f"sha=oldsha\nfetched_at={stale.isoformat()}\n", encoding="utf-8")
        with patch.object(gate, "STAMP_FILE", p):
            result = gate.decide("mcp__github__create_branch", {})
        assert result is not None
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_deny_reason_includes_tool_name(self, tmp_path: Path) -> None:
        with patch.object(gate, "STAMP_FILE", tmp_path / "missing"):
            result = gate.decide("mcp__github__create_branch", {})
        assert result is not None
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "mcp__github__create_branch" in reason


# ---------------------------------------------------------------------------
# main -- stdin/stdout boundary
# ---------------------------------------------------------------------------


class TestMain:
    def test_hook_mode_denies_create_branch_without_stamp(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        event = json.dumps({"tool_name": "mcp__github__create_branch", "tool_input": {"branch": "test"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(event))
        with patch.object(gate, "STAMP_FILE", tmp_path / "missing"):
            exit_code = gate.main([])
        assert exit_code == 0
        out = capsys.readouterr().out
        decision = json.loads(out)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_hook_mode_allows_create_branch_with_fresh_stamp(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = tmp_path / "stamp"
        gate.write_stamp("abc", path=p)
        event = json.dumps({"tool_name": "mcp__github__create_branch", "tool_input": {}})
        monkeypatch.setattr("sys.stdin", io.StringIO(event))
        with patch.object(gate, "STAMP_FILE", p):
            exit_code = gate.main([])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_hook_mode_allows_off_target_tool(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        event = json.dumps({"tool_name": "mcp__github__list_branches", "tool_input": {}})
        monkeypatch.setattr("sys.stdin", io.StringIO(event))
        with patch.object(gate, "STAMP_FILE", tmp_path / "missing"):
            exit_code = gate.main([])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_hook_mode_fails_open_on_malformed_json(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not valid json"))
        exit_code = gate.main([])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_hook_mode_fails_open_on_empty_stdin(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        exit_code = gate.main([])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_check_subcommand_fails_when_no_stamp(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(gate, "STAMP_FILE", tmp_path / "missing"):
            exit_code = gate.main(["check"])
        assert exit_code == 1

    def test_check_subcommand_passes_when_fresh(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        p = tmp_path / "stamp"
        gate.write_stamp("abc", path=p)
        with patch.object(gate, "STAMP_FILE", p):
            exit_code = gate.main(["check"])
        assert exit_code == 0

    def test_check_subcommand_fails_when_stale(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        p = tmp_path / "stamp"
        stale = datetime.now(UTC) - timedelta(hours=2)
        p.write_text(f"sha=old\nfetched_at={stale.isoformat()}\n", encoding="utf-8")
        with patch.object(gate, "STAMP_FILE", p):
            exit_code = gate.main(["check", "--ttl", "3600"])
        assert exit_code == 1

    def test_hook_mode_missing_tool_name_fails_open(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        event = json.dumps({"tool_input": {}})
        monkeypatch.setattr("sys.stdin", io.StringIO(event))
        exit_code = gate.main([])
        assert exit_code == 0
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# fetch_and_record error paths (lines 151-175)
# ---------------------------------------------------------------------------


class TestFetchAndRecord:
    def test_raises_when_git_not_found(self, tmp_path: Path) -> None:
        with patch("_git.shutil.which", return_value=None), pytest.raises(RuntimeError, match="git executable not found"):
            gate.fetch_and_record(repo=tmp_path, stamp_path=tmp_path / "stamp")

    def test_raises_on_fetch_failure(self, tmp_path: Path) -> None:
        import subprocess
        fake_fail = subprocess.CompletedProcess(["git"], returncode=1, stdout="", stderr="network error")
        with patch("_git.subprocess.run", return_value=fake_fail), pytest.raises(RuntimeError, match="git fetch origin main failed"):
            gate.fetch_and_record(repo=tmp_path, stamp_path=tmp_path / "stamp")

    def test_raises_on_rev_parse_failure(self, tmp_path: Path) -> None:
        import subprocess
        fetch_ok = subprocess.CompletedProcess(["git"], returncode=0, stdout="", stderr="")
        rev_fail = subprocess.CompletedProcess(["git"], returncode=1, stdout="", stderr="bad ref")
        call_count = 0

        def fake_run(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return fetch_ok if call_count == 1 else rev_fail

        with patch("_git.subprocess.run", side_effect=fake_run), pytest.raises(RuntimeError, match="git rev-parse"):
            gate.fetch_and_record(repo=tmp_path, stamp_path=tmp_path / "stamp")

    def test_success_returns_stamp(self, tmp_path: Path) -> None:
        import subprocess
        fetch_ok = subprocess.CompletedProcess(["git"], returncode=0, stdout="", stderr="")
        rev_ok = subprocess.CompletedProcess(["git"], returncode=0, stdout="abc1234567890\n", stderr="")
        call_count = 0

        def fake_run(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return fetch_ok if call_count == 1 else rev_ok

        stamp_path = tmp_path / "stamp"
        with patch("_git.subprocess.run", side_effect=fake_run):
            stamp = gate.fetch_and_record(repo=tmp_path, stamp_path=stamp_path)
        assert stamp.sha == "abc1234567890"


# ---------------------------------------------------------------------------
# _build_deny_dict (line 210)
# ---------------------------------------------------------------------------


def test_build_deny_dict_returns_hook_output() -> None:
    result = gate._build_deny_dict("reason text")
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "reason text" in result["hookSpecificOutput"]["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# _cmd_record via main CLI (lines 225-231)
# ---------------------------------------------------------------------------


class TestCmdRecord:
    def test_record_success(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import subprocess
        fetch_ok = subprocess.CompletedProcess(["git"], returncode=0, stdout="", stderr="")
        rev_ok = subprocess.CompletedProcess(["git"], returncode=0, stdout="abc1234567890\n", stderr="")
        call_count = 0

        def fake_run(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return fetch_ok if call_count == 1 else rev_ok

        stamp_path = tmp_path / "stamp"
        with patch("_git.subprocess.run", side_effect=fake_run), patch.object(gate, "STAMP_FILE", stamp_path):
            exit_code = gate.main(["record"])
        assert exit_code == 0
        assert "OK: recorded" in capsys.readouterr().out

    def test_record_failure_surfaces_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(gate, "fetch_and_record", side_effect=RuntimeError("fetch failed")):
            exit_code = gate.main(["record"])
        assert exit_code == 1
        assert "fetch failed" in capsys.readouterr().err
