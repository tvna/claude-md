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


# ---------------------------------------------------------------------------
# _head_checks_failed
# ---------------------------------------------------------------------------


class TestHeadChecksFailed:
    def test_failure_conclusion_is_failed(self) -> None:
        body = json.dumps({"check_runs": [
            {"name": "Verify PR", "conclusion": "success"},
            {"name": "Verify repository scripts", "conclusion": "failure"},
        ]})

        def _call(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
            assert method == "GET" and url.endswith("/commits/abc/check-runs?per_page=100")
            return (200, body)

        assert pm._head_checks_failed(repo="o/r", sha="abc", token="t", apply_call=_call) is True

    def test_running_and_success_runs_are_not_failed(self) -> None:
        body = json.dumps({"check_runs": [
            {"name": "Verify PR", "status": "in_progress", "conclusion": None},
            {"name": "Verify repository scripts", "conclusion": "success"},
        ]})
        assert (
            pm._head_checks_failed(
                repo="o/r", sha="abc", token="t", apply_call=lambda **kw: (200, body)
            )
            is False
        )

    def test_no_check_runs_is_not_failed(self) -> None:
        # Freshly recreated head: no runs registered yet -> not failed, hold kept.
        assert (
            pm._head_checks_failed(
                repo="o/r", sha="abc", token="t",
                apply_call=lambda **kw: (200, json.dumps({"check_runs": []})),
            )
            is False
        )

    def test_http_error_raises(self) -> None:
        with pytest.raises(RuntimeError, match="check-runs"):
            pm._head_checks_failed(
                repo="o/r", sha="abc", token="t", apply_call=lambda **kw: (500, "boom")
            )


# ---------------------------------------------------------------------------
# merge_bot_prs_in_priority_order
# ---------------------------------------------------------------------------

_DOCS = "chore/update-generated-docs"
_TRIAGE = "chore/refresh-auto-retro-triage-report"


def _list_pr(number: int, ref: str) -> dict[str, Any]:
    """A PR as returned by the list endpoint (head.ref, no head.sha)."""
    return {"number": number, "head": {"ref": ref}}


def _make_router(
    *,
    pr_states: dict[int, dict[str, Any]],
    check_runs: dict[str, list[dict[str, Any]]],
    merges: list[int],
    deletes: list[str],
    merge_ok: bool = True,
) -> Any:
    """Return a fake ``apply_call`` routing GitHub REST calls off in-memory state.

    ``pr_states`` maps PR number to its ``_get_pr`` body (mergeable_state + head
    sha); ``check_runs`` maps head sha to its check-run list. Merge (PUT) and
    branch-delete (DELETE) calls are recorded into *merges* / *deletes*.
    """

    def _call(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
        if method == "GET" and "/pulls/" in url and not url.endswith("/merge"):
            number = int(url.rsplit("/pulls/", 1)[1])
            return (200, json.dumps(pr_states[number]))
        if method == "PUT" and url.endswith("/merge"):
            number = int(url.rsplit("/pulls/", 1)[1].split("/merge")[0])
            merges.append(number)
            return (200, "{}") if merge_ok else (405, "blocked")
        if method == "DELETE" and "/git/refs/heads/" in url:
            deletes.append(url.rsplit("/git/refs/heads/", 1)[1])
            return (204, "")
        if method == "GET" and "/check-runs" in url:
            sha = url.rsplit("/commits/", 1)[1].split("/check-runs")[0]
            return (200, json.dumps({"check_runs": check_runs.get(sha, [])}))
        raise AssertionError(f"unexpected call {method} {url}")

    return _call


def _clean(sha: str) -> dict[str, Any]:
    return {"mergeable": True, "mergeable_state": "clean", "head": {"sha": sha}}


def _not_clean(state: str, sha: str) -> dict[str, Any]:
    return {"mergeable": True, "mergeable_state": state, "head": {"sha": sha}}


class TestMergeBotPrsInPriorityOrder:
    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pm.time, "sleep", lambda _s: None)

    def test_higher_in_flight_holds_lower(self, capsys: pytest.CaptureFixture[str]) -> None:
        # docs is in flight (blocked, checks not failed); triage is clean but is
        # held for the next trigger so it does not advance main and re-stale docs.
        prs = [_list_pr(101, _TRIAGE), _list_pr(100, _DOCS)]  # unordered input
        merges: list[int] = []
        deletes: list[str] = []
        router = _make_router(
            pr_states={100: _not_clean("blocked", "docs_sha"), 101: _clean("triage_sha")},
            check_runs={"docs_sha": [{"conclusion": None, "status": "in_progress"}]},
            merges=merges,
            deletes=deletes,
        )
        merged = pm.merge_bot_prs_in_priority_order(prs=prs, repo="o/r", token="t", apply_call=router)
        assert merged == 0
        assert merges == []  # triage was held, docs was not clean -> nothing merged
        assert "held" in capsys.readouterr().out

    def test_higher_clean_merges_first_lower_left_for_next_cycle(self) -> None:
        # docs is clean and merges; triage has gone behind (main advanced) and is
        # left to recreate and merge next cycle.
        prs = [_list_pr(101, _TRIAGE), _list_pr(100, _DOCS)]  # unordered input
        merges: list[int] = []
        deletes: list[str] = []
        router = _make_router(
            pr_states={100: _clean("docs_sha"), 101: _not_clean("behind", "triage_sha")},
            check_runs={"triage_sha": [{"conclusion": None, "status": "in_progress"}]},
            merges=merges,
            deletes=deletes,
        )
        merged = pm.merge_bot_prs_in_priority_order(prs=prs, repo="o/r", token="t", apply_call=router)
        assert merged == 1
        assert merges == [100]  # docs (higher priority) merged first; triage left
        assert deletes == [_DOCS]

    def test_higher_checks_failed_releases_hold_on_lower(self) -> None:
        # docs is blocked AND a required check failed, so it must not permanently
        # block triage; triage is clean and merges this cycle.
        prs = [_list_pr(100, _DOCS), _list_pr(101, _TRIAGE)]
        merges: list[int] = []
        deletes: list[str] = []
        router = _make_router(
            pr_states={100: _not_clean("blocked", "docs_sha"), 101: _clean("triage_sha")},
            check_runs={"docs_sha": [{"conclusion": "failure"}]},
            merges=merges,
            deletes=deletes,
        )
        merged = pm.merge_bot_prs_in_priority_order(prs=prs, repo="o/r", token="t", apply_call=router)
        assert merged == 1
        assert merges == [101]  # triage released and merged; docs stays for its own fix
        assert deletes == [_TRIAGE]

    def test_no_higher_priority_pr_merges_normally(self) -> None:
        # Only lowest-rank bot PRs open: behaves exactly as the pre-#2382 keeper,
        # merging each clean PR with no hold and no check-run probe.
        prs = [_list_pr(101, _TRIAGE), _list_pr(102, "devcontainer/image-pins-x")]
        merges: list[int] = []
        deletes: list[str] = []
        router = _make_router(
            pr_states={101: _clean("triage_sha"), 102: _clean("pin_sha")},
            check_runs={},  # never consulted; no non-clean higher PR to classify
            merges=merges,
            deletes=deletes,
        )
        merged = pm.merge_bot_prs_in_priority_order(prs=prs, repo="o/r", token="t", apply_call=router)
        assert merged == 2
        assert sorted(merges) == [101, 102]
        assert sorted(deletes) == sorted([_TRIAGE, "devcontainer/image-pins-x"])

    def test_lower_merges_when_no_higher_pr_open_even_if_it_is_the_docs_branch(self) -> None:
        # A lone docs PR (no lower series present) merges when clean: the priority
        # order only holds a *lower* series, never the top branch itself.
        prs = [_list_pr(100, _DOCS)]
        merges: list[int] = []
        deletes: list[str] = []
        router = _make_router(
            pr_states={100: _clean("docs_sha")},
            check_runs={},
            merges=merges,
            deletes=deletes,
        )
        merged = pm.merge_bot_prs_in_priority_order(prs=prs, repo="o/r", token="t", apply_call=router)
        assert merged == 1
        assert merges == [100]


class TestPriorityBranchContract:
    def test_priority_list_matches_manual_edit_gate_exempt_set(self) -> None:
        # Single source of truth: the keeper's priority order must cover exactly
        # the bot branches the manual-edit gate recognises, so the two cannot
        # drift apart. Refs #2382.
        import gate_generated_scripts_manual_edit as gate

        assert set(pm._BOT_PR_PRIORITY_BRANCHES) == set(gate.EXEMPT_BRANCHES)

    def test_docs_outranks_triage(self) -> None:
        assert pm._priority_rank(_DOCS) < pm._priority_rank(_TRIAGE)

    def test_unlisted_branch_is_lowest_rank(self) -> None:
        assert pm._priority_rank("devcontainer/image-pins-x") == len(pm._BOT_PR_PRIORITY_BRANCHES)
