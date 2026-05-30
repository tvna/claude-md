"""Tests for ``scripts/scan_docs_inventory.py``."""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_docs_inventory

pytestmark = pytest.mark.shard_ci_ops


def _write_index(root: Path, body: str) -> None:
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "INDEX.md").write_text(body, encoding="utf-8")


def test_verify_reports_docs_missing_from_index(tmp_path: Path) -> None:
    _write_index(tmp_path, "# docs/ index\n")
    (tmp_path / "docs" / "runbooks").mkdir()
    (tmp_path / "docs" / "runbooks" / "preflight.md").write_text(
        "# Preflight\n",
        encoding="utf-8",
    )

    errors = scan_docs_inventory.verify(tmp_path)

    assert errors == [
        "::error file=docs/INDEX.md::docs/INDEX.md does not list docs/runbooks/preflight.md"
    ]


def test_verify_reports_unexpected_top_level_docs(tmp_path: Path) -> None:
    _write_index(
        tmp_path,
        "# docs/ index\n\n- [stray.md](stray.md)\n",
    )
    (tmp_path / "docs" / "stray.md").write_text("# Stray\n", encoding="utf-8")

    errors = scan_docs_inventory.verify(tmp_path)

    assert errors == [
        "::error file=docs/stray.md::unexpected top-level docs file; move it into a lane or add an explicit compatibility exemption"
    ]


def test_verify_allows_index_and_compatibility_pointer(tmp_path: Path) -> None:
    _write_index(
        tmp_path,
        "# docs/ index\n\n- [agent-provenance.md](agent-provenance.md)\n",
    )
    (tmp_path / "docs" / "agent-provenance.md").write_text(
        "# Agent Extension Provenance\n\n"
        "The current runbook lives at\n"
        "[`docs/runbooks/agent-provenance.md`](runbooks/agent-provenance.md).\n\n"
        "This compatibility entry preserves the original path.\n",
        encoding="utf-8",
    )

    assert scan_docs_inventory.verify(tmp_path) == []


def test_repository_docs_inventory_is_current() -> None:
    repo = Path(__file__).resolve().parents[1]

    assert scan_docs_inventory.verify(repo) == []


# ---------------------------------------------------------------------------
# rel() -- ValueError branch (path outside root)
# ---------------------------------------------------------------------------


def test_rel_returns_absolute_posix_when_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    result = scan_docs_inventory.rel(outside, tmp_path)
    assert result == outside.as_posix()


# ---------------------------------------------------------------------------
# extract_target() -- angle-bracket and space formats
# ---------------------------------------------------------------------------


def test_extract_target_angle_bracket_format() -> None:
    assert scan_docs_inventory.extract_target("<path/to/file.md>") == "path/to/file.md"


def test_extract_target_space_separated_title() -> None:
    assert scan_docs_inventory.extract_target('path/to/file.md "Page title"') == "path/to/file.md"


# ---------------------------------------------------------------------------
# iter_docs_markdown() -- no docs directory
# ---------------------------------------------------------------------------


def test_iter_docs_markdown_returns_empty_when_no_docs_dir(tmp_path: Path) -> None:
    assert scan_docs_inventory.iter_docs_markdown(tmp_path) == []


# ---------------------------------------------------------------------------
# collect_index_entries() -- no INDEX.md; protocol-relative URL; empty path; absolute path
# ---------------------------------------------------------------------------


def test_collect_index_entries_returns_empty_when_no_index(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    assert scan_docs_inventory.collect_index_entries(tmp_path) == set()


def test_collect_index_entries_skips_protocol_relative_urls(tmp_path: Path) -> None:
    _write_index(tmp_path, "- [ext](//example.com/docs/file.md)\n")
    assert scan_docs_inventory.collect_index_entries(tmp_path) == set()


def test_collect_index_entries_skips_dot_path(tmp_path: Path) -> None:
    _write_index(tmp_path, "- [ref](.)\n")
    assert scan_docs_inventory.collect_index_entries(tmp_path) == set()


def test_collect_index_entries_handles_absolute_md_link(tmp_path: Path) -> None:
    _write_index(tmp_path, "- [page](/docs/runbooks/guide.md)\n")
    entries = scan_docs_inventory.collect_index_entries(tmp_path)
    assert "docs/runbooks/guide.md" in entries


# ---------------------------------------------------------------------------
# main() CLI -- error output path (monkeypatched verify)
# ---------------------------------------------------------------------------


def test_main_prints_errors_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        scan_docs_inventory,
        "verify",
        lambda root: ["::error file=docs/INDEX.md::docs/INDEX.md does not list docs/missing.md"],
    )
    rc = scan_docs_inventory.main(["verify"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "does not list" in captured.err


def test_main_returns_zero_when_no_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scan_docs_inventory, "verify", lambda root: [])
    assert scan_docs_inventory.main(["verify"]) == 0


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    monkeypatch.setattr(scan_docs_inventory, "verify", lambda root: [])
    monkeypatch.setattr(sys, "argv", ["scan_docs_inventory", "verify"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("scan_docs_inventory", run_name="__main__")
    assert exc_info.value.code == 0
