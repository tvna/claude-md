"""Tests for ``scripts/sanitize_history.py``.

Subprocess and network boundaries are exercised by injecting fake
``opener``/``sleeper`` into the ``apply_call``-backed helpers, just like
``tests/test_github_api.py`` and ``tests/test_labels_apply.py``. We never
talk to a real GitHub API.

Refs #102.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import sanitize_history as sh


FIXTURE_MIN = Path(__file__).parent / "fixtures" / "translations_min.json"


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: str = "") -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        return None


def _http_error(code: int, body: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.test", code, "err", {}, _FakeResponse(code, body)
    )


class _OpenerLog:
    """Capture requests + script responses in order."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: urllib.request.Request) -> _FakeResponse:
        self.calls.append({
            "method": request.method,
            "url": request.full_url,
            "data": request.data.decode("utf-8") if request.data else None,
        })
        resp = self.responses.pop(0)
        if isinstance(resp, urllib.error.HTTPError):
            raise resp
        return resp


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestSha256:
    def test_consistent_per_input(self) -> None:
        assert sh.sha256_hex("hello") == sh.sha256_hex("hello")

    def test_differs_for_different_inputs(self) -> None:
        assert sh.sha256_hex("a") != sh.sha256_hex("b")

    def test_handles_non_ascii(self) -> None:
        # Body strings include real Japanese in production data; the
        # SHA must work over the UTF-8 bytes without crashing.
        d = sh.sha256_hex("日本語")  # NIHONGO
        assert len(d) == 64


class TestItemEndpoint:
    def test_issue(self) -> None:
        url = sh.item_endpoint("x/y", {"type": "issue", "number": 7})
        assert url == "https://api.github.com/repos/x/y/issues/7"

    def test_pr_uses_pulls_endpoint(self) -> None:
        url = sh.item_endpoint("x/y", {"type": "pr", "number": 9})
        assert url == "https://api.github.com/repos/x/y/pulls/9"

    def test_issue_comment(self) -> None:
        url = sh.item_endpoint("x/y", {"type": "issue_comment", "comment_id": 42})
        assert url == "https://api.github.com/repos/x/y/issues/comments/42"

    def test_pr_review_comment(self) -> None:
        url = sh.item_endpoint("x/y", {"type": "pr_review_comment", "comment_id": 43})
        assert url == "https://api.github.com/repos/x/y/pulls/comments/43"

    def test_issue_comment_without_comment_id_raises(self) -> None:
        with pytest.raises(ValueError, match="missing comment_id"):
            sh.item_endpoint("x/y", {"type": "issue_comment", "comment_id": None, "id": 1})

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported item type"):
            sh.item_endpoint("x/y", {"type": "bogus"})


class TestIsExcluded:
    def test_no_exclusion_set(self) -> None:
        assert sh.is_excluded({"type": "pr", "number": 5}, set()) is False

    def test_pr_in_excluded(self) -> None:
        assert sh.is_excluded({"type": "pr", "number": 5}, {5}) is True

    def test_issue_never_excluded(self) -> None:
        assert sh.is_excluded({"type": "issue", "number": 5}, {5}) is False

    def test_pr_review_comment_excluded(self) -> None:
        assert sh.is_excluded({"type": "pr_review_comment", "number": 5}, {5}) is True

    def test_pr_not_in_excluded(self) -> None:
        assert sh.is_excluded({"type": "pr", "number": 7}, {5}) is False


class TestParseExcludePrs:
    @pytest.mark.parametrize("raw,expected", [
        ("", set()),
        (None, set()),
        ("5", {5}),
        ("5,7,9", {5, 7, 9}),
        ("5, 7 , 9", {5, 7, 9}),
        ("5,,9", {5, 9}),
    ])
    def test_parse(self, raw: str | None, expected: set[int]) -> None:
        assert sh.parse_exclude_prs(raw) == expected


