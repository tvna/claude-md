"""Tests for ``scripts/_security_drift_issues.py`` (rolling per-family issues, #1726)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _security_drift_issues as sdi

pytestmark = pytest.mark.shard_ci_ops_2


# ---------------------------------------------------------------------------
# Pure renderers / matchers
# ---------------------------------------------------------------------------

class TestRenderers:
    def test_title_is_stable_and_date_free(self) -> None:
        # Date-free so a re-detected drift maps to the same rolling issue (#1726).
        assert sdi.render_family_issue_title("labels") == (
            "fix(labels-drift): scheduled drift detected"
        )

    def test_is_family_issue_title_matches_stable_and_legacy(self) -> None:
        stable = sdi.render_family_issue_title("labels")
        assert sdi.is_family_issue_title(stable, stable)
        # Legacy dated titles filed before #1726 still match for consolidation.
        assert sdi.is_family_issue_title(f"{stable} (2026-06-12)", stable)
        # A different family's title must not match.
        assert not sdi.is_family_issue_title(
            sdi.render_family_issue_title("apm-instructions"), stable
        )

    def test_body_is_ascii_and_has_parent_and_remediation(self) -> None:
        body = sdi.render_family_issue_body(
            "uv-pin-literal", run_url="https://x/runs/1", run_date="2026-06-03"
        )
        body.encode("ascii")  # raises if any non-ASCII leaked in
        assert "Parent: #178" in body
        assert "## Remediation" in body
        assert "auto-closed once the drift clears" in body


# ---------------------------------------------------------------------------
# Reconcile orchestration (apply boundary injected)
# ---------------------------------------------------------------------------

def _labels_issue(number: int, *, dated: str | None = None) -> dict[str, Any]:
    title = "fix(labels-drift): scheduled drift detected"
    if dated is not None:
        title = f"{title} ({dated})"
    return {"number": number, "title": title}


def _fake_apply(
    open_issues: list[dict[str, Any]] | None = None,
    *,
    get_code: int = 200,
    write_code: int = 201,
) -> tuple[Any, list[dict[str, Any]]]:
    """Build an injectable apply: GET returns ``open_issues`` as JSON; every
    write (POST/PATCH) returns ``write_code``. Records all calls."""
    body = json.dumps(open_issues or [])
    calls: list[dict[str, Any]] = []

    def fake(**kwargs: Any) -> tuple[int, str]:
        calls.append(kwargs)
        if kwargs["method"] == "GET":
            return get_code, body
        return write_code, "{}"

    return fake, calls


def _reconcile(
    fake: Any,
    drifting: list[str],
    *,
    resolved: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    return sdi.reconcile_family_issues(
        apply=fake,
        repo="owner/repo",
        run_url="https://x/runs/1",
        run_date="2026-06-03",
        drifting=drifting,
        resolved=resolved or [],
        dry_run=dry_run,
    )


class TestReconcile:
    def test_dry_run_does_not_call_api(self) -> None:
        def fake(**_kwargs: Any) -> tuple[int, str]:
            raise AssertionError("should not be called")

        assert _reconcile(fake, ["labels", "uv-pin-literal"], dry_run=True) == 0

    def test_creates_when_no_open_issue(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, calls = _fake_apply([])
        monkeypatch.setenv("GH_TOKEN", "tkn")
        assert _reconcile(fake, ["labels", "apm-instructions"]) == 0
        gets = [c for c in calls if c["method"] == "GET"]
        creates = [
            c for c in calls
            if c["method"] == "POST" and c["url"].endswith("/repos/owner/repo/issues")
        ]
        # One list call, then one create per drifting family; the two resolved
        # families with no open issue trigger no calls.
        assert len(gets) == 1
        assert len(creates) == 2
        assert creates[0]["payload"]["labels"] == list(sdi.issue_labels())
        assert creates[0]["payload"]["title"] == (
            "fix(labels-drift): scheduled drift detected"
        )

    def test_dedupes_keeping_oldest_when_drifting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Three stacked labels issues (the #1432/#1507/#1653 pile-up).
        open_issues = [
            _labels_issue(1653, dated="2026-06-12"),
            _labels_issue(1432, dated="2026-06-07"),
            _labels_issue(1507, dated="2026-06-09"),
        ]
        fake, calls = _fake_apply(open_issues)
        monkeypatch.setenv("GH_TOKEN", "tkn")
        assert _reconcile(fake, ["labels"]) == 0
        # Oldest (#1432) stays open; #1507 and #1653 are each commented + closed.
        patched = [c for c in calls if c["method"] == "PATCH"]
        closed_numbers = {int(c["url"].rsplit("/", 1)[-1]) for c in patched}
        assert closed_numbers == {1507, 1653}
        assert all(c["payload"]["state"] == "closed" for c in patched)
        # No new issue is created when one already exists.
        assert not [
            c for c in calls
            if c["method"] == "POST" and c["url"].endswith("/issues")
        ]

    def test_silent_when_single_open_issue_for_drifting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake, calls = _fake_apply([_labels_issue(1432)])  # already canonical
        monkeypatch.setenv("GH_TOKEN", "tkn")
        assert _reconcile(fake, ["labels"]) == 0
        # Only the list GET happens: no create, no close.
        assert [c["method"] for c in calls] == ["GET"]

    def test_auto_closes_resolved_family(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake, calls = _fake_apply([_labels_issue(1432, dated="2026-06-07")])
        monkeypatch.setenv("GH_TOKEN", "tkn")
        # labels is EXPLICITLY covered -> close its open issue.
        assert _reconcile(fake, [], resolved=["labels"]) == 0
        patched = [c for c in calls if c["method"] == "PATCH"]
        assert len(patched) == 1
        assert patched[0]["url"].endswith("/repos/owner/repo/issues/1432")
        assert patched[0]["payload"]["state"] == "closed"

    def test_error_family_left_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A detector error puts labels in NEITHER list. Its open rolling issue
        # must NOT be auto-closed, or a transient failure would hide active drift
        # (#1730 review). Only the list GET happens.
        fake, calls = _fake_apply([_labels_issue(1432, dated="2026-06-07")])
        monkeypatch.setenv("GH_TOKEN", "tkn")
        assert _reconcile(fake, [], resolved=[]) == 0
        assert [c["method"] for c in calls] == ["GET"]

    def test_missing_token_exits_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        fake, _calls = _fake_apply([])
        assert _reconcile(fake, ["labels"]) == 1

    def test_list_failure_exits_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, _calls = _fake_apply([], get_code=422)
        monkeypatch.setenv("GH_TOKEN", "tkn")
        assert _reconcile(fake, ["labels"]) == 1


# ---------------------------------------------------------------------------
# list_open_family_issues filtering
# ---------------------------------------------------------------------------

class TestListOpenFamilyIssues:
    def test_drops_pull_requests_and_malformed(self) -> None:
        fake, _calls = _fake_apply(
            [
                {"number": 1, "title": "fix(labels-drift): scheduled drift detected"},
                {"number": 2, "title": "a PR", "pull_request": {"url": "x"}},
                {"number": "bad", "title": "no int number"},
            ]
        )
        result = sdi.list_open_family_issues(fake, "owner/repo", "tkn")
        assert result == [(1, "fix(labels-drift): scheduled drift detected")]

    def test_returns_none_on_failed_get(self) -> None:
        fake, _calls = _fake_apply([], get_code=500)
        assert sdi.list_open_family_issues(fake, "owner/repo", "tkn") is None

    def test_query_filters_on_type_label_only(self) -> None:
        # Regression: the classic issues-list `labels` param is AND-only, so
        # filtering on the full issue_labels() set (layer + area + type) would
        # make an issue filed under an older label set (e.g. before the
        # #1041/#2313 successor migration) undiscoverable, causing a
        # duplicate to be filed. Only the stable `type:*` label narrows this
        # query; is_family_issue_title does the real per-family narrowing.
        fake, calls = _fake_apply([])
        sdi.list_open_family_issues(fake, "owner/repo", "tkn")
        assert len(calls) == 1
        url = calls[0]["url"]
        assert "labels=type%3Afix" in url
        assert "layer" not in url
        assert "area" not in url
