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


def test_mermaid_text_escapes_quotes_and_newlines() -> None:
    # Mermaid rejects a ``\"`` backslash escape and a raw newline inside a quoted
    # label. The generator swaps a double quote for a single quote and collapses
    # newlines to a space, mirroring ``workflow_diagram._mermaid_escape`` so the
    # rendered label parses (issue #1598).
    assert sag._mermaid_text('say "hi"') == "say 'hi'"
    assert sag._mermaid_text("for x in y:\n    f(x)") == "for x in y:     f(x)"
    assert '"' not in sag._mermaid_text('a"b"c')
    assert "\n" not in sag._mermaid_text("a\nb\nc")


def test_render_mermaid_labels_stay_on_one_line_without_escaped_quotes() -> None:
    # A ``for`` statement that is not decomposed unparses with its multi-line
    # body and a double-quoted f-string; exactly the shape that broke Mermaid
    # parsing before issue #1598. After sanitizing, no label may leak a raw
    # newline or carry a backslash-escaped quote.
    source = textwrap.dedent(
        """
        def run(rows):
            for row in rows:
                key = f"{row['name']}"
            return key
        """
    )

    mermaid = sag.render_mermaid(sag.build_function_graph_from_source(source, "run"))

    assert '\\"' not in mermaid
    for line in mermaid.splitlines():
        # A leaked newline would split a node label across lines, leaving an
        # opening ``["`` without its closing ``"]`` on the same physical line.
        if '["' in line:
            assert line.rstrip().endswith('"]')


def test_render_script_graphs_markdown_includes_only_scripts(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    tests = tmp_path / "tests"
    scripts.mkdir()
    tests.mkdir()
    (scripts / "alpha.py").write_text("def run():\n    return 0\n", encoding="utf-8")
    (tests / "test_alpha.py").write_text("def test_x():\n    pass\n", encoding="utf-8")

    markdown = sag.render_script_ast_markdown(scripts / "alpha.py", Path("scripts/alpha.py"))

    assert markdown.startswith("# AST graph: scripts/alpha.py\n")
    assert "## run(...)" in markdown
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

    markdown = sag.render_script_ast_markdown(scripts / "alpha.py", Path("scripts/alpha.py"))

    assert ".github/workflows/portable-pr-policy.yml" not in markdown
    assert "UV_VERSION" not in markdown
    assert "'<str>'" in markdown


def test_write_all_script_docs_writes_per_script_and_prunes(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "alpha.py").write_text("def run():\n    return 0\n", encoding="utf-8")
    (scripts / "beta.py").write_text("def go():\n    return 1\n", encoding="utf-8")
    ast_dir = tmp_path / "docs/generated/scripts/ast"
    ast_dir.mkdir(parents=True)
    # An orphan doc and the retired legacy outputs must be pruned.
    (ast_dir / "gamma.md").write_text("stale\n", encoding="utf-8")
    legacy = tmp_path / "docs/generated/scripts/python-script-ast-graphs.md"
    legacy.write_text("legacy\n", encoding="utf-8")
    decision = tmp_path / "docs/generated/scripts/auto-retro-decision-tree.md"
    decision.write_text("legacy\n", encoding="utf-8")

    written = sag.write_all_script_docs(tmp_path)

    assert {p.name for p in written} == {"alpha.md", "beta.md"}
    assert (ast_dir / "alpha.md").is_file()
    assert (ast_dir / "beta.md").is_file()
    assert not (ast_dir / "gamma.md").exists()
    assert not legacy.exists()
    assert not decision.exists()
