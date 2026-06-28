"""Tests for ``scripts/scan_docs_inventory.py``."""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_docs_inventory
import yaml

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_pre_commit_hook_is_registered() -> None:
    """Refs #1632 (PR #1625 retro, Fact 4): docs inventory must gate at commit.

    Mirroring the CI scanner into ``.pre-commit-config.yaml`` is the durable
    gate that fails a new standards doc missing its docs/INDEX.md row at commit
    time, not only in CI.
    """
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    entries = {
        hook["id"]: hook["entry"]
        for repo in config["repos"]
        if repo.get("repo") == "local"
        for hook in repo["hooks"]
    }
    assert "scan-docs-inventory" in entries
    assert "scripts/scan_docs_inventory.py verify" in entries["scan-docs-inventory"]


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
# rel(); ValueError branch (path outside root)
# ---------------------------------------------------------------------------


def test_rel_returns_absolute_posix_when_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    result = scan_docs_inventory.rel(outside, tmp_path)
    assert result == outside.as_posix()


# ---------------------------------------------------------------------------
# extract_target(); angle-bracket and space formats
# ---------------------------------------------------------------------------


def test_extract_target_angle_bracket_format() -> None:
    assert scan_docs_inventory.extract_target("<path/to/file.md>") == "path/to/file.md"


def test_extract_target_space_separated_title() -> None:
    assert scan_docs_inventory.extract_target('path/to/file.md "Page title"') == "path/to/file.md"


# ---------------------------------------------------------------------------
# iter_docs_markdown(); no docs directory
# ---------------------------------------------------------------------------


def test_iter_docs_markdown_returns_empty_when_no_docs_dir(tmp_path: Path) -> None:
    assert scan_docs_inventory.iter_docs_markdown(tmp_path) == []


# ---------------------------------------------------------------------------
# collect_index_entries(); no INDEX.md; protocol-relative URL; empty path; absolute path
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
# collect_index_entries(); transitive lane-README following (Refs #2005)
# ---------------------------------------------------------------------------


def test_collect_index_entries_follows_lane_readme_hop(tmp_path: Path) -> None:
    """A lane README's leaf rows count as listed when INDEX points at it."""
    _write_index(tmp_path, "- [standards](standards/README.md)\n")
    standards = tmp_path / "docs" / "standards"
    standards.mkdir(parents=True)
    (standards / "README.md").write_text(
        "# Standards\n\n- [commit-signing.md](commit-signing.md)\n",
        encoding="utf-8",
    )

    entries = scan_docs_inventory.collect_index_entries(tmp_path)

    assert "docs/standards/README.md" in entries
    assert "docs/standards/commit-signing.md" in entries


def test_collect_index_entries_does_not_follow_non_readme_links(tmp_path: Path) -> None:
    """Only ``/README.md`` targets are followed; other docs are leaves."""
    _write_index(tmp_path, "- [page](standards/page.md)\n")
    standards = tmp_path / "docs" / "standards"
    standards.mkdir(parents=True)
    (standards / "page.md").write_text(
        "# Page\n\n- [hidden.md](hidden.md)\n",
        encoding="utf-8",
    )

    entries = scan_docs_inventory.collect_index_entries(tmp_path)

    assert "docs/standards/page.md" in entries
    assert "docs/standards/hidden.md" not in entries


def test_collect_index_entries_stops_after_one_readme_hop(tmp_path: Path) -> None:
    """Recursion is fixed at two levels: a split-lane README linked from
    another split-lane README is collected as a leaf but its own links are not
    followed (only INDEX's direct split-lane links are hopped)."""
    _write_index(tmp_path, "- [standards](standards/README.md)\n")
    docs = tmp_path / "docs"
    (docs / "standards").mkdir(parents=True)
    (docs / "standards" / "README.md").write_text(
        "# Standards\n\n- [prd](../prd/README.md)\n",
        encoding="utf-8",
    )
    (docs / "prd").mkdir(parents=True)
    (docs / "prd" / "README.md").write_text(
        "# PRD\n\n- [deep.md](deep.md)\n",
        encoding="utf-8",
    )

    entries = scan_docs_inventory.collect_index_entries(tmp_path)

    assert "docs/prd/README.md" in entries
    assert "docs/prd/deep.md" not in entries