class TestClassifyDrift:
    def test_live_matches_original_returns_patch(self) -> None:
        assert sh.classify_drift(live="src", original="src", translated="dst") == "patch"

    def test_live_matches_translated_returns_skip(self) -> None:
        assert sh.classify_drift(live="dst", original="src", translated="dst") == "skip"

    def test_live_matches_neither_returns_drift(self) -> None:
        assert sh.classify_drift(live="other", original="src", translated="dst") == "drift"


class TestIndexBackup:
    def test_index_pairs_body_and_title(self) -> None:
        backup = {"items": [
            {"type": "issue", "id": 1, "comment_id": None, "title": "T", "body": "B"},
            {"type": "issue_comment", "id": 2, "comment_id": 2, "title": "", "body": "C"},
        ]}
        idx = sh.index_backup(backup)
        assert idx[("issue", 1, None, "title")] == "T"
        assert idx[("issue", 1, None, "body")] == "B"
        assert idx[("issue_comment", 2, 2, "body")] == "C"
        # comment kinds with empty title are not indexed
        assert ("issue_comment", 2, 2, "title") not in idx


# ---------------------------------------------------------------------------
# run_plan
# ---------------------------------------------------------------------------


class TestRunPlan:
    def test_emits_one_entry_per_actionable_item(self) -> None:
        t = json.loads(FIXTURE_MIN.read_text(encoding="utf-8"))
        plan = sh.run_plan(translations=t, excluded_prs=set())
        assert len(plan) == 3
        assert {entry["type"] for entry in plan} == {"issue", "pr", "issue_comment"}

    def test_exclude_pr_filters_out_target(self) -> None:
        t = json.loads(FIXTURE_MIN.read_text(encoding="utf-8"))
        plan = sh.run_plan(translations=t, excluded_prs={9})
        assert all(entry["type"] != "pr" for entry in plan)
        assert len(plan) == 2


# ---------------------------------------------------------------------------
# run_apply: end-to-end with fake opener
# ---------------------------------------------------------------------------


def _translations_for(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_sha256": "0" * 64,
        "captured_at": "2026-05-24T00:00:00Z",
        "items": items,
    }


def _item(**kw: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "type": "issue",
        "comment_id": None,
        "number": 1,
        "field": "body",
        "original": "src",
        "translated": "dst",
        "confidence": "high",
    }
    base.update(kw)
    return base


class TestRunApplyHappyPath:
    def test_patches_when_live_matches_original(self) -> None:
        t = _translations_for([_item()])
        opener = _OpenerLog([
            _FakeResponse(200, json.dumps({"body": "src"})),
            _FakeResponse(200, json.dumps({"ok": True})),
        ])
        counts = sh.run_apply(
            translations=t, repo="x/y", token="t",
            dry_run=False, batch_size=10, excluded_prs=set(),
            opener=opener, sleeper=lambda _s: None,
        )
        assert counts["patched"] == 1
        assert counts["skipped"] == 0
        assert opener.calls[0]["method"] == "GET"
        assert opener.calls[1]["method"] == "PATCH"
        assert json.loads(opener.calls[1]["data"]) == {"body": "dst"}

    def test_dry_run_skips_patch_call(self) -> None:
        t = _translations_for([_item(), _item(id=2, number=2)])
        opener = _OpenerLog([
            _FakeResponse(200, json.dumps({"body": "src"})),
            _FakeResponse(200, json.dumps({"body": "src"})),
        ])
        counts = sh.run_apply(
            translations=t, repo="x/y", token="t",
            dry_run=True, batch_size=10, excluded_prs=set(),
            opener=opener, sleeper=lambda _s: None,
        )
        assert counts["patched"] == 2
        # 2 GETs only -- no PATCHes
        assert [c["method"] for c in opener.calls] == ["GET", "GET"]

    def test_skips_already_applied_items(self) -> None:
        t = _translations_for([_item()])
        opener = _OpenerLog([
            _FakeResponse(200, json.dumps({"body": "dst"})),  # already translated
        ])
        counts = sh.run_apply(
            translations=t, repo="x/y", token="t",
            dry_run=False, batch_size=10, excluded_prs=set(),
            opener=opener, sleeper=lambda _s: None,
        )
        assert counts["patched"] == 0
        assert counts["skipped"] == 1
        # Only the GET ran -- no PATCH
        assert [c["method"] for c in opener.calls] == ["GET"]


