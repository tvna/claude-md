from __future__ import annotations

import auto_retro as ar
import pytest

pytestmark = pytest.mark.shard_ci_ops_auto_retro_decision_tree


class TestDecisionTree:
    def test_mermaid_is_extracted_from_run_ast(self) -> None:
        text = ar.render_decision_tree_mermaid()
        assert text.startswith("flowchart TD\n")
        assert 'N001["run(...)"]' in text
        assert '["if not pr.merged"]' in text
        assert '["if not any(signals.values())"]' in text
        assert "compute_repair_signals(...)" in text
        assert "create_issue(...)" in text
        assert "return 0" in text

    def test_edges_are_deterministic(self) -> None:
        first = ar.auto_retro_decision_tree_edges()
        second = ar.auto_retro_decision_tree_edges()
        assert first == second
        assert len(first) > 80
        assert any(edge.label == "true" for edge in first)
        assert any(edge.label == "false" for edge in first)
        assert any(edge.label == "raises" for edge in first)

    def test_decision_tree_cli_writes_mermaid(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert ar.main(["decision-tree"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("flowchart TD\n")
        assert "compute_repair_signals" in out
