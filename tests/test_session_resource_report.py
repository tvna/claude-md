"""Tests for ``scripts/session_resource_report.py``.

The ``scripts/`` directory is on ``sys.path`` via the ``pythonpath`` key
under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

The generator is split into pure functions (``compute_elapsed``,
``parse_usage``, ``render_section``) and an I/O seam (``_run_ccusage``,
``gather``, ``main``). The pure functions are exercised directly; the seam
is covered by injecting ``env``/``now_ms`` into :func:`gather` and
monkeypatching the ccusage subprocess, so no test shells out to ccusage.

Refs #1413.
"""

from __future__ import annotations

import json
import re
import subprocess

import body_policy
import pytest
import session_resource_report as srr

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# compute_elapsed
# ---------------------------------------------------------------------------


class TestComputeElapsed:
    def test_minutes_and_seconds(self) -> None:
        # 402 s after spawn -> 0:06:42.
        assert srr.compute_elapsed(1000.0, 1000.0 + 402_000) == "0:06:42"

    def test_hours_zero_padding(self) -> None:
        # 3661 s -> 1:01:01, minutes/seconds zero-padded.
        assert srr.compute_elapsed(0.0, 3_661_000) == "1:01:01"

    def test_string_epoch_ms_parsed(self) -> None:
        assert srr.compute_elapsed("1000", 1000.0 + 5_000) == "0:00:05"

    def test_missing_spawn_returns_none(self) -> None:
        assert srr.compute_elapsed(None, 5_000.0) is None

    def test_non_numeric_returns_none(self) -> None:
        assert srr.compute_elapsed("not-a-number", 5_000.0) is None

    def test_negative_interval_returns_none(self) -> None:
        # Spawn timestamp in the future (clock skew) must not render a bogus
        # duration.
        assert srr.compute_elapsed(10_000.0, 5_000.0) is None


# ---------------------------------------------------------------------------
# parse_usage
# ---------------------------------------------------------------------------


def _row(period: str, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "period": period,
        "inputTokens": 3058,
        "outputTokens": 55836,
        "cacheCreationTokens": 184694,
        "cacheReadTokens": 2315219,
        "totalTokens": 2558807,
        "totalCost": 3.723137,
        "modelsUsed": ["claude-opus-4-8"],
    }
    base.update(over)
    return base


def _grouped(*rows: dict[str, object]) -> str:
    return json.dumps({"session": list(rows), "totals": {}})


def _coerce_row(row: dict[str, object]) -> srr.Usage:
    """Build a :class:`Usage` from a ccusage row dict via the real parser."""
    period = row["period"]
    assert isinstance(period, str)
    usage = srr.parse_usage(_grouped(row), period)
    assert usage is not None
    return usage


def _extract_total(section: str) -> int:
    """Return the integer from the ``- Total tokens: N (input ...)`` line."""
    match = re.search(r"- Total tokens: ([\d,]+)", section)
    assert match is not None, section
    return int(match.group(1).replace(",", ""))


class TestParseUsage:
    def test_matches_by_period(self) -> None:
        raw = _grouped(_row("other"), _row("target"))
        usage = srr.parse_usage(raw, "target")
        assert usage == {
            "input": 3058,
            "output": 55836,
            "cache_create": 184694,
            "cache_read": 2315219,
            "total": 2558807,
            "cost": pytest.approx(3.723137),
            "models": ["claude-opus-4-8"],
            "reasoning": 0,
        }

    def test_single_row_fallback_when_no_period_match(self) -> None:
        # --id filters server-side; a lone row is the requested session even
        # when the period text differs.
        raw = _grouped(_row("unexpected-id"))
        usage = srr.parse_usage(raw, "session-we-asked-for")
        assert usage is not None
        assert usage["total"] == 2558807

    def test_no_match_with_multiple_rows_returns_none(self) -> None:
        raw = _grouped(_row("a"), _row("b"))
        assert srr.parse_usage(raw, "c") is None

    def test_malformed_json_returns_none(self) -> None:
        assert srr.parse_usage("{not json", "x") is None

    def test_missing_keys_returns_none(self) -> None:
        raw = json.dumps({"session": [{"period": "x", "inputTokens": 1}]})
        assert srr.parse_usage(raw, "x") is None

    def test_non_numeric_token_returns_none(self) -> None:
        # A string where a token count is expected degrades the whole row.
        raw = _grouped(_row("x", inputTokens="lots"))
        assert srr.parse_usage(raw, "x") is None

    def test_boolean_token_returns_none(self) -> None:
        # A JSON ``true`` must not be read as the integer 1.
        raw = _grouped(_row("x", totalTokens=True))
        assert srr.parse_usage(raw, "x") is None

    def test_session_not_a_list_returns_none(self) -> None:
        assert srr.parse_usage(json.dumps({"session": {}}), "x") is None

    def test_top_level_not_a_dict_returns_none(self) -> None:
        assert srr.parse_usage(json.dumps([1, 2, 3]), "x") is None


