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

        def _never(**kw: Any) -> bool:
            raise AssertionError("must not attempt a merge when no bot PR is open")

        monkeypatch.setattr(bpa, "_merge_pr_if_clean", _never)
        rc = bpa.main(["merge"])
        assert rc == 0
        assert "no open PRs authored by tvna-bot[bot]" in capsys.readouterr().out

    def test_filters_to_bot_author(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def _list(*, repo: str, author_login: str, token: str) -> list[dict[str, Any]]:
            captured["author_login"] = author_login
            return []

        monkeypatch.setattr(bpa, "_list_open_prs_by_author", _list)
        monkeypatch.setattr(bpa, "_merge_pr_if_clean", lambda **kw: False)
        assert bpa.main(["merge"]) == 0
        assert captured["author_login"] == "tvna-bot[bot]"

    def test_merges_each_clean_pr_with_head_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prs = [_pr(11, "devcontainer/image-pins-x"), _pr(12, "chore/update-generated-docs")]
        monkeypatch.setattr(bpa, "_list_open_prs_by_author", lambda **kw: prs)
        seen: list[tuple[int, str]] = []

        def _merge(*, repo: str, number: int, head_ref: str, token: str) -> bool:
            seen.append((number, head_ref))
            return True

        monkeypatch.setattr(bpa, "_merge_pr_if_clean", _merge)
        rc = bpa.main(["merge"])
        assert rc == 0
        assert seen == [(11, "devcontainer/image-pins-x"), (12, "chore/update-generated-docs")]

    def test_non_clean_pr_is_skipped_but_others_merge(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        prs = [_pr(11, "a"), _pr(12, "b")]
        monkeypatch.setattr(bpa, "_list_open_prs_by_author", lambda **kw: prs)

        # PR 11 is not yet clean (False); PR 12 merges (True).
        def _merge(*, repo: str, number: int, head_ref: str, token: str) -> bool:
            return number == 12

        monkeypatch.setattr(bpa, "_merge_pr_if_clean", _merge)
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
