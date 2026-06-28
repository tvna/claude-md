"""Tests for ``scripts/np_strategy_tracking.py``.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``. Refs #1035.
"""

from __future__ import annotations

import json
from typing import Any

import np_strategy_tracking as nps
import pytest

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# plan_label_swap
# ---------------------------------------------------------------------------


class TestPlanLabelSwap:
    def test_swaps_normal_type_to_tracking(self) -> None:
        plan = nps.plan_label_swap(["type:fix", "layer:p3-harness"])
        assert plan["already_tracking"] is False
        assert plan["removed"] == ["type:fix"]
        assert plan["result"] == ["layer:p3-harness", "type:tracking"]

    def test_already_tracking_is_noop(self) -> None:
        plan = nps.plan_label_swap(["type:tracking", "layer:meta"])
        assert plan["already_tracking"] is True
        assert plan["removed"] == []
        assert plan["result"] == ["layer:meta", "type:tracking"]

    def test_no_type_label_adds_tracking(self) -> None:
        plan = nps.plan_label_swap(["layer:p3-harness"])
        assert plan["already_tracking"] is False
        assert plan["removed"] == []
        assert plan["result"] == ["layer:p3-harness", "type:tracking"]

    def test_multiple_type_labels_collapse_to_one(self) -> None:
        plan = nps.plan_label_swap(["type:fix", "type:tracking", "area:docs"])
        assert plan["already_tracking"] is False
        assert plan["removed"] == ["type:fix"]
        # The tracking label appears once; non-type order preserved.
        assert plan["result"] == ["area:docs", "type:tracking"]

    def test_empty_labels_add_tracking(self) -> None:
        plan = nps.plan_label_swap([])
        assert plan["already_tracking"] is False
        assert plan["result"] == ["type:tracking"]

    def test_preserves_non_type_order(self) -> None:
        plan = nps.plan_label_swap(["b:two", "a:one", "type:feat"])
        assert plan["result"] == ["b:two", "a:one", "type:tracking"]


# ---------------------------------------------------------------------------
# format_rationale
# ---------------------------------------------------------------------------


class TestFormatRationale:
    def test_contains_core_facts(self) -> None:
        text = nps.format_rationale(1005, [1033, 1034], ["type:fix"])
        assert "type:tracking" in text
        assert "#1005" in text
        assert "#1033, #1034" in text
        assert "'type:fix'" in text
        assert "Refs #1035." in text
        assert text.isascii()

    def test_no_prs_and_no_removed(self) -> None:
        text = nps.format_rationale(7, [], [])
        assert "(none specified)" in text
        assert "(no prior type label)" in text
        assert text.isascii()

    def test_optional_reason_appended(self) -> None:
        text = nps.format_rationale(7, [1], ["type:feat"], reason="stacked")
        assert "Reason: stacked" in text


# ---------------------------------------------------------------------------
# parse_prs
# ---------------------------------------------------------------------------


class TestParsePrs:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("", []),
            (None, []),
            ("1033,1034", [1033, 1034]),
            ("1033 1034", [1033, 1034]),
            ("#1033, #1034", [1033, 1034]),
            ("  1033 ,  1034  ", [1033, 1034]),
        ],
    )
    def test_variants(self, raw: str | None, expected: list[int]) -> None:
        assert nps.parse_prs(raw) == expected

    def test_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError):
            nps.parse_prs("not-a-number")


# ---------------------------------------------------------------------------
# Fake GitHub boundary
# ---------------------------------------------------------------------------


class _FakeApi:
    """Records calls and replays programmed (code, body) responses."""

    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, method: str, url: str, payload, token: str, **_k):
        self.calls.append(
            {"method": method, "url": url, "payload": payload, "token": token}
        )
        if self._responses:
            return self._responses.pop(0)
        return (200, "{}")


# ---------------------------------------------------------------------------
# fetch_labels
# ---------------------------------------------------------------------------


