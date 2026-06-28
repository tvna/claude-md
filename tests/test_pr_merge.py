"""Tests for ``scripts/_pr_merge.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import json
from typing import Any

import _pr_merge as pm
import pytest

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# _list_open_prs_by_author
# ---------------------------------------------------------------------------


class TestListOpenPrsByAuthor:
    def test_filters_by_author_login(self) -> None:
        page = json.dumps([
            {"number": 1, "user": {"login": "tvna-bot[bot]"}, "head": {"ref": "a"}},
            {"number": 2, "user": {"login": "dependabot[bot]"}, "head": {"ref": "b"}},
            {"number": 3, "user": {"login": "tvna-bot[bot]"}, "head": {"ref": "c"}},
        ])

        def _call(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
            assert method == "GET"
            return (200, page)

        prs = pm._list_open_prs_by_author(
            repo="o/r", author_login="tvna-bot[bot]", token="t", apply_call=_call
        )
        assert [p["number"] for p in prs] == [1, 3]

    def test_paginates_until_short_page(self) -> None:
        full = json.dumps([{"number": n, "user": {"login": "tvna-bot[bot]"}} for n in range(100)])
        tail = json.dumps([{"number": 100, "user": {"login": "tvna-bot[bot]"}}])
        pages = {1: full, 2: tail}
        seen: list[int] = []

        def _call(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
            page = int(url.split("&page=")[1])
            seen.append(page)
            return (200, pages[page])

        prs = pm._list_open_prs_by_author(
            repo="o/r", author_login="tvna-bot[bot]", token="t", apply_call=_call
        )
        assert len(prs) == 101
        assert seen == [1, 2]  # stopped after the short second page

    def test_http_error_raises(self) -> None:
        def _call(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
            return (500, "boom")

        with pytest.raises(RuntimeError, match="List PRs failed"):
            pm._list_open_prs_by_author(repo="o/r", author_login="x", token="t", apply_call=_call)


# ---------------------------------------------------------------------------
# _merge_pr_if_clean / _poll_pr_mergeability
# ---------------------------------------------------------------------------


class TestMergePrIfClean:
    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pm.time, "sleep", lambda _s: None)

    def test_clean_pr_merges_and_deletes_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            pm,
            "_get_pr",
            lambda **kw: {"mergeable": True, "mergeable_state": "clean", "head": {"sha": "deadbeef"}},
        )
        merged: dict[str, Any] = {}

        def _merge(**kw: Any) -> bool:
            merged.update(kw)
            return True

        monkeypatch.setattr(pm, "_merge_pr", _merge)
        deleted: list[str] = []
        monkeypatch.setattr(pm, "_delete_branch", lambda **kw: deleted.append(kw["branch"]))
        result = pm._merge_pr_if_clean(repo="o/r", number=5, head_ref="feat/x", token="t")
        assert result is True
        assert merged["sha"] == "deadbeef"
        assert merged["merge_method"] == "squash"
        assert deleted == ["feat/x"]

    def test_not_clean_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            pm,
            "_get_pr",
            lambda **kw: {"mergeable": False, "mergeable_state": "dirty", "head": {"sha": "x"}},
        )
        called: list[Any] = []

        def _merge(**kw: Any) -> bool:
            called.append(kw)
            return True

        monkeypatch.setattr(pm, "_merge_pr", _merge)
        result = pm._merge_pr_if_clean(repo="o/r", number=5, head_ref="b", token="t")
        assert result is False
        assert called == []  # never attempts the merge API on a non-clean PR

    def test_merge_race_returns_false_and_keeps_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            pm,
            "_get_pr",
            lambda **kw: {"mergeable": True, "mergeable_state": "clean", "head": {"sha": "s"}},
        )
        monkeypatch.setattr(pm, "_merge_pr", lambda **kw: False)  # 405/409 race
        deleted: list[str] = []
        monkeypatch.setattr(pm, "_delete_branch", lambda **kw: deleted.append(kw["branch"]))
        result = pm._merge_pr_if_clean(repo="o/r", number=5, head_ref="b", token="t")
        assert result is False
        assert deleted == []  # do not delete a branch we did not merge

    def test_clean_without_head_sha_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            pm, "_get_pr", lambda **kw: {"mergeable": True, "mergeable_state": "clean", "head": {}}
        )
        with pytest.raises(RuntimeError, match="no head sha"):
            pm._merge_pr_if_clean(repo="o/r", number=5, head_ref="b", token="t")

    def test_polls_until_mergeable_computed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seq: list[dict[str, Any]] = [
            {"mergeable": None, "mergeable_state": "unknown", "head": {"sha": "s"}},
            {"mergeable": True, "mergeable_state": "clean", "head": {"sha": "s"}},
        ]
        calls = {"n": 0}

        def _get(**kw: Any) -> dict[str, Any]:
            item = seq[min(calls["n"], len(seq) - 1)]
            calls["n"] += 1
            return item

        monkeypatch.setattr(pm, "_get_pr", _get)
        monkeypatch.setattr(pm, "_merge_pr", lambda **kw: True)
        monkeypatch.setattr(pm, "_delete_branch", lambda **kw: None)
        result = pm._merge_pr_if_clean(repo="o/r", number=5, head_ref="b", token="t")
        assert result is True
        assert calls["n"] == 2  # polled past the still-computing response
