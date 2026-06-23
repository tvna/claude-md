"""Unit tests for ``scripts/doc_graph.py``.

Covers :func:`load_graph`, :func:`impact_report`, :func:`render_mermaid`, and
the :class:`DocGraph` query methods. All tests use in-memory TOML strings
written to ``tmp_path`` so the suite runs without touching the real
``docs/graph/`` file.

Refs #1754.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import doc_graph as dg
import pytest

pytestmark = pytest.mark.shard_default

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_TOML = textwrap.dedent(
    """\
    [meta]
    schema_version = 1
    description = "Test graph."

    [[nodes]]
    id = "master"
    path = ".apm/instructions/master.instructions.md"
    type = "universal_text"
    description = "Master source."

    [[nodes]]
    id = "prd_a"
    path = "docs/prd/a.md"
    type = "prd"
    description = "PRD A."

    [[edges]]
    from = "master"
    to = "prd_a"
    type = "governs"
    severity = "blocking"
    note = "Principle changes require PRD A review."
    """
)


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "doc-dependencies.toml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# load_graph; happy path
# ---------------------------------------------------------------------------


class TestLoadGraphHappy:
    def test_nodes_loaded(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        assert set(graph.nodes) == {"master", "prd_a"}

    def test_edge_loaded(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        assert len(graph.edges) == 1
        edge = graph.edges[0]
        assert edge.from_id == "master"
        assert edge.to_id == "prd_a"
        assert edge.type == "governs"
        assert edge.severity == "blocking"

    def test_node_description_optional(self, tmp_path: Path) -> None:
        toml = textwrap.dedent(
            """\
            [[nodes]]
            id = "x"
            path = "x.md"
            type = "prd"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, toml))
        assert graph.nodes["x"].description == ""

    def test_edge_note_optional(self, tmp_path: Path) -> None:
        toml = textwrap.dedent(
            """\
            [[nodes]]
            id = "a"
            path = "a.md"
            type = "prd"
            [[nodes]]
            id = "b"
            path = "b.md"
            type = "standard"
            [[edges]]
            from = "a"
            to = "b"
            type = "governs"
            severity = "blocking"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, toml))
        assert graph.edges[0].note == ""

    def test_edge_default_severity_advisory(self, tmp_path: Path) -> None:
        toml = textwrap.dedent(
            """\
            [[nodes]]
            id = "a"
            path = "a.md"
            type = "prd"
            [[nodes]]
            id = "b"
            path = "b.md"
            type = "harness_script"
            [[edges]]
            from = "a"
            to = "b"
            type = "enforced_by"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, toml))
        assert graph.edges[0].severity == "advisory"

    def test_all_valid_node_types_accepted(self, tmp_path: Path) -> None:
        lines = []
        for i, ntype in enumerate(sorted(dg.VALID_NODE_TYPES)):
            lines.append(f"[[nodes]]\nid = \"n{i}\"\npath = \"{i}.md\"\ntype = \"{ntype}\"\n")
        graph = dg.load_graph(_write_toml(tmp_path, "\n".join(lines)))
        assert len(graph.nodes) == len(dg.VALID_NODE_TYPES)

    def test_all_valid_edge_types_accepted(self, tmp_path: Path) -> None:
        node_lines = textwrap.dedent(
            """\
            [[nodes]]
            id = "src"
            path = "src.md"
            type = "prd"
            [[nodes]]
            id = "dst"
            path = "dst.md"
            type = "harness_script"
            """
        )
        edge_lines = "".join(
            f"[[edges]]\nfrom = \"src\"\nto = \"dst\"\ntype = \"{et}\"\nseverity = \"advisory\"\n"
            for et in sorted(dg.VALID_EDGE_TYPES)
        )
        graph = dg.load_graph(_write_toml(tmp_path, node_lines + edge_lines))
        assert len(graph.edges) == len(dg.VALID_EDGE_TYPES)


# ---------------------------------------------------------------------------
# load_graph; validation errors
# ---------------------------------------------------------------------------


