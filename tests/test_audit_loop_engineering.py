"""Tests for ``scripts/audit_loop_engineering.py`` (Refs #2294, #2268)."""

from __future__ import annotations

from pathlib import Path

import audit_loop_engineering as ale
import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- the committed checklist itself -----------------------------------------


def test_real_audit_file_parses() -> None:
    meta, items = ale.load_audit(ale.DEFAULT_DATA)
    assert meta["source"].startswith("Loop Engineering")
    assert items, "the audit must record at least one item"
    for item in items:
        assert item["id"] and item["dimension"] and item["status"]


def test_real_tree_has_no_drift() -> None:
    """Every recorded machine-checkable status must match the actual tree.

    This is the audit auditing itself: if a recorded present/absent disagrees
    with the working tree, the committed checklist is stale and must be fixed.
    """
    _meta, items = ale.load_audit(ale.DEFAULT_DATA)
    drifted = [item["id"] for item, _c, drift in ale.evaluate(items, REPO_ROOT) if drift]
    assert drifted == [], f"stale recorded statuses: {drifted}"


# --- detect(): the filesystem boundary --------------------------------------


def test_detect_path_exists(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    assert ale.detect({"kind": "path_exists", "target": "a.txt"}, tmp_path) is True
    assert ale.detect({"kind": "path_exists", "target": "missing"}, tmp_path) is False


def test_detect_glob_exists(tmp_path: Path) -> None:
    (tmp_path / "one.md").write_text("x", encoding="utf-8")
    assert ale.detect({"kind": "glob_exists", "target": "*.md"}, tmp_path) is True
    assert ale.detect({"kind": "glob_exists", "target": "*.rst"}, tmp_path) is False


def test_detect_grep_in_glob_matches_and_skips_dirs(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()  # a non-file that the glob yields and must skip
    (tmp_path / "a.txt").write_text("hello NEEDLE world", encoding="utf-8")
    check = {"kind": "grep_in_glob", "glob": "*", "pattern": "NEEDLE"}
    assert ale.detect(check, tmp_path) is True


def test_detect_grep_in_glob_no_match(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("nothing here", encoding="utf-8")
    check = {"kind": "grep_in_glob", "glob": "*.txt", "pattern": "ABSENT"}
    assert ale.detect(check, tmp_path) is False


def test_detect_unknown_kind_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown check kind"):
        ale.detect({"kind": "bogus"}, tmp_path)


# --- computed_status() / is_drift() -----------------------------------------


def test_computed_status_judgment_item_is_none(tmp_path: Path) -> None:
    assert ale.computed_status({"machine_checkable": False}, tmp_path) is None
    assert ale.computed_status({}, tmp_path) is None


def test_computed_status_present_and_absent(tmp_path: Path) -> None:
    (tmp_path / "here").write_text("x", encoding="utf-8")
    present = {"machine_checkable": True, "check": {"kind": "path_exists", "target": "here"}}
    absent = {"machine_checkable": True, "check": {"kind": "path_exists", "target": "nope"}}
    assert ale.computed_status(present, tmp_path) == "present"
    assert ale.computed_status(absent, tmp_path) == "absent"


def test_is_drift_all_branches() -> None:
    assert ale.is_drift({"status": "present"}, None) is False  # judgment item
    assert ale.is_drift({"status": "partial"}, "present") is False  # non-binary recorded
    assert ale.is_drift({"status": "present"}, "present") is False  # agree
    assert ale.is_drift({"status": "present"}, "absent") is True  # disagree


# --- render() ----------------------------------------------------------------


def test_render_flags_drift(tmp_path: Path) -> None:
    (tmp_path / "exists").write_text("x", encoding="utf-8")
    items = [
        {"id": "j1", "dimension": "d", "status": "partial", "machine_checkable": False,
         "evidence": "judgment"},
        {"id": "m1", "dimension": "d", "status": "absent", "machine_checkable": True,
         "check": {"kind": "path_exists", "target": "exists"}, "evidence": "will drift"},
    ]
    out = ale.render({"source": "S", "audit_umbrella": "#1", "last_reviewed": "2026-07-04"},
                     items, tmp_path)
    assert "Loop-engineering achievement audit" in out
    assert "items=2" in out
    assert "[DRIFT]" in out
    assert "DRIFT: m1" in out


def test_render_no_drift(tmp_path: Path) -> None:
    items = [
        {"id": "m1", "dimension": "d", "status": "absent", "machine_checkable": True,
         "check": {"kind": "path_exists", "target": "nope"}, "evidence": "ok"},
    ]
    out = ale.render({}, items, tmp_path)
    assert "DRIFT: none" in out
    assert "[DRIFT]" not in out


# --- run(): CLI entry --------------------------------------------------------


def test_run_prints_table_and_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "audit.toml"
    data.write_text(
        '[meta]\nsource = "T"\n\n'
        '[[items]]\nid = "m1"\ndimension = "d"\nstatus = "absent"\n'
        'machine_checkable = true\n'
        'check = { kind = "path_exists", target = "nope" }\nevidence = "e"\n',
        encoding="utf-8",
    )
    rc = ale.run(["run", "--data", str(data), "--root", str(tmp_path)])
    assert rc == 0
    assert "DRIFT: none" in capsys.readouterr().out
