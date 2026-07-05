"""Tests for ``scripts/preflight_all.py``.

Verifies the manifest contract consumed by
``scripts/scan_ssot_drift.py`` and the prereq / skip / failure
classification that ``run_step`` exposes. CLI smoke tests cover the
``--list`` machine-readable path and the human summary path.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``. Refs #493.
"""

from __future__ import annotations

import json
from pathlib import Path

import preflight_all as pa
import pytest

pytestmark = pytest.mark.shard_preflight
# ---------------------------------------------------------------------------
# STEPS manifest invariants
# ---------------------------------------------------------------------------


class TestStepsManifest:
    def test_names_are_unique(self) -> None:
        names = [s.name for s in pa.STEPS]
        assert len(names) == len(set(names)), f"duplicate step names: {names}"

    def test_argv_is_nonempty(self) -> None:
        for step in pa.STEPS:
            assert step.argv, f"step '{step.name}' has empty argv"

    def test_script_invocations_reference_existing_files(self) -> None:
        # Every ``python3 scripts/<name>.py`` step must resolve to a real
        # file on disk; this catches typos and stale steps.
        repo_root = Path(__file__).resolve().parent.parent
        for step in pa.STEPS:
            for token in step.argv:
                if token.startswith("scripts/") and token.endswith(".py"):
                    assert (repo_root / token).is_file(), (
                        f"step '{step.name}' references missing file {token}"
                    )

    def test_soft_flag_requires_prereq_declaration(self) -> None:
        # Soft steps must declare at least one prereq; otherwise
        # ``soft=True`` would silently swallow a real failure.
        for step in pa.STEPS:
            if step.soft:
                assert step.required_env or step.required_bin, (
                    f"soft step '{step.name}' has no prereqs"
                )


# ---------------------------------------------------------------------------
# missing_prereqs
# ---------------------------------------------------------------------------


class TestMissingPrereqs:
    def test_no_prereqs_returns_empty(self) -> None:
        step = pa.Step(name="x", argv=("true",))
        assert pa.missing_prereqs(step, environ={}) == []

    def test_missing_env(self) -> None:
        step = pa.Step(name="x", argv=("true",), required_env=("FOO",))
        assert pa.missing_prereqs(step, environ={}) == ["env:FOO"]

    def test_present_env(self) -> None:
        step = pa.Step(name="x", argv=("true",), required_env=("FOO",))
        assert pa.missing_prereqs(step, environ={"FOO": "v"}) == []

    def test_empty_env_value_is_missing(self) -> None:
        # An empty string is treated as unset so that
        # ``GH_TOKEN_API=`` in the shell does not let the ruleset gate
        # pretend to be configured.
        step = pa.Step(name="x", argv=("true",), required_env=("FOO",))
        assert pa.missing_prereqs(step, environ={"FOO": ""}) == ["env:FOO"]

    def test_missing_bin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pa.shutil, "which", lambda _name: None)
        step = pa.Step(name="x", argv=("zzz",), required_bin=("zzz",))
        assert pa.missing_prereqs(step, environ={}) == ["bin:zzz"]

    def test_present_bin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pa.shutil, "which", lambda _name: "/usr/bin/zzz")
        step = pa.Step(name="x", argv=("zzz",), required_bin=("zzz",))
        assert pa.missing_prereqs(step, environ={}) == []

    def test_order_is_env_then_bin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pa.shutil, "which", lambda _name: None)
        step = pa.Step(
            name="x",
            argv=("zzz",),
            required_env=("FOO",),
            required_bin=("zzz",),
        )
        assert pa.missing_prereqs(step, environ={}) == ["env:FOO", "bin:zzz"]


# ---------------------------------------------------------------------------
# run_step
# ---------------------------------------------------------------------------


