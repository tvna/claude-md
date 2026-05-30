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
