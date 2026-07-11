"""Tests for ``scripts/scan_label_sot_drift.py``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import scan_label_sot_drift as gate

pytestmark = pytest.mark.shard_policy


def _policy(labels: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal label-policy dict from raw ``[[labels]]`` entries."""
    return {"labels": labels}


def _label(name: str, description: str, color: str) -> dict[str, Any]:
    """Build a labels.json / policy label entry (same identity triple)."""
    return {"name": name, "description": description, "color": color}


def test_verify_parity_clean_when_identity_matches() -> None:
    entry = _label("type:fix", "Defect or broken workflow.", "d73a4a")
    policy = _policy([{**entry, "family": "type", "status": "keep"}])
    assert gate.verify_parity([entry], policy) == []


def test_verify_parity_flags_description_drift() -> None:
    catalog = [_label("type:fix", "Bug fix.", "d73a4a")]
    policy = _policy([_label("type:fix", "Defect or broken workflow.", "d73a4a")])
    errors = gate.verify_parity(catalog, policy)
    assert len(errors) == 1
    assert errors[0].startswith("::error file=.github/labels.json::")
    assert "type:fix" in errors[0]
    assert "description drifts" in errors[0]


def test_verify_parity_flags_color_drift() -> None:
    catalog = [_label("type:fix", "Defect or broken workflow.", "000000")]
    policy = _policy([_label("type:fix", "Defect or broken workflow.", "d73a4a")])
    errors = gate.verify_parity(catalog, policy)
    assert len(errors) == 1
    assert "color drifts" in errors[0]


def test_verify_parity_reports_both_description_and_color_drift() -> None:
    catalog = [_label("type:fix", "Bug fix.", "000000")]
    policy = _policy([_label("type:fix", "Defect or broken workflow.", "d73a4a")])
    errors = gate.verify_parity(catalog, policy)
    assert len(errors) == 2


def test_verify_parity_flags_label_absent_from_policy() -> None:
    catalog = [_label("type:orphan", "No policy home.", "ffffff")]
    errors = gate.verify_parity(catalog, _policy([]))
    assert len(errors) == 1
    assert "no [[labels]] entry in" in errors[0]
    assert "type:orphan" in errors[0]


def test_verify_parity_skips_retro_sourced_labels() -> None:
    # retro:* and type:retrospective are sourced from scripts/_retro_labels.py,
    # not label-policy.toml, so a labels.json-only entry is not a drift.
    retro_label = sorted(gate.RETRO_SOURCED_LABELS)[0]
    catalog = [_label(retro_label, "Anything, unchecked here.", "0e8a16")]
    assert gate.verify_parity(catalog, _policy([])) == []


def test_verify_parity_flags_non_list_catalog() -> None:
    errors = gate.verify_parity({"name": "x"}, _policy([]))
    assert errors == [
        "::error file=.github/labels.json::labels.json must be a JSON array of label objects"
    ]


def test_verify_parity_flags_entry_missing_name() -> None:
    errors = gate.verify_parity([{"description": "d", "color": "ffffff"}], _policy([]))
    assert len(errors) == 1
    assert "missing a string 'name'" in errors[0]


def test_verify_parity_flags_non_object_entry() -> None:
    errors = gate.verify_parity(["not-an-object"], _policy([]))
    assert len(errors) == 1
    assert "is not an object" in errors[0]


def test_verify_parity_flags_non_list_policy_labels() -> None:
    errors = gate.verify_parity([_label("type:fix", "d", "d73a4a")], {"labels": 5})
    assert errors == [
        "::error file=.github/label-policy.toml::label-policy.toml [[labels]] must be an "
        "array of tables"
    ]


def test_index_policy_labels_flags_nameless_entry() -> None:
    # A dict [[labels]] entry with a missing/non-string name fails loudly rather
    # than being silently dropped (which would surface as a misleading missing
    # counterpart against labels.json).
    index, diagnostics = gate.index_policy_labels(_policy([{"family": "type"}, _label("type:fix", "d", "c")]))
    assert set(index) == {"type:fix"}
    assert len(diagnostics) == 1
    assert "missing or non-string 'name'" in diagnostics[0]
    assert diagnostics[0].startswith("::error file=.github/label-policy.toml::")


def test_verify_parity_flags_duplicate_policy_label() -> None:
    # Two [[labels]] entries with the same name must fail loudly rather than
    # let the last copy silently win (Codex review, PR #2447).
    policy = _policy(
        [
            _label("type:fix", "Defect or broken workflow.", "d73a4a"),
            _label("type:fix", "A conflicting second definition.", "000000"),
        ]
    )
    catalog = [_label("type:fix", "Defect or broken workflow.", "d73a4a")]
    errors = gate.verify_parity(catalog, policy)
    assert len(errors) == 1
    assert "declared more than once" in errors[0]
    assert errors[0].startswith("::error file=.github/label-policy.toml::")


