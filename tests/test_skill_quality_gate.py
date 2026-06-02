"""Tests for ``scripts/skill_quality_gate.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import skill_quality_gate

pytestmark = pytest.mark.shard_ci_ops


def _skill_entry(
    path: str,
    *,
    spec: list[dict] | None = None,
    token_count: int = 100,
    token_limit: int = 500,
    exceeded: bool = False,
) -> dict:
    """Build a minimal waza-check skill entry for tests."""
    return {
        "path": path,
        "specCompliance": spec
        if spec is not None
        else [{"name": "spec-name", "passed": True, "summary": "ok"}],
        "tokenBudget": {
            "count": token_count,
            "limit": token_limit,
            "exceeded": exceeded,
        },
    }


# ---------------------------------------------------------------------------
# find_waza
# ---------------------------------------------------------------------------


class TestFindWaza:
    def test_returns_path_from_which(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(skill_quality_gate.shutil, "which", lambda _: "/usr/bin/waza")
        assert skill_quality_gate.find_waza() == "/usr/bin/waza"

    def test_falls_back_to_go_bin_hint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(skill_quality_gate.shutil, "which", lambda _: None)
        binary = tmp_path / "waza"
        binary.write_text("#!/bin/sh\n")
        monkeypatch.setattr(skill_quality_gate, "_GO_BIN_HINTS", (tmp_path,))
        assert skill_quality_gate.find_waza() == str(binary)

    def test_returns_none_when_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(skill_quality_gate.shutil, "which", lambda _: None)
        monkeypatch.setattr(skill_quality_gate, "_GO_BIN_HINTS", (tmp_path,))
        assert skill_quality_gate.find_waza() is None


# ---------------------------------------------------------------------------
# discover_skills / _normalize_target
# ---------------------------------------------------------------------------


class TestDiscoverSkills:
    def test_finds_skill_dirs(self, tmp_path: Path) -> None:
        for name in ("alpha", "beta"):
            d = tmp_path / ".agents" / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text("x")
        found = skill_quality_gate.discover_skills(tmp_path)
        assert [p.name for p in found] == ["alpha", "beta"]

    def test_empty_when_no_skills(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "skills").mkdir(parents=True)
        assert skill_quality_gate.discover_skills(tmp_path) == []


class TestNormalizeTarget:
    def test_accepts_skill_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "myskill"
        d.mkdir()
        (d / "SKILL.md").write_text("x")
        assert skill_quality_gate._normalize_target(tmp_path, "myskill") == d

    def test_accepts_skill_md_file(self, tmp_path: Path) -> None:
        d = tmp_path / "myskill"
        d.mkdir()
        (d / "SKILL.md").write_text("x")
        assert skill_quality_gate._normalize_target(tmp_path, "myskill/SKILL.md") == d

    def test_accepts_absolute_path(self, tmp_path: Path) -> None:
        d = tmp_path / "myskill"
        d.mkdir()
        (d / "SKILL.md").write_text("x")
        assert skill_quality_gate._normalize_target(tmp_path, str(d)) == d

    def test_returns_none_when_no_skill_md(self, tmp_path: Path) -> None:
        (tmp_path / "notaskill").mkdir()
        assert skill_quality_gate._normalize_target(tmp_path, "notaskill") is None


# ---------------------------------------------------------------------------
# evaluate_skill
# ---------------------------------------------------------------------------


class TestEvaluateSkill:
    def test_clean_skill(self) -> None:
        spec, tokens = skill_quality_gate.evaluate_skill(_skill_entry("s/SKILL.md"))
        assert spec == []
        assert tokens == []

    def test_spec_failure_collected(self) -> None:
        entry = _skill_entry(
            "s/SKILL.md",
            spec=[{"name": "spec-name", "passed": False, "summary": "bad name"}],
        )
        spec, _ = skill_quality_gate.evaluate_skill(entry)
        assert spec == ["spec-name: bad name"]

    def test_warning_status_is_not_a_failure(self) -> None:
        # status: warning entries keep passed: true and must not gate.
        entry = _skill_entry(
            "s/SKILL.md",
            spec=[{"name": "spec-license", "passed": True, "status": "warning"}],
        )
        spec, _ = skill_quality_gate.evaluate_skill(entry)
        assert spec == []

    def test_token_exceedance_is_warning(self) -> None:
        entry = _skill_entry("s/SKILL.md", token_count=900, exceeded=True)
        spec, tokens = skill_quality_gate.evaluate_skill(entry)
        assert spec == []
        assert tokens == ["900 tokens (hard limit 500)"]


# ---------------------------------------------------------------------------
# run_waza_check
# ---------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TestRunWazaCheck:
    def test_parses_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {"skills": [_skill_entry("s/SKILL.md")]}
        monkeypatch.setattr(
            skill_quality_gate.subprocess,
            "run",
            lambda *a, **k: _FakeProc(stdout=json.dumps(payload)),
        )
        result = skill_quality_gate.run_waza_check("waza", Path("s"))
        assert result == payload

    def test_empty_output_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            skill_quality_gate.subprocess,
            "run",
            lambda *a, **k: _FakeProc(stdout="   ", stderr="boom", returncode=2),
        )
        with pytest.raises(RuntimeError, match="no JSON"):
            skill_quality_gate.run_waza_check("waza", Path("s"))

    def test_bad_json_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            skill_quality_gate.subprocess,
            "run",
            lambda *a, **k: _FakeProc(stdout="{not json"),
        )
        with pytest.raises(RuntimeError, match="could not parse"):
            skill_quality_gate.run_waza_check("waza", Path("s"))


# ---------------------------------------------------------------------------
# _cmd_verify (integration via mocked waza)
# ---------------------------------------------------------------------------


def _make_args(repo_root: Path, skills: list[str]) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo_root), skills=skills)


class TestCmdVerify:
    def test_waza_missing_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(skill_quality_gate, "find_waza", lambda: None)
        rc = skill_quality_gate._cmd_verify(_make_args(tmp_path, []))
        assert rc == 1

    def test_no_targets_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(skill_quality_gate, "find_waza", lambda: "waza")
        (tmp_path / ".agents" / "skills").mkdir(parents=True)
        rc = skill_quality_gate._cmd_verify(_make_args(tmp_path, []))
        assert rc == 0

    def test_all_skills_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        d = tmp_path / ".agents" / "skills" / "alpha"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("x")
        monkeypatch.setattr(skill_quality_gate, "find_waza", lambda: "waza")
        monkeypatch.setattr(
            skill_quality_gate,
            "run_waza_check",
            lambda _w, sd: {
                "skills": [_skill_entry(str(sd / "SKILL.md"), exceeded=True, token_count=900)]
            },
        )
        rc = skill_quality_gate._cmd_verify(_make_args(tmp_path, []))
        assert rc == 0
        err = capsys.readouterr().err
        assert "::warning" in err  # token warning surfaced

    def test_spec_failure_blocks(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        d = tmp_path / ".agents" / "skills" / "bad"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("x")
        monkeypatch.setattr(skill_quality_gate, "find_waza", lambda: "waza")
        monkeypatch.setattr(
            skill_quality_gate,
            "run_waza_check",
            lambda _w, sd: {
                "skills": [
                    _skill_entry(
                        str(sd / "SKILL.md"),
                        spec=[{"name": "spec-name", "passed": False, "summary": "bad"}],
                    )
                ]
            },
        )
        rc = skill_quality_gate._cmd_verify(_make_args(tmp_path, []))
        assert rc == 1
        assert "::error" in capsys.readouterr().err

    def test_explicit_skill_and_skip_invalid(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        d = tmp_path / "alpha"
        d.mkdir()
        (d / "SKILL.md").write_text("x")
        monkeypatch.setattr(skill_quality_gate, "find_waza", lambda: "waza")
        monkeypatch.setattr(
            skill_quality_gate,
            "run_waza_check",
            lambda _w, sd: {"skills": [_skill_entry(str(sd / "SKILL.md"))]},
        )
        rc = skill_quality_gate._cmd_verify(
            _make_args(tmp_path, ["alpha", "does-not-exist"])
        )
        assert rc == 0
        assert "skipping" in capsys.readouterr().err

    def test_path_outside_repo_root_kept_absolute(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        # Entry path not under repo_root exercises the relative_to suppression.
        d = tmp_path / "alpha"
        d.mkdir()
        (d / "SKILL.md").write_text("x")
        monkeypatch.setattr(skill_quality_gate, "find_waza", lambda: "waza")
        monkeypatch.setattr(
            skill_quality_gate,
            "run_waza_check",
            lambda _w, sd: {"skills": [_skill_entry("/elsewhere/SKILL.md")]},
        )
        rc = skill_quality_gate._cmd_verify(_make_args(tmp_path, ["alpha"]))
        assert rc == 0
        assert "/elsewhere/SKILL.md" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_dispatches_verify(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(skill_quality_gate, "_cmd_verify", lambda _a: 0)
        assert skill_quality_gate.main(["verify"]) == 0

    def test_main_requires_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            skill_quality_gate.main([])
