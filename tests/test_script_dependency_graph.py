"""Tests for scripts/script_dependency_graph.py."""

from __future__ import annotations

from pathlib import Path

import pytest
import script_dependency_graph as sdg

pytestmark = pytest.mark.shard_ci_ops


def _make_scripts(root: Path, files: dict[str, str]) -> Path:
    scripts = root / "scripts"
    scripts.mkdir()
    for name, source in files.items():
        (scripts / name).write_text(source, encoding="utf-8")
    return scripts


def test_iter_script_paths_only_returns_scripts_py(tmp_path: Path) -> None:
    _make_scripts(
        tmp_path,
        {"alpha.py": "x = 1\n", "README.md": "not python\n"},
    )
    assert sdg.iter_script_paths(tmp_path) == (tmp_path / "scripts" / "alpha.py",)


def test_extract_sibling_imports_keeps_only_siblings() -> None:
    source = (
        "import os\n"
        "import _git\n"
        "from _github_api import call\n"
        "from collections import abc\n"
    )
    stems = frozenset({"alpha", "_git", "_github_api"})
    assert sdg.extract_sibling_imports(source, stems, "alpha") == frozenset(
        {"_git", "_github_api"}
    )


def test_extract_sibling_imports_excludes_self_and_relative() -> None:
    source = "import alpha\nfrom . import sibling\n"
    stems = frozenset({"alpha", "sibling"})
    # Self-import is dropped and a relative import (level > 0) is not a sibling.
    assert sdg.extract_sibling_imports(source, stems, "alpha") == frozenset()


def test_dependency_edges_are_sorted_and_deduped(tmp_path: Path) -> None:
    _make_scripts(
        tmp_path,
        {
            "_git.py": "x = 1\n",
            "alpha.py": "import _git\nfrom _git import helper\n",
            "beta.py": "import _git\n",
        },
    )
    edges = sdg.dependency_edges(tmp_path)
    assert edges == (
        sdg.DependencyEdge("alpha", "_git"),
        sdg.DependencyEdge("beta", "_git"),
    )


def test_render_markdown_ranks_hubs_and_lists_isolated() -> None:
    edges = (
        sdg.DependencyEdge("alpha", "_git"),
        sdg.DependencyEdge("beta", "_git"),
        sdg.DependencyEdge("alpha", "_api"),
    )
    stems = frozenset({"alpha", "beta", "_git", "_api", "lonely"})
    markdown = sdg.render_dependency_markdown(edges, stems)

    assert markdown.startswith("# Script dependency graph\n")
    # _git (2 importers) ranks above _api (1 importer).
    git_row = markdown.index("| `_git` |")
    api_row = markdown.index("| `_api` |")
    assert git_row < api_row
    assert "| `_git` | 2 | `alpha`, `beta` |" in markdown
    # The non-participating script is reported as isolated.
    assert "`lonely`" in markdown.split("## Isolated scripts", 1)[1]
    # The Mermaid block renders one line per edge.
    assert "flowchart TD" in markdown
    assert "alpha --> _git" in markdown


def test_render_markdown_handles_empty_graph() -> None:
    stems = frozenset({"alpha"})
    markdown = sdg.render_dependency_markdown((), stems)
    assert "No script imports a sibling script." in markdown
    assert "No sibling-import edges to render." in markdown


def test_write_dependency_doc_writes_expected_path(tmp_path: Path) -> None:
    _make_scripts(
        tmp_path,
        {"_git.py": "x = 1\n", "alpha.py": "import _git\n"},
    )
    target = sdg.write_dependency_doc(tmp_path)
    assert target == tmp_path / "docs/generated/scripts/dependency-graph.md"
    assert target.read_text(encoding="utf-8") == sdg.build_document(tmp_path)
    assert "alpha --> _git" in target.read_text(encoding="utf-8")


def test_all_doc_cli_writes_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_scripts(tmp_path, {"_git.py": "x = 1\n", "alpha.py": "import _git\n"})
    monkeypatch.chdir(tmp_path)
    assert sdg.main(["all-doc"]) == 0
    assert Path("docs/generated/scripts/dependency-graph.md").is_file()


def test_preview_cli_writes_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_scripts(tmp_path, {"_git.py": "x = 1\n", "alpha.py": "import _git\n"})
    monkeypatch.chdir(tmp_path)
    assert sdg.main(["preview"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Script dependency graph\n")
    assert not Path("docs/generated/scripts/dependency-graph.md").exists()