class TestRunApplyDrift:
    def test_drift_aborts_with_systemexit(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        t = _translations_for([_item(), _item(id=2, number=2)])
        opener = _OpenerLog([
            _FakeResponse(200, json.dumps({"body": "edited-by-someone-else"})),
        ])
        with pytest.raises(SystemExit) as excinfo:
            sh.run_apply(
                translations=t, repo="x/y", token="t",
                dry_run=False, batch_size=10, excluded_prs=set(),
                opener=opener, sleeper=lambda _s: None,
            )
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "::error::Drift detected" in err
        # Second item never reached -- only one GET fired.
        assert len(opener.calls) == 1


class TestRunApplyExcludePr:
    def test_excluded_pr_does_not_trigger_api_calls(self) -> None:
        t = _translations_for([_item(type="pr", number=275, id=99)])
        opener = _OpenerLog([])  # any call would IndexError
        counts = sh.run_apply(
            translations=t, repo="x/y", token="t",
            dry_run=False, batch_size=10, excluded_prs={275},
            opener=opener, sleeper=lambda _s: None,
        )
        assert counts["excluded"] == 1
        assert counts["patched"] == 0
        assert opener.calls == []


class TestRunApplyBatchBoundary:
    def test_batch_boundary_printed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        items = [_item(id=i, number=i, original=f"src{i}", translated=f"dst{i}")
                 for i in range(1, 8)]
        # GET responses for 7 items
        responses: list[Any] = []
        for i in range(1, 8):
            responses.append(_FakeResponse(200, json.dumps({"body": f"src{i}"})))
        opener = _OpenerLog(responses)
        sh.run_apply(
            translations=_translations_for(items), repo="x/y", token="t",
            dry_run=True, batch_size=3, excluded_prs=set(),
            opener=opener, sleeper=lambda _s: None,
        )
        out = capsys.readouterr().out
        assert "batch boundary at 3" in out
        assert "batch boundary at 6" in out


# ---------------------------------------------------------------------------
# Retry behaviour: 5xx then 200 is one logical call
# ---------------------------------------------------------------------------


class TestApplyCallRetry:
    def test_get_retries_5xx_until_success(self) -> None:
        t = _translations_for([_item()])
        opener = _OpenerLog([
            _http_error(503, "down"),
            _FakeResponse(200, json.dumps({"body": "src"})),
            _FakeResponse(200, json.dumps({"ok": True})),
        ])
        counts = sh.run_apply(
            translations=t, repo="x/y", token="t",
            dry_run=False, batch_size=10, excluded_prs=set(),
            opener=opener, sleeper=lambda _s: None,
        )
        assert counts["patched"] == 1
        # 1 retried GET (2 opener hits) + 1 PATCH = 3 calls
        assert len(opener.calls) == 3


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class TestCmdPlan:
    def test_prints_json_plan(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = sh.main(["plan", "--in", str(FIXTURE_MIN)])
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["count"] == 3
        assert {entry["type"] for entry in parsed["items"]} == {"issue", "pr", "issue_comment"}

    def test_exclude_pr_flag(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = sh.main(["plan", "--in", str(FIXTURE_MIN), "--exclude-pr", "9"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["count"] == 2


class TestCmdApplyEnvGuards:
    def test_missing_repo_returns_2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.setenv("GH_TOKEN", "fake")
        rc = sh.main(["apply", "--in", str(FIXTURE_MIN)])
        assert rc == 2

    def test_missing_token_returns_2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REPO", "x/y")
        monkeypatch.delenv("GH_TOKEN", raising=False)
        rc = sh.main(["apply", "--in", str(FIXTURE_MIN)])
        assert rc == 2


class TestArgparse:
    def test_unknown_subcommand_exits_nonzero(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            sh.main(["nonsense"])
        assert excinfo.value.code != 0
