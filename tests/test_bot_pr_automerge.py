"""Tests for ``scripts/bot_pr_automerge.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

from typing import Any

import bot_pr_automerge as bpa
import pytest

pytestmark = pytest.mark.shard_ci_ops


@pytest.fixture
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")


def _pr(number: int, ref: str) -> dict[str, Any]:
    return {"number": number, "head": {"ref": ref}}


@pytest.mark.usefixtures("_env")
class TestMergeCommand:
    def test_no_open_bot_pr_is_noop(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(bpa, "_list_open_prs_by_author", lambda **kw: [])

        def _never(**kw: Any) -> int:
            raise AssertionError("must not orchestrate merges when no bot PR is open")

        monkeypatch.setattr(bpa, "merge_bot_prs_in_priority_order", _never)
        rc = bpa.main(["merge"])
        assert rc == 0
        assert "no open PRs authored by tvna-bot[bot]" in capsys.readouterr().out

    def test_filters_to_bot_author(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def _list(*, repo: str, author_login: str, token: str) -> list[dict[str, Any]]:
            captured["author_login"] = author_login
            return []

        monkeypatch.setattr(bpa, "_list_open_prs_by_author", _list)
        monkeypatch.setattr(bpa, "merge_bot_prs_in_priority_order", lambda **kw: 0)
        assert bpa.main(["merge"]) == 0
        assert captured["author_login"] == "tvna-bot[bot]"

    def test_passes_listed_prs_to_priority_orchestrator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prs = [_pr(11, "devcontainer/image-pins-x"), _pr(12, "chore/update-generated-docs")]
        monkeypatch.setattr(bpa, "_list_open_prs_by_author", lambda **kw: prs)
        captured: dict[str, Any] = {}

        def _orchestrate(*, prs: list[dict[str, Any]], repo: str, token: str) -> int:
            captured["prs"] = prs
            captured["repo"] = repo
            return len(prs)

        monkeypatch.setattr(bpa, "merge_bot_prs_in_priority_order", _orchestrate)
        rc = bpa.main(["merge"])
        assert rc == 0
        assert captured["prs"] == prs
        assert captured["repo"] == "owner/repo"

    def test_tally_reports_orchestrator_merge_count(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        prs = [_pr(11, "a"), _pr(12, "b")]
        monkeypatch.setattr(bpa, "_list_open_prs_by_author", lambda **kw: prs)
        # Orchestrator merged one of the two open PRs (the other was held/skipped).
        monkeypatch.setattr(bpa, "merge_bot_prs_in_priority_order", lambda **kw: 1)
        rc = bpa.main(["merge"])
        assert rc == 0
        assert "merged 1 of 2 open PR(s)" in capsys.readouterr().out

    def test_override_author_login_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOT_AUTHOR_LOGIN", "other-bot[bot]")
        captured: dict[str, Any] = {}

        def _list(*, repo: str, author_login: str, token: str) -> list[dict[str, Any]]:
            captured["author_login"] = author_login
            return []

        monkeypatch.setattr(bpa, "_list_open_prs_by_author", _list)
        assert bpa.main(["merge"]) == 0
        assert captured["author_login"] == "other-bot[bot]"

    def test_missing_token_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        assert bpa.main(["merge"]) == 1

    def test_missing_repo_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPO", raising=False)
        assert bpa.main(["merge"]) == 1

    def test_list_api_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(**kw: Any) -> list[dict[str, Any]]:
            raise RuntimeError("List PRs failed")

        monkeypatch.setattr(bpa, "_list_open_prs_by_author", _boom)
        with pytest.raises(RuntimeError, match="List PRs failed"):
            bpa.main(["merge"])
