"""Tests for ``scripts/gate_doc_graph_pr.py``.

Covers :func:`parse_waivers`, :func:`run_gate`, and :func:`main`. All tests
are hermetic: changed-file lists are injected directly into :func:`run_gate`
or patched via ``monkeypatch``; no real ``git diff`` subprocess is called.

Refs #1754.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import gate_doc_graph_pr as gate
import pytest
from doc_graph import DocEdge, DocGraph, DocNode

pytestmark = pytest.mark.shard_default

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_GRAPH_TOML = textwrap.dedent(
    """\
    [meta]
    schema_version = 1

    [[nodes]]
    id = "master"
    path = ".apm/instructions/master.instructions.md"
    type = "universal_text"

    [[nodes]]
    id = "prd_a"
    path = "docs/prd/a.md"
    type = "prd"

    [[nodes]]
    id = "script_x"
    path = "scripts/x.py"
    type = "harness_script"

    [[edges]]
    from = "master"
    to = "prd_a"
    type = "governs"
    severity = "blocking"

    [[edges]]
    from = "prd_a"
    to = "script_x"
    type = "enforced_by"
    severity = "advisory"
    """
)


def _write_graph(tmp_path: Path, content: str = _GRAPH_TOML) -> Path:
    p = tmp_path / "doc-dependencies.toml"
    p.write_text(content)
    return p


def _body_file(tmp_path: Path, body: str = "") -> Path:
    p = tmp_path / "pr-body.txt"
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# parse_waivers
# ---------------------------------------------------------------------------


class TestParseWaivers:
    def test_empty_body(self) -> None:
        assert gate.parse_waivers("") == frozenset()

    def test_single_waiver(self) -> None:
        body = "doc-graph-waiver: prd_a -- typo fix\n"
        assert gate.parse_waivers(body) == frozenset(["prd_a"])

    def test_multiple_waivers(self) -> None:
        body = "doc-graph-waiver: prd_a -- reason1\ndoc-graph-waiver: prd_b -- reason2\n"
        assert gate.parse_waivers(body) == frozenset(["prd_a", "prd_b"])

    def test_case_insensitive_marker(self) -> None:
        assert gate.parse_waivers("DOC-GRAPH-WAIVER: prd_a -- reason") == frozenset(["prd_a"])

    def test_leading_whitespace_ignored(self) -> None:
        assert gate.parse_waivers("   doc-graph-waiver: prd_a -- reason") == frozenset(["prd_a"])

    def test_waiver_without_reason(self) -> None:
        assert gate.parse_waivers("doc-graph-waiver: prd_a") == frozenset(["prd_a"])

    def test_irrelevant_text_ignored(self) -> None:
        body = "Some PR description.\nNo waivers here.\n"
        assert gate.parse_waivers(body) == frozenset()


# ---------------------------------------------------------------------------
# run_gate (pure unit tests, no subprocess)
# ---------------------------------------------------------------------------


class TestRunGate:
    def _make_simple_graph(self) -> DocGraph:
        g = DocGraph()
        g.nodes["master"] = DocNode(
            id="master",
            path=".apm/instructions/master.instructions.md",
            type="universal_text",
        )
        g.nodes["prd_a"] = DocNode(id="prd_a", path="docs/prd/a.md", type="prd")
        g.edges.append(
            DocEdge(from_id="master", to_id="prd_a", type="governs", severity="blocking")
        )
        return g

    def test_empty_changed_files_passes(self) -> None:
        graph = self._make_simple_graph()
        assert gate.run_gate(graph, [], frozenset()) is True

    def test_master_only_fails(self) -> None:
        graph = self._make_simple_graph()
        result = gate.run_gate(
            graph,
            [".apm/instructions/master.instructions.md"],
            frozenset(),
        )
        assert result is False

    def test_master_and_prd_passes(self) -> None:
        graph = self._make_simple_graph()
        result = gate.run_gate(
            graph,
            [".apm/instructions/master.instructions.md", "docs/prd/a.md"],
            frozenset(),
        )
        assert result is True

    def test_waiver_bypasses_block(self) -> None:
        graph = self._make_simple_graph()
        result = gate.run_gate(
            graph,
            [".apm/instructions/master.instructions.md"],
            frozenset(["prd_a"]),
        )
        assert result is True

    def test_wrong_waiver_id_still_fails(self) -> None:
        graph = self._make_simple_graph()
        result = gate.run_gate(
            graph,
            [".apm/instructions/master.instructions.md"],
            frozenset(["prd_b"]),  # wrong id
        )
        assert result is False

    def test_advisory_edge_does_not_block(self) -> None:
        g = DocGraph()
        g.nodes["a"] = DocNode(id="a", path="a.md", type="prd")
        g.nodes["b"] = DocNode(id="b", path="b.py", type="harness_script")
        g.edges.append(
            DocEdge(from_id="a", to_id="b", type="enforced_by", severity="advisory")
        )
        assert gate.run_gate(g, ["a.md"], frozenset()) is True

    def test_unknown_changed_file_passes(self) -> None:
        graph = self._make_simple_graph()
        assert gate.run_gate(graph, ["unknown/file.md"], frozenset()) is True


# ---------------------------------------------------------------------------
# main() integration (subprocess patched)
# ---------------------------------------------------------------------------


class TestMain:
    def _run_main(
        self,
        tmp_path: Path,
        changed: list[str],
        body: str = "",
        graph_toml: str = _GRAPH_TOML,
    ) -> int:
        graph_path = _write_graph(tmp_path, graph_toml)
        body_path = _body_file(tmp_path, body)
        with patch("gate_doc_graph_pr.get_changed_files", return_value=changed):
            return gate.main(
                [
                    "--graph", str(graph_path),
                    "--body-file", str(body_path),
                    "--base-ref", "origin/main",
                ]
            )

    def test_master_only_exits_1(self, tmp_path: Path) -> None:
        assert self._run_main(
            tmp_path, [".apm/instructions/master.instructions.md"]
        ) == 1

    def test_master_and_prd_exits_0(self, tmp_path: Path) -> None:
        assert self._run_main(
            tmp_path,
            [".apm/instructions/master.instructions.md", "docs/prd/a.md"],
        ) == 0

    def test_waiver_exits_0(self, tmp_path: Path) -> None:
        assert self._run_main(
            tmp_path,
            [".apm/instructions/master.instructions.md"],
            body="doc-graph-waiver: prd_a -- typo only\n",
        ) == 0

    def test_no_changed_files_exits_0(self, tmp_path: Path) -> None:
        assert self._run_main(tmp_path, []) == 0

    def test_unknown_file_exits_0(self, tmp_path: Path) -> None:
        assert self._run_main(tmp_path, ["some/other/file.md"]) == 0

    def test_missing_graph_exits_0(self, tmp_path: Path) -> None:
        with patch("gate_doc_graph_pr.get_changed_files", return_value=["foo.md"]):
            result = gate.main(
                ["--graph", str(tmp_path / "nonexistent.toml")]
            )
        assert result == 0

    def test_invalid_graph_exits_1(self, tmp_path: Path) -> None:
        bad_toml = "[[nodes]]\nid = \"x\"\npath = \"x.md\"\ntype = \"bogus_type\"\n"
        assert self._run_main(tmp_path, ["x.md"], graph_toml=bad_toml) == 1

    def test_advisory_edge_does_not_cause_failure(self, tmp_path: Path) -> None:
        # prd_a changes, script_x is advisory -> should not fail
        assert self._run_main(tmp_path, ["docs/prd/a.md"]) == 0

    def test_body_file_takes_precedence_over_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PR_BODY", "doc-graph-waiver: prd_a -- from env\n")
        graph_path = _write_graph(tmp_path)
        body_path = _body_file(tmp_path, "")  # no waiver in file
        with patch(
            "gate_doc_graph_pr.get_changed_files",
            return_value=[".apm/instructions/master.instructions.md"],
        ):
            result = gate.main(
                [
                    "--graph", str(graph_path),
                    "--body-file", str(body_path),
                    "--base-ref", "origin/main",
                ]
            )
        # body-file has no waiver, env is ignored, so gate fails
        assert result == 1

    def test_env_pr_body_used_when_no_body_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PR_BODY", "doc-graph-waiver: prd_a -- from env\n")
        graph_path = _write_graph(tmp_path)
        with patch(
            "gate_doc_graph_pr.get_changed_files",
            return_value=[".apm/instructions/master.instructions.md"],
        ):
            result = gate.main(
                [
                    "--graph", str(graph_path),
                    "--base-ref", "origin/main",
                ]
            )
        assert result == 0
