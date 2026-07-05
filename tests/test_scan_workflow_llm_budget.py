"""Tests for ``scripts/scan_workflow_llm_budget.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_workflow_llm_budget

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]

_MARKERS = ["uses: anthropics/claude-code-action", "claude -p"]


def _policy(budgets: list[dict[str, object]]) -> dict[str, object]:
    return {
        "meta": {"schema_version": 1, "tracking_issue": 2269},
        "markers": [{"pattern": p} for p in _MARKERS],
        "budgets": budgets,
    }


# ---------------------------------------------------------------------------
# extract_markers / extract_budgets
# ---------------------------------------------------------------------------


class TestExtract:
    def test_extract_markers(self) -> None:
        assert scan_workflow_llm_budget.extract_markers(_policy([])) == _MARKERS

    def test_extract_markers_missing_key_is_empty(self) -> None:
        assert scan_workflow_llm_budget.extract_markers({}) == []

    def test_extract_budgets_keyed_by_workflow(self) -> None:
        budgets = [
            {
                "workflow": "llm.yml",
                "max_tokens_per_run": 100000,
                "max_runs_per_day": 24,
                "max_retries": 2,
            }
        ]
        result = scan_workflow_llm_budget.extract_budgets(_policy(budgets))
        assert result == {"llm.yml": budgets[0]}

    def test_extract_budgets_missing_key_is_empty(self) -> None:
        assert scan_workflow_llm_budget.extract_budgets({}) == {}


# ---------------------------------------------------------------------------
# missing_budget_keys
# ---------------------------------------------------------------------------


class TestMissingBudgetKeys:
    def test_none_budget_reports_all(self) -> None:
        missing = scan_workflow_llm_budget.missing_budget_keys(None)
        assert "max_runs_per_day" in missing
        assert "max_retries" in missing
        assert "max_tokens_per_run or max_cost_usd_per_run" in missing

    def test_complete_with_tokens_is_empty(self) -> None:
        budget: dict[str, object] = {"max_tokens_per_run": 1, "max_runs_per_day": 1, "max_retries": 1}
        assert scan_workflow_llm_budget.missing_budget_keys(budget) == []

    def test_complete_with_cost_is_empty(self) -> None:
        budget: dict[str, object] = {"max_cost_usd_per_run": 1.5, "max_runs_per_day": 1, "max_retries": 1}
        assert scan_workflow_llm_budget.missing_budget_keys(budget) == []

    def test_missing_cost_and_tokens(self) -> None:
        budget: dict[str, object] = {"max_runs_per_day": 1, "max_retries": 1}
        assert scan_workflow_llm_budget.missing_budget_keys(budget) == [
            "max_tokens_per_run or max_cost_usd_per_run"
        ]

    def test_missing_max_retries(self) -> None:
        budget: dict[str, object] = {"max_tokens_per_run": 1, "max_runs_per_day": 1}
        assert scan_workflow_llm_budget.missing_budget_keys(budget) == ["max_retries"]


# ---------------------------------------------------------------------------
# scan_line / scan_text
# ---------------------------------------------------------------------------


class TestScanLine:
    def test_detects_marker(self) -> None:
        assert scan_workflow_llm_budget.scan_line("  claude -p 'do the thing'", _MARKERS) == "claude -p"

    def test_no_marker_returns_none(self) -> None:
        assert scan_workflow_llm_budget.scan_line("  uv run pytest", _MARKERS) is None

    def test_comment_line_is_skipped(self) -> None:
        assert scan_workflow_llm_budget.scan_line("  # claude -p is documented here", _MARKERS) is None


class TestScanText:
    def test_returns_empty_when_clean(self) -> None:
        text = "name: x\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        assert scan_workflow_llm_budget.scan_text(text, _MARKERS) == []

    def test_returns_line_numbers_1_based(self) -> None:
        text = (
            "name: x\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      - run: claude -p 'hi'\n"
        )
        assert scan_workflow_llm_budget.scan_text(text, _MARKERS) == [(5, "claude -p")]

    def test_flattens_shell_continuation(self) -> None:
        text = "noop\n  claude \\\n    -p 'hi'\ndone\n"
        assert scan_workflow_llm_budget.scan_text(text, _MARKERS) == [(2, "claude -p")]


# ---------------------------------------------------------------------------
# find_marker_hits / find_violations
# ---------------------------------------------------------------------------


def _make_workflow_repo(tmp_path: Path) -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    return tmp_path


class TestFindViolations:
    def test_marker_without_budget_is_a_violation(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/llm.yml").write_text(
            "name: llm\njobs:\n  a:\n    steps:\n      - run: claude -p 'hi'\n"
        )
        violations = scan_workflow_llm_budget.find_violations(repo, policy=_policy([]))
        assert len(violations) == 1
        hit, missing = violations[0]
        assert hit.workflow == Path(".github/workflows/llm.yml")
        assert hit.pattern == "claude -p"
        assert "max_tokens_per_run or max_cost_usd_per_run" in missing

    def test_marker_with_complete_budget_is_clean(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/llm.yml").write_text(
            "name: llm\njobs:\n  a:\n    steps:\n      - run: claude -p 'hi'\n"
        )
        budgets = [
            {
                "workflow": "llm.yml",
                "max_tokens_per_run": 100000,
                "max_runs_per_day": 24,
                "max_retries": 2,
            }
        ]
        violations = scan_workflow_llm_budget.find_violations(repo, policy=_policy(budgets))
        assert violations == []

    def test_marker_with_incomplete_budget_names_missing_keys(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/llm.yml").write_text(
            "      - run: claude -p 'hi'\n"
        )
        budgets = [{"workflow": "llm.yml", "max_tokens_per_run": 1}]
        violations = scan_workflow_llm_budget.find_violations(repo, policy=_policy(budgets))
        assert len(violations) == 1
        _hit, missing = violations[0]
        assert missing == ["max_runs_per_day", "max_retries"]

    def test_no_marker_no_violation(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "      - run: uv run pytest\n"
        )
        assert scan_workflow_llm_budget.find_violations(repo, policy=_policy([])) == []

    def test_missing_workflow_dir_is_clean(self, tmp_path: Path) -> None:
        assert scan_workflow_llm_budget.find_violations(tmp_path, policy=_policy([])) == []

    def test_real_repo_has_no_violations(self) -> None:
        """The checked-in repo must pass the gate end-to-end (#2269 fact:
        no workflow invokes an LLM today)."""
        policy = scan_workflow_llm_budget.load_policy(
            REPO_ROOT / scan_workflow_llm_budget.POLICY_PATH
        )
        violations = scan_workflow_llm_budget.find_violations(REPO_ROOT, policy=policy)
        assert violations == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_verify_cli_clean(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".gitapex").mkdir()
        (repo / ".gitapex/llm-budget-policy.toml").write_text(
            "[meta]\nschema_version = 1\ntracking_issue = 2269\n"
            'markers = []\nbudgets = []\n'
        )
        exit_code = scan_workflow_llm_budget.main(
            ["verify", "--repo-root", str(repo)]
        )
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    def test_verify_cli_dirty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/llm.yml").write_text(
            "      - run: claude -p 'hi'\n"
        )
        (repo / ".gitapex").mkdir()
        (repo / ".gitapex/llm-budget-policy.toml").write_text(
            "[meta]\nschema_version = 1\ntracking_issue = 2269\n\n"
            '[[markers]]\npattern = "claude -p"\n\nbudgets = []\n'
        )
        exit_code = scan_workflow_llm_budget.main(
            ["verify", "--repo-root", str(repo)]
        )
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "::error file=" in captured.err
        assert "llm.yml" in captured.err
        assert "FAIL" in captured.err

    def test_verify_cli_malformed_policy(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".gitapex").mkdir()
        (repo / ".gitapex/llm-budget-policy.toml").write_text("not = valid = toml = [")
        exit_code = scan_workflow_llm_budget.main(
            ["verify", "--repo-root", str(repo)]
        )
        assert exit_code == 1
        assert "cannot parse policy file" in capsys.readouterr().err

    def test_real_repo_verify_cli_clean(self) -> None:
        """The real tree passes end-to-end via the CLI, matching the
        ``.github/workflows/verify-agents.yml`` invocation."""
        assert scan_workflow_llm_budget.main(["verify", "--repo-root", str(REPO_ROOT)]) == 0

    def test_no_subcommand_exits_nonzero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            scan_workflow_llm_budget.main([])
        assert exc.value.code == 2
