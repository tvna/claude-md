"""Tests for ``scripts/preflight_all.py``.

Verifies the manifest contract consumed by
``scripts/scan_preflight_drift.py`` and the prereq / skip / failure
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
        # Soft steps must declare at least one prereq -- otherwise
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
        assert result == pa.StepResult(name="ok", status="pass")

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
            assert set(entry.keys()) == {"name", "argv", "required_env", "required_bin", "soft"}

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