def test_verify_parity_flags_duplicate_catalog_label() -> None:
    # A duplicate name in labels.json (the live catalog) must fail loudly too,
    # symmetric to the policy-side uniqueness check.
    label = _label("type:fix", "Defect or broken workflow.", "d73a4a")
    errors = gate.verify_parity([label, dict(label)], _policy([label]))
    assert len(errors) == 1
    assert "more than once in labels.json" in errors[0]
    assert errors[0].startswith("::error file=.github/labels.json::")


def test_verify_parity_flags_retro_label_dual_sourced_in_policy() -> None:
    # A retro-sourced label must not ALSO be authored in label-policy.toml;
    # two homes for one label is single-SoT drift in the reverse direction.
    retro = sorted(gate.RETRO_SOURCED_LABELS)[0]
    catalog = [_label(retro, "d", "0e8a16")]
    policy = _policy([_label(retro, "d", "0e8a16")])
    errors = gate.verify_parity(catalog, policy)
    assert len(errors) == 1
    assert "one authoritative home" in errors[0]
    assert errors[0].startswith("::error file=.github/label-policy.toml::")


def test_verify_against_real_repository_is_clean() -> None:
    assert gate.verify(gate.REPO_ROOT) == []


def test_verify_reports_missing_labels_json(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "label-policy.toml").write_text("", encoding="utf-8")
    errors = gate.verify(tmp_path)
    assert errors == [
        "::error file=.github/labels.json::catalog file .github/labels.json not found"
    ]


def test_verify_reports_missing_label_policy(tmp_path: Path) -> None:
    github = tmp_path / ".github"
    github.mkdir()
    (github / "labels.json").write_text("[]", encoding="utf-8")
    errors = gate.verify(tmp_path)
    assert errors == [
        "::error file=.github/label-policy.toml::policy file .github/label-policy.toml not found"
    ]


def test_verify_reports_malformed_labels_json(tmp_path: Path) -> None:
    github = tmp_path / ".github"
    github.mkdir()
    (github / "labels.json").write_text("{ not json", encoding="utf-8")
    (github / "label-policy.toml").write_text("", encoding="utf-8")
    errors = gate.verify(tmp_path)
    assert len(errors) == 1
    assert errors[0].startswith("::error file=.github/labels.json::labels.json is not valid JSON:")


def test_verify_reports_malformed_label_policy_toml(tmp_path: Path) -> None:
    github = tmp_path / ".github"
    github.mkdir()
    (github / "labels.json").write_text("[]", encoding="utf-8")
    (github / "label-policy.toml").write_text("this is = = not toml", encoding="utf-8")
    errors = gate.verify(tmp_path)
    assert len(errors) == 1
    assert errors[0].startswith(
        "::error file=.github/label-policy.toml::label-policy.toml is not valid TOML:"
    )


def test_verify_reports_unreadable_labels_json(tmp_path: Path) -> None:
    # A non-UTF-8 (or otherwise unreadable) catalog file yields a scoped
    # annotation, not a raw traceback, honoring the docstring Contract.
    github = tmp_path / ".github"
    github.mkdir()
    (github / "labels.json").write_bytes(b"\xff\xfe\x00")
    (github / "label-policy.toml").write_text("", encoding="utf-8")
    errors = gate.verify(tmp_path)
    assert len(errors) == 1
    assert errors[0].startswith("::error file=.github/labels.json::labels.json could not be read:")


def test_verify_end_to_end_detects_drift(tmp_path: Path) -> None:
    github = tmp_path / ".github"
    github.mkdir()
    (github / "labels.json").write_text(
        json.dumps([_label("type:fix", "Bug fix.", "d73a4a")]), encoding="utf-8"
    )
    (github / "label-policy.toml").write_text(
        '[[labels]]\nname = "type:fix"\ndescription = "Defect or broken workflow."\ncolor = "d73a4a"\n',
        encoding="utf-8",
    )
    errors = gate.verify(tmp_path)
    assert len(errors) == 1
    assert "description drifts" in errors[0]


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


def test_main_verify_with_repo_root(tmp_path: Path) -> None:
    # Covers the Path(args.repo_root) conversion; tmp_path has no input files,
    # so verify reports the missing catalog and main exits 1.
    rc = gate.main(["verify", "--repo-root", str(tmp_path)])
    assert rc == 1
