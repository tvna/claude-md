"""Tests for ``scripts/scan_harness_doc_coverage.py``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import scan_harness_doc_coverage

pytestmark = pytest.mark.shard_default


REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / ".github/label-policy.toml"


def _write_policy(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    """Write a minimal label-policy.toml with the given area_paths entries."""
    lines = ["schema_version = 2\n"]
    for e in entries:
        lines.append("[[area_paths]]\n")
        lines.append(f'area = "{e["area"]}"\n')
        paths_str = ", ".join(f'"{p}"' for p in e.get("paths", []))
        lines.append(f"paths = [{paths_str}]\n")
        if e.get("broad"):
            lines.append("broad = true\n")
    policy = tmp_path / "label-policy.toml"
    policy.write_text("".join(lines))
    return policy


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def test_load_entries_returns_list(tmp_path: Path) -> None:
    policy = _write_policy(
        tmp_path,
        [{"area": "area:preflight", "paths": ["scripts/gate_*.py"]}],
    )
    entries = scan_harness_doc_coverage.load_entries(policy)
    assert len(entries) == 1
    assert entries[0]["area"] == "area:preflight"


def test_is_specifically_covered_non_broad_match() -> None:
    entries = [{"area": "area:preflight", "paths": ["scripts/gate_*.py"]}]
    assert scan_harness_doc_coverage.is_specifically_covered("scripts/gate_foo.py", entries)


def test_is_specifically_covered_broad_entry_ignored() -> None:
    entries = [{"area": "area:scripts-tests", "paths": ["scripts/**"], "broad": True}]
    assert not scan_harness_doc_coverage.is_specifically_covered("scripts/foo.py", entries)


def test_is_specifically_covered_non_broad_wins_over_broad() -> None:
    entries: list[dict[str, Any]] = [
        {"area": "area:scripts-tests", "paths": ["scripts/**"], "broad": True},
        {"area": "area:preflight", "paths": ["scripts/gate_*.py"]},
    ]
    assert scan_harness_doc_coverage.is_specifically_covered("scripts/gate_foo.py", entries)


def test_is_specifically_covered_no_match_returns_false() -> None:
    entries = [{"area": "area:preflight", "paths": ["scripts/gate_*.py"]}]
    assert not scan_harness_doc_coverage.is_specifically_covered("scripts/other.py", entries)


def test_collect_scripts_excludes_private(tmp_path: Path) -> None:
    (tmp_path / "public.py").touch()
    (tmp_path / "_private.py").touch()
    result = scan_harness_doc_coverage.collect_scripts(tmp_path)
    names = [p.name for p in result]
    assert "public.py" in names
    assert "_private.py" not in names


def test_collect_workflows(tmp_path: Path) -> None:
    (tmp_path / "foo.yml").touch()
    (tmp_path / "bar.yml").touch()
    result = scan_harness_doc_coverage.collect_workflows(tmp_path)
    names = {p.name for p in result}
    assert names == {"foo.yml", "bar.yml"}


# ---------------------------------------------------------------------------
# verify() integration tests
# ---------------------------------------------------------------------------


def test_verify_passes_when_all_covered(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "gate_foo.py").touch()

    policy = _write_policy(
        tmp_path,
        [{"area": "area:preflight", "paths": ["scripts/gate_*.py"]}],
    )
    errors = scan_harness_doc_coverage.verify(
        root=tmp_path,
        policy_path=policy,
        scripts_dir=scripts_dir,
        workflows_dir=tmp_path / "nonexistent_workflows",
    )
    assert errors == []


def test_verify_fails_for_uncovered_script(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "orphan.py").touch()

    policy = _write_policy(
        tmp_path,
        [{"area": "area:scripts-tests", "paths": ["scripts/**"], "broad": True}],
    )
    errors = scan_harness_doc_coverage.verify(
        root=tmp_path,
        policy_path=policy,
        scripts_dir=scripts_dir,
        workflows_dir=tmp_path / "nonexistent_workflows",
    )
    assert len(errors) == 1
    assert "orphan.py" in errors[0]
    assert "no specific area_paths coverage" in errors[0]


def test_verify_fails_for_uncovered_workflow(tmp_path: Path) -> None:
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "verify-pr.yml").touch()

    policy = _write_policy(
        tmp_path,
        [{"area": "area:github-workflows", "paths": [".github/**"], "broad": True}],
    )
    errors = scan_harness_doc_coverage.verify(
        root=tmp_path,
        policy_path=policy,
        scripts_dir=tmp_path / "nonexistent_scripts",
        workflows_dir=workflows_dir,
    )
    assert len(errors) == 1
    assert "verify-pr.yml" in errors[0]


def test_verify_skips_missing_policy(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    errors = scan_harness_doc_coverage.verify(
        root=tmp_path,
        policy_path=tmp_path / "missing.toml",
    )
    assert errors == []
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_verify_private_scripts_exempt(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "_private.py").touch()

    policy = _write_policy(tmp_path, [])
    errors = scan_harness_doc_coverage.verify(
        root=tmp_path,
        policy_path=policy,
        scripts_dir=scripts_dir,
        workflows_dir=tmp_path / "nonexistent_workflows",
    )
    assert errors == []


def test_verify_allowlist_suppresses_uncovered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "orphan.py").touch()

    monkeypatch.setattr(
        scan_harness_doc_coverage,
        "COVERAGE_ALLOWLIST",
        {"scripts/orphan.py": "Refs #1761: cannot classify yet."},
    )
    policy = _write_policy(
        tmp_path,
        [{"area": "area:scripts-tests", "paths": ["scripts/**"], "broad": True}],
    )
    errors = scan_harness_doc_coverage.verify(
        root=tmp_path,
        policy_path=policy,
        scripts_dir=scripts_dir,
        workflows_dir=tmp_path / "nonexistent_workflows",
    )
    assert errors == []


def test_verify_stale_allowlist_removed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    # orphan.py is in allowlist but does not exist

    monkeypatch.setattr(
        scan_harness_doc_coverage,
        "COVERAGE_ALLOWLIST",
        {"scripts/orphan.py": "Refs #1761: cannot classify yet."},
    )
    policy = _write_policy(tmp_path, [])
    errors = scan_harness_doc_coverage.verify(
        root=tmp_path,
        policy_path=policy,
        scripts_dir=scripts_dir,
        workflows_dir=tmp_path / "nonexistent_workflows",
    )
    assert len(errors) == 1
    assert "no longer exists" in errors[0]


def test_verify_stale_allowlist_now_covered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "gate_foo.py").touch()

    monkeypatch.setattr(
        scan_harness_doc_coverage,
        "COVERAGE_ALLOWLIST",
        {"scripts/gate_foo.py": "Refs #1761: used to be uncovered."},
    )
    policy = _write_policy(
        tmp_path,
        [{"area": "area:preflight", "paths": ["scripts/gate_*.py"]}],
    )
    errors = scan_harness_doc_coverage.verify(
        root=tmp_path,
        policy_path=policy,
        scripts_dir=scripts_dir,
        workflows_dir=tmp_path / "nonexistent_workflows",
    )
    assert len(errors) == 1
    assert "now has specific coverage" in errors[0]


# ---------------------------------------------------------------------------
# End-to-end: real repo tree must pass
# ---------------------------------------------------------------------------


def test_real_repo_passes() -> None:
    """Verify the live repo tree satisfies scan_harness_doc_coverage.verify()."""
    errors = scan_harness_doc_coverage.verify(root=REPO_ROOT)
    assert errors == [], "\n".join(errors)
