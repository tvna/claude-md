#!/usr/bin/env python3
"""Generate Mermaid AST control-flow graphs for Python scripts.

The generator parses source files directly instead of importing them, so it can
process every ``scripts/*.py`` file without triggering workflow side effects.

Contract:
- Inputs: subcommands ``auto-retro-decision-tree``,
  ``auto-retro-decision-tree-doc``, and ``all-doc``; optional ``--output`` and
  ``--root`` paths.
- Outputs: Mermaid on stdout for preview mode, or checked-in Markdown files
  under ``docs/generated/scripts/`` for doc modes; exit 0 when generation
  succeeds.
- Failure policy: fails loud per CLAUDE.md section 4 when a source file cannot
  be parsed, a requested function is absent, or an output file cannot be
  written.
"""

from __future__ import annotations

import argparse
import ast
import copy
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path("scripts")
ALL_SCRIPTS_DOC_PATH = Path("docs/generated/scripts/python-script-ast-graphs.md")
AUTO_RETRO_DECISION_TREE_DOC_PATH = Path("docs/generated/scripts/auto-retro-decision-tree.md")
AUTO_RETRO_SOURCE_PATH = Path(__file__).resolve().parent / "auto_retro.py"


@dataclass(frozen=True)
class GraphEdge:
    """One renderable edge in an AST graph."""

    source: str
    target: str
    label: str


@dataclass(frozen=True)
class GraphNode:
    """One renderable node in an AST graph."""

    node_id: str
    label: str


@dataclass(frozen=True)
class FunctionGraph:
    """A Mermaid-ready graph for one top-level function."""

    name: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


def iter_script_paths(root: Path = Path()) -> tuple[Path, ...]:
    """Return repository ``scripts/*.py`` files in deterministic order."""
    scripts_dir = root / SCRIPTS_DIR
    if not scripts_dir.is_dir():
        return ()
    return tuple(sorted(path for path in scripts_dir.glob("*.py") if path.is_file()))


def _mermaid_text(text: str) -> str:
    return text.replace('"', '\\"')


def _safe_label_node(node: ast.AST) -> ast.AST:
    class SafeLabelTransformer(ast.NodeTransformer):
        def visit_Constant(self, node: ast.Constant) -> ast.AST:
            if isinstance(node.value, str):
                return ast.copy_location(ast.Constant(value="<str>"), node)
            return node

    return SafeLabelTransformer().visit(copy.deepcopy(node))


def _ast_text(node: ast.AST, *, safe_strings: bool = False) -> str:
    """Return deterministic source text for one AST node."""
    if safe_strings:
        node = _safe_label_node(node)
    return ast.unparse(node).strip()


def _called_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
    return None


def _stmt_label(stmt: ast.stmt, *, safe_strings: bool = False) -> str:
    if isinstance(stmt, ast.Assign):
        targets = ", ".join(_ast_text(t, safe_strings=safe_strings) for t in stmt.targets)
        called = _called_name(stmt.value)
        if called is not None:
            return f"{targets} = {called}(...)"
        return f"{targets} = {_ast_text(stmt.value, safe_strings=safe_strings)}"
    if isinstance(stmt, ast.AnnAssign):
        target = _ast_text(stmt.target, safe_strings=safe_strings)
        if stmt.value is None:
            return target
        called = _called_name(stmt.value)
        if called is not None:
            return f"{target} = {called}(...)"
        return f"{target} = {_ast_text(stmt.value, safe_strings=safe_strings)}"
    if isinstance(stmt, ast.Expr):
        called = _called_name(stmt.value)
        if called is not None:
            return f"{called}(...)"
        return _ast_text(stmt.value, safe_strings=safe_strings)
    if isinstance(stmt, ast.Return):
        return f"return {_ast_text(stmt.value, safe_strings=safe_strings)}" if stmt.value else "return"
    if isinstance(stmt, ast.Raise):
        return f"raise {_ast_text(stmt.exc, safe_strings=safe_strings)}" if stmt.exc else "raise"
    if isinstance(stmt, ast.If):
        return f"if {_ast_text(stmt.test, safe_strings=safe_strings)}"
    if isinstance(stmt, ast.Try):
        return "try"
    return _ast_text(stmt, safe_strings=safe_strings)


