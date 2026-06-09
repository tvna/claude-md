#!/usr/bin/env python3
"""Generate Mermaid AST control-flow graphs for Python scripts.

The generator parses source files directly instead of importing them, so it can
process every ``scripts/*.py`` file without triggering workflow side effects.

``all-doc`` writes one Markdown file per script under
``docs/generated/scripts/ast/`` and owns that directory: it deletes any orphan
``*.md`` that no longer maps to a ``scripts/*.py`` file, and removes the two
legacy monolithic outputs (``python-script-ast-graphs.md`` and
``auto-retro-decision-tree.md``) on sight. Content under
``docs/generated/scripts/`` is owned by the post-merge automation; the pre-push
and pre-merge gates no longer regenerate it (refs #1540).

Contract:
- Inputs: subcommands ``auto-retro-decision-tree`` (stdout preview) and
  ``all-doc`` (per-script docs); optional ``--root`` path.
- Outputs: Mermaid on stdout for preview mode, or one checked-in Markdown file
  per script under ``docs/generated/scripts/ast/`` for ``all-doc``; exit 0 when
  generation succeeds.
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
# Per-script AST docs live under this directory, one ``<stem>.md`` per
# ``scripts/*.py``. ``all-doc`` owns the directory entirely.
AST_DOC_DIR = Path("docs/generated/scripts/ast")
# Legacy monolithic outputs retired by #1540. ``all-doc`` deletes them on sight
# so the post-merge regeneration removes them without a hand-authored edit.
LEGACY_DOC_PATHS: tuple[Path, ...] = (
    Path("docs/generated/scripts/python-script-ast-graphs.md"),
    Path("docs/generated/scripts/auto-retro-decision-tree.md"),
)
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


def render_script_ast_markdown(path: Path, display_path: Path) -> str:
    """Render one script's AST graphs as a per-script Markdown document."""
    lines = [
        f"# AST graph: {display_path}",
        "",
        f"This file is generated from `{display_path}` by "
        "`python3 scripts/script_ast_graph.py all-doc`. Do not edit it by "
        "hand: content under `docs/generated/scripts/` is owned by the "
        "post-merge automation (refs #1540) -- update the source script "
        "instead.",
        "",
    ]
    graphs = build_script_graphs(path, safe_strings=True)
    if not graphs:
        lines.extend(["No top-level functions found.", ""])
    else:
        for graph in graphs:
            safe_graph = _safe_generated_doc_graph(graph)
            lines.extend([f"## {graph.name}(...)", "", "```mermaid", render_mermaid(safe_graph).rstrip(), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def doc_filename_for(path: Path) -> str:
    """Return the per-script doc filename for a ``scripts/*.py`` path."""
    return f"{path.stem}.md"


def write_all_script_docs(root: Path = Path()) -> tuple[Path, ...]:
    """Write one AST doc per script under ``ast/`` and prune stale outputs.

    Owns ``docs/generated/scripts/ast/`` end to end: writes ``<stem>.md`` for
    every ``scripts/*.py``, deletes any orphan ``*.md`` whose source script is
    gone, and removes the retired legacy monolithic docs. Returns the written
    doc paths in deterministic order.
    """
    out_dir = root / AST_DOC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    expected: set[str] = set()
    for path in iter_script_paths(root):
        display_path = path.relative_to(root) if path.is_absolute() else path
        target = out_dir / doc_filename_for(path)
        target.write_text(render_script_ast_markdown(path, display_path), encoding="utf-8")
        written.append(target)
        expected.add(target.name)

    # Prune orphan per-script docs whose source script no longer exists.
    for existing in sorted(out_dir.glob("*.md")):
        if existing.name not in expected:
            existing.unlink()

    # Remove the retired legacy monolithic outputs so the post-merge
    # regeneration decommissions them without a hand-authored deletion.
    for legacy in LEGACY_DOC_PATHS:
        legacy_path = root / legacy
        if legacy_path.exists():
            legacy_path.unlink()

    return tuple(written)


def _cmd_auto_retro_decision_tree(_args: argparse.Namespace) -> int:
    sys.stdout.write(render_mermaid(build_function_graph(AUTO_RETRO_SOURCE_PATH, "run")))
    return 0


def _cmd_all_doc(args: argparse.Namespace) -> int:
    write_all_script_docs(Path(args.root))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_auto = sub.add_parser(
        "auto-retro-decision-tree",
        help="Render scripts/auto_retro.py::run as Mermaid (stdout preview).",
    )
    p_auto.set_defaults(func=_cmd_auto_retro_decision_tree)

    p_all_doc = sub.add_parser(
        "all-doc",
        help="Write per-script AST docs under docs/generated/scripts/ast/.",
    )
    p_all_doc.add_argument(
        "--root",
        default=".",
        help="Repository root (default current directory).",
    )
    p_all_doc.set_defaults(func=_cmd_all_doc)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
