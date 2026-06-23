#!/usr/bin/env python3
"""Core library for the typed document dependency graph.

Loads ``docs/graph/doc-dependencies.toml``, validates the graph structure,
and provides query functions used by ``gate_doc_graph_pr.py`` (the CI gate)
and ``doc_graph_viz.py`` (the Mermaid diagram generator).

Graph model
-----------
*Nodes* are documents, compiled artifacts, scripts, and workflows. Each node
has a unique ``id``, a repository-relative ``path``, and a ``type``.

*Edges* are typed, directed relationships. An edge ``from -> to`` means
"when FROM changes, TO should be reviewed / updated." Severity determines
enforcement:

- ``blocking``: the CI gate fails when TO is absent from the PR diff (unless
  a ``doc-graph-waiver: TO_ID; reason`` line is present in the PR body).
- ``advisory``: the gate emits a note but does not fail.

Valid edge types:

- ``governs``    ; upstream principles define/constrain downstream; blocking.
- ``compiled_to``; upstream compiles deterministically into downstream; blocking.
- ``derives_from``-- downstream design was derived from upstream; blocking.
- ``enforced_by``; downstream script enforces upstream rule; advisory.
- ``implements`` ; downstream is the concrete implementation of upstream; advisory.
- ``references`` ; upstream cites downstream; advisory.

Architecture: pure functions on top (:func:`load_graph`, :func:`impact_report`,
:func:`render_mermaid`), no side effects. A single filesystem read in
:func:`load_graph`; the TOML file; feeds all downstream operations.

Contract:
- Inputs: a ``Path`` pointing at the TOML graph file.
- Outputs: :class:`DocGraph` (dataclass); :class:`ImpactReport` per PR diff;
  Mermaid diagram string for visualization.
- Failure policy: :class:`GraphValidationError` (subclass of ``ValueError``)
  on any structural violation; fails loud per CLAUDE.md section 4.

Tested by ``tests/test_doc_graph.py``. Refs #1754.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Node types drawn from the four-lane ownership model.
VALID_NODE_TYPES: frozenset[str] = frozenset(
    {
        "universal_text",
        "compiled_artifact",
        "prd",
        "standard",
        "runbook",
        "harness_script",
        "harness_workflow",
        "archive",
    }
)

#: Edge types whose default enforcement is blocking (upstream change -> co-change required).
BLOCKING_EDGE_TYPES: frozenset[str] = frozenset({"governs", "compiled_to", "derives_from"})

#: Edge types whose default enforcement is advisory (informational note only).
ADVISORY_EDGE_TYPES: frozenset[str] = frozenset({"enforced_by", "implements", "references"})

VALID_EDGE_TYPES: frozenset[str] = BLOCKING_EDGE_TYPES | ADVISORY_EDGE_TYPES
VALID_SEVERITIES: frozenset[str] = frozenset({"blocking", "advisory"})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocNode:
    """One node in the dependency graph."""

    id: str
    path: str
    type: str
    description: str = ""


@dataclass(frozen=True)
class DocEdge:
    """One directed dependency edge."""

    from_id: str
    to_id: str
    type: str
    severity: str  # "blocking" | "advisory"
    note: str = ""


@dataclass
class DocGraph:
    """The full dependency graph: node registry and edge list."""

    nodes: dict[str, DocNode] = field(default_factory=dict)
    edges: list[DocEdge] = field(default_factory=list)

    def node_for_path(self, file_path: str) -> DocNode | None:
        """Return the node whose ``path`` matches *file_path*, or ``None``."""
        for node in self.nodes.values():
            if node.path == file_path:
                return node
        return None

    def blocking_dependents(self, node_id: str) -> list[DocNode]:
        """Return nodes that must co-change when *node_id* changes.

        Only outgoing edges with ``severity == "blocking"`` are included.
        """
        result: list[DocNode] = []
        for edge in self.edges:
            if edge.from_id == node_id and edge.severity == "blocking":
                target = self.nodes.get(edge.to_id)
                if target is not None:
                    result.append(target)
        return result

    def advisory_dependents(self, node_id: str) -> list[tuple[DocNode, str]]:
        """Return ``(node, edge_type)`` for advisory outgoing edges from *node_id*."""
        result: list[tuple[DocNode, str]] = []
        for edge in self.edges:
            if edge.from_id == node_id and edge.severity == "advisory":
                target = self.nodes.get(edge.to_id)
                if target is not None:
                    result.append((target, edge.type))
        return result


@dataclass
class ImpactReport:
    """The result of running :func:`impact_report` for a set of changed files."""

    required_co_changes: list[tuple[DocNode, DocNode]]
    """``(changed_node, required_node)`` pairs where ``required_node`` is absent from the PR."""

    advisory_notes: list[tuple[DocNode, DocNode, str]]
    """``(changed_node, noted_node, edge_type)`` informational entries."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GraphValidationError(ValueError):
    """Raised when the TOML graph file fails structural validation."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_graph(path: Path) -> DocGraph:
    """Parse and validate *path* (TOML) and return a :class:`DocGraph`.

    Raises :class:`GraphValidationError` on any structural violation:
    unknown type, duplicate ID, or edge referencing an unknown node ID.
    """
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    graph = DocGraph()

    for raw in data.get("nodes", []):
        node_type = raw.get("type", "")
        if node_type not in VALID_NODE_TYPES:
            raise GraphValidationError(
                f"Unknown node type {node_type!r} for node {raw.get('id')!r}. "
                f"Valid types: {sorted(VALID_NODE_TYPES)}"
            )
        node_id = raw["id"]
        if node_id in graph.nodes:
            raise GraphValidationError(f"Duplicate node id {node_id!r}")
        graph.nodes[node_id] = DocNode(
            id=node_id,
            path=raw["path"],
            type=node_type,
            description=raw.get("description", ""),
        )

    for raw in data.get("edges", []):
        from_id = raw["from"]
        to_id = raw["to"]
        edge_type = raw.get("type", "")
        severity = raw.get("severity", "advisory")

        if from_id not in graph.nodes:
            raise GraphValidationError(
                f"Edge references unknown from-node {from_id!r}"
            )
        if to_id not in graph.nodes:
            raise GraphValidationError(
                f"Edge references unknown to-node {to_id!r}"
            )
        if edge_type not in VALID_EDGE_TYPES:
            raise GraphValidationError(
                f"Unknown edge type {edge_type!r}. "
                f"Valid types: {sorted(VALID_EDGE_TYPES)}"
            )
        if severity not in VALID_SEVERITIES:
            raise GraphValidationError(
                f"Unknown severity {severity!r}. Valid values: {sorted(VALID_SEVERITIES)}"
            )
        graph.edges.append(
            DocEdge(
                from_id=from_id,
                to_id=to_id,
                type=edge_type,
                severity=severity,
                note=raw.get("note", ""),
            )
        )

    return graph


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def impact_report(graph: DocGraph, changed_files: list[str]) -> ImpactReport:
    """Return the impact of *changed_files* against *graph*.

    For each changed file that maps to a graph node, collects:
    - ``required_co_changes``: blocking dependents whose path is absent from
      *changed_files*.
    - ``advisory_notes``: advisory dependents (informational only).
    """
    changed_paths: frozenset[str] = frozenset(changed_files)
    required: list[tuple[DocNode, DocNode]] = []
    advisory: list[tuple[DocNode, DocNode, str]] = []

    for file_path in changed_files:
        node = graph.node_for_path(file_path)
        if node is None:
            continue

        for dep in graph.blocking_dependents(node.id):
            if dep.path not in changed_paths:
                required.append((node, dep))

        for dep, edge_type in graph.advisory_dependents(node.id):
            advisory.append((node, dep, edge_type))

    return ImpactReport(required_co_changes=required, advisory_notes=advisory)


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

# Mermaid shape open/close pairs by node type.
_MERMAID_SHAPES: dict[str, tuple[str, str]] = {
    "universal_text": ("([", "])"),
    "compiled_artifact": ("[", "]"),
    "prd": ("[", "]"),
    "standard": ("[", "]"),
    "runbook": ("[", "]"),
    "harness_script": (">", "]"),
    "harness_workflow": ("[/", "/]"),
    "archive": ("[", "]"),
}

# Mermaid arrow style by (severity, edge_type).
_MERMAID_ARROWS: dict[tuple[str, str], str] = {
    ("blocking", "governs"): "-->|governs|",
    ("blocking", "compiled_to"): "==>|compiled to|",
    ("blocking", "derives_from"): "-->|derives from|",
    ("advisory", "enforced_by"): "-.->|enforced by|",
    ("advisory", "implements"): "-.->|implements|",
    ("advisory", "references"): "-.->|references|",
}


def render_mermaid(graph: DocGraph) -> str:
    """Return a Mermaid ``flowchart LR`` diagram of *graph* as a fenced code block."""
    lines: list[str] = ["```mermaid", "flowchart LR"]

    for node in graph.nodes.values():
        open_bracket, close_bracket = _MERMAID_SHAPES.get(node.type, ("[", "]"))
        label = node.id.replace("_", " ")
        lines.append(f'    {node.id}{open_bracket}"{label}"{close_bracket}')

    for edge in graph.edges:
        arrow = _MERMAID_ARROWS.get((edge.severity, edge.type), "-->")
        lines.append(f"    {edge.from_id} {arrow} {edge.to_id}")

    lines.append("```")
    return "\n".join(lines)
