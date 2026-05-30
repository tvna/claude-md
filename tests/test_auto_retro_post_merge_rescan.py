"""Tests for the deferred Post-merge checklist re-scan in ``scripts/auto_retro.py``.

Covers the ``post-merge-rescan`` subcommand added by #421: pure-function
gate verification, the ``post_merge_rescan_run`` orchestrator (with
monkeypatched ``gh_api``), and the CLI wiring.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import auto_retro as ar
import pytest

pytestmark = pytest.mark.shard_ci_ops_auto_retro_rescan


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_PR_BODY_WITH_POST_MERGE = (
    "## Summary\n\nx\n\n"
    "## Related Issue\n\nCloses #100\n\n"
    "## Facts\n\n- a\n\n"
    "## Assumptions\n\n- a\n\n"
    "## Risk and blast radius\n\n- low\n\n"
    "## Rollback\n\n- revert\n\n"
    "## Verification\n\n"
    "- command: `echo ok`\n"
    "  result: `exit 0`\n\n"
    "## Checklist\n\n"
    "### Bootstrap\n\n"
    "- [x] Facts vs. Assumptions split\n\n"
    "### After-merge (CI)\n\n"
    "- [x] pytest exits 0\n\n"
    "### Post-merge (auto-retro signal)\n\n"
    "- [ ] Linked issue closed by the merge (or `Refs #` with rationale recorded)\n"
    "- [ ] auto-retro issue opened by `.github/workflows/auto-retro.yml`\n"
    "- [ ] No follow-up `fix(...)` PR needed within 24h of merge\n"
)

_PR_BODY_ALL_CHECKED = (
    "## Summary\n\nx\n\n"
    "## Related Issue\n\nCloses #100\n\n"
    "## Checklist\n\n"
    "### Post-merge (auto-retro signal)\n\n"
    "- [x] Linked issue closed by the merge\n"
    "- [x] auto-retro issue opened\n"
    "- [x] No follow-up fix(...) PR needed within 24h\n"
)

_RETRO_BODY = (
    "## Scope\n\nx\n\n"
    "## Facts\n\n- a\n\n"
    "## Proposed work\n\n"
    "<!-- auto-filled:repair-history -->\n"
    "1. Repair history\n\n"
    "| # | Repair | What |\n"
    "|---|--------|------|\n"
    "| 1 | Iteration commit | x |\n"
    "<!-- /auto-filled:repair-history -->\n\n"
    "## Verification\n\n- v\n\n"
    "## Acceptance criteria\n\n"
    "- [ ] Repair history table complete.\n"
)


def _search_item(
    number: int,
    title: str = "feat(harness): do a thing",
    user_login: str = "tvna",
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "user": {"login": user_login},
    }


def _retro_search_item(
    number: int,
    pr_number: int = 42,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"fix(auto-retro): review PR #{pr_number} repair loops",
    }


def _rescan_recorder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    merged_prs: list[dict[str, Any]] | None = None,
    pr_details: dict[int, dict[str, Any]] | None = None,
    retro_searches: dict[int, list[dict[str, Any]]] | None = None,
    retro_bodies: dict[int, str] | None = None,
    issue_states: dict[int, str] | None = None,
    fix_prs: list[dict[str, Any]] | None = None,
    search_error: bool = False,
    patch_error_for: set[int] | None = None,
) -> list[tuple[str, str, Any]]:
    """Record gh_api calls for post_merge_rescan_run tests."""
    merged_prs = merged_prs or []
    pr_details = pr_details or {}
    retro_searches = retro_searches or {}
    retro_bodies = retro_bodies or {}
    issue_states = issue_states or {}
    fix_prs = fix_prs or []
    patch_error_for = patch_error_for or set()
    seen: list[tuple[str, str, Any]] = []

    def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
        seen.append((method, path, body))
        from urllib.parse import unquote
        decoded = unquote(path)
        if method == "GET" and path.startswith("/search/issues"):
            if search_error:
                raise subprocess.CalledProcessError(
                    1, "gh", stderr="search boom"
                )
            if "type:pr" in decoded and "is:merged" in decoded:
                if "merged:" in decoded and ".." in decoded:
                    return json.dumps({"items": fix_prs})
                return json.dumps({"items": merged_prs})
            for pr_num, items in retro_searches.items():
                if f"PR #{pr_num}" in decoded:
                    return json.dumps({"items": items})
            return json.dumps({"items": []})
        if method == "GET" and "/pulls/" in path:
            for pr_num, detail in pr_details.items():
                if f"/pulls/{pr_num}" in path:
                    return json.dumps(detail)
            return "{}"
        if method == "GET" and "/issues/" in path:
            number = _number_from_path(path)
            if number in retro_bodies:
                return json.dumps({
                    "number": number,
                    "body": retro_bodies[number],
                    "state": issue_states.get(number, "open"),
                })
            if number in issue_states:
                return json.dumps({"state": issue_states[number]})
            return json.dumps({"state": "open"})
        if method == "PATCH" and "/issues/" in path:
            number = _number_from_path(path)
            if number in patch_error_for:
                raise subprocess.CalledProcessError(
                    1, "gh", stderr="patch boom"
                )
            return "{}"
        return ""

    monkeypatch.setattr(ar, "gh_api", fake_api)
    return seen


def _number_from_path(path: str) -> int:
    for part in path.split("?", 1)[0].split("/"):
        if part.isdigit():
            return int(part)
    return -1


# ---------------------------------------------------------------------------
# _hours_between
# ---------------------------------------------------------------------------


class TestHoursBetween:
    def test_same_time_returns_zero(self) -> None:
        assert ar._hours_between(
            "2026-05-29T04:00:00Z", "2026-05-29T04:00:00Z"
        ) == 0.0

    def test_24h_difference(self) -> None:
        assert ar._hours_between(
            "2026-05-28T04:00:00Z", "2026-05-29T04:00:00Z"
        ) == 24.0

    def test_absolute_value(self) -> None:
        result = ar._hours_between(
            "2026-05-29T04:00:00Z", "2026-05-28T04:00:00Z"
        )
        assert result == 24.0


# ---------------------------------------------------------------------------
# verify_post_merge_gates (pure logic with monkeypatched API)
# ---------------------------------------------------------------------------


class TestVerifyPostMergeGates:
    def test_empty_body_returns_empty(self) -> None:
        results = ar.verify_post_merge_gates(
            "o/r", 42, "", "2026-05-28T10:00:00Z", "2026-05-29T10:00:00Z"
        )
        assert results == []

    def test_all_checked_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ar, "gh_api", lambda *_a, **_kw: json.dumps({"items": []})
        )
        results = ar.verify_post_merge_gates(
            "o/r", 42, _PR_BODY_ALL_CHECKED,
            "2026-05-28T10:00:00Z", "2026-05-29T10:00:00Z",
        )
        assert results == []

    def test_linked_issue_closed_satisfied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            if "/issues/100" in path:
                return json.dumps({"state": "closed"})
            if "/search/issues" in path:
                return json.dumps({"items": [_retro_search_item(200, 42)]})
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        results = ar.verify_post_merge_gates(
            "o/r", 42, _PR_BODY_WITH_POST_MERGE,
            "2026-05-28T10:00:00Z", "2026-05-29T10:00:00Z",
        )
        linked_gate = next(r for r in results if r.gate == "linked_issue_closed")
        assert linked_gate.satisfied is True

    def test_linked_issue_not_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            if "/issues/100" in path:
                return json.dumps({"state": "open"})
            if "/search/issues" in path:
                return json.dumps({"items": []})
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        results = ar.verify_post_merge_gates(
            "o/r", 42, _PR_BODY_WITH_POST_MERGE,
            "2026-05-28T10:00:00Z", "2026-05-29T10:00:00Z",
        )
        linked_gate = next(r for r in results if r.gate == "linked_issue_closed")
        assert linked_gate.satisfied is False

    def test_retro_issue_opened_satisfied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            if "/issues/100" in path:
                return json.dumps({"state": "closed"})
            if "/search/issues" in path:
                return json.dumps({"items": [_retro_search_item(200, 42)]})
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        results = ar.verify_post_merge_gates(
            "o/r", 42, _PR_BODY_WITH_POST_MERGE,
            "2026-05-28T10:00:00Z", "2026-05-29T10:00:00Z",
        )
        retro_gate = next(r for r in results if r.gate == "retro_issue_opened")
        assert retro_gate.satisfied is True

    def test_retro_issue_not_opened(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            if "/issues/100" in path:
                return json.dumps({"state": "closed"})
            if "/search/issues" in path:
                return json.dumps({"items": []})
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        results = ar.verify_post_merge_gates(
            "o/r", 42, _PR_BODY_WITH_POST_MERGE,
            "2026-05-28T10:00:00Z", "2026-05-29T10:00:00Z",
        )
        retro_gate = next(r for r in results if r.gate == "retro_issue_opened")
        assert retro_gate.satisfied is False

    def test_no_followup_fix_satisfied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            if "/issues/100" in path:
                return json.dumps({"state": "closed"})
            if "/search/issues" in path:
                return json.dumps({"items": []})
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        results = ar.verify_post_merge_gates(
            "o/r", 42, _PR_BODY_WITH_POST_MERGE,
            "2026-05-28T10:00:00Z", "2026-05-29T10:00:00Z",
        )
        fix_gate = next(r for r in results if r.gate == "no_followup_fix")
        assert fix_gate.satisfied is True

    def test_followup_fix_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from urllib.parse import unquote

        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            decoded = unquote(path)
            if "/issues/100" in path:
                return json.dumps({"state": "closed"})
            if "/search/issues" in path:
                if "merged:" in decoded and ".." in decoded:
                    return json.dumps({
                        "items": [{"number": 50, "title": "fix(harness): repair"}]
                    })
                return json.dumps({"items": []})
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        results = ar.verify_post_merge_gates(
            "o/r", 42, _PR_BODY_WITH_POST_MERGE,
            "2026-05-28T10:00:00Z", "2026-05-29T10:00:00Z",
        )
        fix_gate = next(r for r in results if r.gate == "no_followup_fix")
        assert fix_gate.satisfied is False


# ---------------------------------------------------------------------------
# post_merge_rescan_run orchestrator
# ---------------------------------------------------------------------------


class TestPostMergeRescanRun:
    def test_skips_retro_pr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(10, title="fix(auto-retro): review PR #9")],
        )
        assert ar.post_merge_rescan_run(
            "o/r", "2026-05-29T10:00:00Z", 48
        ) == 0

    def test_skips_bot_authored_pr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(10, user_login="dependabot[bot]")],
        )
        assert ar.post_merge_rescan_run(
            "o/r", "2026-05-29T10:00:00Z", 48
        ) == 0

    def test_skips_pr_too_recent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(42)],
            pr_details={42: {
                "merged_at": "2026-05-29T08:00:00Z",
                "body": _PR_BODY_WITH_POST_MERGE,
            }},
        )
        assert ar.post_merge_rescan_run(
            "o/r", "2026-05-29T10:00:00Z", 48
        ) == 0

    def test_skips_all_post_merge_checked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(42)],
            pr_details={42: {
                "merged_at": "2026-05-28T04:00:00Z",
                "body": _PR_BODY_ALL_CHECKED,
            }},
        )
        assert ar.post_merge_rescan_run(
            "o/r", "2026-05-29T10:00:00Z", 48
        ) == 0

    def test_skips_no_retro_to_append_to(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(42)],
            pr_details={42: {
                "merged_at": "2026-05-28T04:00:00Z",
                "body": _PR_BODY_WITH_POST_MERGE,
            }},
            retro_searches={42: []},
            issue_states={100: "open"},
        )
        assert ar.post_merge_rescan_run(
            "o/r", "2026-05-29T10:00:00Z", 48
        ) == 0

    def test_appends_unsatisfied_gates_to_retro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(42)],
            pr_details={42: {
                "merged_at": "2026-05-28T04:00:00Z",
                "body": _PR_BODY_WITH_POST_MERGE,
            }},
            retro_searches={42: [_retro_search_item(200, 42)]},
            retro_bodies={200: _RETRO_BODY},
            issue_states={100: "open"},
        )
        assert ar.post_merge_rescan_run(
            "o/r", "2026-05-29T10:00:00Z", 48
        ) == 0
        patches = [
            (m, p, b)
            for m, p, b in seen
            if m == "PATCH" and "/issues/200" in p
        ]
        assert len(patches) == 1
        body = patches[0][2]["body"]
        assert "Post-merge gate:" in body
        assert ar._RESCAN_MARKER in body

    def test_skips_already_rescanned_retro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rescan_body = _RETRO_BODY + f"\n{ar._RESCAN_MARKER}\n"
        seen = _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(42)],
            pr_details={42: {
                "merged_at": "2026-05-28T04:00:00Z",
                "body": _PR_BODY_WITH_POST_MERGE,
            }},
            retro_searches={42: [_retro_search_item(200, 42)]},
            retro_bodies={200: rescan_body},
            issue_states={100: "open"},
        )
        ar.post_merge_rescan_run("o/r", "2026-05-29T10:00:00Z", 48)
        patches = [
            (m, p, b)
            for m, p, b in seen
            if m == "PATCH" and "/issues/200" in p
        ]
        assert len(patches) == 0

    def test_search_error_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _rescan_recorder(monkeypatch, search_error=True)
        assert ar.post_merge_rescan_run(
            "o/r", "2026-05-29T10:00:00Z", 48
        ) == 0

    def test_patch_error_skips_pr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(42)],
            pr_details={42: {
                "merged_at": "2026-05-28T04:00:00Z",
                "body": _PR_BODY_WITH_POST_MERGE,
            }},
            retro_searches={42: [_retro_search_item(200, 42)]},
            retro_bodies={200: _RETRO_BODY},
            issue_states={100: "open"},
            patch_error_for={200},
        )
        assert ar.post_merge_rescan_run(
            "o/r", "2026-05-29T10:00:00Z", 48
        ) == 0

    def test_all_gates_satisfied_skips(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _rescan_recorder(
            monkeypatch,
            merged_prs=[_search_item(42)],
            pr_details={42: {
                "merged_at": "2026-05-28T04:00:00Z",
                "body": _PR_BODY_WITH_POST_MERGE,
            }},
            retro_searches={42: [_retro_search_item(200, 42)]},
            retro_bodies={200: _RETRO_BODY},
            issue_states={100: "closed"},
        )
        ar.post_merge_rescan_run("o/r", "2026-05-29T10:00:00Z", 48)
        patches = [
            (m, p, b)
            for m, p, b in seen
            if m == "PATCH" and "/issues/200" in p
        ]
        assert len(patches) == 0


# ---------------------------------------------------------------------------
# _build_rescan_summary
# ---------------------------------------------------------------------------


class TestBuildRescanSummary:
    def test_empty_run(self) -> None:
        text = ar._build_rescan_summary([], [], 48)
        assert "48 hours" in text
        assert "(none)" in text

    def test_appended_and_skipped(self) -> None:
        text = ar._build_rescan_summary(
            [(42, 200)],
            [(43, "too recent")],
            48,
        )
        assert "PR #42" in text
        assert "retro #200" in text
        assert "PR #43" in text
        assert "too recent" in text


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


class TestPostMergeRescanCli:
    def test_cli_missing_repo_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        assert ar.main(["post-merge-rescan"]) == 1
        assert "missing --repo" in capsys.readouterr().err

    def test_cli_invalid_hours_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.setenv("AUTO_RETRO_RESCAN_HOURS", "not-a-number")
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "")
        assert ar.main(["post-merge-rescan"]) == 1
        assert "invalid rescan hours" in capsys.readouterr().err

    def test_cli_zero_hours_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "")
        assert ar.main(["post-merge-rescan", "--hours", "0"]) == 1
        assert "must be positive" in capsys.readouterr().err

    def test_cli_default_hours_used_when_unset(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.delenv("AUTO_RETRO_RESCAN_HOURS", raising=False)
        captured: dict[str, Any] = {}

        def fake_run(repo: str, now_iso: str, hours: int) -> int:
            captured["hours"] = hours
            return 0

        monkeypatch.setattr(ar, "post_merge_rescan_run", fake_run)
        assert ar.main(["post-merge-rescan"]) == 0
        assert captured["hours"] == ar._DEFAULT_RESCAN_HOURS

    def test_cli_env_hours_override(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.setenv("AUTO_RETRO_RESCAN_HOURS", "72")
        captured: dict[str, Any] = {}

        def fake_run(repo: str, now_iso: str, hours: int) -> int:
            captured["hours"] = hours
            return 0

        monkeypatch.setattr(ar, "post_merge_rescan_run", fake_run)
        assert ar.main(["post-merge-rescan"]) == 0
        assert captured["hours"] == 72


# ---------------------------------------------------------------------------
# Workflow file contract
# ---------------------------------------------------------------------------


def test_rescan_workflow_file_exists_and_runs_rescan_subcommand() -> None:
    """The schedule workflow that backs post_merge_rescan_run must exist
    and invoke the right CLI subcommand.
    """
    repo_root = Path(__file__).resolve().parent.parent
    workflow = (
        repo_root / ".github" / "workflows"
        / "auto-retro-post-merge-rescan.yml"
    )
    assert workflow.exists(), (
        "Deferred Post-merge rescan needs "
        ".github/workflows/auto-retro-post-merge-rescan.yml "
        "(issue #421)"
    )
    text = workflow.read_text(encoding="utf-8")
    assert "python3 scripts/auto_retro.py post-merge-rescan" in text
    assert "schedule:" in text
    assert "issues: write" in text
    assert "pull-requests: read" in text
