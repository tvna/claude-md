from __future__ import annotations

import json
import subprocess
from pathlib import Path

import auto_retro as ar
import pytest
from auto_retro_test_helpers import merged_event, orchestrator_recorder

pytestmark = pytest.mark.shard_ci_ops_auto_retro_create_slow


class TestCLI:
    def test_run_reads_event_file_and_creates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        event = merged_event(number=8)
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event))
        seen = orchestrator_recorder(monkeypatch)
        exit_code = ar.main(
            ["run", "--event-file", str(event_file), "--repo", "o/r"]
        )
        assert exit_code == 0
        assert any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_run_uses_env_vars(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        event = merged_event(number=9)
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("REPO", "o/r")
        orchestrator_recorder(monkeypatch)
        assert ar.main(["run"]) == 0

    def test_run_missing_event_path_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
        monkeypatch.setenv("REPO", "o/r")
        assert ar.main(["run"]) == 1
        assert "GITHUB_EVENT_PATH" in capsys.readouterr().err

    def test_run_missing_repo_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{}")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        assert ar.main(["run"]) == 1
        assert "REPO" in capsys.readouterr().err

    def test_run_malformed_event_file_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{not json")
        exit_code = ar.main(
            ["run", "--event-file", str(event_file), "--repo", "o/r"]
        )
        assert exit_code == 1
        assert "cannot read event file" in capsys.readouterr().err

    def test_run_no_pr_in_event_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{}")
        exit_code = ar.main(
            ["run", "--event-file", str(event_file), "--repo", "o/r"]
        )
        assert exit_code == 1
        assert "no pull_request.number" in capsys.readouterr().err

    def test_run_gh_api_failure_is_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def _raise(*_a, **_kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="auth fail")

        monkeypatch.setattr(ar, "gh_api", _raise)
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(merged_event()))
        exit_code = ar.main(
            ["run", "--event-file", str(event_file), "--repo", "o/r"]
        )
        assert exit_code == 1
        assert "gh api failed" in capsys.readouterr().err
