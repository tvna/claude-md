"""Tests for ``scripts/scan_area_path_coverage.py``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import scan_area_path_coverage

pytestmark = pytest.mark.shard_ci_ops


def _policy(
    *,
    areas: list[str],
    area_paths: list[dict[str, Any]],
    extra_labels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal policy dict with the given area labels and mappings."""
    labels: list[dict[str, Any]] = [{"name": name, "family": "area"} for name in areas]
    labels.extend(extra_labels or [])
    return {"labels": labels, "area_paths": area_paths}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_declared_area_labels_only_area_family() -> None:
    policy = _policy(
        areas=["area:docs"],
        area_paths=[],
        extra_labels=[
            {"name": "type:fix", "family": "type"},
            {"family": "area"},  # missing name -> ignored
            "not-a-dict",  # type: ignore[list-item]
        ],
    )
    assert scan_area_path_coverage.declared_area_labels(policy) == {"area:docs"}


def test_area_path_entries_filters_non_dict() -> None:
    policy: dict[str, Any] = {"area_paths": [{"area": "area:docs", "paths": ["docs/**"]}, "bad"]}
    entries = scan_area_path_coverage.area_path_entries(policy)
    assert entries == [{"area": "area:docs", "paths": ["docs/**"]}]


def test_mapped_areas_skips_non_string_area() -> None:
    policy: dict[str, Any] = {"area_paths": [{"area": "area:docs"}, {"area": 7}, {"paths": []}]}
    assert scan_area_path_coverage.mapped_areas(policy) == {"area:docs"}


def test_glob_top_levels_extracts_first_segment() -> None:
    policy: dict[str, Any] = {
        "area_paths": [
            {"area": "area:docs", "paths": ["docs/**", "README*.md", "", 5]},
            {"area": "area:scripts-tests", "paths": ["scripts/preflight_*.py"]},
        ]
    }
    assert scan_area_path_coverage.glob_top_levels(policy) == {"docs", "README*.md", "scripts"}


def _fake_runner(dirs: list[str]) -> Callable[[list[str], Path], str]:
    """Return a git runner stub that yields *dirs* as ls-tree output."""

    def run(args: list[str], cwd: Path) -> str:
        return "".join(f"{name}\n" for name in dirs)

    return run


def test_tracked_top_level_dirs_parses_ls_tree(tmp_path: Path) -> None:
    dirs = scan_area_path_coverage.tracked_top_level_dirs(
        tmp_path, runner=_fake_runner(["scripts", "docs", ""])
    )
    assert dirs == {"scripts", "docs"}


def test_tracked_top_level_dirs_against_real_repo() -> None:
    dirs = scan_area_path_coverage.tracked_top_level_dirs(scan_area_path_coverage.REPO_ROOT)
    # The real repository has these tracked top-level lanes; the exact set may
    # grow, so assert membership rather than equality.
    assert {"scripts", "tests", "docs"} <= dirs


def test_run_git_raises_on_failure() -> None:
    with pytest.raises(RuntimeError, match="git ls-tree .* failed"):
        scan_area_path_coverage._run_git(
            ["ls-tree", "-d", "--name-only", "nonexistent-ref-xyz"], scan_area_path_coverage.REPO_ROOT
        )


def test_run_git_raises_when_git_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(scan_area_path_coverage.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="git executable not found"):
        scan_area_path_coverage._run_git(["status"], tmp_path)

# ---------------------------------------------------------------------------
# Structural verification
# ---------------------------------------------------------------------------


def test_verify_policy_happy_path() -> None:
    policy = _policy(
        areas=["area:docs", "area:scripts-tests"],
        area_paths=[
            {"area": "area:docs", "paths": ["docs/**"]},
            {"area": "area:scripts-tests", "paths": ["scripts/**"]},
        ],
    )
    assert scan_area_path_coverage.verify_policy(policy) == []


def test_verify_policy_flags_undeclared_mapped_area() -> None:
    policy = _policy(
        areas=["area:docs"],
        area_paths=[
            {"area": "area:docs", "paths": ["docs/**"]},
            {"area": "area:ghost", "paths": ["ghost/**"]},
        ],
    )
    errors = scan_area_path_coverage.verify_policy(policy)
    assert errors == [
        "::error file=.github/label-policy.toml::area_paths maps undeclared area "
        "area:ghost; add it to the area family or remove the mapping"
    ]