class AstGraphBuilder:
    """Build a simple control-flow graph from Python AST statements."""

    def __init__(self, *, safe_strings: bool = False) -> None:
        self._next_id = 0
        self._safe_strings = safe_strings
        self.nodes: list[GraphNode] = []
        self.edges: list[GraphEdge] = []

    def _new_node(self, label: str) -> str:
        self._next_id += 1
        node_id = f"N{self._next_id:03d}"
        self.nodes.append(GraphNode(node_id=node_id, label=label))
        return node_id

    def _connect(self, incoming: list[tuple[str, str]], target: str) -> None:
        for source, label in incoming:
            self.edges.append(GraphEdge(source, target, label))

    def build_function(self, function: ast.FunctionDef) -> FunctionGraph:
        start = self._new_node(f"{function.name}(...)")
        statements = list(function.body)
        if (
            statements
            and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)
        ):
            statements = statements[1:]
        exits = self._build_block(statements, [(start, "start")])
        if exits:
            done = self._new_node("end")
            self._connect(exits, done)
        return FunctionGraph(function.name, tuple(self.nodes), tuple(self.edges))

    def _build_block(
        self, statements: list[ast.stmt], incoming: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        exits = incoming
        for stmt in statements:
            if not exits:
                break
            if isinstance(stmt, ast.If):
                exits = self._build_if(stmt, exits)
            elif isinstance(stmt, ast.Try):
                exits = self._build_try(stmt, exits)
            else:
                exits = self._build_plain(stmt, exits)
        return exits

    def _build_plain(
        self, stmt: ast.stmt, incoming: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        node_id = self._new_node(_stmt_label(stmt, safe_strings=self._safe_strings))
        self._connect(incoming, node_id)
        if isinstance(stmt, ast.Return | ast.Raise):
            return []
        return [(node_id, "")]

    def _build_if(self, stmt: ast.If, incoming: list[tuple[str, str]]) -> list[tuple[str, str]]:
        node_id = self._new_node(_stmt_label(stmt))
        self._connect(incoming, node_id)
        body_exits = self._build_block(stmt.body, [(node_id, "true")])
        if stmt.orelse:
            orelse_exits = self._build_block(stmt.orelse, [(node_id, "false")])
        else:
            orelse_exits = [(node_id, "false")]
        return body_exits + orelse_exits

    def _build_try(self, stmt: ast.Try, incoming: list[tuple[str, str]]) -> list[tuple[str, str]]:
        node_id = self._new_node(_stmt_label(stmt))
        self._connect(incoming, node_id)
        exits = self._build_block(stmt.body, [(node_id, "try")])
        for handler in stmt.handlers:
            if handler.type is None:
                label = "except"
            else:
                label = f"except {_ast_text(handler.type, safe_strings=self._safe_strings)}"
            handler_id = self._new_node(label)
            self.edges.append(GraphEdge(node_id, handler_id, "raises"))
            exits.extend(self._build_block(handler.body, [(handler_id, "")]))
        if stmt.orelse:
            exits = self._build_block(stmt.orelse, exits)
        if stmt.finalbody:
            exits = self._build_block(stmt.finalbody, exits)
        return exits


def _module_from_source(source: str) -> ast.Module:
    return ast.parse(source)


def _top_level_functions(module: ast.Module) -> tuple[ast.FunctionDef, ...]:
    return tuple(stmt for stmt in module.body if isinstance(stmt, ast.FunctionDef))


def build_function_graph_from_source(source: str, function_name: str) -> FunctionGraph:
    """Build a graph for one named top-level function from source text."""
    module = _module_from_source(source)
    for function in _top_level_functions(module):
        if function.name == function_name:
            return AstGraphBuilder().build_function(function)
    raise ValueError(f"function not found: {function_name}")


def build_function_graph(path: Path, function_name: str) -> FunctionGraph:
    """Build a graph for one named top-level function from a file."""
    return build_function_graph_from_source(path.read_text(encoding="utf-8"), function_name)


def build_script_graphs(path: Path, *, safe_strings: bool = False) -> tuple[FunctionGraph, ...]:
    """Build graphs for every top-level function in one script."""
    module = _module_from_source(path.read_text(encoding="utf-8"))
    return tuple(AstGraphBuilder(safe_strings=safe_strings).build_function(function) for function in _top_level_functions(module))


def render_mermaid(graph: FunctionGraph) -> str:
    """Render one function graph as Mermaid."""
    lines = ["flowchart TD"]
    for node in graph.nodes:
        lines.append(f'    {node.node_id}["{_mermaid_text(node.label)}"]')
    for edge in graph.edges:
        if edge.label:
            lines.append(f'    {edge.source} -->|"{_mermaid_text(edge.label)}"| {edge.target}')
        else:
            lines.append(f"    {edge.source} --> {edge.target}")
    return "\n".join(lines) + "\n"


def _safe_generated_doc_label(label: str) -> str:
    return label.replace("UV_VERSION", "UV_PIN_SYMBOL")


def _safe_generated_doc_graph(graph: FunctionGraph) -> FunctionGraph:
    return FunctionGraph(
        name=graph.name,
        nodes=tuple(GraphNode(node.node_id, _safe_generated_doc_label(node.label)) for node in graph.nodes),
        edges=graph.edges,
    )


def render_function_markdown(
    path: Path,
    function_name: str,
    title: str,
    command: str,
    source_label: str | None = None,
) -> str:
    """Render one function graph as a checked-in Markdown document."""
    graph = build_function_graph(path, function_name)
    source = source_label or str(path)
    return (
        f"# {title}\n"
        "\n"
        f"This file is generated from `{source}::{function_name}` by "
        f"`{command}`. Do not edit it by hand; update the source script "
        "and regenerate instead.\n"
        "\n"
        "```mermaid\n"
        f"{render_mermaid(graph)}"
        "```\n"
    )


def render_all_script_graphs_markdown(root: Path = Path()) -> str:
    """Render Markdown containing AST graphs for every ``scripts/*.py`` file."""
    lines = [
        "# Python script AST graphs",
        "",
        "This file is generated from `scripts/*.py` by "
        "`python3 scripts/script_ast_graph.py all-doc`. Do not edit it by "
        "hand; update the source scripts and regenerate instead.",
        "",
    ]
    for path in iter_script_paths(root):
        display_path = path.relative_to(root) if path.is_absolute() else path
        lines.extend([f"## {display_path}", ""])
        graphs = build_script_graphs(path, safe_strings=True)
        if not graphs:
            lines.extend(["No top-level functions found.", ""])
            continue
        for graph in graphs:
            safe_graph = _safe_generated_doc_graph(graph)
            lines.extend([f"### {graph.name}(...)", "", "```mermaid", render_mermaid(safe_graph).rstrip(), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_auto_retro_decision_tree_markdown() -> str:
    """Render the legacy auto-retro decision tree document."""
    return render_function_markdown(
        AUTO_RETRO_SOURCE_PATH,
        "run",
        "Auto-retro decision tree",
        "python3 scripts/script_ast_graph.py auto-retro-decision-tree-doc",
        source_label="scripts/auto_retro.py",
    )


def _cmd_auto_retro_decision_tree(_args: argparse.Namespace) -> int:
    sys.stdout.write(render_mermaid(build_function_graph(AUTO_RETRO_SOURCE_PATH, "run")))
    return 0


def _cmd_auto_retro_decision_tree_doc(args: argparse.Namespace) -> int:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_auto_retro_decision_tree_markdown(), encoding="utf-8")
    return 0


def _cmd_all_doc(args: argparse.Namespace) -> int:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_all_script_graphs_markdown(Path(args.root)), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_auto = sub.add_parser(
        "auto-retro-decision-tree",
        help="Render scripts/auto_retro.py::run as Mermaid.",
    )
    p_auto.set_defaults(func=_cmd_auto_retro_decision_tree)

    p_auto_doc = sub.add_parser(
        "auto-retro-decision-tree-doc",
        help="Write the checked-in auto-retro decision tree document.",
    )
    p_auto_doc.add_argument(
        "--output",
        default=str(AUTO_RETRO_DECISION_TREE_DOC_PATH),
        help=f"Markdown output path (default {AUTO_RETRO_DECISION_TREE_DOC_PATH}).",
    )
    p_auto_doc.set_defaults(func=_cmd_auto_retro_decision_tree_doc)

    p_all_doc = sub.add_parser(
        "all-doc",
        help="Write AST graph documentation for every scripts/*.py file.",
    )
    p_all_doc.add_argument(
        "--root",
        default=".",
        help="Repository root (default current directory).",
    )
    p_all_doc.add_argument(
        "--output",
        default=str(ALL_SCRIPTS_DOC_PATH),
        help=f"Markdown output path (default {ALL_SCRIPTS_DOC_PATH}).",
    )
    p_all_doc.set_defaults(func=_cmd_all_doc)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
