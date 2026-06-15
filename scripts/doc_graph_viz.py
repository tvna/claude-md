#!/usr/bin/env python3
"""Generate a Mermaid document dependency diagram from the graph TOML.

Writes ``docs/generated/graph/doc-dependency-graph.md``. Owned by the
post-merge automation (``decision-tree`` job in
``.github/workflows/post-merge.yml``); not hand-editable (guarded by
``scripts/gate_generated_scripts_manual_edit.py``).

The ``all-doc`` subcommand writes the output file; ``preview`` prints to
stdout without writing. Same single-producer ownership pattern as
``scripts/script_dependency_graph.py`` (refs #1543).

Contract:
- Inputs: ``all-doc`` or ``preview`` subcommand; ``--graph`` (default
  ``docs/graph/doc-dependencies.toml``); ``--out`` (default
  ``docs/generated/graph/doc-dependency-graph.md``).
- Outputs: Mermaid ``flowchart LR`` diagram wrapped in a Markdown file;
  exit 0 on success.
- Failure policy: fails loud per CLAUDE.md section 4 when the graph file
  is missing or invalid, or the output path cannot be written.

Tested by ``tests/test_doc_graph_viz.py``. Refs #1754.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_graph import GraphValidationError, load_graph, render_mermaid

_GRAPH_PATH = Path("docs/graph/doc-dependencies.toml")
_OUT_PATH = Path("docs/generated/graph/doc-dependency-graph.md")

_LEGEND = """\
## Legend

### Node shapes

| Shape | Node type |
|---|---|
| `([...])` round | `universal_text` |
| `[...]` rectangle | `prd`, `standard`, `runbook`, `archive` |
| `>[...]` flag | `harness_script` |
| `[/.../]` parallelogram | `harness_workflow` |
| `[...]` rectangle | `compiled_artifact` |

### Edge styles

| Arrow | Edge type | Severity |
|---|---|---|
| `-->\\|governs\\|` solid | `governs` | blocking |
| `==>\\|compiled to\\|` double | `compiled_to` | blocking |
| `-->\\|derives from\\|` solid | `derives_from` | blocking |
| `-.->` dashed | `enforced_by`, `implements`, `references` | advisory |

Blocking edges: co-change required or waived (`doc-graph-waiver: NODE_ID -- reason`).
Advisory edges: informational note only.
"""


def _build_content(graph_path: Path) -> str:
    graph = load_graph(graph_path)
    diagram = render_mermaid(graph)
    node_count = len(graph.nodes)
    edge_count = len(graph.edges)
    blocking = sum(1 for e in graph.edges if e.severity == "blocking")
    advisory = edge_count - blocking

    return (
        f"# Document Dependency Graph\n\n"
        f"Auto-generated from `{graph_path}`. Do not edit manually.\n"
        f"Source: `python3 scripts/doc_graph_viz.py all-doc`.\n\n"
        f"Nodes: {node_count} | Edges: {edge_count} "
        f"({blocking} blocking, {advisory} advisory)\n\n"
        f"{diagram}\n\n"
        f"{_LEGEND}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Mermaid doc-dependency diagram."
    )
    parser.add_argument("subcommand", choices=["all-doc", "preview"])
    parser.add_argument(
        "--graph",
        default=str(_GRAPH_PATH),
        help="Path to doc-dependencies.toml (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        default=str(_OUT_PATH),
        help="Output path for all-doc subcommand (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    graph_path = Path(args.graph)
    if not graph_path.exists():
        print(f"::error::doc_graph_viz: graph file not found at {graph_path}", file=sys.stderr)
        return 1

    try:
        content = _build_content(graph_path)
    except GraphValidationError as exc:
        print(f"::error::doc_graph_viz: graph validation error: {exc}", file=sys.stderr)
        return 1

    if args.subcommand == "preview":
        print(content)
        return 0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    graph = load_graph(graph_path)
    print(
        f"Wrote {out_path} ({len(graph.nodes)} nodes, {len(graph.edges)} edges)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
