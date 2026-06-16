"""Tests for ``scripts/preflight_coverage.py``.

Refs #952.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import preflight_coverage as cov
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# changed_scripts
# ---------------------------------------------------------------------------


class TestChangedScripts:
    def test_returns_changed_py_files(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/git"),
            patch("preflight_coverage.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="scripts/preflight_foo.py\nscripts/body_policy.py\n",
                stderr="",
            )
            result = cov.changed_scripts(tmp_path)
        assert result == ["scripts/preflight_foo.py", "scripts/body_policy.py"]

    def test_filters_private_helpers(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/git"),
            patch("preflight_coverage.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="scripts/_github_api.py\nscripts/preflight_foo.py\n",
                stderr="",
            )
            result = cov.changed_scripts(tmp_path)
        assert result == ["scripts/preflight_foo.py"]

    def test_filters_non_py_files(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/git"),
            patch("preflight_coverage.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="scripts/translations.json\nscripts/preflight_foo.py\n",
                stderr="",
            )
            result = cov.changed_scripts(tmp_path)
        assert result == ["scripts/preflight_foo.py"]

    def test_empty_diff_returns_empty_list(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/git"),
            patch("preflight_coverage.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            )
            result = cov.changed_scripts(tmp_path)
        assert result == []

    def test_raises_on_git_failure(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/git"),
            patch("preflight_coverage.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=128,
                stdout="",
                stderr="not a git repository",
            )
            with pytest.raises(RuntimeError, match="git diff failed"):
                cov.changed_scripts(tmp_path)

    def test_raises_when_git_not_found(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="git executable not found"),
        ):
            cov.changed_scripts(tmp_path)

    def test_custom_base_ref_is_passed_to_git(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/git"),
            patch("preflight_coverage.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            )
            cov.changed_scripts(tmp_path, base_ref="HEAD~1")
        cmd = mock_run.call_args[0][0]
        assert "HEAD~1" in cmd

    def test_diff_filter_excludes_deleted_files(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/git"),
            patch("preflight_coverage.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            )
            cov.changed_scripts(tmp_path)
        cmd = mock_run.call_args[0][0]
        assert "--diff-filter=d" in cmd


# ---------------------------------------------------------------------------
# ensure_coverage_json
# ---------------------------------------------------------------------------


class TestEnsureCoverageJson:
    def test_returns_existing_json(self, tmp_path: Path) -> None:
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text("{}")
        result = cov.ensure_coverage_json(tmp_path)
        assert result == cov_file

    def test_runs_pytest_when_absent(self, tmp_path: Path) -> None:
        expected = tmp_path / "coverage.json"

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            expected.write_text("{}")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/uv"),
            patch("preflight_coverage.subprocess.run", side_effect=fake_run),
        ):
            result = cov.ensure_coverage_json(tmp_path)
        assert result == expected

    def test_raises_when_uv_not_found_and_no_json(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="uv not found"),
        ):
            cov.ensure_coverage_json(tmp_path)

    def test_raises_when_pytest_fails_to_produce_json(self, tmp_path: Path) -> None:
        with (
            patch("preflight_coverage.shutil.which", return_value="/usr/bin/uv"),
            patch("preflight_coverage.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            with pytest.raises(RuntimeError, match="coverage.json not generated"):
                cov.ensure_coverage_json(tmp_path)


# ---------------------------------------------------------------------------
# parse_coverage_json
# ---------------------------------------------------------------------------


class TestParseCoverageJson:
    def test_extracts_percent_covered(self, tmp_path: Path) -> None:
        data = {
            "files": {
                "scripts/preflight_foo.py": {
                    "summary": {
                        "percent_covered": 92.5,
                        "covered_lines": 37,
                        "num_statements": 40,
                    }
                }
            }
        }
        p = tmp_path / "coverage.json"
        p.write_text(json.dumps(data))
        result = cov.parse_coverage_json(p)
        assert result == {"scripts/preflight_foo.py": 92.5}

    def test_handles_integer_percent(self, tmp_path: Path) -> None:
        data = {"files": {"scripts/foo.py": {"summary": {"percent_covered": 100}}}}
        p = tmp_path / "coverage.json"
        p.write_text(json.dumps(data))
        result = cov.parse_coverage_json(p)
        assert result["scripts/foo.py"] == 100.0

    def test_skips_missing_summary(self, tmp_path: Path) -> None:
        data = {"files": {"scripts/foo.py": {"no_summary": True}}}
        p = tmp_path / "coverage.json"
        p.write_text(json.dumps(data))
        result = cov.parse_coverage_json(p)
        assert result == {}

    def test_skips_non_numeric_percent(self, tmp_path: Path) -> None:
        data = {
            "files": {"scripts/foo.py": {"summary": {"percent_covered": "N/A"}}}
        }
        p = tmp_path / "coverage.json"
        p.write_text(json.dumps(data))
        result = cov.parse_coverage_json(p)
        assert result == {}

    def test_empty_files(self, tmp_path: Path) -> None:
        data: dict[str, object] = {"files": {}}
        p = tmp_path / "coverage.json"
        p.write_text(json.dumps(data))
        result = cov.parse_coverage_json(p)
        assert result == {}

    def test_non_dict_files_returns_empty(self, tmp_path: Path) -> None:
        data = {"files": "not-a-dict"}
        p = tmp_path / "coverage.json"
        p.write_text(json.dumps(data))
        result = cov.parse_coverage_json(p)
        assert result == {}


# ---------------------------------------------------------------------------
# check_per_file
# ---------------------------------------------------------------------------


class TestCheckPerFile:
    def test_passes_when_all_above_floor(self) -> None:
        coverage = {"scripts/foo.py": 95.0, "scripts/bar.py": 100.0}
        failures = cov.check_per_file(
            ["scripts/foo.py", "scripts/bar.py"], coverage, floor=90.0
        )
        assert failures == []

    def test_fails_when_below_floor(self) -> None:
        coverage = {"scripts/foo.py": 75.0}
        failures = cov.check_per_file(["scripts/foo.py"], coverage, floor=90.0)
        assert len(failures) == 1
        path, reason = failures[0]
        assert path == "scripts/foo.py"
        assert "75.0%" in reason

    def test_fails_when_absent(self) -> None:
        failures = cov.check_per_file(["scripts/foo.py"], {}, floor=90.0)
        assert len(failures) == 1
        path, reason = failures[0]
        assert path == "scripts/foo.py"
        assert "absent" in reason

    def test_exactly_at_floor_passes(self) -> None:
        coverage = {"scripts/foo.py": 90.0}
        failures = cov.check_per_file(["scripts/foo.py"], coverage, floor=90.0)
        assert failures == []

    def test_mixed_pass_and_fail(self) -> None:
        coverage = {"scripts/foo.py": 95.0, "scripts/bar.py": 60.0}
        targets = ["scripts/foo.py", "scripts/bar.py"]
        failures = cov.check_per_file(targets, coverage, floor=90.0)
        assert len(failures) == 1
        assert failures[0][0] == "scripts/bar.py"

    def test_empty_targets_returns_empty(self) -> None:
        failures = cov.check_per_file([], {"scripts/foo.py": 95.0}, floor=90.0)
        assert failures == []


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_passes_when_no_changed_scripts(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("preflight_coverage.changed_scripts", return_value=[]):
            rc = cov.main([])
        assert rc == 0
        assert "no public scripts" in capsys.readouterr().out

    def test_passes_when_coverage_above_floor(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cov_data = {
            "files": {
                "scripts/preflight_foo.py": {"summary": {"percent_covered": 95.0}}
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov_data))
        with patch(
            "preflight_coverage.changed_scripts",
            return_value=["scripts/preflight_foo.py"],
        ):
            rc = cov.main(["--coverage-json", str(cov_file)])
        assert rc == 0
        assert "95.0%" in capsys.readouterr().out

    def test_fails_when_coverage_below_floor(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cov_data = {
            "files": {
                "scripts/preflight_foo.py": {"summary": {"percent_covered": 70.0}}
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov_data))
        with patch(
            "preflight_coverage.changed_scripts",
            return_value=["scripts/preflight_foo.py"],
        ):
            rc = cov.main(["--coverage-json", str(cov_file)])
        assert rc == 1
        assert "70.0%" in capsys.readouterr().err

    def test_fails_when_script_absent_from_coverage(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps({"files": {}}))
        with patch(
            "preflight_coverage.changed_scripts",
            return_value=["scripts/preflight_foo.py"],
        ):
            rc = cov.main(["--coverage-json", str(cov_file)])
        assert rc == 1
        assert "absent" in capsys.readouterr().err

    def test_git_failure_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch(
            "preflight_coverage.changed_scripts",
            side_effect=RuntimeError("git diff failed: not a repo"),
        ):
            rc = cov.main([])
        assert rc == 1
        assert "coverage preflight" in capsys.readouterr().err

    def test_custom_floor_respected(self, tmp_path: Path) -> None:
        cov_data = {
            "files": {"scripts/foo.py": {"summary": {"percent_covered": 85.0}}}
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov_data))
        with patch(
            "preflight_coverage.changed_scripts", return_value=["scripts/foo.py"]
        ):
            assert (
                cov.main(["--coverage-json", str(cov_file), "--floor", "80"]) == 0
            )
            assert (
                cov.main(["--coverage-json", str(cov_file), "--floor", "90"]) == 1
            )

    def test_unreadable_coverage_json_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text("not valid json{{{")
        with patch(
            "preflight_coverage.changed_scripts",
            return_value=["scripts/preflight_foo.py"],
        ):
            rc = cov.main(["--coverage-json", str(cov_file)])
        assert rc == 1
        assert "cannot read" in capsys.readouterr().err

    def test_multiple_failures_reported(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cov_data = {
            "files": {
                "scripts/foo.py": {"summary": {"percent_covered": 50.0}},
                "scripts/bar.py": {"summary": {"percent_covered": 60.0}},
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov_data))
        with patch(
            "preflight_coverage.changed_scripts",
            return_value=["scripts/foo.py", "scripts/bar.py"],
        ):
            rc = cov.main(["--coverage-json", str(cov_file)])
        assert rc == 1
        stderr = capsys.readouterr().err
        assert "2 script(s)" in stderr
