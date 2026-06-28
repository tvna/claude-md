"""Tests for ``scripts/doc_graph_viz.py``.

Covers :func:`main` (both ``all-doc`` and ``preview`` subcommands). All tests
use ``tmp_path`` to avoid touching real ``docs/generated/`` output.

Refs #1754.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import doc_graph_viz as viz
import pytest

pytestmark = pytest.mark.shard_default

_MINIMAL_TOML = textwrap.dedent(
    """\
    [meta]
    schema_version = 1

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
    """
)


def _graph_path(tmp_path: Path, content: str = _MINIMAL_TOML) -> Path:
    p = tmp_path / "doc-dependencies.toml"
    p.write_text(content)
    return p


class TestPreview:
    def test_preview_exits_0(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        result = viz.main(["preview", "--graph", str(_graph_path(tmp_path))])
        assert result == 0

    def test_preview_contains_mermaid(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        viz.main(["preview", "--graph", str(_graph_path(tmp_path))])
        out = capsys.readouterr().out
        assert "```mermaid" in out
        assert "flowchart LR" in out

    def test_preview_contains_node_ids(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        viz.main(["preview", "--graph", str(_graph_path(tmp_path))])
        out = capsys.readouterr().out
        assert "master" in out
        assert "prd_a" in out

    def test_preview_contains_legend(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        viz.main(["preview", "--graph", str(_graph_path(tmp_path))])
        out = capsys.readouterr().out
        assert "## Legend" in out


class TestAllDoc:
    def test_all_doc_exits_0(self, tmp_path: Path) -> None:
        out_path = tmp_path / "out.md"
        result = viz.main(
            ["all-doc", "--graph", str(_graph_path(tmp_path)), "--out", str(out_path)]
        )
        assert result == 0

    def test_all_doc_creates_file(self, tmp_path: Path) -> None:
        out_path = tmp_path / "subdir" / "out.md"
        viz.main(["all-doc", "--graph", str(_graph_path(tmp_path)), "--out", str(out_path)])
        assert out_path.exists()

    def test_all_doc_content_has_mermaid(self, tmp_path: Path) -> None:
        out_path = tmp_path / "out.md"
        viz.main(["all-doc", "--graph", str(_graph_path(tmp_path)), "--out", str(out_path)])
        content = out_path.read_text()
        assert "```mermaid" in content
        assert "flowchart LR" in content

    def test_all_doc_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c" / "out.md"
        viz.main(
            ["all-doc", "--graph", str(_graph_path(tmp_path)), "--out", str(nested)]
        )
        assert nested.exists()

    def test_missing_graph_exits_1(self, tmp_path: Path) -> None:
        result = viz.main(
            ["all-doc", "--graph", str(tmp_path / "nonexistent.toml")]
        )
        assert result == 1

    def test_invalid_graph_exits_1(self, tmp_path: Path) -> None:
        bad = _graph_path(tmp_path, '[[nodes]]\nid="x"\npath="x.md"\ntype="bogus"\n')
        out_path = tmp_path / "out.md"
        result = viz.main(
            ["all-doc", "--graph", str(bad), "--out", str(out_path)]
        )
        assert result == 1

    def test_node_count_in_output(self, tmp_path: Path) -> None:
        out_path = tmp_path / "out.md"
        viz.main(["all-doc", "--graph", str(_graph_path(tmp_path)), "--out", str(out_path)])
        content = out_path.read_text()
        # two nodes in the minimal graph
        assert "Nodes: 2" in content

    def test_edge_count_in_output(self, tmp_path: Path) -> None:
        out_path = tmp_path / "out.md"
        viz.main(["all-doc", "--graph", str(_graph_path(tmp_path)), "--out", str(out_path)])
        content = out_path.read_text()
        assert "Edges: 1" in content
