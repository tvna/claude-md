"""Tests for scripts/scan_compile_from_source.py.

The gate flags command-position ``go install`` / ``cargo install`` under
scripts/ and .github/workflows/ unless ack'd (#1154). These tests pin the
command-position matching (vs. log mentions), comment skipping, the ack escape
hatch, and a real-repo self-check.
"""

from __future__ import annotations

import pytest
import scan_compile_from_source as gate

pytestmark = pytest.mark.shard_ci_ops


@pytest.mark.parametrize(
    "line",
    [
        "go install github.com/foo/bar@v1",
        "  cargo install ripgrep",
        "uv run x && go install foo@latest",
        "run: go install tool@v2",
    ],
)
def test_scan_line_flags_command_position(line: str) -> None:
    assert gate.scan_line(line) is True


@pytest.mark.parametrize(
    "line",
    [
        '#   a pinned `go install` (compiles from source)',  # comment
        'echo "installing via go install foo"',  # log mention, not a command
        'go install foo@v1  # compile-source-ack: backstop',  # ack'd
        "gofmt installed here",  # not the install idiom
    ],
)
def test_scan_line_allows(line: str) -> None:
    assert gate.scan_line(line) is False


def test_find_hits_flags_planted(tmp_path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "scripts" / "x.sh").write_text("go install foo@v1\n")
    hits = gate.find_hits(tmp_path)
    assert len(hits) == 1
    assert hits[0].startswith("scripts/x.sh:")


def test_find_hits_honours_ack(tmp_path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.sh").write_text(
        f"go install foo@v1 {gate.ACK_MARKER}: backstop\n"
    )
    assert gate.find_hits(tmp_path) == []


def test_real_repo_is_clean() -> None:
    """The actual tree must compile no tool from source unacked."""
    assert gate.find_hits(gate.REPO_ROOT) == []


def test_cli_verify_clean_repo() -> None:
    assert gate.main(["verify"]) == 0


def test_cli_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["list"]) == 0
    # Clean repo -> no output lines; just assert it ran without error.
    capsys.readouterr()
