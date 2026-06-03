"""Tests for ``scripts/scan_allowlist_rationale.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import scan_allowlist_rationale as rationale

pytestmark = pytest.mark.shard_ci_ops


def _write_network(tmp_path: Path, name: str, text: str) -> Path:
    network_dir = tmp_path.joinpath(*rationale.NETWORK_SUBDIR)
    network_dir.mkdir(parents=True, exist_ok=True)
    (network_dir / name).write_text(text, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_missing_network_dir_errors(self, tmp_path: Path) -> None:
        errors = rationale.verify(tmp_path)
        assert len(errors) == 1
        assert "network allowlist directory not found" in errors[0]

    def test_no_allowlist_files_errors(self, tmp_path: Path) -> None:
        network_dir = tmp_path.joinpath(*rationale.NETWORK_SUBDIR)
        network_dir.mkdir(parents=True)
        errors = rationale.verify(tmp_path)
        assert len(errors) == 1
        assert "no *.allowlist files" in errors[0]

    def test_host_with_inline_rationale_passes(self, tmp_path: Path) -> None:
        _write_network(
            tmp_path,
            "shared.allowlist",
            "# header comment\napi.example.com  # required at runtime.\n",
        )
        assert rationale.verify(tmp_path) == []

    def test_bare_host_fails(self, tmp_path: Path) -> None:
        _write_network(tmp_path, "shared.allowlist", "api.example.com\n")
        errors = rationale.verify(tmp_path)
        assert len(errors) == 1
        assert "api.example.com" in errors[0]
        assert "no triage rationale" in errors[0]
        assert "line=1" in errors[0]

    def test_host_with_empty_inline_comment_fails(self, tmp_path: Path) -> None:
        _write_network(tmp_path, "shared.allowlist", "api.example.com  #\n")
        errors = rationale.verify(tmp_path)
        assert len(errors) == 1
        assert "no triage rationale" in errors[0]

    def test_include_directive_needs_no_rationale(self, tmp_path: Path) -> None:
        _write_network(
            tmp_path,
            "claude.allowlist",
            "@include shared.allowlist\napi.anthropic.com  # Anthropic API.\n",
        )
        assert rationale.verify(tmp_path) == []

    def test_blank_and_comment_lines_ignored(self, tmp_path: Path) -> None:
        _write_network(
            tmp_path,
            "shared.allowlist",
            "\n# standalone comment\n\napi.example.com  # ok.\n",
        )
        assert rationale.verify(tmp_path) == []

    def test_multiple_files_all_checked(self, tmp_path: Path) -> None:
        _write_network(tmp_path, "shared.allowlist", "a.example.com  # ok.\n")
        _write_network(tmp_path, "codex.allowlist", "b.example.com\n")
        errors = rationale.verify(tmp_path)
        assert len(errors) == 1
        assert "b.example.com" in errors[0]


# ---------------------------------------------------------------------------
# _cmd_verify / main
# ---------------------------------------------------------------------------


class TestCmd:
    def test_cmd_verify_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(rationale, "verify", lambda _root: [])
        args = argparse.Namespace(repo_root=str(tmp_path))
        assert rationale._cmd_verify(args) == 0

    def test_cmd_verify_fail(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(rationale, "verify", lambda _root: ["::error::boom"])
        args = argparse.Namespace(repo_root=str(tmp_path))
        assert rationale._cmd_verify(args) == 1
        assert "::error::boom" in capsys.readouterr().err

    def test_main_dispatches_verify(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rationale, "_cmd_verify", lambda _a: 0)
        assert rationale.main(["verify"]) == 0

    def test_main_requires_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            rationale.main([])


def test_repository_allowlists_are_triaged() -> None:
    """The real repo must pass: every committed allowlist host has a rationale."""
    repo = Path(__file__).resolve().parents[1]
    assert rationale.verify(repo) == []
