"""Tests for ``scripts/preflight_uv_version.py``.

Refs #1207.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import preflight_uv_version as gate
import pytest

pytestmark = pytest.mark.shard_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_pyproject(tmp_path: Path, pin: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(f'[tool.uv]\nrequired-version = "=={pin}"\n')
    return p


def _fake_uv(tmp_path: Path, version: str) -> str:
    """Write an executable ``uv`` stub that prints ``uv <version> (...)``."""
    fake = tmp_path / "uv"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "uv {version} (fake 2026-06-05 aarch64-apple-darwin)"\n'
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(fake)


class TestParseUvVersion:
    def test_extracts_version_from_brew_shape(self) -> None:
        assert gate.parse_uv_version("uv 0.11.16 (Homebrew 2026-05-21 aarch64-apple-darwin)") == "0.11.16"

    def test_extracts_version_from_release_shape(self) -> None:
        assert gate.parse_uv_version("uv 0.11.11 (release 2026-05-01)") == "0.11.11"

    def test_returns_none_when_first_token_is_not_uv(self) -> None:
        assert gate.parse_uv_version("foo 0.11.16") is None

    def test_returns_none_on_empty(self) -> None:
        assert gate.parse_uv_version("") is None

    def test_returns_none_on_single_token(self) -> None:
        assert gate.parse_uv_version("uv") is None


class TestCheckVersion:
    def test_match_passes(self) -> None:
        result = gate.check_version(pin="0.11.11", running="0.11.11")
        assert result.status == "pass"
        assert "matches" in result.detail

    def test_mismatch_fails(self) -> None:
        result = gate.check_version(pin="0.11.11", running="0.11.16")
        assert result.status == "fail"
        assert "0.11.16" in result.detail
        assert "0.11.11" in result.detail

    def test_missing_uv_fails(self) -> None:
        result = gate.check_version(pin="0.11.11", running=None)
        assert result.status == "fail"
        assert "not found" in result.detail


class TestProbeUvVersion:
    def test_returns_version_when_fake_uv_prints_expected_shape(self, tmp_path: Path) -> None:
        fake = _fake_uv(tmp_path, "0.11.42")
        assert gate.probe_uv_version(uv_path=fake) == "0.11.42"

    def test_returns_none_when_uv_absent_from_path(self) -> None:
        with patch("preflight_uv_version.shutil.which", return_value=None):
            assert gate.probe_uv_version() is None

    def test_returns_none_when_uv_exits_nonzero(self, tmp_path: Path) -> None:
        broken = tmp_path / "uv"
        broken.write_text("#!/usr/bin/env bash\nexit 7\n")
        broken.chmod(broken.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        assert gate.probe_uv_version(uv_path=str(broken)) is None


class TestCli:
    def test_verify_passes_when_versions_match(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_pyproject(tmp_path, "0.11.11")
        with patch("preflight_uv_version.probe_uv_version", return_value="0.11.11"):
            exit_code = gate.main(["verify", "--repo-root", str(tmp_path)])
        assert exit_code == 0
        assert "OK:" in capsys.readouterr().out

    def test_verify_fails_with_fix_it_on_mismatch(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_pyproject(tmp_path, "0.11.11")
        with patch("preflight_uv_version.probe_uv_version", return_value="0.11.16"):
            exit_code = gate.main(["verify", "--repo-root", str(tmp_path)])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "0.11.16" in err
        assert "0.11.11" in err
        assert "setup_pinned_uv.sh" in err
        assert "nix develop" in err

    def test_verify_fails_when_uv_absent(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_pyproject(tmp_path, "0.11.11")
        with patch("preflight_uv_version.probe_uv_version", return_value=None):
            exit_code = gate.main(["verify", "--repo-root", str(tmp_path)])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "not found" in err

    def test_verify_fails_when_pin_unreadable(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = gate.main(["verify", "--repo-root", str(tmp_path)])
        assert exit_code == 1
        assert "cannot read uv pin" in capsys.readouterr().err

    def test_pyproject_override(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        custom = tmp_path / "custom.toml"
        custom.write_text('[tool.uv]\nrequired-version = "==9.9.9"\n')
        with patch("preflight_uv_version.probe_uv_version", return_value="9.9.9"):
            exit_code = gate.main(
                ["verify", "--repo-root", str(tmp_path), "--pyproject", str(custom)]
            )
        assert exit_code == 0


class TestRepoIntegration:
    """End-to-end test against the real repo pyproject.toml and the real
    ``preflight_uv_version.py`` invocation as CI runs it.
    """

    def test_script_runs_as_module_invocation(self) -> None:
        """The CI step invokes ``python3 scripts/preflight_uv_version.py verify``.
        Exercise that exact shape so a wiring bug (missing main, bad shebang
        path resolution) surfaces here too.
        """
        env = os.environ.copy()
        # Run with PATH stripped of uv so the script reports the missing-uv
        # branch deterministically (we are testing the wiring, not the host).
        # Subtract any directory that contains ``uv`` so the absent-uv branch
        # fires regardless of whether the host has uv installed.
        path_dirs = [d for d in env.get("PATH", "").split(os.pathsep) if not Path(d, "uv").exists()]
        env["PATH"] = os.pathsep.join(path_dirs)
        completed = subprocess.run(
            ["python3", "scripts/preflight_uv_version.py", "verify"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert completed.returncode == 1
        assert "not found" in completed.stderr
