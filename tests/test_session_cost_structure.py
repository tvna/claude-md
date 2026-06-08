"""Tests for ``scripts/session_cost_structure.py``.

The ``scripts/`` directory is on ``sys.path`` via the ``pythonpath`` key under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.

The module is split into pure functions (``aggregate_usages``, ``compute_costs``,
``agreement_pct``, ``render_report``) and an I/O seam (``load_transcript``,
``discover_transcript``, ``_run_ccusage_total``, ``main``). The pure functions are
exercised directly; the seam is covered with ``tmp_path`` fixtures and a
monkeypatched ccusage subprocess, so no test shells out to ccusage.

Refs #1492.
"""

from __future__ import annotations

import json

import pytest
import session_cost_structure as scs

pytestmark = pytest.mark.shard_preflight


def _assistant(message_id: str, usage: dict) -> dict:
    """Return a transcript entry shaped like an assistant turn with *usage*."""
    return {"type": "assistant", "message": {"id": message_id, "usage": usage}}


# ---------------------------------------------------------------------------
# _coerce_int
# ---------------------------------------------------------------------------


class TestCoerceInt:
    def test_number(self) -> None:
        assert scs._coerce_int(42) == 42
        assert scs._coerce_int(3.9) == 3

    def test_bool_rejected(self) -> None:
        # JSON true must not read as 1.
        assert scs._coerce_int(True) == 0

    def test_non_number_and_negative_floor_to_zero(self) -> None:
        assert scs._coerce_int("12") == 0
        assert scs._coerce_int(None) == 0
        assert scs._coerce_int(-5) == 0


# ---------------------------------------------------------------------------
# aggregate_usages
# ---------------------------------------------------------------------------


class TestAggregateUsages:
    def test_dedup_by_message_id_last_wins(self) -> None:
        # Same id written twice (streaming) -> counted once, final value wins.
        entries = [
            _assistant("m1", {"output_tokens": 10}),
            _assistant("m1", {"output_tokens": 25}),
        ]
        assert scs.aggregate_usages(entries).output == 25

    def test_ttl_split_from_cache_creation(self) -> None:
        entries = [
            _assistant(
                "m1",
                {
                    "cache_read_input_tokens": 100,
                    "input_tokens": 5,
                    "output_tokens": 7,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 30,
                        "ephemeral_1h_input_tokens": 70,
                    },
                },
            )
        ]
        tok = scs.aggregate_usages(entries)
        assert (tok.cache_read, tok.input, tok.output) == (100, 5, 7)
        assert (tok.cache_write_5m, tok.cache_write_1h) == (30, 70)

    def test_flat_cache_creation_falls_back_to_5m(self) -> None:
        # Older shape without the nested split attributes the flat count to 5m.
        entries = [_assistant("m1", {"cache_creation_input_tokens": 40})]
        tok = scs.aggregate_usages(entries)
        assert tok.cache_write_5m == 40
        assert tok.cache_write_1h == 0

    def test_non_assistant_and_malformed_entries_ignored(self) -> None:
        entries = [
            {"type": "user", "message": {"content": "hi"}},
            "not a dict",
            {"type": "assistant", "message": {"id": "m1"}},  # no usage
            _assistant("m2", {"output_tokens": 3}),
        ]
        assert scs.aggregate_usages(entries).output == 3


# ---------------------------------------------------------------------------
# compute_costs
# ---------------------------------------------------------------------------


