"""Tests for ``scripts/compare_cache_regimes.py``.

The ``scripts/`` directory is on ``sys.path`` via the ``pythonpath`` key under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.

The module is pure arithmetic over a supplied JSON fixture: ``parse_regimes``
aggregates per-regime means and validates the shape (failing loudly), and
``render_comparison`` formats the baseline-relative table. The I/O seam
(``_load_input``, ``main``) is covered with ``tmp_path`` and captured streams.

Refs #1492.
"""

from __future__ import annotations

import json
from typing import Any

import auto_retro
import compare_cache_regimes as ccr
import pytest
import session_resource_report as srr

pytestmark = pytest.mark.shard_preflight


def _resource_section(cost: float) -> str:
    """Render a real ``## Resource Consumption`` section via its producer.

    Grounding the cost fixture in ``session_resource_report.render_section``
    (rather than a hand-typed string) means a format drift in that producer
    breaks :func:`ccr.parse_pr_cost`'s test instead of silently mis-parsing.
    """
    usage = srr.Usage(
        input=1,
        output=2,
        cache_create=3,
        cache_read=4,
        total=10,
        cost=cost,
        models=["claude-opus-4-8"],
        reasoning=0,
    )
    return srr.render_section("0:10:00", usage)


def _repair_table(
    check_runs: list[dict[str, Any]] | None,
    commit_subjects: list[str],
    pr_commit_count: int,
    pr_type: str = "",
) -> str:
    """Render a real Repair history table via its producer in ``auto_retro``.

    Same grounding rationale as :func:`_resource_section`: the table that
    :func:`ccr.parse_retro_repairs` counts is the exact text
    ``auto_retro._build_repair_history_table`` pre-fills into a retro issue.
    """
    return auto_retro._build_repair_history_table(
        check_runs, commit_subjects, pr_commit_count, None, pr_type
    )


def _doc() -> dict[str, Any]:
    return {
        "regimes": [
            {"name": "baseline-5m", "prs": [{"cost": 2.0, "repairs": 2}, {"cost": 4.0, "repairs": 0}]},
            {"name": "candidate-1h", "prs": [{"cost": 3.0, "repairs": 1}]},
        ]
    }


# ---------------------------------------------------------------------------
# parse_regimes
# ---------------------------------------------------------------------------


class TestParseRegimes:
    def test_means_per_regime(self) -> None:
        summaries = ccr.parse_regimes(_doc())
        baseline, candidate = summaries
        assert (baseline.n, baseline.cost_per_pr, baseline.repairs_per_pr) == (2, 3.0, 1.0)
        assert (candidate.n, candidate.cost_per_pr, candidate.repairs_per_pr) == (1, 3.0, 1.0)

    def test_missing_regimes_key_raises(self) -> None:
        with pytest.raises(ccr.InputError, match="non-empty list"):
            ccr.parse_regimes({})

    def test_empty_pr_list_raises(self) -> None:
        with pytest.raises(ccr.InputError, match="non-empty list"):
            ccr.parse_regimes({"regimes": [{"name": "x", "prs": []}]})

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ccr.InputError, match="name"):
            ccr.parse_regimes({"regimes": [{"prs": [{"cost": 1, "repairs": 0}]}]})

    def test_non_numeric_cost_raises(self) -> None:
        with pytest.raises(ccr.InputError, match="cost"):
            ccr.parse_regimes(
                {"regimes": [{"name": "x", "prs": [{"cost": "free", "repairs": 0}]}]}
            )

    def test_bool_cost_rejected(self) -> None:
        # JSON true must not be averaged as 1.
        with pytest.raises(ccr.InputError):
            ccr.parse_regimes(
                {"regimes": [{"name": "x", "prs": [{"cost": True, "repairs": 0}]}]}
            )


# ---------------------------------------------------------------------------
# render_comparison
# ---------------------------------------------------------------------------


class TestRenderComparison:
    def test_baseline_has_no_delta_candidate_does(self) -> None:
        out = ccr.render_comparison(ccr.parse_regimes(_doc()))
        out.encode("ascii")  # must be ASCII-safe for a GitHub paste
        assert "baseline-5m" in out and "candidate-1h" in out
        # candidate cost 3.0 vs baseline 3.0 -> +0.0000 delta present.
        assert "+0.0000" in out

    def test_delta_sign_reflects_increase(self) -> None:
        doc = {
            "regimes": [
                {"name": "base", "prs": [{"cost": 2.0, "repairs": 0}]},
                {"name": "worse", "prs": [{"cost": 5.0, "repairs": 3}]},
            ]
        }
        out = ccr.render_comparison(ccr.parse_regimes(doc))
        assert "+3.0000" in out  # cost delta
        assert "+3.0000" in out  # repairs delta


# ---------------------------------------------------------------------------
# I/O seam: _load_input / main
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_reads_file_and_prints_table(self, tmp_path, capsys) -> None:
        path = tmp_path / "regimes.json"
        path.write_text(json.dumps(_doc()), encoding="utf-8")
        rc = ccr.main(["--input", str(path)])
        assert rc == 0
        assert "Cache regime comparison" in capsys.readouterr().out

    def test_main_invalid_json_exits_one(self, tmp_path, capsys) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        rc = ccr.main(["--input", str(path)])
        assert rc == 1
        assert "not valid JSON" in capsys.readouterr().err

    def test_main_reads_stdin(self, capsys, monkeypatch) -> None:
        monkeypatch.setattr("sys.stdin", _StdinStub(json.dumps(_doc())))
        rc = ccr.main([])
        assert rc == 0
        assert "baseline-5m" in capsys.readouterr().out


