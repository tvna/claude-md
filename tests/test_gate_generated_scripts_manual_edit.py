"""Tests for scripts/gate_generated_scripts_manual_edit.py."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import gate_generated_scripts_manual_edit as gate
import pytest

pytestmark = pytest.mark.shard_preflight


def _fake_runner(stdout: str):
    def runner(_cmd, **_kwargs):
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    return runner


def test_resolve_base_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_REF", "origin/feature")
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    assert gate.resolve_base() == "origin/feature"


def test_resolve_base_uses_github_base_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BASE_REF", raising=False)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    assert gate.resolve_base() == "origin/main"


def test_resolve_base_falls_back_to_origin_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BASE_REF", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    assert gate.resolve_base() == "origin/main"


def test_resolve_branch_prefers_explicit() -> None:
    assert gate.resolve_branch("feature/x") == "feature/x"


def test_resolve_branch_uses_github_head_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_HEAD_REF", "chore/update-generated-docs")
    assert gate.resolve_branch(None) == "chore/update-generated-docs"


def test_changed_generated_scripts_filters_prefix() -> None:
    stdout = (
        "docs/generated/scripts/ast/auto_retro.md\n"
        "docs/generated/workflows/post-merge-if-branches.md\n"
        "scripts/auto_retro.py\n"
        "docs/generated/scripts/auto-retro-triage-report.md\n"
    )
    changed = gate.changed_generated_scripts(
        "origin/main", runner=_fake_runner(stdout)
    )
    assert changed == frozenset(
        {
            "docs/generated/scripts/ast/auto_retro.md",
            "docs/generated/scripts/auto-retro-triage-report.md",
        }
    )


def test_is_exempt() -> None:
    assert gate.is_exempt("chore/update-generated-docs") is True
    assert gate.is_exempt("feature/x") is False
    assert gate.is_exempt("") is False


def test_evaluate_passes_when_no_changes() -> None:
    code, errors = gate.evaluate(frozenset(), "feature/x")
    assert code == 0
    assert errors == []


def test_evaluate_passes_for_exempt_branch() -> None:
    code, errors = gate.evaluate(
        frozenset({"docs/generated/scripts/ast/x.md"}),
        "chore/update-generated-docs",
    )
    assert code == 0
    assert errors == []


def test_evaluate_fails_for_nonbot_edit() -> None:
    code, errors = gate.evaluate(
        frozenset({"docs/generated/scripts/ast/x.md"}), "feature/x"
    )
    assert code == 1
    assert len(errors) == 1
    assert "must not be edited by hand" in errors[0]
    assert "docs/generated/scripts/ast/x.md" in errors[0]


def test_verify_cli_passes_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "changed_generated_scripts", lambda *_a, **_kw: frozenset())
    monkeypatch.setattr(gate, "resolve_branch", lambda *_a, **_kw: "feature/x")
    assert gate.main(["verify", "--base-ref", "origin/main"]) == 0


def test_verify_cli_fails_on_manual_edit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        gate,
        "changed_generated_scripts",
        lambda *_a, **_kw: frozenset({"docs/generated/scripts/ast/x.md"}),
    )
    monkeypatch.setattr(gate, "resolve_branch", lambda *_a, **_kw: "feature/x")
    assert gate.main(["verify", "--base-ref", "origin/main"]) == 1
    assert "must not be edited by hand" in capsys.readouterr().err


def test_verify_cli_passes_for_exempt_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gate,
        "changed_generated_scripts",
        lambda *_a, **_kw: frozenset({"docs/generated/scripts/ast/x.md"}),
    )
    monkeypatch.setattr(
        gate, "resolve_branch", lambda *_a, **_kw: "chore/update-generated-docs"
    )
    assert gate.main(["verify", "--base-ref", "origin/main"]) == 0


def test_verify_cli_fails_loud_on_git_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_a, **_kw):
        raise subprocess.CalledProcessError(1, ["git", "diff"])

    monkeypatch.setattr(gate, "changed_generated_scripts", boom)
    assert gate.main(["verify", "--base-ref", "origin/main"]) == 1
    assert "git invocation failed" in capsys.readouterr().err