class TestFetchLabels:
    def test_parses_dict_and_string_entries(self) -> None:
        body = json.dumps(
            {"labels": [{"name": "type:fix"}, "layer:p3-harness"]}
        )
        api = _FakeApi([(200, body)])
        assert nps.fetch_labels("o/r", 5, "t", apply_call=api) == [
            "type:fix",
            "layer:p3-harness",
        ]
        assert api.calls[0]["method"] == "GET"
        assert api.calls[0]["url"].endswith("/repos/o/r/issues/5")

    def test_non_2xx_raises(self) -> None:
        api = _FakeApi([(404, "not found")])
        with pytest.raises(RuntimeError):
            nps.fetch_labels("o/r", 5, "t", apply_call=api)


# ---------------------------------------------------------------------------
# put_labels / post_comment
# ---------------------------------------------------------------------------


class TestMutations:
    def test_put_labels_success(self) -> None:
        api = _FakeApi([(200, "[]")])
        assert nps.put_labels("o/r", 5, ["type:tracking"], "t", apply_call=api) == 200
        call = api.calls[0]
        assert call["method"] == "PUT"
        assert call["url"].endswith("/repos/o/r/issues/5/labels")
        assert call["payload"] == {"labels": ["type:tracking"]}

    def test_put_labels_failure_raises(self) -> None:
        api = _FakeApi([(422, "bad")])
        with pytest.raises(RuntimeError):
            nps.put_labels("o/r", 5, ["type:tracking"], "t", apply_call=api)

    def test_post_comment_success(self) -> None:
        api = _FakeApi([(201, "{}")])
        assert nps.post_comment("o/r", 5, "hello", "t", apply_call=api) == 201
        call = api.calls[0]
        assert call["method"] == "POST"
        assert call["url"].endswith("/repos/o/r/issues/5/comments")
        assert call["payload"] == {"body": "hello"}

    def test_post_comment_failure_raises(self) -> None:
        api = _FakeApi([(500, "err")])
        with pytest.raises(RuntimeError):
            nps.post_comment("o/r", 5, "hello", "t", apply_call=api)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    def test_plan_mode_does_not_mutate(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = json.dumps({"labels": [{"name": "type:fix"}]})
        api = _FakeApi([(200, body)])
        rc = nps.run(
            mode="plan",
            repo="o/r",
            issue=1005,
            prs=[1033, 1034],
            reason=None,
            token="t",
            apply_call=api,
        )
        assert rc == 0
        # Only the GET happened; no PUT, no POST.
        assert [c["method"] for c in api.calls] == ["GET"]
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "type:tracking" in out

    def test_apply_mode_swaps_and_comments(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = json.dumps({"labels": [{"name": "type:fix"}, "layer:p3-harness"]})
        api = _FakeApi([(200, body), (200, "[]"), (201, "{}")])
        rc = nps.run(
            mode="apply",
            repo="o/r",
            issue=1005,
            prs=[1033, 1034],
            reason=None,
            token="t",
            apply_call=api,
        )
        assert rc == 0
        methods = [c["method"] for c in api.calls]
        assert methods == ["GET", "PUT", "POST"]
        put_call = api.calls[1]
        assert put_call["payload"] == {
            "labels": ["layer:p3-harness", "type:tracking"]
        }
        post_call = api.calls[2]
        assert "type:tracking" in post_call["payload"]["body"]
        assert "applied" in capsys.readouterr().out

    def test_already_tracking_is_noop(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = json.dumps({"labels": [{"name": "type:tracking"}]})
        api = _FakeApi([(200, body)])
        rc = nps.run(
            mode="apply",
            repo="o/r",
            issue=1005,
            prs=[],
            reason=None,
            token="t",
            apply_call=api,
        )
        assert rc == 0
        assert [c["method"] for c in api.calls] == ["GET"]
        assert "no-op" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_missing_repo_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.setenv("GH_TOKEN", "t")
        assert nps.main(["plan", "--issue", "5"]) == 1
        assert "--repo" in capsys.readouterr().out

    def test_missing_token_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert nps.main(["plan", "--repo", "o/r", "--issue", "5"]) == 1
        assert "GH_TOKEN" in capsys.readouterr().out
