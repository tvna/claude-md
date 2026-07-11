from __future__ import annotations

from pathlib import Path

import auto_retro as ar
import pytest
from auto_retro_test_helpers import merged_event, orchestrator_recorder

pytestmark = pytest.mark.shard_ci_ops_auto_retro_skips


class TestRunSkips:
    def test_skip_when_not_merged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(monkeypatch)
        event = merged_event(merged=False)
        assert ar.run(event, "o/r") == 0
        assert seen == []

    def test_skip_when_merged_by_dependabot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(monkeypatch)
        event = merged_event(merged_by={"login": "dependabot[bot]"})
        assert ar.run(event, "o/r") == 0
        assert seen == []

    def test_skip_when_pr_is_retro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(monkeypatch)
        event = merged_event(
            title="fix(auto-retro): review PR #200 repair loops"
        )
        assert ar.run(event, "o/r") == 0
        assert seen == []

    @pytest.mark.parametrize(
        "existing_number,title_prefix",
        [(100, "fix"), (200, "chore")],
        ids=["legacy-prefix", "canonical-prefix"],
    )
    def test_skip_when_existing_retro_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        existing_number: int,
        title_prefix: str,
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            existing=[{
                "number": existing_number,
                "title": f"{title_prefix}(auto-retro): review PR #42 repair loops",
            }],
        )
        assert ar.run(merged_event(number=42), "o/r") == 0
        # Only the search call should fire; no commits fetch, no create.
        methods_paths = [(c[0], c[1]) for c in seen]
        assert any("/search/issues" in p for _, p in methods_paths)
        assert not any("/commits" in p for _, p in methods_paths)
        assert not any(p == "/repos/o/r/issues" for _, p in methods_paths)

    def test_skip_when_existing_retro_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            existing=[
                {
                    "number": 50,
                    "title": "fix(auto-retro): review PR #42 repair loops",
                    "state": "closed",
                }
            ],
        )
        assert ar.run(merged_event(number=42), "o/r") == 0
        assert not any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_skip_when_zero_review_comments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive-control merge: no inline review comments -> no retro."""
        seen = orchestrator_recorder(monkeypatch, review_comments=[])
        assert ar.run(merged_event(number=42), "o/r") == 0
        # Comments endpoint must have been queried.
        assert any(
            method == "GET" and "/comments" in path
            for method, path, _ in seen
        )
        # No commits fetch, no issue creation.
        assert not any(
            method == "GET" and "/commits" in path
            for method, path, _ in seen
        )
        assert not any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_step_summary_written_on_skip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        orchestrator_recorder(monkeypatch)
        ar.run(merged_event(merged=False), "o/r")
        text = summary.read_text(encoding="utf-8")
        assert "## auto-retro summary" in text
        assert "`skip`" in text


class TestSkipComment:
    """Skip-notification comment posted when auto-retro evaluates but skips.

    Covers issue #932: without a comment, operators cannot tell whether the
    background job ran and intentionally skipped or crashed silently.
    """

    def _is_skip_comment_post(
        self, method: str, path: str, body: object
    ) -> bool:
        return (
            method == "POST"
            and path.endswith("/comments")
            and isinstance(body, dict)
            and ar._SKIP_COMMENT_MARKER in (body.get("body") or "")
        )

    def test_skip_comment_posted_for_no_signal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No repair signals -> skip comment on source PR (opt-in #1386)."""
        monkeypatch.setenv("AUTO_RETRO_PR_COMMENTS", "1")
        seen = orchestrator_recorder(monkeypatch, review_comments=[])
        assert ar.run(merged_event(number=42), "o/r") == 0
        assert any(self._is_skip_comment_post(*t) for t in seen)

    def test_skip_comment_posted_for_prior_skip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prior FP rate skip also posts a skip comment (opt-in #1386)."""
        monkeypatch.setenv("AUTO_RETRO_PR_COMMENTS", "1")
        monkeypatch.setattr(
            ar,
            "should_skip_by_prior",
            lambda *_: (True, "prior FP rate 0.90 (n=50)"),
        )
        seen = orchestrator_recorder(monkeypatch)  # default has review comment
        assert ar.run(merged_event(number=42), "o/r") == 0
        assert any(self._is_skip_comment_post(*t) for t in seen)

    def test_prior_skip_tags_cofire_marker_for_multi_commit_alone(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """#2463 review: when the label prior skips a multi_commit_pr-alone
        PR, the recorded reason still carries the greppable interim co-fire
        marker (#2436) so the Phase 2 measurement counts prior-suppressed
        lone-signal cases too, not only the exempt-rows path. The prior gate
        still decides the skip; only the recorded reason gains the marker.
        """
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setattr(
            ar,
            "should_skip_by_prior",
            lambda *_: (True, "prior FP rate 0.90 (n=50)"),
        )
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {"commit": {"message": "feat(x): add a"}},
                {"commit": {"message": "feat(x): add b"}},
            ],
        )
        event = merged_event(
            number=2463, title="feat(x): rework", body="", commits=2
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        printed = capsys.readouterr().out
        # The prior reason AND the greppable co-fire marker are both recorded.
        assert "prior FP rate 0.90" in printed
        assert ar._INTERIM_COFIRE_MARKER in printed
        assert ar._INTERIM_COFIRE_MARKER in summary.read_text(encoding="utf-8")

    def test_skip_comment_idempotent_patches_existing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rerun updates an existing skip comment via PATCH, not a new POST.

        PR-thread comments are opt-in since #1386, so the flag is set."""
        monkeypatch.setenv("AUTO_RETRO_PR_COMMENTS", "1")
        seen = orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            back_link_comments=[
                {
                    "id": 777,
                    "body": (
                        f"{ar._SKIP_COMMENT_MARKER}\n"
                        "auto-retro skipped: previous reason"
                    ),
                }
            ],
        )
        assert ar.run(merged_event(number=42), "o/r") == 0
        assert any(
            method == "PATCH" and "/issues/comments/777" in path
            for method, path, _ in seen
        )
        assert not any(self._is_skip_comment_post(*t) for t in seen)

    def test_skip_comment_fail_soft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Network error posting skip comment must not change the exit code.

        PR-thread comments are opt-in since #1386, so the flag is set."""
        monkeypatch.setenv("AUTO_RETRO_PR_COMMENTS", "1")
        orchestrator_recorder(
            monkeypatch, review_comments=[], back_link_post_error=True
        )
        assert ar.run(merged_event(number=42), "o/r") == 0

    def test_structural_skips_do_not_post_skip_comment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Structural skips leave no comment; only evaluation skips do."""
        structural_events = [
            merged_event(merged=False),
            merged_event(merged_by={"login": "dependabot[bot]"}),
            merged_event(title="fix(auto-retro): review PR #200 repair loops"),
        ]
        for event in structural_events:
            seen = orchestrator_recorder(monkeypatch)
            assert ar.run(event, "o/r") == 0
            assert not any(
                method == "POST" and "/comments" in path
                for method, path, _ in seen
            ), f"Unexpected skip comment posted for {event}"

    @pytest.mark.parametrize(
        "existing_number,title_prefix",
        [(100, "fix"), (200, "chore")],
        ids=["legacy-prefix", "canonical-prefix"],
    )
    def test_existing_retro_skip_does_not_post_skip_comment(
        self,
        monkeypatch: pytest.MonkeyPatch,
        existing_number: int,
        title_prefix: str,
    ) -> None:
        """When a retro already exists the PR has a back-link; no skip comment."""
        seen = orchestrator_recorder(
            monkeypatch,
            existing=[{
                "number": existing_number,
                "title": f"{title_prefix}(auto-retro): review PR #42 repair loops",
            }],
        )
        assert ar.run(merged_event(number=42), "o/r") == 0
        assert not any(self._is_skip_comment_post(*t) for t in seen)

    def test_skip_comment_off_by_default_no_signal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default (no AUTO_RETRO_PR_COMMENTS): an evaluation skip posts no
        comment; the skip is recorded only in the step summary (#1386)."""
        monkeypatch.delenv("AUTO_RETRO_PR_COMMENTS", raising=False)
        seen = orchestrator_recorder(monkeypatch, review_comments=[])
        assert ar.run(merged_event(number=42), "o/r") == 0
        assert not any(self._is_skip_comment_post(*t) for t in seen)

    def test_skip_comment_off_by_default_prior_skip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default: a prior-FP skip also posts no comment (#1386)."""
        monkeypatch.delenv("AUTO_RETRO_PR_COMMENTS", raising=False)
        monkeypatch.setattr(
            ar,
            "should_skip_by_prior",
            lambda *_: (True, "prior FP rate 0.90 (n=50)"),
        )
        seen = orchestrator_recorder(monkeypatch)
        assert ar.run(merged_event(number=42), "o/r") == 0
        assert not any(self._is_skip_comment_post(*t) for t in seen)
