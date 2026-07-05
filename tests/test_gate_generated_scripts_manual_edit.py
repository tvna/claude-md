"""Tests for scripts/gate_generated_scripts_manual_edit.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import gate_generated_scripts_manual_edit as gate
import pytest

pytestmark = pytest.mark.shard_preflight


def _fake_runner(stdout: str):
    def runner(_cmd, **_kwargs):
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    return runner


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _cwd_runner(repo: Path):
    """A real ``subprocess.run`` runner pinned to *repo* for live-git tests."""

    def runner(cmd, **_kwargs):
        return subprocess.run(
            cmd, cwd=repo, capture_output=True, text=True, check=True
        )

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


def test_changed_generated_docs_filters_prefixes() -> None:
    stdout = (
        "docs/generated/scripts/ast/auto_retro.md\n"
        "docs/generated/workflows/post-merge-if-branches.md\n"
        "scripts/auto_retro.py\n"
        "docs/generated/scripts/auto-retro-triage-report.md\n"
    )
    changed = gate.changed_generated_docs(
        "origin/main", runner=_fake_runner(stdout)
    )
    # Both docs/generated/scripts/ and docs/generated/workflows/ are protected
    # (refs #1545); only the non-generated source file is excluded.
    assert changed == frozenset(
        {
            "docs/generated/scripts/ast/auto_retro.md",
            "docs/generated/workflows/post-merge-if-branches.md",
            "docs/generated/scripts/auto-retro-triage-report.md",
        }
    )


def test_changed_generated_docs_protects_module_size_snapshot() -> None:
    # Refs #2013: the module-size snapshot joined the single-producer model, so
    # a non-bot branch hand-editing it (or stale-conflict-resolving it) must be
    # surfaced by the same inverse gate that protects docs/generated/.
    stdout = (
        ".gitapex/module-size-distribution.toml\n"
        ".gitapex/some-other-file.toml\n"
        "scripts/auto_retro.py\n"
    )
    changed = gate.changed_generated_docs(
        "origin/main", runner=_fake_runner(stdout)
    )
    # Only the snapshot is protected; sibling .gitapex/ files and source
    # files are not (exact-path match, not a .gitapex/ prefix).
    assert changed == frozenset({".gitapex/module-size-distribution.toml"})


def test_evaluate_fails_for_nonbot_snapshot_edit() -> None:
    code, errors = gate.evaluate(
        frozenset({".gitapex/module-size-distribution.toml"}), "feature/x"
    )
    assert code == 1
    assert len(errors) == 1
    assert "must not be edited by hand" in errors[0]
    assert ".gitapex/module-size-distribution.toml" in errors[0]


def test_evaluate_passes_snapshot_edit_for_exempt_branch() -> None:
    # The post-merge decision-tree job folds the snapshot into the same
    # chore/update-generated-docs PR, so that bot branch stays exempt for it.
    code, errors = gate.evaluate(
        frozenset({".gitapex/module-size-distribution.toml"}),
        "chore/update-generated-docs",
    )
    assert code == 0
    assert errors == []


def test_is_exempt() -> None:
    assert gate.is_exempt("chore/update-generated-docs") is True
    # Regression guard for #1553: the triage-report job writes
    # docs/generated/scripts/auto-retro-triage-report.md on this fixed branch
    # via createCommitOnBranch, so it must be exempt like the decision-tree
    # branch. Its omission failed PR #1552 on this gate after the title (#1551)
    # and body-shape (#1554) blockers were cleared.
    assert gate.is_exempt("chore/refresh-auto-retro-triage-report") is True
    assert gate.is_exempt("feature/x") is False
    assert gate.is_exempt("") is False


def test_triage_report_branch_is_exempt_and_aligned() -> None:
    # The exempt branch literal must match auto_retro's source-of-truth
    # constant so a rename of the triage-report branch cannot silently drop
    # the exemption.
    import auto_retro

    assert auto_retro._TRIAGE_REPORT_PR_BRANCH in gate.EXEMPT_BRANCHES


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
    monkeypatch.setattr(gate, "changed_generated_docs", lambda *_a, **_kw: frozenset())
    monkeypatch.setattr(gate, "resolve_branch", lambda *_a, **_kw: "feature/x")
    assert gate.main(["verify", "--base-ref", "origin/main"]) == 0


def test_verify_cli_fails_on_manual_edit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        gate,
        "changed_generated_docs",
        lambda *_a, **_kw: frozenset({"docs/generated/scripts/ast/x.md"}),
    )
    monkeypatch.setattr(gate, "resolve_branch", lambda *_a, **_kw: "feature/x")
    assert gate.main(["verify", "--base-ref", "origin/main"]) == 1
    assert "must not be edited by hand" in capsys.readouterr().err


def test_verify_cli_passes_for_exempt_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gate,
        "changed_generated_docs",
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

    monkeypatch.setattr(gate, "changed_generated_docs", boom)
    assert gate.main(["verify", "--base-ref", "origin/main"]) == 1
    assert "git invocation failed" in capsys.readouterr().err


def _seed_advancing_main_repo(repo: Path) -> None:
    """Build the retro #1703 repair-4 scenario in a real git repo.

    base commit (gen file present) -> branch `feature` makes a NON-generated
    change -> `main` then advances with a commit that rewrites the generated
    file. The branch never touched docs/generated/, but main did after the
    branch was cut.
    """
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    # The dev environment enforces commit signing globally; a throwaway repo
    # has no signing key, so disable it locally to keep the fixture hermetic.
    _git(repo, "config", "commit.gpgsign", "false")
    gen = repo / "docs" / "generated" / "scripts" / "x.md"
    gen.parent.mkdir(parents=True)
    gen.write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    _git(repo, "switch", "-q", "-c", "feature")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "src.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "branch: edit source only")

    _git(repo, "switch", "-q", "main")
    gen.write_text("v2 regenerated post-merge\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main: post-merge regen of docs/generated")


def test_advancing_main_does_not_falsely_flag_branch(tmp_path: Path) -> None:
    # Regression for retro #1703 repair 4: with main advanced past the branch,
    # the two-dot diff (main..feature) reports the base-only generated churn as
    # a branch edit (the false positive). The three-dot diff (main...feature),
    # anchored at the merge-base, reports nothing because the branch never
    # touched docs/generated/. This asserts the three-dot behavior, so it goes
    # red against the old two-dot code and green after the fix.
    _seed_advancing_main_repo(tmp_path)
    runner = _cwd_runner(tmp_path)

    changed = gate.changed_generated_docs("main", head="feature", runner=runner)
    assert changed == frozenset()

    # Two-dot would have flagged it: prove the scenario is real, not a no-op.
    two_dot = subprocess.run(
        ["git", "diff", "--name-only", "main..feature"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "docs/generated/scripts/x.md" in two_dot


def test_real_branch_edit_still_flagged_under_three_dot(tmp_path: Path) -> None:
    # The three-dot fix must not blind the gate: a genuine hand-edit to a
    # protected file on the branch still surfaces.
    _seed_advancing_main_repo(tmp_path)
    _git(tmp_path, "switch", "-q", "feature")
    (tmp_path / "docs" / "generated" / "scripts" / "x.md").write_text(
        "hand edited on branch\n", encoding="utf-8"
    )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "branch: hand-edit generated file")

    changed = gate.changed_generated_docs(
        "main", head="feature", runner=_cwd_runner(tmp_path)
    )
    assert "docs/generated/scripts/x.md" in changed