class TestLoadGraphValidationErrors:
    def test_unknown_node_type(self, tmp_path: Path) -> None:
        bad = _MINIMAL_TOML.replace('type = "universal_text"', 'type = "bogus"')
        with pytest.raises(dg.GraphValidationError, match="Unknown node type"):
            dg.load_graph(_write_toml(tmp_path, bad))

    def test_duplicate_node_id(self, tmp_path: Path) -> None:
        dup = _MINIMAL_TOML + textwrap.dedent(
            """\
            [[nodes]]
            id = "master"
            path = "other.md"
            type = "prd"
            """
        )
        with pytest.raises(dg.GraphValidationError, match="Duplicate node id"):
            dg.load_graph(_write_toml(tmp_path, dup))

    def test_edge_unknown_from(self, tmp_path: Path) -> None:
        bad = _MINIMAL_TOML.replace('from = "master"', 'from = "ghost"')
        with pytest.raises(dg.GraphValidationError, match="unknown from-node"):
            dg.load_graph(_write_toml(tmp_path, bad))

    def test_edge_unknown_to(self, tmp_path: Path) -> None:
        bad = _MINIMAL_TOML.replace('to = "prd_a"', 'to = "ghost"')
        with pytest.raises(dg.GraphValidationError, match="unknown to-node"):
            dg.load_graph(_write_toml(tmp_path, bad))

    def test_unknown_edge_type(self, tmp_path: Path) -> None:
        bad = _MINIMAL_TOML.replace('type = "governs"', 'type = "foobar"')
        with pytest.raises(dg.GraphValidationError, match="Unknown edge type"):
            dg.load_graph(_write_toml(tmp_path, bad))

    def test_unknown_severity(self, tmp_path: Path) -> None:
        bad = _MINIMAL_TOML.replace('severity = "blocking"', 'severity = "critical"')
        with pytest.raises(dg.GraphValidationError, match="Unknown severity"):
            dg.load_graph(_write_toml(tmp_path, bad))


# ---------------------------------------------------------------------------
# DocGraph.node_for_path
# ---------------------------------------------------------------------------


