from __future__ import annotations

import auto_retro as ar
import pytest
from auto_retro_test_helpers import merged_event, orchestrator_recorder

pytestmark = pytest.mark.shard_ci_ops_auto_retro_create_slow


class TestRunCreateFailSoft:
    def test_fail_safe_creates_when_comments_endpoint_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient API failure on the comments lookup must NOT silently
        skip the retro. Fall back to creating the issue."""
        seen = orchestrator_recorder(
            monkeypatch,
            comments_error=True,
            commits=[
                {"commit": {"message": "feat(harness): step one"}},
                {"commit": {"message": "fixup! step one"}},
            ],
        )
        assert ar.run(merged_event(number=42, commits=2), "o/r") == 0
        # Issue creation must still happen (fail-safe path).
        assert any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_fail_soft_creates_when_check_runs_endpoint_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient API failure on the check-runs lookup must NOT block
        retro creation. Issue #343 fail-soft contract."""
        seen = orchestrator_recorder(monkeypatch, check_runs_error=True)
        assert ar.run(merged_event(number=42), "o/r") == 0
        # Issue creation must still happen.
        assert any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_back_link_failure_does_not_abort_retro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the back-link POST fails, run() must still return 0 -- the
        retro issue is already created and rolling it back would be
        worse than a missing back-link.

        PR-thread comments are opt-in since #1386, so the flag is set."""
        monkeypatch.setenv("AUTO_RETRO_PR_COMMENTS", "1")
        seen = orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
            back_link_post_error=True,
            commits=[
                {"commit": {"message": "feat(harness): step one"}},
                {"commit": {"message": "fixup! step one"}},
            ],
        )
        assert ar.run(merged_event(number=42, commits=2), "o/r") == 0
        # Issue creation happened.
        assert any(
            m == "POST" and p == "/repos/o/r/issues"
            for m, p, _b in seen
        )

    def test_terminal_label_failure_does_not_abort_retro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the label POST fails, run() must still return 0 -- the retro
        issue and back-link comment are already in place; the label is a
        secondary signal and must not roll back the audit trail.

        PR-thread comments are opt-in since #1386, so the flag is set."""
        monkeypatch.setenv("AUTO_RETRO_PR_COMMENTS", "1")
        seen = orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
            terminal_label_post_error=True,
            commits=[
                {"commit": {"message": "feat(harness): step one"}},
                {"commit": {"message": "fixup! step one"}},
            ],
        )
        assert ar.run(merged_event(number=42, commits=2), "o/r") == 0
        # Retro creation and back-link both landed before the failing label.
        assert any(
            m == "POST" and p == "/repos/o/r/issues"
            for m, p, _b in seen
        )
        assert any(
            m == "POST" and p == "/repos/o/r/issues/42/comments"
            for m, p, _b in seen
        )
