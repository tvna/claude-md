"""Tests for scripts/scan_provisioning_hook_serial.py.

A pre-commit hook that provisions a shared binary (entry runs install_*.sh)
must be require_serial so prek does not race parallel copies (#1150, #1155).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import scan_provisioning_hook_serial as gate

pytestmark = pytest.mark.shard_ci_ops


def _cfg(entry: str, *, serial: bool | None) -> dict[str, Any]:
    hook: dict[str, Any] = {"id": "h", "entry": entry}
    if serial is not None:
        hook["require_serial"] = serial
    return {"repos": [{"repo": "local", "hooks": [hook]}]}


def test_detects_provisioning_hook() -> None:
    cfg = _cfg("bash -c 'scripts/install_waza.sh && x'", serial=True)
    assert len(gate.provisioning_hooks(cfg)) == 1


def test_non_provisioning_hook_ignored() -> None:
    cfg = _cfg("uv run python scripts/foo.py verify", serial=None)
    assert gate.provisioning_hooks(cfg) == []
    assert gate.find_gaps(cfg) == []


def test_provisioning_without_serial_is_flagged() -> None:
    cfg = _cfg("scripts/install_waza.sh", serial=None)
    gaps = gate.find_gaps(cfg)
    assert len(gaps) == 1
    assert "require_serial" in gaps[0]


def test_provisioning_serial_false_is_flagged() -> None:
    cfg = _cfg("scripts/install_waza.sh", serial=False)
    assert len(gate.find_gaps(cfg)) == 1


def test_provisioning_with_serial_passes() -> None:
    cfg = _cfg("scripts/install_waza.sh", serial=True)
    assert gate.find_gaps(cfg) == []


def test_real_config_is_clean() -> None:
    """skill-quality-gate provisions waza and must stay require_serial."""
    cfg = gate._load_config()
    assert gate.provisioning_hooks(cfg), "expected a provisioning hook in config"
    assert gate.find_gaps(cfg) == []


def test_cli_verify_clean() -> None:
    assert gate.main(["verify"]) == 0


def test_cli_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["list"]) == 0
    assert "require_serial" in capsys.readouterr().out


def test_load_config_missing_file_raises_systemexit(tmp_path: Path) -> None:
    # OSError when config file is absent -> lines 86-87 (except + raise SystemExit).
    with pytest.raises(SystemExit):
        gate._load_config(tmp_path / "nonexistent.yaml")


def test_load_config_non_dict_yaml_raises_systemexit(tmp_path: Path) -> None:
    # YAML that parses to a list (not a mapping) -> line 90 (raise SystemExit).
    bad = tmp_path / "bad.yaml"
    bad.write_text("- list\n- item\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        gate._load_config(bad)