# ---------------------------------------------------------------------------
# render_section
# ---------------------------------------------------------------------------


_USAGE: srr.Usage = {
    "input": 3064,
    "output": 57757,
    "cache_create": 188285,
    "cache_read": 2671781,
    "total": 2920887,
    "cost": 3.9719,
    "models": ["claude-opus-4-8"],
    "reasoning": 0,
}


_ELAPSED_LABEL = "Elapsed (since previous PR or session start)"


class TestRenderSection:
    def test_heading_present_and_first(self) -> None:
        out = srr.render_section("0:09:11", _USAGE)
        assert out.startswith("## Resource Consumption\n")

    def test_live_values_with_thousands_separators(self) -> None:
        out = srr.render_section("0:09:11", _USAGE)
        assert "0:09:11" in out
        assert "2,920,887" in out
        assert "input 3,064" in out
        assert "cache-read 2,671,781" in out
        assert "$3.9719" in out
        # The Model(s) line carries the redacted tier, never the verbatim id.
        assert "Model(s): Opus-class" in out
        assert "claude-opus-4-8" not in out

    def test_usage_none_renders_unavailable(self) -> None:
        out = srr.render_section("0:09:11", None)
        # Elapsed still shown; the token/cost/model lines degrade.
        assert f"{_ELAPSED_LABEL}: 0:09:11" in out
        assert out.count(srr._UNAVAILABLE) == 3

    def test_elapsed_none_renders_unavailable(self) -> None:
        out = srr.render_section(None, _USAGE)
        assert f"{_ELAPSED_LABEL}: {srr._UNAVAILABLE}" in out
        assert "2,920,887" in out

    def test_both_none_all_unavailable(self) -> None:
        out = srr.render_section(None, None)
        assert out.count(srr._UNAVAILABLE) == 4

    def test_empty_models_list_is_unavailable(self) -> None:
        usage: srr.Usage = {
            "input": 1,
            "output": 1,
            "cache_create": 1,
            "cache_read": 1,
            "total": 4,
            "cost": 0.1,
            "models": [],
            "reasoning": 0,
        }
        out = srr.render_section("0:00:01", usage)
        assert f"Model(s): {srr._UNAVAILABLE}" in out

    def test_output_is_ascii(self) -> None:
        assert srr.render_section("0:09:11", _USAGE).isascii()
        assert srr.render_section(None, None).isascii()


# ---------------------------------------------------------------------------
# redact_model / redact_models (model-identity redaction)
# ---------------------------------------------------------------------------


class TestRedactModel:
    def test_opus_id_maps_to_tier(self) -> None:
        assert srr.redact_model("claude-opus-4-8") == "Opus-class"

    def test_sonnet_id_maps_to_tier(self) -> None:
        assert srr.redact_model("claude-sonnet-4-6") == "Sonnet-class"

    def test_haiku_id_maps_to_tier(self) -> None:
        assert srr.redact_model("claude-haiku-4-5-20251001") == "Haiku-class"

    def test_older_shape_with_family_after_version(self) -> None:
        # A substring match so an older claude-3-5-sonnet-... shape still
        # resolves to the family tier.
        assert srr.redact_model("claude-3-5-sonnet-20241022") == "Sonnet-class"

    def test_unknown_id_falls_back(self) -> None:
        # A non-Claude or unrecognized id never leaks verbatim.
        assert srr.redact_model("gpt-4o") == srr._UNKNOWN_MODEL_TIER
        assert srr.redact_model("some-other-model") == srr._UNKNOWN_MODEL_TIER

    def test_no_verbatim_version_in_output(self) -> None:
        assert "4-8" not in srr.redact_model("claude-opus-4-8")


