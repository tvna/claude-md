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

import compare_cache_regimes as ccr
import pytest

pytestmark = pytest.mark.shard_preflight


def _doc() -> dict:
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