def test_verify_policy_flags_area_without_mapping() -> None:
    policy = _policy(
        areas=["area:docs", "area:orphan"],
        area_paths=[{"area": "area:docs", "paths": ["docs/**"]}],
    )
    errors = scan_area_path_coverage.verify_policy(policy)
    assert errors == [
        "::error file=.github/label-policy.toml::area label area:orphan has no "
        "area_paths mapping; add owned paths or retire the label"
    ]


def test_verify_policy_flags_missing_area_key() -> None:
    policy = _policy(areas=[], area_paths=[{"paths": ["docs/**"]}])
    errors = scan_area_path_coverage.verify_policy(policy)
    assert errors == ["::error file=.github/label-policy.toml::area_paths entry is missing a string 'area' key"]


def test_verify_policy_flags_empty_paths() -> None:
    policy = _policy(areas=["area:docs"], area_paths=[{"area": "area:docs", "paths": []}])
    errors = scan_area_path_coverage.verify_policy(policy)
    assert errors == ["::error file=.github/label-policy.toml::area_paths entry for area:docs declares no paths"]


# ---------------------------------------------------------------------------
# Directory coverage
# ---------------------------------------------------------------------------


def test_verify_directory_coverage_flags_uncovered_dir(tmp_path: Path) -> None:
    policy = _policy(areas=["area:scripts-tests"], area_paths=[{"area": "area:scripts-tests", "paths": ["scripts/**"]}])
    errors = scan_area_path_coverage.verify_directory_coverage(
        policy, tmp_path, runner=_fake_runner(["scripts", "newlane"])
    )
    assert errors == [
        "::error file=.github/label-policy.toml::top-level directory newlane/ is not claimed "
        "by any area_paths glob; add an area:* mapping that owns it"
    ]


def test_verify_directory_coverage_happy(tmp_path: Path) -> None:
    policy = _policy(
        areas=["area:scripts-tests", "area:hooks"],
        area_paths=[
            {"area": "area:scripts-tests", "paths": ["scripts/**"]},
            {"area": "area:hooks", "paths": [".claude/settings.json"]},
        ],
    )
    errors = scan_area_path_coverage.verify_directory_coverage(
        policy, tmp_path, runner=_fake_runner(["scripts", ".claude"])
    )
    assert errors == []


# ---------------------------------------------------------------------------
# Top-level verify()
# ---------------------------------------------------------------------------


def test_verify_reports_missing_policy_file(tmp_path: Path) -> None:
    errors = scan_area_path_coverage.verify(tmp_path)
    assert errors == ["::error file=.github/label-policy.toml::policy file .github/label-policy.toml not found"]


def test_verify_against_real_repository_is_clean() -> None:
    assert scan_area_path_coverage.verify(scan_area_path_coverage.REPO_ROOT) == []


def test_verify_combines_structural_and_coverage(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    policy_text = (
        '[[labels]]\nname = "area:github-workflows"\nfamily = "area"\n\n'
        '[[area_paths]]\narea = "area:github-workflows"\npaths = [".github/**"]\n'
    )
    (tmp_path / ".github" / "label-policy.toml").write_text(policy_text, encoding="utf-8")
    errors = scan_area_path_coverage.verify(tmp_path, runner=_fake_runner([".github", "stray"]))
    assert errors == [
        "::error file=.github/label-policy.toml::top-level directory stray/ is not claimed "
        "by any area_paths glob; add an area:* mapping that owns it"
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_main_returns_zero_when_no_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_area_path_coverage, "verify", lambda root: [])
    assert scan_area_path_coverage.main(["verify"]) == 0


def test_main_prints_errors_to_stderr(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(scan_area_path_coverage, "verify", lambda root: ["::error file=x::boom"])
    rc = scan_area_path_coverage.main(["verify"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "boom" in captured.err


def test_main_rejects_unknown_command() -> None:
    with pytest.raises(SystemExit) as excinfo:
        scan_area_path_coverage.main(["bogus"])
    assert excinfo.value.code == 2
