"""Tests for ``scripts/scan_hook_predicate_surface_drift.py``.

Refs #2133 (PR #2120 retrospective #2121, P1). Verifies that the gate flags a
git hook whose ``if:`` predicate is narrower than the script's declared command
surface (the silent-inert-matcher class PR #2120 hit), requires a declaration on
narrow-predicate hooks, and passes when every predicate admits its surface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import scan_hook_predicate_surface_drift as g

pytestmark = pytest.mark.shard_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]


def _hook(script: str, inner: str) -> g.GitHook:
    predicate = f"Bash({inner})"
    return g.GitHook(
        script=script,
        command=f'cd "$x" && python3 scripts/{script}.py',
        predicate=predicate,
        inner=inner,
    )


def _settings(handlers: list[dict[str, Any]]) -> dict[str, Any]:
    return {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": handlers}]}}


# ---------------------------------------------------------------------------
# predicate parsing
# ---------------------------------------------------------------------------
def test_predicate_inner_extracts_glob() -> None:
    assert g._predicate_inner("Bash(*git commit*)") == "*git commit*"
    assert g._predicate_inner("  Bash(*git *)  ") == "*git *"


def test_predicate_inner_rejects_non_bash() -> None:
    assert g._predicate_inner("Read(*)") is None  # only Bash(...) predicates parse
    assert g._predicate_inner("not a predicate") is None


def test_is_git_predicate() -> None:
    assert g._is_git_predicate("*git commit*")
    assert not g._is_git_predicate("*npm run*")


# ---------------------------------------------------------------------------
# admission semantics
# ---------------------------------------------------------------------------
def test_broad_predicate_admits_every_subcommand() -> None:
    for sub in ("commit", "merge", "rebase", "cherry-pick", "push"):
        assert g._admits(g.BROAD_INNER, sub)


def test_narrow_commit_predicate_admits_only_commit() -> None:
    assert g._admits("*git commit*", "commit")
    assert not g._admits("*git commit*", "merge")
    assert not g._admits("*git commit*", "push")


def test_narrow_push_predicate_admits_only_push() -> None:
    assert g._admits("*git push*", "push")
    assert not g._admits("*git push*", "commit")


# ---------------------------------------------------------------------------
# iter_git_hooks
# ---------------------------------------------------------------------------
def test_iter_git_hooks_finds_git_handlers_only() -> None:
    settings = _settings(
        [
            {"if": "Bash(*git commit*)", "command": "python3 scripts/a.py"},
            {"if": "Bash(*npm run*)", "command": "python3 scripts/b.py"},
            {"if": "Bash(*git *)", "command": 'cd "$x" && python3 scripts/c.py'},
            {"command": "python3 scripts/d.py"},  # no if: -> skipped
        ]
    )
    hooks = list(g.iter_git_hooks(settings))
    assert sorted(h.script for h in hooks) == ["a", "c"]


def test_iter_git_hooks_tolerates_malformed_config() -> None:
    assert list(g.iter_git_hooks({})) == []
    assert list(g.iter_git_hooks({"hooks": "nope"})) == []
    assert list(g.iter_git_hooks({"hooks": {"PreToolUse": [None, {"hooks": "x"}]}})) == []


# ---------------------------------------------------------------------------
# check_hook policy
# ---------------------------------------------------------------------------
def test_broad_predicate_needs_no_declaration() -> None:
    assert g.check_hook(_hook("x", g.BROAD_INNER), None) == []


def test_narrow_predicate_missing_declaration_is_flagged() -> None:
    problems = g.check_hook(_hook("x", "*git commit*"), None)
    assert len(problems) == 1
    assert g.SURFACE_ATTR in problems[0]


def test_narrow_predicate_admitting_its_surface_passes() -> None:
    assert g.check_hook(_hook("x", "*git commit*"), frozenset({"commit"})) == []
    assert g.check_hook(_hook("x", "*git push*"), frozenset({"push"})) == []


def test_pr2120_regression_narrow_predicate_broad_surface_is_flagged() -> None:
    # The exact PR #2120 bug: signing widened its surface to commit/merge/... but
    # stayed under Bash(*git commit*), so git merge never fired the hook.
    surface = frozenset({"commit", "merge", "rebase", "cherry-pick", "revert", "am", "pull"})
    problems = g.check_hook(_hook("check_commit_signing_ready", "*git commit*"), surface)
    assert len(problems) == 1
    msg = problems[0]
    # Every unadmitted subcommand is named, the admitted one is not in the list,
    # and the fix (broaden the predicate) is pointed at.
    listed = msg.split("subcommand(s) ", 1)[1].split("];", 1)[0]
    for unadmitted in ("merge", "rebase", "pull", "am", "cherry-pick", "revert"):
        assert unadmitted in listed
    assert "'commit'" not in listed
    assert g.BROAD_INNER in msg


def test_any_git_sentinel_requires_broad_predicate() -> None:
    assert g.check_hook(_hook("x", g.BROAD_INNER), g.ANY_GIT) == []
    problems = g.check_hook(_hook("x", "*git commit*"), g.ANY_GIT)
    assert len(problems) == 1
    assert "ANY_GIT" in problems[0]


def test_malformed_surface_is_flagged() -> None:
    assert g.check_hook(_hook("x", "*git commit*"), ["commit"])  # list, not set
    assert g.check_hook(_hook("x", "*git commit*"), frozenset())  # empty
    assert g.check_hook(_hook("x", "*git commit*"), frozenset({1, 2}))  # non-str


# ---------------------------------------------------------------------------
# find_drift integration against the real rendered config
# ---------------------------------------------------------------------------
def test_real_claude_settings_has_no_drift() -> None:
    settings = json.loads(g.CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    assert g.find_drift(settings) == []


def test_find_drift_reports_unimportable_script() -> None:
    settings = _settings(
        [{"if": "Bash(*git commit*)", "command": "python3 scripts/does_not_exist_zzz.py"}]
    )
    problems = g.find_drift(settings)
    assert len(problems) == 1
    assert "could not be imported" in problems[0]


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------
def test_cli_verify_passes_on_real_tree(capsys: pytest.CaptureFixture[str]) -> None:
    assert g.main(["verify"]) == 0


def test_cli_verify_fails_on_drifted_fixture(tmp_path: Path) -> None:
    drifted = _settings(
        [{"if": "Bash(*git commit*)", "command": "python3 scripts/check_commit_signing_ready.py"}]
    )
    fixture = tmp_path / "settings.json"
    fixture.write_text(json.dumps(drifted), encoding="utf-8")
    assert g.main(["verify", "--settings", str(fixture)]) == 1
