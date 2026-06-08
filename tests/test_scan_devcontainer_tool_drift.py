"""Tests for ``scripts/scan_devcontainer_tool_drift.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import scan_devcontainer_tool_drift as drift

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# required_bins
# ---------------------------------------------------------------------------


def test_required_bins_reads_preflight_steps() -> None:
    bins = drift.required_bins()
    # uv and waza are declared required_bin in preflight_all.py STEPS.
    assert "uv" in bins
    assert "waza" in bins


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def _write_flake(tmp_path: Path, text: str) -> Path:
    (tmp_path / "flake.nix").write_text(text, encoding="utf-8")
    return tmp_path


class TestVerify:
    def test_missing_flake_errors(self, tmp_path: Path) -> None:
        errors = drift.verify(tmp_path)
        assert len(errors) == 1
        assert "flake.nix not found" in errors[0]

    def test_all_provisioned_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(drift, "required_bins", lambda: {"uv", "waza"})
        _write_flake(tmp_path, "pinned-uv ... waza-cli ...")
        assert drift.verify(tmp_path) == []

    def test_marker_absent_from_flake_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(drift, "required_bins", lambda: {"waza"})
        _write_flake(tmp_path, "pinned-uv only, no waza here")
        errors = drift.verify(tmp_path)
        assert len(errors) == 1
        assert "waza-cli" in errors[0]
        assert "not provisioned" in errors[0]

    def test_unregistered_tool_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(drift, "required_bins", lambda: {"mystery"})
        _write_flake(tmp_path, "anything")
        errors = drift.verify(tmp_path)
        assert len(errors) == 1
        assert "provisioning marker" in errors[0]
        assert "mystery" in errors[0]

    def test_allowlisted_tool_skipped(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(drift, "required_bins", lambda: {"mystery"})
        monkeypatch.setattr(drift, "ALLOWLIST", {"mystery": "host-only tool"})
        _write_flake(tmp_path, "anything")
        assert drift.verify(tmp_path) == []


# ---------------------------------------------------------------------------
# _cmd_verify / main
# ---------------------------------------------------------------------------


class TestCmd:
    def test_cmd_verify_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(drift, "verify", lambda _root: [])
        args = argparse.Namespace(repo_root=str(tmp_path))
        assert drift._cmd_verify(args) == 0

    def test_cmd_verify_fail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setattr(drift, "verify", lambda _root: ["::error::boom"])
        args = argparse.Namespace(repo_root=str(tmp_path))
        assert drift._cmd_verify(args) == 1
        assert "::error::boom" in capsys.readouterr().err

    def test_main_dispatches_verify(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(drift, "_cmd_verify", lambda _a: 0)
        assert drift.main(["verify"]) == 0

    def test_main_requires_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            drift.main([])


def test_repository_devcontainer_tools_are_provisioned() -> None:
    """The real repo must pass: uv and waza are both in flake.nix."""
    repo = Path(__file__).resolve().parents[1]
    assert drift.verify(repo) == []
