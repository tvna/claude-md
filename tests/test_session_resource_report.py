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
}


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
        assert "claude-opus-4-8" in out

    def test_usage_none_renders_unavailable(self) -> None:
        out = srr.render_section("0:09:11", None)
        # Elapsed still shown; the token/cost/model lines degrade.
        assert "Elapsed (session start to PR create): 0:09:11" in out
        assert out.count(srr._UNAVAILABLE) == 3

    def test_elapsed_none_renders_unavailable(self) -> None:
        out = srr.render_section(None, _USAGE)
        assert f"Elapsed (session start to PR create): {srr._UNAVAILABLE}" in out
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
        }
        out = srr.render_section("0:00:01", usage)
        assert f"Model(s): {srr._UNAVAILABLE}" in out

    def test_output_is_ascii(self) -> None:
        assert srr.render_section("0:09:11", _USAGE).isascii()
        assert srr.render_section(None, None).isascii()


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
    def test_live_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            srr, "_run_ccusage", lambda _sid: _grouped(_row("sess-1"))
        )
        env = {
            "CCR_SPAWN_TIMESTAMP_MS": "1000",
            "CLAUDE_CODE_SESSION_ID": "sess-1",
        }
        out = srr.gather(env=env, now_ms=1000.0 + 90_000)
        assert "Elapsed (session start to PR create): 0:01:30" in out
        assert "2,558,807" in out
        assert "$3.7231" in out

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
        assert "Elapsed (session start to PR create): 0:00:01" in out
        assert out.count(srr._UNAVAILABLE) == 3

    def test_ccusage_absent_degrades(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(srr, "_run_ccusage", lambda _sid: None)
        env = {"CLAUDE_CODE_SESSION_ID": "sess-1"}
        out = srr.gather(env=env, now_ms=5_000.0)
        # No spawn ts and no ccusage -> the full unavailable form.
        assert out.count(srr._UNAVAILABLE) == 4


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
