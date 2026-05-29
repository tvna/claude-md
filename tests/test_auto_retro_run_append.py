from __future__ import annotations

import json

import auto_retro as ar
import pytest
from auto_retro_test_helpers import merged_event

pytestmark = pytest.mark.shard_ci_ops_auto_retro_append


class TestRunAppendBranch:
    """Tests run() routing a fix-typed PR to append rather than create."""

    _RETRO_BODY = (
        "## Scope\n\nx\n"
        "<!-- auto-filled:repair-history -->\n"
        "| # | Repair | What |\n"
        "|---|--------|------|\n"
        "<!-- /auto-filled:repair-history -->\n"
    )

    def _setup(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        retro_title: str,
        retro_body: str = "",
    ) -> list[tuple]:
        seen: list[tuple] = []
        retro_body = retro_body or self._RETRO_BODY

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET" and path.startswith("/search/issues"):
                return json.dumps({"items": []})
            if method == "GET" and path == "/repos/o/r/issues/66":
                return json.dumps(
                    {"title": retro_title, "body": retro_body}
                )
            if method == "GET" and "/pulls/" in path and "/comments" in path:
                return json.dumps([])
            if method == "GET" and "/pulls/" in path and "/commits" in path:
                return json.dumps([])
            if method == "GET" and "/check-runs" in path:
                return json.dumps({"check_runs": []})
            if method == "GET" and "/pulls/" in path:
                return json.dumps({"merge_commit_sha": None})
            if method == "POST" and path.endswith("/issues"):
                return json.dumps(
                    {"number": 999, "html_url": "https://x/i/999"}
                )
            if method == "PATCH":
                return json.dumps({"number": 66})
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        return seen

    def test_fix_pr_referencing_retro_triggers_append(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = self._setup(
            monkeypatch,
            retro_title="fix(auto-retro): review PR #20 repair loops",
        )
        event = merged_event(
            number=77,
            title="fix(harness): patch",
            body="Refs #66\n",
        )
        assert ar.run(event, "o/r") == 0
        assert any(m == "PATCH" for m, _, _ in seen)
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_fix_pr_referencing_non_retro_creates_normally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = self._setup(
            monkeypatch,
            retro_title="feat(harness): not a retro",
        )
        event = merged_event(
            number=78,
            title="fix(harness): patch",
            body="Refs #66\n",
        )
        # Without a retro target, run() falls through to create_issue
        # via the standard signal aggregate (multi_commit, fix_typed,
        # etc.). fix_typed_title fires for this title, so an issue is
        # created.
        assert ar.run(event, "o/r") == 0
        # PATCH must NOT fire because no retro was found.
        assert not any(m == "PATCH" for m, _, _ in seen)
