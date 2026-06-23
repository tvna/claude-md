from __future__ import annotations

from pathlib import Path

import auto_retro as ar
import pytest
from auto_retro_test_helpers import merged_event, orchestrator_recorder

pytestmark = pytest.mark.shard_ci_ops_auto_retro_signals


class TestRunAggregateSignals:
    """Coverage for the issue #298 aggregate-gate behavior on top of TestRun."""

    def test_skips_when_zero_comments_body_refs_have_no_standalone_work(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(monkeypatch, review_comments=[])
        event = merged_event(number=300, body="Refs #287\nRefs #298")
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_skips_g2_no_signal_rows_even_with_review_comments(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """G2-style retro noise: a signal fires, but the repair table
        would contain only the no-automated-signal sentinel.

        Refs #595. Mirrors #592's G2 examples, including #585.
        """
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[{"id": 1, "body": "comment without row data"}],
            commits=[
                {
                    "commit": {
                        "message": (
                            "docs(security): establish ATT&CK review cadence"
                        )
                    }
                }
            ],
        )
        event = merged_event(
            number=583,
            title="docs(security): establish ATT&CK review cadence",
            body="",
            commits=1,
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        printed = capsys.readouterr().out
        assert "no standalone repair workload" in printed
        assert "no standalone repair workload" in summary.read_text(
            encoding="utf-8"
        )

    def test_skips_when_body_has_only_failed_verification(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Refs #1236: verification-prose failures are non-actionable
        # policy-artifact anomaly hints. A PR whose only repair evidence is
        # a failed `## Verification` row no longer opens a retro; the prose
        # heuristic over untrusted body text was the dominant FP source.
        seen = orchestrator_recorder(monkeypatch, review_comments=[])
        event = merged_event(
            number=300,
            body=(
                "Refs #287\n\n"
                "## Verification\n\n"
                "- command: `pytest`\n"
                "  result: `failed: 3 tests broken`\n"
            ),
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        assert "no repair signal fired" in capsys.readouterr().out

    def test_skips_when_zero_comments_fix_typed_has_only_canonical_fix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[{"commit": {"message": "fix(harness): qualify gate names"}}],
        )
        event = merged_event(
            number=301, title="fix(harness): qualify gate names", commits=1
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_creates_retro_when_zero_comments_but_iteration_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {"commit": {"message": "feat(harness): add first"}},
                {"commit": {"message": "fixup! add first"}},
            ],
        )
        event = merged_event(number=302, commits=2)
        assert ar.run(event, "o/r") == 0
        assert any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_skips_when_only_signal_is_rebase_debt_multi_commit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """multi_commit_pr must not fire on rebase debt alone.

        Event reports ``commits=2`` but the commit list contains one
        merge-from-main commit plus one real development commit, so
        ``pure_commits == 1`` and the gate stays False. With no other
        signal firing, run() must skip without creating a retro.
        """
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {
                    "commit": {
                        "message": "Merge branch 'main' into feature\n"
                    }
                },
                {"commit": {"message": "feat(x): add x"}},
            ],
        )
        event = merged_event(
            number=304,
            title="feat(x): add x",
            body="",
            commits=2,
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        assert "multi_commit_pr=false" in capsys.readouterr().out

    def test_skips_when_only_signal_is_revert_multi_commit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A revert-only multi-commit PR must not open a retro (#1287).

        Event reports ``commits=2`` but the commit list is one revert plus
        the original commit, so ``pure_commits == 1`` and multi_commit_pr
        stays False. With no other signal firing, run() must skip.
        """
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {"commit": {"message": 'Revert "feat(x): add x"\n'}},
                {"commit": {"message": "feat(x): add x"}},
            ],
        )
        event = merged_event(
            number=1287,
            title="revert(x): roll back add x",
            body="",
            commits=2,
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        assert "multi_commit_pr=false" in capsys.readouterr().out

    def test_opens_retro_when_revert_co_fires_with_review_comment(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A revert co-firing with an inline review comment opens a retro:
        the revert alone is suppressed, but the co-fire signal carries it."""
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[{"id": 1, "body": "please rework this rollback"}],
            commits=[
                {"commit": {"message": 'Revert "feat(x): add x"\n'}},
                {"commit": {"message": "feat(x): add x"}},
            ],
        )
        event = merged_event(
            number=1288,
            title="revert(x): roll back add x",
            body="",
            commits=2,
        )
        assert ar.run(event, "o/r") == 0
        assert any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_revert_subtraction_is_precise_but_still_needs_co_fire(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Revert is subtracted without over-suppressing real multi-commit.

        With two real dev commits left after subtracting the revert,
        ``multi_commit_pr`` stays True (the subtraction is precise); but a
        revert-bearing multi-commit PR whose rows are all policy-artifact and
        with no co-firing actionable signal (review / CI / verification) still
        skips. Per the user's design: multi-commit alone cannot determine an
        anomaly; it needs a co-fire. Refs #1287.
        """
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {"commit": {"message": 'Revert "feat(x): add x"\n'}},
                {"commit": {"message": "feat(x): add a"}},
                {"commit": {"message": "feat(x): add b"}},
            ],
        )
        event = merged_event(
            number=1289,
            title="feat(x): rework feature",
            body="",
            commits=3,
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        # Proves the revert was subtracted but the two real commits remain.
        assert "multi_commit_pr=true" in capsys.readouterr().out

    def test_skips_policy_artifact_only_rows_even_when_refs_fire(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """G1-style retro noise: refs plus merge/multi rows only.

        Refs #594. Mirrors the #592 examples where the generated Repair
        history table contains only exempt policy-artifact rows.
        """
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        # PR-thread skip comments are opt-in since #1386.
        monkeypatch.setenv("AUTO_RETRO_PR_COMMENTS", "1")
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {
                    "commit": {
                        "message": "Merge branch 'main' into feature\n"
                    }
                },
                {"commit": {"message": "feat(harness): add first"}},
                {"commit": {"message": "docs(harness): add second"}},
            ],
        )
        event = merged_event(
            number=576,
            title="feat(harness): G1 policy artifact example",
            body="Refs #592",
            commits=3,
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        printed = capsys.readouterr().out
        assert "only policy-artifact repair rows generated" in printed
        assert "only policy-artifact repair rows generated" in summary.read_text(
            encoding="utf-8"
        )
        assert any(
            m == "POST"
            and p == "/repos/o/r/issues/576/comments"
            and isinstance(b, dict)
            and ar._SKIP_COMMENT_MARKER in (b.get("body") or "")
            for m, p, b in seen
        )

    def test_policy_artifact_rows_plus_ci_failure_still_creates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {
                    "commit": {
                        "message": "Merge branch 'main' into feature\n"
                    }
                },
                {"commit": {"message": "feat(harness): add first"}},
                {"commit": {"message": "docs(harness): add second"}},
            ],
            pr_detail={"merge_commit_sha": "deadbeef"},
            check_runs=[
                {
                    "name": "verify-agents",
                    "conclusion": "failure",
                    "completed_at": "2026-05-28T00:00:00Z",
                }
            ],
        )
        event = merged_event(
            number=588,
            title="feat(harness): G1 plus real CI failure",
            body="Refs #592",
            commits=3,
        )
        assert ar.run(event, "o/r") == 0
        assert any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_policy_artifact_rows_plus_review_repair_still_creates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[{"id": 1, "body": "fix requested"}],
            commits=[
                {
                    "commit": {
                        "message": "Merge branch 'main' into feature\n"
                    }
                },
                {"commit": {"message": "feat(harness): add first"}},
                {"commit": {"message": "docs(harness): add second"}},
            ],
        )
        event = merged_event(
            number=589,
            title="feat(harness): G1 plus review repair",
            body="Refs #592",
            commits=3,
        )
        assert ar.run(event, "o/r") == 0
        assert any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_policy_artifact_rows_plus_iteration_commit_still_creates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {
                    "commit": {
                        "message": "Merge branch 'main' into feature\n"
                    }
                },
                {"commit": {"message": "feat(harness): add first"}},
                {"commit": {"message": "fixup! add first"}},
            ],
        )
        event = merged_event(
            number=590,
            title="feat(harness): G1 plus iteration commit",
            body="Refs #592",
            commits=3,
        )
        assert ar.run(event, "o/r") == 0
        assert any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_skips_with_detailed_reason_when_no_signal_fires(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        seen = orchestrator_recorder(monkeypatch, review_comments=[])
        event = merged_event(
            number=303, title="docs: tweak", body="", commits=1
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        printed = capsys.readouterr().out
        assert "no repair signal fired" in printed
        assert "inline_review_comments=false" in printed
        assert "fix_typed_title=false" in printed
        assert "multi_commit_pr=false" in printed
        # Step summary also carries the same reason for the audit trail.
        assert "no repair signal fired" in summary.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Post-2026-05-26 PR shape readers (issue #fluffy-bubble)
# ---------------------------------------------------------------------------