class TestRedactModels:
    def test_order_preserving_and_deduplicated(self) -> None:
        tiers = srr.redact_models(
            ["claude-opus-4-8", "claude-sonnet-4-6", "claude-opus-4-7"]
        )
        # Two Opus ids collapse to a single Opus-class entry; order preserved.
        assert tiers == ["Opus-class", "Sonnet-class"]

    def test_empty_list_returns_empty(self) -> None:
        assert srr.redact_models([]) == []

    def test_unknown_ids_collapse_to_single_fallback(self) -> None:
        assert srr.redact_models(["foo", "bar"]) == [srr._UNKNOWN_MODEL_TIER]


# ---------------------------------------------------------------------------
# Contract with body_policy
# ---------------------------------------------------------------------------


class TestBodyPolicyContract:
    def test_section_is_a_required_pr_heading(self) -> None:
        assert "Resource Consumption" in body_policy._PR_REQUIRED

    def test_rendered_section_satisfies_heading_extraction(self) -> None:
        out = srr.render_section("0:09:11", _USAGE)
        headings = {text for _level, text in body_policy.extract_headings(out)}
        assert "Resource Consumption" in headings


# ---------------------------------------------------------------------------
# gather (I/O seam, ccusage monkeypatched)
# ---------------------------------------------------------------------------


