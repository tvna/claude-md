from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import post_issue_comment as pic

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_apply_call(status: int, body: dict[str, Any] | str = "") -> Callable[..., tuple[int, str]]:
    encoded = json.dumps(body) if isinstance(body, dict) else body

    def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
        return status, encoded

    return apply_call


# ---------------------------------------------------------------------------
# _post_comment()
# ---------------------------------------------------------------------------


class TestPostComment:
    def test_posts_to_correct_url(self) -> None:
        captured: list[str] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.append(url)
            return 201, json.dumps({"id": 1})

        pic._post_comment(repo="owner/repo", issue_number=42, body="hello", token="tok", apply_call=apply_call)
        assert "/issues/42/comments" in captured[0]
        assert "owner/repo" in captured[0]

    def test_sends_body_in_payload(self) -> None:
        captured_payloads: list[Any] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured_payloads.append(payload)
            return 201, json.dumps({"id": 1})

        pic._post_comment(repo="owner/repo", issue_number=1, body="test body", token="tok", apply_call=apply_call)
        assert captured_payloads[0]["body"] == "test body"

    def test_http_error_raises_runtime_error(self) -> None:
        apply_call = _make_apply_call(422, {"message": "validation failed"})
        with pytest.raises(RuntimeError, match="422"):
            pic._post_comment(repo="owner/repo", issue_number=1, body="b", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _cmd_create() / create subcommand
# ---------------------------------------------------------------------------


class TestCmdCreate:
    def test_success_with_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setattr(pic, "_post_comment", lambda **kw: None)
        rc = pic.main(["create", "--issue-number", "7", "--body", "hello"])
        assert rc == 0

    def test_success_with_body_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("file content", encoding="utf-8")
        received: list[str] = []
        monkeypatch.setattr(pic, "_post_comment", lambda **kw: received.append(kw["body"]))
        rc = pic.main(["create", "--issue-number", "7", "--body-file", str(body_file)])
        assert rc == 0
        assert received[0] == "file content"

    def test_missing_token_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("REPO", "owner/repo")
        rc = pic.main(["create", "--issue-number", "1", "--body", "b"])
        assert rc == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_missing_repo_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.delenv("REPO", raising=False)
        rc = pic.main(["create", "--issue-number", "1", "--body", "b"])
        assert rc == 1
        assert "REPO" in capsys.readouterr().err

    def test_missing_body_and_body_file_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        rc = pic.main(["create", "--issue-number", "1"])
        assert rc == 1
        assert "body" in capsys.readouterr().err.lower()
