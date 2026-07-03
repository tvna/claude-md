"""Tests for scripts/verify_generated_docs_ownership.py.

The module is the retirement path for docs/generated/ (#2226): OWNERSHIP maps
every generated path pattern to its producer script, ``verify`` fails when a
registered producer is gone, and ``retire`` deletes files no pattern owns.
These tests pin the segment-wise pattern matcher, the registry sanity check,
the retire semantics on fixture trees, and the real-repo wiring (producers
exist and each is invoked by post-merge.yml; the retire sweep itself is wired
into the decision-tree job).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest
import verify_generated_docs_ownership as gate

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_repo(tmp_path: Path) -> Path:
    """Materialise producers and one owned file per registry pattern."""
    for surface in gate.OWNERSHIP:
        producer = tmp_path / surface.producer
        producer.parent.mkdir(parents=True, exist_ok=True)
        producer.write_text("# producer\n")
        owned = tmp_path / Path(gate.GENERATED_ROOT) / surface.pattern.replace("*", "sample")
        owned.parent.mkdir(parents=True, exist_ok=True)
        owned.write_text("owned\n")
    return tmp_path


class TestPatternMatching:
    def test_star_does_not_cross_directory_boundary(self) -> None:
        assert gate.pattern_matches("scripts/*.md", PurePosixPath("scripts/ast/x.md")) is False

    def test_star_matches_within_segment(self) -> None:
        assert gate.pattern_matches("scripts/ast/*.md", PurePosixPath("scripts/ast/x.md")) is True
        assert gate.pattern_matches(
            "workflows/*-if-branches.md", PurePosixPath("workflows/verify-pr-if-branches.md")
        ) is True

    def test_exact_pattern_matches_only_itself(self) -> None:
        assert gate.pattern_matches(
            "graph/doc-dependency-graph.md", PurePosixPath("graph/doc-dependency-graph.md")
        ) is True
        assert gate.pattern_matches(
            "graph/doc-dependency-graph.md", PurePosixPath("graph/other.md")
        ) is False


class TestRegistrySanity:
    def test_fixture_repo_is_clean(self, tmp_path: Path) -> None:
        assert gate.registry_errors(_make_repo(tmp_path)) == []

    def test_missing_producer_fails_with_retirement_remediation(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        (root / gate.OWNERSHIP[0].producer).unlink()
        errors = gate.registry_errors(root)
        assert len(errors) == 1
        assert gate.OWNERSHIP[0].producer in errors[0]
        assert "drop its registry entry" in errors[0]

    def test_real_repo_registry_is_consistent(self) -> None:
        # Every registered producer exists on the current tree. A retiring PR
        # keeps this green by dropping the registry entry in the same change.
        assert gate.registry_errors(REPO_ROOT) == []

    def test_patterns_are_relative_and_confined(self) -> None:
        for surface in gate.OWNERSHIP:
            pattern = PurePosixPath(surface.pattern)
            assert not pattern.is_absolute()
            assert ".." not in pattern.parts


class TestRetire:
    def test_orphan_is_deleted_and_owned_files_survive(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        orphan = root / Path(gate.GENERATED_ROOT) / "scripts" / "retired-feature.md"
        orphan.write_text("stale\n")
        retired = gate.retire_orphans(root)
        assert retired == [orphan]
        assert not orphan.exists()
        for surface in gate.OWNERSHIP:
            owned = root / Path(gate.GENERATED_ROOT) / surface.pattern.replace("*", "sample")
            assert owned.exists()

    def test_clean_tree_is_a_noop(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        before = sorted((root / Path(gate.GENERATED_ROOT)).rglob("*"))
        assert gate.retire_orphans(root) == []
        assert sorted((root / Path(gate.GENERATED_ROOT)).rglob("*")) == before

    def test_emptied_subdirectory_is_pruned_but_root_kept(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        retired_dir = root / Path(gate.GENERATED_ROOT) / "retired-surface"
        retired_dir.mkdir()
        (retired_dir / "a.md").write_text("stale\n")
        (retired_dir / "nested").mkdir()
        (retired_dir / "nested" / "b.md").write_text("stale\n")
        retired = gate.retire_orphans(root)
        assert len(retired) == 2
        assert not retired_dir.exists()
        assert (root / Path(gate.GENERATED_ROOT)).is_dir()

    def test_never_leaves_docs_generated(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        outside = root / "docs" / "standards" / "kept.md"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("hand-written\n")
        gate.retire_orphans(root)
        assert outside.exists()

    def test_missing_generated_root_is_a_noop(self, tmp_path: Path) -> None:
        assert gate.retire_orphans(tmp_path) == []


class TestCli:
    def test_verify_exit_codes(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        assert gate.main(["verify", "--root", str(root)]) == 0
        (root / gate.OWNERSHIP[0].producer).unlink()
        assert gate.main(["verify", "--root", str(root)]) == 1

    def test_list_reports_owner_and_orphan(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        root = _make_repo(tmp_path)
        (root / Path(gate.GENERATED_ROOT) / "scripts" / "stale.md").write_text("x\n")
        assert gate.main(["list", "--root", str(root)]) == 0
        out = capsys.readouterr().out
        assert "docs/generated/scripts/stale.md\tORPHAN" in out
        assert "docs/generated/scripts/trigger-map.md\tscripts/script_trigger_map.py" in out

    def test_retire_reports_each_deletion(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        root = _make_repo(tmp_path)
        (root / Path(gate.GENERATED_ROOT) / "scripts" / "stale.md").write_text("x\n")
        assert gate.main(["retire", "--root", str(root)]) == 0
        out = capsys.readouterr().out
        assert "retired orphaned doc: docs/generated/scripts/stale.md" in out
        assert "retired 1 orphaned file(s)" in out


class TestWiring:
    def test_every_producer_is_invoked_by_post_merge(self) -> None:
        # The registry claims must correspond to generators the post-merge
        # automation actually runs; a claim whose producer was unwired is a
        # retirement someone forgot to finish.
        post_merge = (REPO_ROOT / ".github" / "workflows" / "post-merge.yml").read_text()
        for surface in gate.OWNERSHIP:
            assert PurePosixPath(surface.producer).name in post_merge, (
                f"OWNERSHIP producer {surface.producer!r} is not referenced by "
                "post-merge.yml; either wire it or retire its registry entry."
            )

    def test_retire_sweep_is_wired_into_post_merge(self) -> None:
        # Two wirings, not one: the decision-tree job publishes the deletions
        # through the drift PR, and the verify-docs-drift job mirrors the
        # sweep so a tracked orphan already on main (drift PR failed to open
        # or merge) surfaces as a staged deletion instead of a clean diff
        # (Codex review on PR #2233).
        post_merge = (REPO_ROOT / ".github" / "workflows" / "post-merge.yml").read_text()
        assert post_merge.count("verify_generated_docs_ownership.py retire") >= 2

    def test_verify_gate_is_wired_into_preflight(self) -> None:
        import preflight_steps

        commands = {step.argv[1:] for step in preflight_steps.STEPS if len(step.argv) >= 3}
        assert ("scripts/verify_generated_docs_ownership.py", "verify") in commands
