#!/usr/bin/env python3
"""Generate a Mermaid import-dependency graph across ``scripts/*.py``.

The per-script AST docs under ``docs/generated/scripts/ast/`` (#1540) show
intra-function control flow but not how the scripts depend on one another. This
generator parses every ``scripts/*.py`` source with :mod:`ast` -- it never
imports them, so it runs without triggering workflow side effects -- and keeps
only the edges that point at a *sibling* script (e.g. ``from _git import ...``
resolves to ``scripts/_git.py``). Standard-library and third-party imports are
discarded.

``all-doc`` writes one ``docs/generated/scripts/dependency-graph.md`` view with a
shared-module fan-in table (importer count ranks the high-blast-radius helpers),
an isolated-scripts list, and a Mermaid flowchart over the scripts that
participate in at least one sibling-import edge. Content under
``docs/generated/scripts/`` is owned by the post-merge automation; the pre-push
and pre-merge gates no longer regenerate it (refs #1540, #1543).

Architecture: pure functions on top (:func:`extract_sibling_imports`,
:func:`dependency_edges`, :func:`render_dependency_markdown`), a single
filesystem write at the bottom (:func:`write_dependency_doc`).

Contract:
- Inputs: subcommands ``all-doc`` (writes the doc) and ``preview`` (stdout
  preview); optional ``--root`` path (defaults to the current directory).
- Outputs: ``docs/generated/scripts/dependency-graph.md`` for ``all-doc``, the
  same Markdown on stdout for ``preview``; exit 0 when generation succeeds.
- Failure policy: fails loud per CLAUDE.md section 4 when a source file cannot
  be parsed or the output file cannot be written.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path("scripts")
DOC_PATH = Path("docs/generated/scripts/dependency-graph.md")


@dataclass(frozen=True, order=True)
class DependencyEdge:
    """One ``importer -> imported`` edge between two sibling scripts."""

    importer: str
    imported: str


def iter_script_paths(root: Path = Path()) -> tuple[Path, ...]:
    """Return repository ``scripts/*.py`` files in deterministic order."""
    scripts_dir = root / SCRIPTS_DIR
    if not scripts_dir.is_dir():
        return ()
    return tuple(sorted(path for path in scripts_dir.glob("*.py") if path.is_file()))


def script_stems(paths: tuple[Path, ...]) -> frozenset[str]:
    """Return the module stems (``_git`` for ``scripts/_git.py``) of *paths*."""
    return frozenset(path.stem for path in paths)


def _imported_top_levels(module: ast.Module) -> frozenset[str]:
    """Return the top-level module name of every absolute import in *module*."""
    names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        # level > 0 is a relative import; scripts/ has no package, so a sibling
        # import is always the absolute ``from _git import ...``.
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return frozenset(names)


def extract_sibling_imports(
    source: str, stems: frozenset[str], self_stem: str
) -> frozenset[str]:
    """Return the sibling-script stems that *source* imports (excluding self)."""
    module = ast.parse(source)
    return frozenset(
        name for name in _imported_top_levels(module) if name in stems and name != self_stem
    )


def dependency_edges(root: Path = Path()) -> tuple[DependencyEdge, ...]:
    """Return the deduplicated, sorted sibling-import edges across scripts."""
    paths = iter_script_paths(root)
    stems = script_stems(paths)
    edges: set[DependencyEdge] = set()
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for imported in extract_sibling_imports(source, stems, path.stem):
            edges.add(DependencyEdge(importer=path.stem, imported=imported))
    return tuple(sorted(edges))


def _fan_in(edges: tuple[DependencyEdge, ...]) -> dict[str, list[str]]:
    """Map each imported module to its sorted list of importer stems."""
    table: dict[str, set[str]] = {}
    for edge in edges:
        table.setdefault(edge.imported, set()).add(edge.importer)
    return {imported: sorted(importers) for imported, importers in table.items()}


def _participating(edges: tuple[DependencyEdge, ...]) -> frozenset[str]:
    """Return every stem that appears on either side of an edge."""
    return frozenset(stem for edge in edges for stem in (edge.importer, edge.imported))


def render_dependency_markdown(
    edges: tuple[DependencyEdge, ...], stems: frozenset[str]
) -> str:
    """Render the dependency graph as a Markdown document."""
    lines = [
        "# Script dependency graph",
        "",
        "This file is generated from `scripts/*.py` import statements by "
        "`python3 scripts/script_dependency_graph.py all-doc`. Do not edit it "
        "by hand: content under `docs/generated/scripts/` is owned by the "
        "post-merge automation (refs #1540, #1543) -- update the source "
        "scripts instead.",
        "",
    ]

    fan_in = _fan_in(edges)
    lines.extend(["## Shared module fan-in", ""])
    if not fan_in:
        lines.extend(["No script imports a sibling script.", ""])
    else:
        lines.extend(["| Module | Imported by | Importers |", "| --- | --- | --- |"])
        # Hubs first: highest importer count, then module name.
        for imported in sorted(fan_in, key=lambda name: (-len(fan_in[name]), name)):
            importers = fan_in[imported]
            importer_cells = ", ".join(f"`{name}`" for name in importers)
            lines.append(f"| `{imported}` | {len(importers)} | {importer_cells} |")
        lines.append("")

    participating = _participating(edges)
    isolated = sorted(stems - participating)
    lines.extend(["## Isolated scripts", ""])
    if not isolated:
        lines.extend(["Every script participates in at least one sibling-import edge.", ""])
    else:
        lines.append(
            f"{len(isolated)} script(s) import no sibling module and are imported "
            "by none:"
        )
        lines.append("")
        lines.append(", ".join(f"`{stem}`" for stem in isolated))
        lines.append("")

    lines.extend(["## Dependency graph", ""])
    if not edges:
        lines.extend(["No sibling-import edges to render.", ""])
    else:
        mermaid = ["flowchart TD"]
        for edge in edges:
            mermaid.append(f"    {edge.importer} --> {edge.imported}")
        lines.extend(["```mermaid", "\n".join(mermaid), "```", ""])

    return "\n".join(lines).rstrip() + "\n"


def build_document(root: Path = Path()) -> str:
    """Build the dependency-graph Markdown for the repository at *root*."""
    paths = iter_script_paths(root)
    return render_dependency_markdown(dependency_edges(root), script_stems(paths))


def write_dependency_doc(root: Path = Path()) -> Path:
    """Write the dependency-graph doc under ``docs/generated/scripts/``."""
    target = root / DOC_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_document(root), encoding="utf-8")
    return target


def _cmd_all_doc(args: argparse.Namespace) -> int:
    write_dependency_doc(Path(args.root))
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    sys.stdout.write(build_document(Path(args.root)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_all_doc = sub.add_parser(
        "all-doc",
        help="Write docs/generated/scripts/dependency-graph.md.",
    )
    p_all_doc.add_argument("--root", default=".", help="Repository root (default current directory).")
    p_all_doc.set_defaults(func=_cmd_all_doc)

    p_preview = sub.add_parser(
        "preview",
        help="Print the dependency-graph Markdown to stdout (no write).",
    )
    p_preview.add_argument("--root", default=".", help="Repository root (default current directory).")
    p_preview.set_defaults(func=_cmd_preview)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