def test_collect_index_entries_does_not_follow_unsplit_lane_readme(tmp_path: Path) -> None:
    """Refs #2005: only the declared split-lane READMEs are followed. A README
    for a small lane (table stays inline in INDEX) is collected as a leaf but
    its links are not, so a small-lane doc cannot be covered via its README."""
    _write_index(tmp_path, "- [proposals](proposals/README.md)\n")
    proposals = tmp_path / "docs" / "proposals"
    proposals.mkdir(parents=True)
    (proposals / "README.md").write_text(
        "# Proposals\n\n- [foo.md](foo.md)\n",
        encoding="utf-8",
    )

    entries = scan_docs_inventory.collect_index_entries(tmp_path)

    assert "docs/proposals/README.md" in entries
    assert "docs/proposals/foo.md" not in entries


def test_verify_accepts_doc_listed_only_via_lane_readme(tmp_path: Path) -> None:
    """A leaf doc absent from INDEX but present in its lane README passes."""
    _write_index(tmp_path, "# docs/ index\n\n- [standards](standards/README.md)\n")
    standards = tmp_path / "docs" / "standards"
    standards.mkdir(parents=True)
    (standards / "README.md").write_text(
        "# Standards\n\n- [commit-signing.md](commit-signing.md)\n",
        encoding="utf-8",
    )
    (standards / "commit-signing.md").write_text("# Commit signing\n", encoding="utf-8")

    assert scan_docs_inventory.verify(tmp_path) == []


def test_verify_reports_doc_hidden_behind_non_readme_link(tmp_path: Path) -> None:
    """A leaf reachable only through a non-README link stays uncovered."""
    _write_index(tmp_path, "# docs/ index\n\n- [page](standards/page.md)\n")
    standards = tmp_path / "docs" / "standards"
    standards.mkdir(parents=True)
    (standards / "page.md").write_text(
        "# Page\n\n- [hidden.md](hidden.md)\n",
        encoding="utf-8",
    )
    (standards / "hidden.md").write_text("# Hidden\n", encoding="utf-8")

    errors = scan_docs_inventory.verify(tmp_path)

    assert errors == [
        "::error file=docs/INDEX.md::docs/INDEX.md does not list docs/standards/hidden.md"
    ]


def test_verify_flags_small_lane_doc_listed_only_in_readme(tmp_path: Path) -> None:
    """Refs #2005: a small-lane doc reachable only through its (unsplit) lane
    README is still flagged, enforcing that small lanes keep their table inline
    in INDEX rather than migrating listings into the README."""
    _write_index(tmp_path, "# docs/ index\n\n- [proposals](proposals/README.md)\n")
    proposals = tmp_path / "docs" / "proposals"
    proposals.mkdir(parents=True)
    (proposals / "README.md").write_text(
        "# Proposals\n\n- [foo.md](foo.md)\n",
        encoding="utf-8",
    )
    (proposals / "foo.md").write_text("# Foo\n", encoding="utf-8")

    errors = scan_docs_inventory.verify(tmp_path)

    assert errors == [
        "::error file=docs/INDEX.md::docs/INDEX.md does not list docs/proposals/foo.md"
    ]


# ---------------------------------------------------------------------------
# main() CLI; error output path (monkeypatched verify)
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


# ---------------------------------------------------------------------------
# INDEX byte budget (Refs #1665)
# ---------------------------------------------------------------------------


def test_index_within_budget_passes(tmp_path: Path) -> None:
    _write_index(tmp_path, "# docs/ index\n")
    assert scan_docs_inventory.verify_index_budget(tmp_path) == []


def test_index_over_budget_reports_error(tmp_path: Path) -> None:
    oversize = "# docs/ index\n" + ("x" * (scan_docs_inventory.MAX_INDEX_BYTES + 1))
    _write_index(tmp_path, oversize)

    errors = scan_docs_inventory.verify_index_budget(tmp_path)

    assert len(errors) == 1
    assert "over the" in errors[0]
    assert "navigation budget" in errors[0]
    assert str(scan_docs_inventory.MAX_INDEX_BYTES) in errors[0]


def test_missing_index_has_no_budget_error(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    assert scan_docs_inventory.verify_index_budget(tmp_path) == []


def test_verify_surfaces_budget_error(tmp_path: Path) -> None:
    oversize = "# docs/ index\n" + ("y" * (scan_docs_inventory.MAX_INDEX_BYTES + 1))
    _write_index(tmp_path, oversize)

    errors = scan_docs_inventory.verify(tmp_path)

    assert any("navigation budget" in error for error in errors)


def test_real_index_is_within_budget() -> None:
    """The committed docs/INDEX.md must stay under the navigation budget."""
    index = REPO_ROOT / "docs" / "INDEX.md"
    assert index.stat().st_size <= scan_docs_inventory.MAX_INDEX_BYTES
