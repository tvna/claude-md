"""Tests for scripts/script_ast_graph.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import script_ast_graph as sag

pytestmark = pytest.mark.shard_ci_ops_auto_retro_decision_tree


def test_iter_script_paths_only_returns_scripts_py(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    tests = tmp_path / "tests"
    tools = tmp_path / "tools"
    scripts.mkdir()
    tests.mkdir()
    tools.mkdir()
    (scripts / "alpha.py").write_text("def run():\n    return 0\n", encoding="utf-8")
    (scripts / "README.md").write_text("not python\n", encoding="utf-8")
    (tests / "test_alpha.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    (tools / "beta.py").write_text("def run():\n    return 0\n", encoding="utf-8")

    assert sag.iter_script_paths(tmp_path) == (scripts / "alpha.py",)


def test_build_function_graph_from_source_handles_if_and_try() -> None:
    source = textwrap.dedent(
        """
        def run(flag):
            if flag:
                return ok()
            try:
                value = load()
            except RuntimeError:
                raise
            return value
        """
    )

    graph = sag.build_function_graph_from_source(source, "run")
    mermaid = sag.render_mermaid(graph)

    assert mermaid.startswith("flowchart TD\n")
    assert 'N001["run(...)"]' in mermaid
    assert '["if flag"]' in mermaid
    assert '["except RuntimeError"]' in mermaid
    assert "-->|\"true\"|" in mermaid
    assert "-->|\"raises\"|" in mermaid


def test_render_script_graphs_markdown_includes_only_scripts(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    tests = tmp_path / "tests"
    scripts.mkdir()
    tests.mkdir()
    (scripts / "alpha.py").write_text("def run():\n    return 0\n", encoding="utf-8")
    (tests / "test_alpha.py").write_text("def test_x():\n    pass\n", encoding="utf-8")

    markdown = sag.render_all_script_graphs_markdown(tmp_path)

    assert markdown.startswith("# Python script AST graphs\n")
    assert "## scripts/alpha.py" in markdown
    assert "### run(...)" in markdown
    assert "tests/test_alpha.py" not in markdown


def test_render_script_graphs_markdown_redacts_string_literals(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "alpha.py").write_text(
        "def run():\n"
        "    _UV_VERSION_SYMBOL = '<str>'\n"
        "    evidence = '.github/workflows/portable-pr-policy.yml'\n"
        "    return _UV_VERSION_SYMBOL\n",
        encoding="utf-8",
    )

    markdown = sag.render_all_script_graphs_markdown(tmp_path)

    assert ".github/workflows/portable-pr-policy.yml" not in markdown
    assert "UV_VERSION" not in markdown
    assert "'<str>'" in markdown


def test_auto_retro_compat_markdown_uses_existing_title() -> None:
    markdown = sag.render_function_markdown(
        Path("scripts/auto_retro.py"),
        "run",
        title="Auto-retro decision tree",
        command="python3 scripts/script_ast_graph.py auto-retro-decision-tree-doc",
    )

    assert markdown.startswith("# Auto-retro decision tree\n")
    assert "scripts/auto_retro.py::run" in markdown
    assert "```mermaid\nflowchart TD\n" in markdown
    assert "compute_repair_signals" in markdown