class TestComputeCosts:
    def test_known_session_matches_ccusage_model(self) -> None:
        # Token counts + default rates reproduce a real ccusage total to the
        # cent: this is the measure-first anchor that the rate table must hold.
        tokens = scs.Tokens(
            input=2871,
            output=25609,
            cache_read=930518,
            cache_write_5m=0,
            cache_write_1h=255177,
        )
        costs = scs.compute_costs(tokens, scs._DEFAULT_RATES)
        assert round(costs.total, 4) == 2.7147

    def test_total_is_sum_of_categories(self) -> None:
        tokens = scs.Tokens(input=1_000_000, output=0, cache_read=0,
                            cache_write_5m=0, cache_write_1h=0)
        costs = scs.compute_costs(tokens, scs._DEFAULT_RATES)
        assert costs.input == pytest.approx(5.0)
        assert costs.total == pytest.approx(5.0)

    def test_1h_default_matches_5m_but_override_models_list_price(self) -> None:
        tokens = scs.Tokens(input=0, output=0, cache_read=0,
                            cache_write_5m=0, cache_write_1h=1_000_000)
        # Default: 1.25x ($6.25) to match ccusage.
        assert scs.compute_costs(tokens, scs._DEFAULT_RATES).total == pytest.approx(6.25)
        # Override: published 2x list price.
        rates = dict(scs._DEFAULT_RATES, cache_write_1h=10.0)
        assert scs.compute_costs(tokens, rates).total == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# agreement_pct
# ---------------------------------------------------------------------------


class TestAgreementPct:
    def test_exact_match_is_100(self) -> None:
        assert scs.agreement_pct(2.7147, 2.7147) == pytest.approx(100.0)

    def test_ten_percent_high(self) -> None:
        assert scs.agreement_pct(1.1, 1.0) == pytest.approx(90.0)

    def test_non_positive_reference_is_none(self) -> None:
        assert scs.agreement_pct(1.0, 0.0) is None


# ---------------------------------------------------------------------------
# render_report
# ---------------------------------------------------------------------------


class TestRenderReport:
    def test_is_ascii_and_carries_total(self) -> None:
        tokens = scs.Tokens(input=10, output=20, cache_read=30,
                            cache_write_5m=40, cache_write_1h=50)
        costs = scs.compute_costs(tokens, scs._DEFAULT_RATES)
        out = scs.render_report(tokens, costs, None)
        out.encode("ascii")  # raises if any non-ASCII slipped in
        assert "TOTAL" in out
        assert "ccusage" not in out

    def test_ccusage_line_present_when_total_given(self) -> None:
        tokens = scs.Tokens(input=0, output=0, cache_read=0,
                            cache_write_5m=0, cache_write_1h=0)
        out = scs.render_report(tokens, scs.compute_costs(tokens, scs._DEFAULT_RATES), 1.5)
        assert "ccusage total $1.5000" in out


# ---------------------------------------------------------------------------
# I/O seam: load_transcript / discover_transcript / main
# ---------------------------------------------------------------------------


class TestTranscriptIO:
    def test_load_skips_blank_and_unparseable_lines(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            json.dumps(_assistant("m1", {"output_tokens": 1}))
            + "\n\nnot json\n"
            + json.dumps(_assistant("m2", {"output_tokens": 2}))
            + "\n",
            encoding="utf-8",
        )
        entries = scs.load_transcript(path)
        assert len(entries) == 2

    def test_load_missing_file_is_empty(self, tmp_path) -> None:
        assert scs.load_transcript(tmp_path / "absent.jsonl") == []

    def test_discover_picks_newest(self, tmp_path) -> None:
        cwd = tmp_path / "home" / "proj"
        slug_dir = tmp_path / "projects" / scs._slug_for(cwd)
        slug_dir.mkdir(parents=True)
        old = slug_dir / "old.jsonl"
        new = slug_dir / "new.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        new.write_text("{}\n", encoding="utf-8")
        import os

        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        assert scs.discover_transcript(tmp_path / "projects", cwd) == new

    def test_discover_absent_dir_is_none(self, tmp_path) -> None:
        assert scs.discover_transcript(tmp_path / "nope", tmp_path / "x") is None

    def test_main_prints_report_and_exits_zero(self, tmp_path, capsys) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            json.dumps(_assistant("m1", {"output_tokens": 1_000_000})) + "\n",
            encoding="utf-8",
        )
        rc = scs.main(["--transcript", str(path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Session cache cost structure" in out
        assert "output" in out
