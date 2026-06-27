"""Tests for ``scripts/scan_commit_type_label_drift.py``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import scan_commit_type_label_drift as gate

pytestmark = pytest.mark.shard_policy


def _label_policy(labels: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal label-policy dict from raw label entries."""
    return {"labels": labels}


def _title_policy(types: list[str]) -> dict[str, Any]:
    """Build a minimal title-policy dict with the given commit types."""
    return {"title_policy": {"types": types}}


def test_commit_types_extracts_string_set() -> None:
    title = _title_policy(["feat", "fix"])
    assert gate.commit_types(title) == {"feat", "fix"}


def test_verify_policy_clean_when_label_is_real_type() -> None:
    label = _label_policy([{"name": "type:feat", "family": "type"}])
    title = _title_policy(["feat", "fix"])
    assert gate.verify_policy(label, title) == []


def test_verify_policy_clean_when_tracking_is_exempted() -> None:
    label = _label_policy(
        [
            {"name": "type:feat", "family": "type"},
            {"name": "type:tracking", "family": "type", "commit_type": False},
        ]
    )
    title = _title_policy(["feat"])
    assert gate.verify_policy(label, title) == []


def test_verify_policy_flags_unknown_stem() -> None:  # invariant (a)
    label = _label_policy([{"name": "type:foo", "family": "type"}])
    title = _title_policy(["feat", "fix"])
    errors = gate.verify_policy(label, title)
    assert errors == [
        "::error file=.github/label-policy.toml::type label type:foo has stem 'foo' "
        "that is not a commit type in .github/title-policy.toml; add it to "
        "[title_policy].types or set commit_type = false"
    ]


def test_verify_policy_flags_false_marker_on_real_type() -> None:  # invariant (b)
    label = _label_policy([{"name": "type:feat", "family": "type", "commit_type": False}])
    title = _title_policy(["feat"])
    errors = gate.verify_policy(label, title)
    assert errors == [
        "::error file=.github/label-policy.toml::type label type:feat sets commit_type = "
        "false but 'feat' IS a commit type in .github/title-policy.toml; remove the "
        "commit_type marker"
    ]


def test_verify_policy_flags_marker_on_non_type_family() -> None:  # invariant (c)
    label = _label_policy([{"name": "area:docs", "family": "area", "commit_type": False}])
    title = _title_policy(["feat"])
    errors = gate.verify_policy(label, title)
    assert errors == [
        "::error file=.github/label-policy.toml::label area:docs sets commit_type but "
        "family is 'area'; the commit_type marker is only valid on type:* labels"
    ]


def test_verify_policy_flags_non_boolean_marker() -> None:  # invariant (d)
    label = _label_policy([{"name": "type:tracking", "family": "type", "commit_type": "no"}])
    title = _title_policy(["feat"])
    errors = gate.verify_policy(label, title)
    assert errors == [
        "::error file=.github/label-policy.toml::type label type:tracking commit_type "
        "must be a boolean, got 'no'"
    ]


def test_verify_reports_missing_label_policy(tmp_path: Path) -> None:
    errors = gate.verify(tmp_path)
    assert errors == [
        "::error file=.github/label-policy.toml::policy file .github/label-policy.toml not found"
    ]


def test_verify_reports_missing_title_policy(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "label-policy.toml").write_text("", encoding="utf-8")
    errors = gate.verify(tmp_path)
    assert errors == [
        "::error file=.github/label-policy.toml::policy file .github/title-policy.toml not found"
    ]


def test_verify_against_real_repository_is_clean() -> None:
    assert gate.verify(gate.REPO_ROOT) == []


def test_main_returns_zero_when_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "verify", lambda root: [])
    assert gate.main(["verify"]) == 0


def test_main_prints_errors_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gate, "verify", lambda root: ["::error file=x::boom"])
    rc = gate.main(["verify"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "boom" in captured.err


def test_main_rejects_unknown_command() -> None:
    with pytest.raises(SystemExit) as excinfo:
        gate.main(["bogus"])
    assert excinfo.value.code == 2


def test_title_policy_diagnostic_none_when_well_formed() -> None:
    assert gate.title_policy_diagnostic(_title_policy(["feat"])) is None


def test_verify_policy_flags_missing_title_policy_table() -> None:
    errors = gate.verify_policy(_label_policy([{"name": "type:feat", "family": "type"}]), {})
    assert errors == [
        "::error file=.github/label-policy.toml::title-policy.toml is missing the "
        "[title_policy] table or it is not a table"
    ]


def test_verify_policy_flags_types_not_a_list() -> None:
    label = _label_policy([{"name": "type:feat", "family": "type"}])
    errors = gate.verify_policy(label, {"title_policy": {"types": "feat"}})
    assert errors == [
        "::error file=.github/label-policy.toml::title-policy.toml [title_policy].types "
        "is not a list"
    ]


def test_main_verify_with_repo_root(tmp_path: Path) -> None:
    # Covers the Path(args.repo_root) conversion; tmp_path has no policy files,
    # so verify reports the missing label policy and main exits 1.
    rc = gate.main(["verify", "--repo-root", str(tmp_path)])
    assert rc == 1
