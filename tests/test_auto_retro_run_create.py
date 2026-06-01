from __future__ import annotations

from pathlib import Path

import auto_retro as ar
import pytest
from auto_retro_test_helpers import merged_event, orchestrator_recorder

pytestmark = pytest.mark.shard_ci_ops_auto_retro_create


class TestRunCreate:
    def test_happy_path_creates_issue(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            commits=[
                {"commit": {"message": "feat(harness): step one\n\nbody"}},
                {"commit": {"message": "fix(harness): step two"}},
            ],
            created_response={"number": 777, "html_url": "https://x/i/777"},
        )
        event = merged_event(
            number=42,
            title="feat(harness): centralize post-merge tracking",
            labels=[
                {"name": "type:feat"},
                {"name": "layer:p3-harness"},
                {"name": "layer:meta"},
            ],
        )
        assert ar.run(event, "o/r") == 0
        # Final POST is the issue creation; inspect its body.
        post_calls = [
            (m, p, b) for m, p, b in seen if m == "POST" and p == "/repos/o/r/issues"
        ]
        assert len(post_calls) == 1
        _, _, payload = post_calls[0]
        assert payload["title"] == (
            "chore(auto-retro): review PR #42 repair loops"
        )
        assert "feat(harness): step one" in payload["body"]
        assert "fix(harness): step two" in payload["body"]
        assert payload["labels"] == [
            "type:docs", "layer:meta", "layer:p3-harness"
        ]

    def test_step_summary_written_on_create(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        orchestrator_recorder(
            monkeypatch,
            commits=[
                {"commit": {"message": "feat(harness): step one"}},
                {"commit": {"message": "fixup! step one"}},
            ],
        )
        event = merged_event(number=42, commits=2)
        ar.run(event, "o/r")
        text = summary.read_text(encoding="utf-8")
        assert "## auto-retro summary" in text
        assert "`created`" in text
        assert "#42" in text

    def test_check_runs_threaded_into_body_when_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: a failing check_run on the merge SHA produces a
        ``CI fail:`` row inside the created issue body."""
        seen = orchestrator_recorder(
            monkeypatch,
            pr_detail={"merge_commit_sha": "deadbeef"},
            check_runs=[
                {
                    "name": "verify-body-policy",
                    "conclusion": "failure",
                    "completed_at": "2026-05-24T14:36:21Z",
                }
            ],
        )
        assert ar.run(merged_event(number=42), "o/r") == 0
        post_calls = [
            (m, p, b)
            for m, p, b in seen
            if m == "POST" and p == "/repos/o/r/issues"
        ]
        assert len(post_calls) == 1
        body = post_calls[0][2]["body"]
        assert "CI fail: verify-body-policy" in body
        assert "<!-- auto-filled:repair-history -->" in body

    def test_issue_380_reproducer_null_sha_resolves_after_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance criterion 3 of issue #380: re-running the retro
        #345 row 1 scenario must auto-fill the failed ``gate`` check_run
        instead of degrading to the sentinel. PR-detail returns null on
        the first attempt and resolves on the second; the resolved SHA
        feeds the check-runs lookup; the rendered Repair history table
        names the failed check_run and does NOT carry the
        ``(no automated repair signals detected)`` sentinel.
        """
        monkeypatch.setattr(ar.time, "sleep", lambda *_a, **_kw: None)
        seen = orchestrator_recorder(
            monkeypatch,
            pr_detail_sequence=[
                {"merge_commit_sha": None},
                {"merge_commit_sha": "deadbeef"},
            ],
            check_runs=[
                {
                    "id": 77653399942,
                    "name": "gate",
                    "conclusion": "failure",
                    "completed_at": "2026-05-25T03:48:28Z",
                }
            ],
        )
        assert ar.run(merged_event(number=42), "o/r") == 0
        # PR-detail endpoint was called twice (one null + one resolve).
        pr_detail_calls = [
            (m, p)
            for m, p, _b in seen
            if m == "GET" and p == "/repos/o/r/pulls/42"
        ]
        assert len(pr_detail_calls) == 2
        # The created retro issue body carries the gate check_run and
        # not the sentinel: the regression that motivated issue #380
        # would re-emerge if either assertion flips.
        post_calls = [
            (m, p, b)
            for m, p, b in seen
            if m == "POST" and p == "/repos/o/r/issues"
        ]
        assert len(post_calls) == 1
        body = post_calls[0][2]["body"]
        assert "CI fail: gate" in body
        assert "(no automated repair signals detected)" not in body

    def test_back_link_comment_posted_after_create(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() must POST the back-link comment on the source PR after
        create_issue returns. Ordering matters: the back-link references
        the retro number, so the retro must exist first."""
        seen = orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
            commits=[
                {"commit": {"message": "feat(harness): step one"}},
                {"commit": {"message": "fixup! step one"}},
            ],
        )
        assert ar.run(merged_event(number=42, commits=2), "o/r") == 0
        create_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues"
        )
        back_link_post_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues/42/comments"
        )
        assert create_idx < back_link_post_idx, (
            "back-link must be posted after the retro issue is created"
        )
        back_link_call = seen[back_link_post_idx]
        assert back_link_call[2] == {
            "body": f"{ar._BACK_LINK_MARKER}\nRetrospective: #777",
        }

    def test_back_link_patched_when_marker_already_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A re-run on the same merged PR finds an existing back-link
        marker and PATCHes it instead of creating a duplicate."""
        seen = orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
            back_link_comments=[
                {"id": 8675309, "body": f"{ar._BACK_LINK_MARKER}\nold"},
            ],
            commits=[
                {"commit": {"message": "feat(harness): step one"}},
                {"commit": {"message": "fixup! step one"}},
            ],
        )
        assert ar.run(merged_event(number=42, commits=2), "o/r") == 0
        assert any(
            m == "PATCH" and p == "/repos/o/r/issues/comments/8675309"
            for m, p, _b in seen
        )
        # No POST to /issues/{n}/comments when patching.
        assert not any(
            m == "POST" and p.endswith("/issues/42/comments")
            for m, p, _b in seen
        )

    def test_terminal_label_applied_after_back_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() must POST the terminal label to the source PR after the
        back-link comment lands. Ordering matters: a subscribed session
        consumes the labeled webhook as the terminal-state signal, so the
        back-link comment (the human-visible reverse pointer) must already
        be in place by the time the label fires."""
        seen = orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
            commits=[
                {"commit": {"message": "feat(harness): step one"}},
                {"commit": {"message": "fixup! step one"}},
            ],
        )
        assert ar.run(merged_event(number=42, commits=2), "o/r") == 0
        back_link_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues/42/comments"
        )
        label_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues/42/labels"
        )
        assert back_link_idx < label_idx, (
            "terminal label must be POSTed after the back-link comment"
        )
        assert seen[label_idx][2] == {"labels": [ar._TERMINAL_LABEL]}