class TestGather:
    def test_live_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        # First PR of the session: no checkpoint, so the cumulative total is
        # the window and elapsed runs from the spawn timestamp.
        monkeypatch.setattr(
            srr, "_run_ccusage", lambda _sid: _grouped(_row("sess-1"))
        )
        env = {
            "CCR_SPAWN_TIMESTAMP_MS": "1000",
            "CLAUDE_CODE_SESSION_ID": "sess-1",
            "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path),
        }
        out = srr.gather(env=env, now_ms=1000.0 + 90_000)
        assert f"{_ELAPSED_LABEL}: 0:01:30" in out
        assert "2,558,807" in out
        assert "$3.7231" in out
        # End-to-end the Model(s) line is redacted to the capability tier.
        assert "Model(s): Opus-class" in out
        assert "claude-opus-4-8" not in out

    def test_no_session_id_degrades(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # No session id -> ccusage is never consulted; tokens unavailable but
        # elapsed still rendered from the spawn timestamp.
        called = {"n": 0}

        def _fake(_sid: str) -> str | None:
            called["n"] += 1
            return None

        monkeypatch.setattr(srr, "_run_ccusage", _fake)
        env = {"CCR_SPAWN_TIMESTAMP_MS": "1000"}
        out = srr.gather(env=env, now_ms=1000.0 + 1_000)
        assert f"{_ELAPSED_LABEL}: 0:00:01" in out
        assert out.count(srr._UNAVAILABLE) == 3

    def test_ccusage_absent_degrades(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(srr, "_run_ccusage", lambda _sid: None)
        env = {"CLAUDE_CODE_SESSION_ID": "sess-1"}
        out = srr.gather(env=env, now_ms=5_000.0)
        # No spawn ts and no ccusage -> the full unavailable form.
        assert out.count(srr._UNAVAILABLE) == 4


# ---------------------------------------------------------------------------
# Per-PR checkpoint: write_checkpoint + delta_usage + multi-PR gather (#1435)
# ---------------------------------------------------------------------------


class TestDeltaUsage:
    def test_no_baseline_returns_cumulative(self) -> None:
        cumulative = _coerce_row(_row("x"))
        assert srr.delta_usage(cumulative, None) == cumulative

    def test_subtracts_baseline_per_field(self) -> None:
        baseline = _coerce_row(_row("x"))
        cumulative = _coerce_row(
            _row(
                "x",
                inputTokens=4058,
                outputTokens=56836,
                cacheCreationTokens=185694,
                cacheReadTokens=2316219,
                totalTokens=2562807,
                totalCost=4.723137,
            )
        )
        delta = srr.delta_usage(cumulative, baseline)
        assert delta["input"] == 1000
        assert delta["output"] == 1000
        assert delta["cache_create"] == 1000
        assert delta["cache_read"] == 1000
        assert delta["total"] == 4000
        assert delta["cost"] == pytest.approx(1.0)

    def test_negative_field_falls_back_to_cumulative(self) -> None:
        # A stale checkpoint whose totals exceed the current cumulative (e.g. a
        # different session) must not produce a negative delta.
        baseline = _coerce_row(_row("x", totalTokens=9_000_000))
        cumulative = _coerce_row(_row("x"))
        assert srr.delta_usage(cumulative, baseline) == cumulative


class TestCheckpointRoundTrip:
    def test_save_then_load(self, tmp_path: pytest.TempPathFactory) -> None:
        env = {"CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path)}
        usage = _coerce_row(_row("sess-1"))
        srr.save_checkpoint("sess-1", 1234.0, usage, env)
        loaded = srr.load_checkpoint("sess-1", env)
        assert loaded is not None
        assert loaded["ts_ms"] == 1234.0
        assert loaded["usage"] == usage

    def test_load_missing_returns_none(self, tmp_path: pytest.TempPathFactory) -> None:
        env = {"CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path)}
        assert srr.load_checkpoint("never-written", env) is None

    def test_no_session_id_no_path(self) -> None:
        assert srr._checkpoint_path("", {}) is None
        assert srr.load_checkpoint("", {}) is None

    def test_corrupt_file_returns_none(self, tmp_path: pytest.TempPathFactory) -> None:
        env = {"CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path)}
        path = srr._checkpoint_path("sess-1", env)
        assert path is not None
        path.write_text("{not json", encoding="utf-8")
        assert srr.load_checkpoint("sess-1", env) is None

    def test_write_checkpoint_records_current_cumulative(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setattr(
            srr, "_run_ccusage", lambda _sid: _grouped(_row("sess-1"))
        )
        env = {
            "CLAUDE_CODE_SESSION_ID": "sess-1",
            "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path),
        }
        srr.write_checkpoint(env=env, now_ms=5000.0)
        loaded = srr.load_checkpoint("sess-1", env)
        assert loaded is not None
        assert loaded["ts_ms"] == 5000.0
        assert loaded["usage"]["total"] == 2558807

    def test_write_checkpoint_no_ccusage_is_noop(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        # ccusage unavailable -> any prior checkpoint is left intact, not blanked.
        env = {
            "CLAUDE_CODE_SESSION_ID": "sess-1",
            "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path),
        }
        srr.save_checkpoint("sess-1", 1.0, _coerce_row(_row("sess-1")), env)
        monkeypatch.setattr(srr, "_run_ccusage", lambda _sid: None)
        srr.write_checkpoint(env=env, now_ms=9999.0)
        loaded = srr.load_checkpoint("sess-1", env)
        assert loaded is not None
        assert loaded["ts_ms"] == 1.0  # unchanged


class TestMultiPRWindowing:
    """The #1435 regression: a second PR in one session must report the delta
    since the first PR-create, and the two deltas must sum to the session
    total -- no double-counting of the first PR's tokens."""

    def test_second_pr_reports_delta_not_cumulative(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        env = {
            "CCR_SPAWN_TIMESTAMP_MS": "1000",
            "CLAUDE_CODE_SESSION_ID": "sess-1",
            "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path),
        }

        # --- PR #1: cumulative 1,000,000 total tokens, cost $1.0 ---
        pr1 = _row(
            "sess-1",
            inputTokens=100,
            outputTokens=200,
            cacheCreationTokens=300,
            cacheReadTokens=400,
            totalTokens=1_000_000,
            totalCost=1.0,
        )
        monkeypatch.setattr(srr, "_run_ccusage", lambda _sid: _grouped(pr1))
        out1 = srr.gather(env=env, now_ms=1000.0 + 60_000)
        assert "1,000,000" in out1
        assert "$1.0000" in out1
        assert f"{_ELAPSED_LABEL}: 0:01:00" in out1  # from spawn (no checkpoint yet)

        # The PostToolUse create hook advances the checkpoint at PR #1 create.
        srr.write_checkpoint(env=env, now_ms=1000.0 + 60_000)

        # --- PR #2: cumulative grew to 1,500,000 total, cost $1.6 ---
        pr2 = _row(
            "sess-1",
            inputTokens=150,
            outputTokens=260,
            cacheCreationTokens=360,
            cacheReadTokens=470,
            totalTokens=1_500_000,
            totalCost=1.6,
        )
        monkeypatch.setattr(srr, "_run_ccusage", lambda _sid: _grouped(pr2))
        out2 = srr.gather(env=env, now_ms=1000.0 + 60_000 + 120_000)

        # PR #2 must report its own slice, not the cumulative 1,500,000.
        assert "500,000" in out2
        assert "1,500,000" not in out2
        assert "$0.6000" in out2
        # Elapsed for PR #2 runs from the PR #1 checkpoint, not session spawn.
        assert f"{_ELAPSED_LABEL}: 0:02:00" in out2

    def test_per_pr_deltas_sum_to_session_total(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        env = {
            "CCR_SPAWN_TIMESTAMP_MS": "0",
            "CLAUDE_CODE_SESSION_ID": "sess-1",
            "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path),
        }
        cumulatives = [300_000, 700_000, 1_200_000]
        reported: list[int] = []
        for i, total in enumerate(cumulatives):
            row = _row("sess-1", totalTokens=total, totalCost=float(total) / 1e6)
            monkeypatch.setattr(srr, "_run_ccusage", lambda _sid, r=row: _grouped(r))
            out = srr.gather(env=env, now_ms=float((i + 1) * 1000))
            reported.append(_extract_total(out))
            srr.write_checkpoint(env=env, now_ms=float((i + 1) * 1000))
        assert sum(reported) == cumulatives[-1]
        assert reported == [300_000, 400_000, 500_000]


# ---------------------------------------------------------------------------
# _coerce_number
# ---------------------------------------------------------------------------


class TestCoerceNumber:
    def test_int_and_float_pass_through(self) -> None:
        assert srr._coerce_number(5) == 5.0
        assert srr._coerce_number(2.5) == 2.5

    def test_non_number_raises(self) -> None:
        with pytest.raises(ValueError, match="not a number"):
            srr._coerce_number("nope")

    def test_bool_raises(self) -> None:
        with pytest.raises(ValueError, match="not a number"):
            srr._coerce_number(True)


# ---------------------------------------------------------------------------
# _run_ccusage (subprocess seam)
# ---------------------------------------------------------------------------


class TestRunCcusage:
    def test_empty_session_id_returns_none(self) -> None:
        assert srr._run_ccusage("") is None

    def test_ccusage_not_on_path_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(srr.shutil, "which", lambda _name: None)
        assert srr._run_ccusage("sess") is None

    def test_success_returns_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(srr.shutil, "which", lambda _name: "/fake/ccusage")

        def fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess:
            assert argv == ["/fake/ccusage", "session", "--json"]
            return subprocess.CompletedProcess(argv, 0, stdout='{"session": []}', stderr="")

        monkeypatch.setattr(srr.subprocess, "run", fake_run)
        assert srr._run_ccusage("sess") == '{"session": []}'

    def test_non_zero_exit_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(srr.shutil, "which", lambda _name: "/fake/ccusage")

        def fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(argv, 1, stdout="x", stderr="boom")

        monkeypatch.setattr(srr.subprocess, "run", fake_run)
        assert srr._run_ccusage("sess") is None

    def test_subprocess_error_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(srr.shutil, "which", lambda _name: "/fake/ccusage")

        def boom(*_a: object, **_k: object) -> object:
            raise OSError("cannot exec")

        monkeypatch.setattr(srr.subprocess, "run", boom)
        assert srr._run_ccusage("sess") is None


# ---------------------------------------------------------------------------
# gather default branches (os.environ / wall clock)
# ---------------------------------------------------------------------------


class TestGatherDefaults:
    def test_defaults_to_os_environ_and_wall_clock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # env=None -> os.environ; now_ms=None -> time.time(). ccusage stubbed
        # so the test never shells out.
        monkeypatch.setattr(srr, "_run_ccusage", lambda _sid: None)
        out = srr.gather()
        assert out.startswith("## Resource Consumption")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_writes_section_and_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(srr, "gather", lambda: "## Resource Consumption\n- x\n")
        assert srr.main([]) == 0
        assert capsys.readouterr().out == "## Resource Consumption\n- x\n"


# ---------------------------------------------------------------------------
# Codex support (#1467)
# ---------------------------------------------------------------------------


def _codex_json(
    *,
    inp: int = 1000,
    output: int = 500,
    cache_read: int = 200,
    total: int = 1700,
    cost: float = 0.025,
    reasoning: int = 0,
) -> str:
    """Return a ``ccusage codex session --json`` payload (confirmed schema, #1467)."""
    return json.dumps(
        {
            "sessions": [],
            "totals": {
                "inputTokens": inp,
                "outputTokens": output,
                "cachedInputTokens": cache_read,
                "totalTokens": total,
                "costUSD": cost,
                "reasoningOutputTokens": reasoning,
            },
        }
    )


class TestIsCodex:
    def test_agent_container_codex_returns_true(self) -> None:
        assert srr._is_codex({"AGENT_CONTAINER": "codex"}) is True

    def test_absent_env_returns_false(self) -> None:
        assert srr._is_codex({}) is False

    def test_other_value_returns_false(self) -> None:
        assert srr._is_codex({"AGENT_CONTAINER": "claude"}) is False

    def test_claude_code_env_returns_false(self) -> None:
        assert srr._is_codex({"CLAUDE_CODE_SESSION_ID": "abc"}) is False


class TestParseUsageCodex:
    def test_parses_confirmed_totals_schema(self) -> None:
        usage = srr.parse_usage_codex(_codex_json())
        assert usage == {
            "input": 1000,
            "output": 500,
            "cache_create": 0,
            "cache_read": 200,
            "total": 1700,
            "cost": pytest.approx(0.025),
            "models": [],
            "reasoning": 0,
        }

    def test_cache_create_is_always_zero(self) -> None:
        usage = srr.parse_usage_codex(_codex_json())
        assert usage is not None
        assert usage["cache_create"] == 0

    def test_models_is_always_empty(self) -> None:
        usage = srr.parse_usage_codex(_codex_json())
        assert usage is not None
        assert usage["models"] == []

    def test_reasoning_tokens_surfaced(self) -> None:
        usage = srr.parse_usage_codex(_codex_json(reasoning=12345))
        assert usage is not None
        assert usage["reasoning"] == 12345

    def test_all_zeros_returns_valid_usage(self) -> None:
        raw = json.dumps(
            {
                "sessions": [],
                "totals": {
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cachedInputTokens": 0,
                    "totalTokens": 0,
                    "costUSD": 0,
                    "reasoningOutputTokens": 0,
                },
            }
        )
        usage = srr.parse_usage_codex(raw)
        assert usage is not None
        assert usage["total"] == 0

    def test_malformed_json_returns_none(self) -> None:
        assert srr.parse_usage_codex("{not json") is None

    def test_missing_totals_key_returns_none(self) -> None:
        assert srr.parse_usage_codex(json.dumps({"sessions": []})) is None

    def test_missing_token_field_returns_none(self) -> None:
        raw = json.dumps({"sessions": [], "totals": {"inputTokens": 1}})
        assert srr.parse_usage_codex(raw) is None

    def test_non_numeric_field_returns_none(self) -> None:
        raw = json.dumps(
            {
                "sessions": [],
                "totals": {
                    "inputTokens": "lots",
                    "outputTokens": 0,
                    "cachedInputTokens": 0,
                    "totalTokens": 0,
                    "costUSD": 0,
                    "reasoningOutputTokens": 0,
                },
            }
        )
        assert srr.parse_usage_codex(raw) is None

    def test_boolean_field_returns_none(self) -> None:
        raw = json.dumps(
            {
                "sessions": [],
                "totals": {
                    "inputTokens": True,
                    "outputTokens": 0,
                    "cachedInputTokens": 0,
                    "totalTokens": 0,
                    "costUSD": 0,
                    "reasoningOutputTokens": 0,
                },
            }
        )
        assert srr.parse_usage_codex(raw) is None

    def test_top_level_not_a_dict_returns_none(self) -> None:
        assert srr.parse_usage_codex(json.dumps([1, 2, 3])) is None


class TestRunCcusageCodex:
    def test_ccusage_not_on_path_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(srr.shutil, "which", lambda _name: None)
        assert srr._run_ccusage_codex() is None

    def test_success_returns_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(srr.shutil, "which", lambda _name: "/fake/ccusage")

        def fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess:
            assert argv == ["/fake/ccusage", "codex", "session", "--json"]
            return subprocess.CompletedProcess(argv, 0, stdout=_codex_json(), stderr="")

        monkeypatch.setattr(srr.subprocess, "run", fake_run)
        assert srr._run_ccusage_codex() == _codex_json()

    def test_non_zero_exit_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(srr.shutil, "which", lambda _name: "/fake/ccusage")

        def fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(argv, 1, stdout="x", stderr="boom")

        monkeypatch.setattr(srr.subprocess, "run", fake_run)
        assert srr._run_ccusage_codex() is None

    def test_subprocess_error_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(srr.shutil, "which", lambda _name: "/fake/ccusage")

        def boom(*_a: object, **_k: object) -> object:
            raise OSError("cannot exec")

        monkeypatch.setattr(srr.subprocess, "run", boom)
        assert srr._run_ccusage_codex() is None


class TestCodexRolloutSessionId:
    def test_returns_uuid_from_most_recent_file(self, tmp_path: pytest.TempPathFactory) -> None:
        sessions_dir = tmp_path / "sessions" / "2026" / "06" / "14"
        sessions_dir.mkdir(parents=True)
        rollout = sessions_dir / "rollout-1749945000000-550e8400-e29b-41d4-a716-446655440000.jsonl"
        rollout.write_text("", encoding="utf-8")
        result = srr._codex_rollout_session_id(_base=tmp_path / "sessions")
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_no_files_returns_empty_string(self, tmp_path: pytest.TempPathFactory) -> None:
        (tmp_path / "sessions").mkdir()
        result = srr._codex_rollout_session_id(_base=tmp_path / "sessions")
        assert result == ""

    def test_missing_base_dir_returns_empty_string(self, tmp_path: pytest.TempPathFactory) -> None:
        result = srr._codex_rollout_session_id(_base=tmp_path / "no-such-dir" / "sessions")
        assert result == ""

    def test_concurrent_sessions_returns_empty_string(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        sessions_dir = tmp_path / "sessions" / "2026" / "06" / "14"
        sessions_dir.mkdir(parents=True)
        r1 = sessions_dir / "rollout-1749945000000-aaaaaaaa-0000-0000-0000-000000000001.jsonl"
        r2 = sessions_dir / "rollout-1749945000001-aaaaaaaa-0000-0000-0000-000000000002.jsonl"
        r1.write_text("", encoding="utf-8")
        r2.write_text("", encoding="utf-8")
        # Give both the same mtime so they appear concurrent.
        import os as _os
        import time as _time

        now = _time.time()
        _os.utime(r1, (now, now))
        _os.utime(r2, (now, now))
        result = srr._codex_rollout_session_id(_base=tmp_path / "sessions")
        assert result == ""

    def test_malformed_filename_no_uuid_returns_empty(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        bad = sessions_dir / "rollout-notauuid.jsonl"
        bad.write_text("", encoding="utf-8")
        result = srr._codex_rollout_session_id(_base=tmp_path / "sessions")
        assert result == ""

    def test_only_most_recent_file_chosen(self, tmp_path: pytest.TempPathFactory) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        old = sessions_dir / "rollout-100-aaaaaaaa-0000-0000-0000-000000000001.jsonl"
        new = sessions_dir / "rollout-200-bbbbbbbb-0000-0000-0000-000000000002.jsonl"
        old.write_text("", encoding="utf-8")
        new.write_text("", encoding="utf-8")
        import os as _os
        import time as _time

        _os.utime(old, (1.0, 1.0))
        _os.utime(new, (_time.time() + 10, _time.time() + 10))
        result = srr._codex_rollout_session_id(_base=tmp_path / "sessions")
        assert result == "bbbbbbbb-0000-0000-0000-000000000002"


class TestRenderSectionReasoning:
    def test_reasoning_shown_when_nonzero(self) -> None:
        usage: srr.Usage = {**_USAGE, "reasoning": 5000}  # type: ignore[misc]
        out = srr.render_section("0:01:00", usage)
        assert "reasoning 5,000" in out

    def test_reasoning_hidden_when_zero(self) -> None:
        usage: srr.Usage = {**_USAGE, "reasoning": 0}  # type: ignore[misc]
        out = srr.render_section("0:01:00", usage)
        assert "reasoning" not in out

    def test_reasoning_hidden_produces_same_format_as_before(self) -> None:
        # Claude Code path (reasoning=0) must produce byte-identical output to
        # the pre-Codex format; the breakdown must NOT contain "reasoning".
        out = srr.render_section("0:09:11", _USAGE)
        assert "reasoning" not in out
        assert "input 3,064" in out
        assert "output 57,757" in out


class TestGatherCodex:
    def test_codex_live_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setattr(srr, "_run_ccusage_codex", lambda: _codex_json())
        monkeypatch.setattr(srr, "_codex_rollout_session_id", lambda: "test-uuid-1")
        env = {"AGENT_CONTAINER": "codex", "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path)}
        out = srr.gather(env=env, now_ms=5000.0)
        # No checkpoint yet -> elapsed unavailable; tokens/cost from totals.
        assert f"{_ELAPSED_LABEL}: {srr._UNAVAILABLE}" in out
        assert "1,700" in out
        assert "$0.0250" in out
        assert f"Model(s): {srr._UNAVAILABLE}" in out

    def test_codex_reasoning_tokens_surfaced(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setattr(srr, "_run_ccusage_codex", lambda: _codex_json(reasoning=9999))
        monkeypatch.setattr(srr, "_codex_rollout_session_id", lambda: "test-uuid-r")
        env = {"AGENT_CONTAINER": "codex", "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path)}
        out = srr.gather(env=env, now_ms=5000.0)
        assert "reasoning 9,999" in out

    def test_codex_no_rollout_file_degrades_elapsed_and_checkpoint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setattr(srr, "_run_ccusage_codex", lambda: _codex_json())
        monkeypatch.setattr(srr, "_codex_rollout_session_id", lambda: "")
        env = {"AGENT_CONTAINER": "codex", "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path)}
        out = srr.gather(env=env, now_ms=5000.0)
        # Tokens still available from totals even without a rollout UUID.
        assert "1,700" in out
        assert f"{_ELAPSED_LABEL}: {srr._UNAVAILABLE}" in out

    def test_codex_no_ccusage_degrades_tokens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(srr, "_run_ccusage_codex", lambda: None)
        monkeypatch.setattr(srr, "_codex_rollout_session_id", lambda: "test-uuid-1")
        env = {"AGENT_CONTAINER": "codex"}
        out = srr.gather(env=env, now_ms=5000.0)
        assert out.count(srr._UNAVAILABLE) == 4

    def test_codex_second_pr_elapsed_from_checkpoint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setattr(srr, "_run_ccusage_codex", lambda: _codex_json())
        monkeypatch.setattr(srr, "_codex_rollout_session_id", lambda: "test-uuid-2")
        env = {"AGENT_CONTAINER": "codex", "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path)}

        # PR #1: gather then write checkpoint.
        srr.gather(env=env, now_ms=0.0)
        srr.write_checkpoint(env=env, now_ms=0.0)

        # PR #2: elapsed runs from the checkpoint (0 ms -> 90 s = 0:01:30).
        out2 = srr.gather(env=env, now_ms=90_000.0)
        assert f"{_ELAPSED_LABEL}: 0:01:30" in out2

    def test_codex_second_pr_delta_tokens(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        env = {"AGENT_CONTAINER": "codex", "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path)}
        monkeypatch.setattr(srr, "_codex_rollout_session_id", lambda: "test-uuid-3")

        # PR #1 cumulative: 1000 total.
        monkeypatch.setattr(srr, "_run_ccusage_codex", lambda: _codex_json(total=1000, inp=600, output=400, cache_read=0, cost=0.01))
        srr.gather(env=env, now_ms=0.0)
        srr.write_checkpoint(env=env, now_ms=0.0)

        # PR #2 cumulative: 1500 total -> delta 500.
        monkeypatch.setattr(srr, "_run_ccusage_codex", lambda: _codex_json(total=1500, inp=900, output=600, cache_read=0, cost=0.015))
        out2 = srr.gather(env=env, now_ms=1000.0)
        assert "500" in out2
        assert "1,500" not in out2

    def test_claude_code_path_unaffected_by_codex_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        # Ensure the Claude Code path is byte-identical: AGENT_CONTAINER absent.
        monkeypatch.setattr(
            srr, "_run_ccusage", lambda _sid: _grouped(_row("sess-cc"))
        )
        env = {
            "CCR_SPAWN_TIMESTAMP_MS": "1000",
            "CLAUDE_CODE_SESSION_ID": "sess-cc",
            "CCR_CCUSAGE_CHECKPOINT_DIR": str(tmp_path),
        }
        out = srr.gather(env=env, now_ms=1000.0 + 60_000)
        assert f"{_ELAPSED_LABEL}: 0:01:00" in out
        assert "2,558,807" in out
        assert "Model(s): Opus-class" in out
