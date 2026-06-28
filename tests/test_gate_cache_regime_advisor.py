"""Tests for ``scripts/gate_cache_regime_advisor.py``.

The ``scripts/`` directory is on ``sys.path`` via the ``pythonpath`` key under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.

The gate is advisory: it must never emit a blocking decision, must fail open on
bad input, and must only warn when the cache-read/write amortisation ratio falls
below the floor with enough write volume to judge. Pure logic
(``amortization_advice``) is exercised directly; the Stop seam (``evaluate``,
``main``) is covered with a ``tmp_path`` transcript and captured stdout/stderr.

Refs #1492.
"""

from __future__ import annotations

import json
from typing import Any

import gate_cache_regime_advisor as advisor
import pytest

pytestmark = pytest.mark.shard_preflight


def _assistant(message_id: str, usage: dict[str, Any]) -> dict[str, Any]:
    return {"type": "assistant", "message": {"id": message_id, "usage": usage}}


# ---------------------------------------------------------------------------
# amortization_advice
# ---------------------------------------------------------------------------


class TestAmortizationAdvice:
    def test_healthy_ratio_is_silent(self) -> None:
        # ~5.3x amortisation, the observed-healthy reference -> no advisory.
        assert advisor.amortization_advice(1_390_000, 262_000) is None

    def test_thrash_ratio_advises(self) -> None:
        advice = advisor.amortization_advice(40_000, 100_000)
        assert advice is not None
        assert "0.40" in advice
        advice.encode("ascii")  # advisory must be ASCII-safe for any log sink

    def test_warmup_write_volume_is_silent(self) -> None:
        # Below the warm-up floor the ratio is meaningless -> stay silent even
        # though reads (0) are far below writes.
        assert advisor.amortization_advice(0, 1_000) is None

    def test_exactly_at_floor_is_silent(self) -> None:
        assert advisor.amortization_advice(100_000, 100_000) is None


# ---------------------------------------------------------------------------
# evaluate (Stop seam)
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_non_stop_event_silent(self) -> None:
        assert advisor.evaluate({"hook_event_name": "PreToolUse"}) is None

    def test_stop_hook_active_silent(self) -> None:
        assert advisor.evaluate({"stop_hook_active": True}) is None

    def test_missing_transcript_silent(self) -> None:
        assert advisor.evaluate({"hook_event_name": "Stop"}) is None

    def test_thrash_transcript_advises(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            json.dumps(
                _assistant(
                    "m1",
                    {
                        "cache_read_input_tokens": 10_000,
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 0,
                            "ephemeral_1h_input_tokens": 200_000,
                        },
                    },
                )
            )
            + "\n",
            encoding="utf-8",
        )
        advice = advisor.evaluate({"hook_event_name": "Stop", "transcript_path": str(path)})
        assert advice is not None
        assert "amortisation floor" in advice


# ---------------------------------------------------------------------------
# main: advisory-only, never blocks
# ---------------------------------------------------------------------------


class TestMain:
    def test_thrash_warns_on_stderr_but_writes_no_decision(self, tmp_path, capsys, monkeypatch) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            json.dumps(
                _assistant(
                    "m1",
                    {
                        "cache_read_input_tokens": 10_000,
                        "cache_creation": {"ephemeral_1h_input_tokens": 200_000},
                    },
                )
            )
            + "\n",
            encoding="utf-8",
        )
        event = json.dumps({"hook_event_name": "Stop", "transcript_path": str(path)})
        monkeypatch.setattr("sys.stdin", _StdinStub(event))
        rc = advisor.main()
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out == ""  # no blocking decision ever written to stdout
        assert "cache regime advisory" in captured.err

    def test_malformed_stdin_fails_open(self, capsys, monkeypatch) -> None:
        monkeypatch.setattr("sys.stdin", _StdinStub("{not json"))
        rc = advisor.main()
        assert rc == 0
        assert capsys.readouterr().out == ""


class _StdinStub:
    """Minimal stdin replacement returning a fixed payload from ``read()``."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def read(self) -> str:
        return self._payload