class TestRunStep:
    def test_pass(self, tmp_path: Path) -> None:
        step = pa.Step(name="ok", argv=("true",))
        result = pa.run_step(step, cwd=tmp_path, environ={})
        assert result.name == "ok"
        assert result.status == "pass"
        assert result.detail == ""
        assert result.duration_s >= 0.0

    def test_fail_returns_exit_code_detail(self, tmp_path: Path) -> None:
        step = pa.Step(name="ng", argv=("false",))
        result = pa.run_step(step, cwd=tmp_path, environ={})
        assert result.name == "ng"
        assert result.status == "fail"
        assert "exit=" in result.detail

    def test_soft_skip_on_missing_env(self, tmp_path: Path) -> None:
        step = pa.Step(
            name="needs_token",
            argv=("false",),  # would fail if executed
            required_env=("MISSING",),
            soft=True,
        )
        result = pa.run_step(step, cwd=tmp_path, environ={})
        assert result.status == "skip"
        assert "env:MISSING" in result.detail

    def test_hard_fail_on_missing_env(self, tmp_path: Path) -> None:
        # A non-soft step with a missing prereq is reported as fail so the
        # gap is not silently swallowed.
        step = pa.Step(
            name="needs_token_hard",
            argv=("true",),
            required_env=("MISSING",),
            soft=False,
        )
        result = pa.run_step(step, cwd=tmp_path, environ={})
        assert result.status == "fail"
        assert "env:MISSING" in result.detail


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class TestMainCli:
    def test_list_emits_json_manifest(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = pa.main(["--list"])
        assert exit_code == 0
        captured = capsys.readouterr()
        manifest = json.loads(captured.out)
        assert isinstance(manifest, list)
        assert manifest, "manifest must not be empty"
        names = {entry["name"] for entry in manifest}
        # Spot-check a few well-known gates rather than the full set so
        # the test does not have to track every future addition.
        assert {
            "scan_apm_portability",
            "verify_apm_checksums",
            "uv_pin_drift",
            "nixpkgs_cooldown",
        } <= names
        for entry in manifest:
            assert set(entry.keys()) == {
                "name",
                "argv",
                "required_env",
                "required_bin",
                "soft",
                "heavy",
            }

    def test_main_returns_one_when_step_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_step = pa.Step(name="will_fail", argv=("false",))
        monkeypatch.setattr(pa, "STEPS", (fake_step,))
        exit_code = pa.main([])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "fail" in captured.out
        assert "will_fail" in captured.err  # ::error:: annotation

    def test_main_returns_zero_when_all_pass(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_step = pa.Step(name="will_pass", argv=("true",))
        monkeypatch.setattr(pa, "STEPS", (fake_step,))
        exit_code = pa.main([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "pass" in captured.out

    def test_main_treats_soft_skip_as_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_step = pa.Step(
            name="needs_secret",
            argv=("false",),
            required_env=("MISSING",),
            soft=True,
        )
        monkeypatch.setattr(pa, "STEPS", (fake_step,))
        exit_code = pa.main([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "skip" in captured.out
        assert "needs_secret" in captured.err  # ::warning:: annotation


# ---------------------------------------------------------------------------
# run_all; fail-fast cheap tier + heavy-tier skip cache (refs #985)
# ---------------------------------------------------------------------------


class TestRunAll:
    @pytest.fixture(autouse=True)
    def _no_cache_io(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Default: cache miss + cheap fingerprint + no-op record/path so the
        # heavy tier always executes unless a test opts into a fresh cache.
        monkeypatch.setattr(pa.preflight_cache, "cache_path", lambda *a, **k: tmp_path / "c.json")
        monkeypatch.setattr(pa.preflight_cache, "compute_fingerprint", lambda *a, **k: "fp")
        monkeypatch.setattr(pa.preflight_cache, "load", lambda *_a, **_k: None)
        self.recorded: list[str] = []
        monkeypatch.setattr(
            pa.preflight_cache,
            "record",
            lambda _p, fp: self.recorded.append(fp),
        )

    def test_cheap_failure_short_circuits_heavy(self) -> None:
        cheap_fail = pa.Step(name="cheap", argv=("false",))
        # ``true`` would pass if executed; the skip proves it never ran.
        heavy = pa.Step(name="heavy", argv=("true",), heavy=True)
        results = pa.run_all((cheap_fail, heavy), pa.REPO_ROOT, {})
        by_name = {r.name: r for r in results}
        assert by_name["cheap"].status == "fail"
        assert by_name["heavy"].status == "skip"
        assert "upstream gate failed" in by_name["heavy"].detail
        assert self.recorded == []

    def test_all_cheap_pass_runs_and_records_heavy(self) -> None:
        cheap = pa.Step(name="cheap", argv=("true",))
        heavy = pa.Step(name="heavy", argv=("true",), heavy=True)
        results = pa.run_all((cheap, heavy), pa.REPO_ROOT, {})
        by_name = {r.name: r for r in results}
        assert by_name["heavy"].status == "pass"
        assert "cached" not in by_name["heavy"].detail
        assert self.recorded == ["fp"]  # fingerprint recorded after green run

    def test_fresh_cache_skips_heavy_execution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            pa.preflight_cache,
            "load",
            lambda *_a, **_k: {"fingerprint": "fp", "status": "pass", "recorded_at": "T"},
        )
        cheap = pa.Step(name="cheap", argv=("true",))
        # ``false`` would FAIL if executed; a pass proves the cache skipped it.
        heavy = pa.Step(name="heavy", argv=("false",), heavy=True)
        results = pa.run_all((cheap, heavy), pa.REPO_ROOT, {})
        by_name = {r.name: r for r in results}
        assert by_name["heavy"].status == "pass"
        assert "cached" in by_name["heavy"].detail
        assert self.recorded == []  # nothing executed, no re-record

    def test_disabled_cache_forces_run_even_when_fresh(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            pa.preflight_cache,
            "load",
            lambda *_a, **_k: {"fingerprint": "fp", "status": "pass", "recorded_at": "T"},
        )
        cheap = pa.Step(name="cheap", argv=("true",))
        heavy = pa.Step(name="heavy", argv=("false",), heavy=True)
        results = pa.run_all((cheap, heavy), pa.REPO_ROOT, {"PREFLIGHT_NO_CACHE": "1"})
        by_name = {r.name: r for r in results}
        # Forced run executes ``false`` -> fail, and a failed run is not recorded.
        assert by_name["heavy"].status == "fail"
        assert self.recorded == []

    def test_no_heavy_steps_returns_cheap_only(self) -> None:
        cheap = pa.Step(name="cheap", argv=("true",))
        results = pa.run_all((cheap,), pa.REPO_ROOT, {})
        assert [r.name for r in results] == ["cheap"]

    def test_heavy_soft_skip_not_recorded(self) -> None:
        cheap = pa.Step(name="cheap", argv=("true",))
        heavy = pa.Step(
            name="heavy",
            argv=("true",),
            required_bin=("definitely-not-on-path-zzz",),
            soft=True,
            heavy=True,
        )
        results = pa.run_all((cheap, heavy), pa.REPO_ROOT, {})
        by_name = {r.name: r for r in results}
        assert by_name["heavy"].status == "skip"
        assert self.recorded == []  # suite never ran -> must not cache a pass

    def test_fingerprint_none_runs_but_does_not_record(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # git/filesystem error -> fingerprint None -> run the suite, never cache.
        def boom(*_a: object, **_k: object) -> str:
            raise OSError("boom")

        monkeypatch.setattr(pa.preflight_cache, "compute_fingerprint", boom)
        cheap = pa.Step(name="cheap", argv=("true",))
        heavy = pa.Step(name="heavy", argv=("true",), heavy=True)
        results = pa.run_all((cheap, heavy), pa.REPO_ROOT, {})
        by_name = {r.name: r for r in results}
        assert by_name["heavy"].status == "pass"
        assert self.recorded == []


# ---------------------------------------------------------------------------
# Cheap-tier parallelization (refs #1245)
# ---------------------------------------------------------------------------


class TestCheapWorkers:
    def test_override_clamped_to_n(self) -> None:
        assert pa._cheap_workers(3, {"PREFLIGHT_CHEAP_WORKERS": "10"}) == 3

    def test_override_one_forces_serial(self) -> None:
        assert pa._cheap_workers(5, {"PREFLIGHT_CHEAP_WORKERS": "1"}) == 1

    def test_invalid_override_falls_back_to_scaled(self) -> None:
        # A non-int override is ignored; the scaled default still clamps to n.
        assert pa._cheap_workers(2, {"PREFLIGHT_CHEAP_WORKERS": "abc"}) == 2

    def test_default_is_positive(self) -> None:
        assert pa._cheap_workers(4, {}) >= 1


class TestRunCheap:
    def test_results_in_declaration_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Real thread pool (no WORKERS override): every step returns, in order.
        monkeypatch.setattr(
            pa, "run_step", lambda step, _c, _e: pa.StepResult(name=step.name, status="pass")
        )
        steps = [pa.Step(name=f"s{i}", argv=("true",)) for i in range(8)]
        results = pa._run_cheap(steps, pa.REPO_ROOT, {})
        assert [r.name for r in results] == [f"s{i}" for i in range(8)]
        assert all(r.status == "pass" for r in results)

    def test_serial_steps_run_first_in_declaration_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def recording(step: pa.Step, _c: Path, _e: dict[str, str]) -> pa.StepResult:
            calls.append(step.name)
            return pa.StepResult(name=step.name, status="pass")

        monkeypatch.setattr(pa, "run_step", recording)
        # Interleave the working-tree-mutating serial step among parallel ones.
        names = [
            "a",
            "b",
            "preflight_branch_base",
            "c",
            "d",
            "e",
        ]
        steps = [pa.Step(name=n, argv=("true",)) for n in names]
        # Force the parallel tier serial so the call order is deterministic.
        pa._run_cheap(steps, pa.REPO_ROOT, {"PREFLIGHT_CHEAP_WORKERS": "1"})
        # The serial step runs first, ahead of the parallel ones.
        assert calls[:1] == ["preflight_branch_base"]
        # The parallel steps follow, in declaration order under WORKERS=1.
        assert calls[1:] == ["a", "b", "c", "d", "e"]

    def test_workers_one_preserves_serial_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def recording(step: pa.Step, _c: Path, _e: dict[str, str]) -> pa.StepResult:
            calls.append(step.name)
            return pa.StepResult(name=step.name, status="pass")

        monkeypatch.setattr(pa, "run_step", recording)
        steps = [pa.Step(name=f"p{i}", argv=("true",)) for i in range(5)]
        pa._run_cheap(steps, pa.REPO_ROOT, {"PREFLIGHT_CHEAP_WORKERS": "1"})
        assert calls == [f"p{i}" for i in range(5)]

    def test_parallel_failure_surfaces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(step: pa.Step, _c: Path, _e: dict[str, str]) -> pa.StepResult:
            status = "fail" if step.name == "p2" else "pass"
            return pa.StepResult(name=step.name, status=status)

        monkeypatch.setattr(pa, "run_step", fake)
        steps = [pa.Step(name=f"p{i}", argv=("true",)) for i in range(5)]
        results = pa._run_cheap(steps, pa.REPO_ROOT, {})
        by_name = {r.name: r for r in results}
        assert by_name["p2"].status == "fail"
        assert [r.name for r in results] == [f"p{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# step skipping; the narrowed PREFLIGHT_SKIP replacement (refs #2133)
# ---------------------------------------------------------------------------
class TestResolveSkips:
    def test_cli_and_env_combine(self) -> None:
        names = pa.resolve_skips(["prek"], {"PREFLIGHT_SKIP_STEPS": "ruff, mypy"})
        assert names == {"prek", "ruff", "mypy"}

    def test_empty_sources_yield_empty(self) -> None:
        assert pa.resolve_skips(None, {}) == set()
        assert pa.resolve_skips([], {"PREFLIGHT_SKIP_STEPS": " , "}) == set()


class TestPartitionSkips:
    def _steps(self) -> tuple[pa.Step, ...]:
        return (
            pa.Step(name="cheap", argv=("true",)),
            pa.Step(name="prek", argv=("true",)),
        )

    def test_named_step_is_partitioned_out_and_reported(self) -> None:
        to_run, skipped, unknown = pa.partition_skips(self._steps(), {"prek"})
        assert [s.name for s in to_run] == ["cheap"]
        assert [r.name for r in skipped] == ["prek"]
        assert skipped[0].status == "skip"
        assert "PREFLIGHT_SKIP_STEPS" in skipped[0].detail
        assert unknown == []

    def test_unknown_name_skips_nothing(self) -> None:
        to_run, skipped, unknown = pa.partition_skips(self._steps(), {"typo"})
        assert [s.name for s in to_run] == ["cheap", "prek"]
        assert skipped == []
        assert unknown == ["typo"]


class TestMainSkip:
    def test_skip_prek_still_runs_other_steps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ran: list[str] = []

        def fake_run_all(
            steps: tuple[pa.Step, ...], _cwd: Path, _env: dict[str, str]
        ) -> list[pa.StepResult]:
            ran.extend(s.name for s in steps)
            return [pa.StepResult(name=s.name, status="pass") for s in steps]

        steps = (
            pa.Step(name="scan_repo_double_hyphen", argv=("true",)),
            pa.Step(name="preflight_coverage", argv=("true",), heavy=True),
            pa.Step(name="prek", argv=("true",)),
        )
        monkeypatch.setattr(pa, "STEPS", steps)
        monkeypatch.setattr(pa, "run_all", fake_run_all)
        monkeypatch.setattr(pa.os, "environ", {"PREFLIGHT_SKIP_STEPS": "prek"})

        rc = pa.main([])
        assert rc == 0
        # prek dropped; the cheap dash gate and coverage still ran.
        assert "prek" not in ran
        assert "scan_repo_double_hyphen" in ran
        assert "preflight_coverage" in ran
