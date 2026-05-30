from __future__ import annotations

import json
from pathlib import Path

import nixpkgs_cooldown as nc
import pytest

pytestmark = pytest.mark.shard_ci_ops


def _write_pyproject(path: Path, value: str = "14 days") -> None:
    path.write_text(f'[tool.uv]\nexclude-newer = "{value}"\n', encoding="utf-8")


def _write_lock(path: Path, last_modified: int = 1_700_000_000) -> None:
    path.write_text(
        json.dumps({"nodes": {"nixpkgs": {"locked": {"lastModified": last_modified}}}}),
        encoding="utf-8",
    )


def test_reads_uv_cooldown_days(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "14 days")
    assert nc.read_uv_cooldown_days(pyproject) == 14


def test_rejects_missing_uv_cooldown(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.uv]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exclude-newer"):
        nc.read_uv_cooldown_days(pyproject)


def test_rejects_non_day_uv_cooldown(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "2 weeks")
    with pytest.raises(ValueError, match="<N> days"):
        nc.read_uv_cooldown_days(pyproject)


def test_reads_nixpkgs_last_modified(tmp_path: Path) -> None:
    lock = tmp_path / "flake.lock"
    _write_lock(lock, 1_700_000_000)
    assert nc.read_nixpkgs_last_modified(lock) == 1_700_000_000


def test_rejects_missing_nixpkgs_last_modified(tmp_path: Path) -> None:
    lock = tmp_path / "flake.lock"
    lock.write_text(json.dumps({"nodes": {"nixpkgs": {"locked": {}}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="lastModified"):
        nc.read_nixpkgs_last_modified(lock)


def test_verify_cooldown_passes_when_old_enough(tmp_path: Path) -> None:
    _write_pyproject(tmp_path / "pyproject.toml", "14 days")
    _write_lock(tmp_path / "flake.lock", 1_700_000_000)
    now = 1_700_000_000 + (14 * 24 * 60 * 60)
    assert nc.verify_cooldown(tmp_path, now_epoch=now) == []


def test_verify_cooldown_fails_when_too_new(tmp_path: Path) -> None:
    _write_pyproject(tmp_path / "pyproject.toml", "14 days")
    _write_lock(tmp_path / "flake.lock", 1_700_000_000)
    now = 1_700_000_000 + (13 * 24 * 60 * 60)
    errors = nc.verify_cooldown(tmp_path, now_epoch=now)
    assert errors
    assert "14 days" in errors[0]


def test_rejects_missing_pyproject_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot read"):
        nc.read_uv_cooldown_days(tmp_path / "missing.toml")


def test_rejects_malformed_toml(tmp_path: Path) -> None:
    bad = tmp_path / "pyproject.toml"
    bad.write_bytes(b"[[invalid")
    with pytest.raises(ValueError, match="malformed TOML"):
        nc.read_uv_cooldown_days(bad)


def test_rejects_non_string_exclude_newer(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool.uv]\nexclude-newer = 14\n', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a string"):
        nc.read_uv_cooldown_days(pyproject)


def test_rejects_missing_lock_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot read"):
        nc.read_nixpkgs_last_modified(tmp_path / "missing.lock")


def test_rejects_malformed_lock_json(tmp_path: Path) -> None:
    bad = tmp_path / "flake.lock"
    bad.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed JSON"):
        nc.read_nixpkgs_last_modified(bad)


def test_rejects_non_positive_last_modified(tmp_path: Path) -> None:
    lock = tmp_path / "flake.lock"
    lock.write_text(
        json.dumps({"nodes": {"nixpkgs": {"locked": {"lastModified": 0}}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="positive integer"):
        nc.read_nixpkgs_last_modified(lock)


def test_main_cli_fails_with_error_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_pyproject(tmp_path / "pyproject.toml", "14 days")
    _write_lock(tmp_path / "flake.lock", 1_700_000_000)
    now = 1_700_000_000 + (13 * 24 * 60 * 60)

    exit_code = nc.main(["verify", "--repo-root", str(tmp_path), "--now-epoch", str(now)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "nixpkgs cooldown check failed" in out


def test_main_cli_passes_when_lock_is_old_enough(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_pyproject(tmp_path / "pyproject.toml", "14 days")
    _write_lock(tmp_path / "flake.lock", 1_700_000_000)
    now = 1_700_000_000 + (14 * 24 * 60 * 60)

    exit_code = nc.main(["verify", "--repo-root", str(tmp_path), "--now-epoch", str(now)])

    assert exit_code == 0
    assert "OK" in capsys.readouterr().out


def test_main_cli_reports_value_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = nc.main(["verify", "--repo-root", str(tmp_path)])

    assert exit_code == 1
    assert "error:" in capsys.readouterr().err
