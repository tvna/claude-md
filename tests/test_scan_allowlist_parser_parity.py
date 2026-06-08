"""Tests for ``scripts/scan_allowlist_parser_parity.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath`` key
under ``[tool.pytest.ini_options]`` in ``pyproject.toml``. These tests exercise
the bash<->Python parser-parity gate end to end (they shell out to ``bash``,
which is present on every supported runner).
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest
import scan_allowlist_parser_parity as parity
from _allowlist import resolve_hosts

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_LIB = REPO_ROOT.joinpath(*parity.EGRESS_LIB_SUBPATH)


def _scaffold(
    tmp_path: Path, *, lib_body: str, allowlists: dict[str, str]
) -> Path:
    """Build a tmp repo-root with an egress lib and allowlist files."""
    scripts_dir = tmp_path.joinpath(".devcontainer", "scripts")
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "_egress-lib.sh").write_text(lib_body, encoding="utf-8")
    network_dir = tmp_path.joinpath(*parity.NETWORK_SUBDIR)
    network_dir.mkdir(parents=True)
    for name, text in allowlists.items():
        (network_dir / name).write_text(text, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# bash_resolve_hosts
# ---------------------------------------------------------------------------


def test_bash_resolve_hosts_matches_python_on_includes(tmp_path: Path) -> None:
    (tmp_path / "shared.allowlist").write_text(
        "github.com  # shared\n", encoding="utf-8"
    )
    agent = tmp_path / "agent.allowlist"
    agent.write_text(
        "@include shared.allowlist\n"
        "# comment\n"
        "api.agent.com  # agent host\n",
        encoding="utf-8",
    )
    assert parity.bash_resolve_hosts(agent, REAL_LIB) == resolve_hosts(agent)
    assert parity.bash_resolve_hosts(agent, REAL_LIB) == {
        "github.com",
        "api.agent.com",
    }


def test_bash_resolve_hosts_raises_on_parse_failure(tmp_path: Path) -> None:
    lib = tmp_path / "lib.sh"
    lib.write_text("read_allowlist() { return 3; }\n", encoding="utf-8")
    target = tmp_path / "a.allowlist"
    target.write_text("a.example.com\n", encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError):
        parity.bash_resolve_hosts(target, lib)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def test_verify_passes_when_parsers_agree(tmp_path: Path) -> None:
    root = _scaffold(
        tmp_path,
        lib_body=REAL_LIB.read_text(encoding="utf-8"),
        allowlists={
            "shared.allowlist": "github.com  # shared\n",
            "agent.allowlist": "@include shared.allowlist\napi.agent.com  # host\n",
        },
    )
    assert parity.verify(root) == []


def test_verify_reports_mismatch(tmp_path: Path) -> None:
    # A bash parser that injects an extra host diverges from the Python parser.
    root = _scaffold(
        tmp_path,
        lib_body='read_allowlist() { printf "%s\\n" real.example.com extra.example.com; }\n',
        allowlists={"a.allowlist": "real.example.com  # ok\n"},
    )
    errors = parity.verify(root)
    assert len(errors) == 1
    assert "parser mismatch" in errors[0]
    assert "extra.example.com" in errors[0]


def test_verify_reports_bash_failure(tmp_path: Path) -> None:
    root = _scaffold(
        tmp_path,
        lib_body="read_allowlist() { return 4; }\n",
        allowlists={"a.allowlist": "a.example.com  # ok\n"},
    )
    errors = parity.verify(root)
    assert len(errors) == 1
    assert "bash read_allowlist failed" in errors[0]


def test_verify_missing_lib_errors(tmp_path: Path) -> None:
    network_dir = tmp_path.joinpath(*parity.NETWORK_SUBDIR)
    network_dir.mkdir(parents=True)
    (network_dir / "a.allowlist").write_text("a.example.com  # ok\n", encoding="utf-8")
    errors = parity.verify(tmp_path)
    assert len(errors) == 1
    assert "egress bash library not found" in errors[0]


def test_verify_missing_network_dir_errors(tmp_path: Path) -> None:
    scripts_dir = tmp_path.joinpath(".devcontainer", "scripts")
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "_egress-lib.sh").write_text(
        REAL_LIB.read_text(encoding="utf-8"), encoding="utf-8"
    )
    errors = parity.verify(tmp_path)
    assert len(errors) == 1
    assert "network allowlist directory not found" in errors[0]


def test_verify_no_allowlist_files_errors(tmp_path: Path) -> None:
    root = _scaffold(
        tmp_path, lib_body=REAL_LIB.read_text(encoding="utf-8"), allowlists={}
    )
    errors = parity.verify(root)
    assert len(errors) == 1
    assert "no *.allowlist files" in errors[0]


# ---------------------------------------------------------------------------
# _cmd_verify / main
# ---------------------------------------------------------------------------


def test_cmd_verify_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(parity, "verify", lambda _root: [])
    args = argparse.Namespace(repo_root=str(tmp_path))
    assert parity._cmd_verify(args) == 0


def test_cmd_verify_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(parity, "verify", lambda _root: ["::error::boom"])
    args = argparse.Namespace(repo_root=str(tmp_path))
    assert parity._cmd_verify(args) == 1
    assert "::error::boom" in capsys.readouterr().err


def test_main_dispatches_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parity, "_cmd_verify", lambda _a: 0)
    assert parity.main(["verify"]) == 0


def test_main_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        parity.main([])


def test_repository_parsers_agree() -> None:
    """The real repo must pass: bash and Python resolve identical host sets."""
    assert parity.verify(REPO_ROOT) == []
