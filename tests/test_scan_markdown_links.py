"""Tests for ``scripts/scan_markdown_links.py``."""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_markdown_links

pytestmark = pytest.mark.shard_ci_ops


def test_verify_passes_for_existing_file_and_heading(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\nSee [details](details.md#setup-flow).\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "details.md").write_text(
        "# Setup flow\n",
        encoding="utf-8",
    )

    assert scan_markdown_links.verify(tmp_path) == []


def test_verify_reports_missing_file(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[missing](docs/missing.md)\n", encoding="utf-8")

    errors = scan_markdown_links.verify(tmp_path)

    assert len(errors) == 1
    assert "missing local link target" in errors[0]
    assert "README.md:1" in errors[0]


def test_verify_reports_missing_heading_fragment(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[bad](target.md#missing)\n", encoding="utf-8")
    (tmp_path / "target.md").write_text("# Present\n", encoding="utf-8")

    errors = scan_markdown_links.verify(tmp_path)

    assert len(errors) == 1
    assert "missing heading fragment" in errors[0]


def test_duplicate_headings_get_github_suffixes(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[second](target.md#repeat-1)\n", encoding="utf-8")
    (tmp_path / "target.md").write_text("# Repeat\n\n## Repeat\n", encoding="utf-8")

    assert scan_markdown_links.verify(tmp_path) == []


def test_skips_external_urls_and_template_placeholder(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text(
        "[external](https://example.com)\n[agent](agent-session-url)\n",
        encoding="utf-8",
    )

    assert scan_markdown_links.verify(tmp_path) == []


def test_reference_style_links_are_checked(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[guide]: docs/guide.md\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")

    assert scan_markdown_links.verify(tmp_path) == []


def test_repository_links_are_currently_valid() -> None:
    repo = Path(__file__).resolve().parents[1]

    assert scan_markdown_links.verify(repo) == []