class _StdinStub:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def read(self) -> str:
        return self._payload


# ---------------------------------------------------------------------------
# Auto-collection: parse_pr_cost (cost from the PR-body Resource Consumption)
# ---------------------------------------------------------------------------


class TestParsePrCost:
    def test_reads_cost_from_rendered_section(self) -> None:
        body = "## Summary\n\nwork\n\n" + _resource_section(3.14)
        assert ccr.parse_pr_cost(body, "x") == pytest.approx(3.14)

    def test_ignores_dollar_amount_outside_the_section(self) -> None:
        # A `$` in unrelated prose must not be read as the cost: the parser
        # slices to the Resource Consumption section first.
        body = "## Notes\n\nWe saved $99.99 last week.\n\n" + _resource_section(2.50)
        assert ccr.parse_pr_cost(body, "x") == pytest.approx(2.50)

    def test_unavailable_marker_raises(self) -> None:
        # render_section(elapsed, None) emits the unavailable cost marker.
        body = srr.render_section("0:10:00", None)
        with pytest.raises(ccr.InputError, match="unavailable"):
            ccr.parse_pr_cost(body, "x")

    def test_missing_section_raises(self) -> None:
        with pytest.raises(ccr.InputError, match="Resource Consumption"):
            ccr.parse_pr_cost("# PR\n\nno resource section here", "x")


# ---------------------------------------------------------------------------
# Auto-collection: parse_retro_repairs (repairs from the Repair history table)
# ---------------------------------------------------------------------------


class TestParseRetroRepairs:
    def test_counts_genuine_repairs_excluding_exempt_policy_artifacts(self) -> None:
        # 2 CI fail rows (genuine) + 1 Iteration commit (fixup!, genuine and
        # counted despite the policy-artifact marker). The Merge-from-main row
        # and the Multi-commit PR row (pr_commit_count > 1) are exempt policy
        # artifacts and must not count.
        table = _repair_table(
            [
                {"conclusion": "failure", "name": "ci-a"},
                {"conclusion": "failure", "name": "ci-b"},
            ],
            ["fixup! tighten parser", "Merge branch 'main' into feature"],
            3,
        )
        assert ccr.parse_retro_repairs(table, "x") == 3

    def test_sentinel_table_counts_zero(self) -> None:
        # No signals -> auto_retro emits the `--` sentinel row.
        table = _repair_table(None, [], 1)
        assert ccr.parse_retro_repairs(table, "x") == 0

    def test_single_ci_failure_counts_one(self) -> None:
        table = _repair_table([{"conclusion": "failure", "name": "ci"}], [], 1)
        assert ccr.parse_retro_repairs(table, "x") == 1

    def test_missing_table_raises(self) -> None:
        with pytest.raises(ccr.InputError, match="Repair history table"):
            ccr.parse_retro_repairs("no table in this body", "x")


# ---------------------------------------------------------------------------
# Auto-collection wired through parse_regimes
# ---------------------------------------------------------------------------


class TestParseRegimesAutoCollection:
    def test_resolves_both_fields_from_supplied_bodies(self) -> None:
        doc = {
            "regimes": [
                {
                    "name": "candidate",
                    "prs": [
                        {
                            "pr_body": _resource_section(3.14),
                            "retro_body": _repair_table(
                                [{"conclusion": "failure", "name": "ci"}], [], 1
                            ),
                        }
                    ],
                }
            ]
        }
        (summary,) = ccr.parse_regimes(doc)
        assert summary.cost_per_pr == pytest.approx(3.14)
        assert summary.repairs_per_pr == pytest.approx(1.0)

    def test_mixes_inline_and_collected_fields_per_record(self) -> None:
        doc = {
            "regimes": [
                {
                    "name": "r",
                    "prs": [
                        # inline cost, collected repairs (sentinel -> 0)
                        {"cost": 5.0, "retro_body": _repair_table(None, [], 1)},
                        # collected cost, inline repairs
                        {"pr_body": _resource_section(1.0), "repairs": 2},
                    ],
                }
            ]
        }
        (summary,) = ccr.parse_regimes(doc)
        assert summary.cost_per_pr == pytest.approx(3.0)  # (5.0 + 1.0) / 2
        assert summary.repairs_per_pr == pytest.approx(1.0)  # (0 + 2) / 2

    def test_missing_cost_source_raises(self) -> None:
        with pytest.raises(ccr.InputError, match="cost"):
            ccr.parse_regimes({"regimes": [{"name": "r", "prs": [{"repairs": 0}]}]})

    def test_missing_repairs_source_raises(self) -> None:
        with pytest.raises(ccr.InputError, match="repairs"):
            ccr.parse_regimes({"regimes": [{"name": "r", "prs": [{"cost": 1.0}]}]})