class TestNodeForPath:
    def test_found(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        node = graph.node_for_path(".apm/instructions/master.instructions.md")
        assert node is not None
        assert node.id == "master"

    def test_not_found(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        assert graph.node_for_path("nonexistent.md") is None


# ---------------------------------------------------------------------------
# DocGraph.blocking_dependents
# ---------------------------------------------------------------------------


class TestBlockingDependents:
    def test_returns_blocking_target(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        deps = graph.blocking_dependents("master")
        assert [d.id for d in deps] == ["prd_a"]

    def test_advisory_excluded(self, tmp_path: Path) -> None:
        extra = textwrap.dedent(
            """\
            [[nodes]]
            id = "script_x"
            path = "scripts/x.py"
            type = "harness_script"
            [[edges]]
            from = "master"
            to = "script_x"
            type = "enforced_by"
            severity = "advisory"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML + extra))
        ids = [d.id for d in graph.blocking_dependents("master")]
        assert "prd_a" in ids
        assert "script_x" not in ids

    def test_no_outgoing_edges_returns_empty(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        assert graph.blocking_dependents("prd_a") == []

    def test_unknown_node_id_returns_empty(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        assert graph.blocking_dependents("nonexistent") == []


# ---------------------------------------------------------------------------
# DocGraph.advisory_dependents
# ---------------------------------------------------------------------------


class TestAdvisoryDependents:
    def test_returns_advisory_targets(self, tmp_path: Path) -> None:
        extra = textwrap.dedent(
            """\
            [[nodes]]
            id = "script_x"
            path = "scripts/x.py"
            type = "harness_script"
            [[edges]]
            from = "master"
            to = "script_x"
            type = "enforced_by"
            severity = "advisory"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML + extra))
        results = graph.advisory_dependents("master")
        assert len(results) == 1
        node, edge_type = results[0]
        assert node.id == "script_x"
        assert edge_type == "enforced_by"

    def test_blocking_excluded(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        # prd_a is a blocking dependent, should not appear in advisory_dependents
        assert graph.advisory_dependents("master") == []


# ---------------------------------------------------------------------------
# impact_report
# ---------------------------------------------------------------------------


class TestImpactReport:
    def test_changed_upstream_requires_downstream(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        report = dg.impact_report(
            graph, [".apm/instructions/master.instructions.md"]
        )
        assert len(report.required_co_changes) == 1
        changed, required = report.required_co_changes[0]
        assert changed.id == "master"
        assert required.id == "prd_a"

    def test_both_files_present_no_required(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        report = dg.impact_report(
            graph,
            [
                ".apm/instructions/master.instructions.md",
                "docs/prd/a.md",
            ],
        )
        assert report.required_co_changes == []

    def test_unknown_file_no_impact(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        report = dg.impact_report(graph, ["unknown/file.md"])
        assert report.required_co_changes == []
        assert report.advisory_notes == []

    def test_empty_changed_files(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        report = dg.impact_report(graph, [])
        assert report.required_co_changes == []

    def test_advisory_appears_in_notes(self, tmp_path: Path) -> None:
        extra = textwrap.dedent(
            """\
            [[nodes]]
            id = "script_x"
            path = "scripts/x.py"
            type = "harness_script"
            [[edges]]
            from = "master"
            to = "script_x"
            type = "enforced_by"
            severity = "advisory"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML + extra))
        report = dg.impact_report(
            graph, [".apm/instructions/master.instructions.md"]
        )
        assert len(report.advisory_notes) == 1
        _, noted, edge_type = report.advisory_notes[0]
        assert noted.id == "script_x"
        assert edge_type == "enforced_by"

    def test_downstream_change_does_not_trigger_upstream(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        # Changing prd_a (the downstream) should NOT require master (the upstream).
        report = dg.impact_report(graph, ["docs/prd/a.md"])
        assert report.required_co_changes == []


# ---------------------------------------------------------------------------
# render_mermaid
# ---------------------------------------------------------------------------


class TestRenderMermaid:
    def test_fenced_code_block(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        result = dg.render_mermaid(graph)
        assert result.startswith("```mermaid")
        assert result.endswith("```")

    def test_flowchart_direction(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        assert "flowchart LR" in dg.render_mermaid(graph)

    def test_node_ids_present(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        result = dg.render_mermaid(graph)
        assert "master" in result
        assert "prd_a" in result

    def test_governs_arrow_present(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        assert "-->|governs|" in dg.render_mermaid(graph)

    def test_compiled_to_double_arrow(self, tmp_path: Path) -> None:
        toml = textwrap.dedent(
            """\
            [[nodes]]
            id = "src"
            path = "src.md"
            type = "universal_text"
            [[nodes]]
            id = "dst"
            path = "dst.md"
            type = "compiled_artifact"
            [[edges]]
            from = "src"
            to = "dst"
            type = "compiled_to"
            severity = "blocking"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, toml))
        assert "==>|compiled to|" in dg.render_mermaid(graph)

    def test_advisory_dashed_arrow(self, tmp_path: Path) -> None:
        toml = textwrap.dedent(
            """\
            [[nodes]]
            id = "a"
            path = "a.md"
            type = "prd"
            [[nodes]]
            id = "b"
            path = "b.py"
            type = "harness_script"
            [[edges]]
            from = "a"
            to = "b"
            type = "enforced_by"
            severity = "advisory"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, toml))
        assert "-.->|enforced by|" in dg.render_mermaid(graph)

    def test_universal_text_round_shape(self, tmp_path: Path) -> None:
        graph = dg.load_graph(_write_toml(tmp_path, _MINIMAL_TOML))
        # universal_text nodes use ([...]) shape
        assert '(["master"])' in dg.render_mermaid(graph)

    def test_harness_script_flag_shape(self, tmp_path: Path) -> None:
        toml = textwrap.dedent(
            """\
            [[nodes]]
            id = "the_script"
            path = "scripts/x.py"
            type = "harness_script"
            """
        )
        graph = dg.load_graph(_write_toml(tmp_path, toml))
        assert ">\"the script\"]" in dg.render_mermaid(graph)
