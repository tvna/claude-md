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
            title="retro(feat-harness): review PR #200 repair loops"
        )
        assert ar.run(event, "o/r") == 0
        assert seen == []

    def test_skip_when_existing_retro_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = orchestrator_recorder(
            monkeypatch,
            existing=[
                {
                    "number": 100,
                    "title": "retro(feat-harness): review PR #42 repair loops",
                }
            ],
        )
        event = merged_event(number=42)
        assert ar.run(event, "o/r") == 0
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
                    "title": "retro(chore): review PR #42 repair loops",
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
