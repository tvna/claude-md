from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import publish_instruction_release as pir

pytestmark = pytest.mark.shard_ci_ops


def _release_apply_call(captured: list[dict[str, Any]], *, release_id: int = 42, html_url: str = "https://x/r") -> Any:
    def _call(*, method: str, url: str, payload: dict[str, Any] | None, token: str) -> tuple[int, str]:
        captured.append({"method": method, "url": url, "payload": payload, "token": token})
        return 201, json.dumps({"id": release_id, "html_url": html_url})

    return _call


def _ok_upload(captured: list[dict[str, Any]]) -> Any:
    def _call(*, repo: str, release_id: int, name: str, content: bytes, content_type: str, token: str) -> tuple[int, str]:
        captured.append({"name": name, "content": content, "content_type": content_type, "release_id": release_id})
        return 201, "{}"

    return _call


def test_content_type_markdown_and_default() -> None:
    assert pir._content_type("CLAUDE.md") == "text/markdown"
    assert pir._content_type("SHA256SUMS") == "application/octet-stream"


def test_publish_creates_release_then_uploads_each_asset(tmp_path: Path) -> None:
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("master\n", encoding="utf-8")
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("abc  CLAUDE.md\n", encoding="utf-8")

    release_calls: list[dict[str, Any]] = []
    uploads: list[dict[str, Any]] = []

    url = pir.publish(
        repo="o/r",
        tag="v1.0.0",
        asset_paths=[str(claude), str(sums)],
        token="t",
        apply_call=_release_apply_call(release_calls),
        upload_asset=_ok_upload(uploads),
    )

    assert url == "https://x/r"
    assert release_calls[0]["payload"]["tag_name"] == "v1.0.0"
    assert [u["name"] for u in uploads] == ["CLAUDE.md", "SHA256SUMS"]
    assert uploads[0]["content_type"] == "text/markdown"
    assert uploads[0]["content"] == b"master\n"
    assert all(u["release_id"] == 42 for u in uploads)


def test_publish_fails_loud_on_missing_asset(tmp_path: Path) -> None:
    missing = tmp_path / "AGENTS.md"
    release_calls: list[dict[str, Any]] = []

    with pytest.raises(RuntimeError, match="Asset not found"):
        pir.publish(
            repo="o/r",
            tag="t",
            asset_paths=[str(missing)],
            token="t",
            apply_call=_release_apply_call(release_calls),
            upload_asset=_ok_upload([]),
        )
    # The release must not be created when an asset is missing.
    assert release_calls == []


def test_publish_requires_at_least_one_asset() -> None:
    with pytest.raises(RuntimeError, match="at least one --asset"):
        pir.publish(repo="o/r", tag="t", asset_paths=[], token="t")


def test_publish_fails_loud_on_release_create_error(tmp_path: Path) -> None:
    asset = tmp_path / "CLAUDE.md"
    asset.write_text("x", encoding="utf-8")

    def _bad_create(*, method: str, url: str, payload: dict[str, Any] | None, token: str) -> tuple[int, str]:
        return 422, '{"message":"already_exists"}'

    with pytest.raises(RuntimeError, match="Create release failed: HTTP 422"):
        pir.publish(repo="o/r", tag="t", asset_paths=[str(asset)], token="t", apply_call=_bad_create, upload_asset=_ok_upload([]))


def test_publish_fails_loud_on_upload_error(tmp_path: Path) -> None:
    asset = tmp_path / "CLAUDE.md"
    asset.write_text("x", encoding="utf-8")

    def _bad_upload(*, repo: str, release_id: int, name: str, content: bytes, content_type: str, token: str) -> tuple[int, str]:
        return 500, "boom"

    with pytest.raises(RuntimeError, match="Upload asset CLAUDE.md failed: HTTP 500"):
        pir.publish(
            repo="o/r",
            tag="t",
            asset_paths=[str(asset)],
            token="t",
            apply_call=_release_apply_call([]),
            upload_asset=_bad_upload,
        )


def test_cmd_publish_requires_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("REPO", "o/r")
    rc = pir.main(["publish", "--tag", "t", "--asset", str(tmp_path / "CLAUDE.md")])
    assert rc == 1


def test_cmd_publish_requires_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GH_TOKEN", "t")
    monkeypatch.delenv("REPO", raising=False)
    rc = pir.main(["publish", "--tag", "t", "--asset", str(tmp_path / "CLAUDE.md")])
    assert rc == 1


def test_main_publish_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    asset = tmp_path / "CLAUDE.md"
    asset.write_text("master\n", encoding="utf-8")
    monkeypatch.setenv("GH_TOKEN", "t")
    monkeypatch.setenv("REPO", "o/r")

    monkeypatch.setattr(pir, "_github_apply_call", _release_apply_call([], html_url="https://x/rel"))
    monkeypatch.setattr(pir, "_github_upload_asset", _ok_upload([]))

    rc = pir.main(["publish", "--tag", "v1.0.0", "--asset", str(asset)])
    assert rc == 0
    assert "https://x/rel" in capsys.readouterr().out


def test_create_release_non_json_response_fails_loud(tmp_path: Path) -> None:
    # HTTP 200 but non-JSON body -> lines 88-89 (JSONDecodeError path).
    asset = tmp_path / "CLAUDE.md"
    asset.write_text("x", encoding="utf-8")

    def _non_json(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
        return 200, "not-json"

    with pytest.raises(RuntimeError, match="non-JSON"):
        pir.publish(repo="o/r", tag="t", asset_paths=[str(asset)], token="t",
                    apply_call=_non_json, upload_asset=_ok_upload([]))


def test_create_release_missing_id_fails_loud(tmp_path: Path) -> None:
    # HTTP 200, valid JSON but missing "id" key -> line 91.
    asset = tmp_path / "CLAUDE.md"
    asset.write_text("x", encoding="utf-8")

    def _no_id(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
        return 200, json.dumps({"html_url": "https://x/r"})

    with pytest.raises(RuntimeError, match="no release id"):
        pir.publish(repo="o/r", tag="t", asset_paths=[str(asset)], token="t",
                    apply_call=_no_id, upload_asset=_ok_upload([]))


def test_cmd_publish_runtime_error_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # When publish() raises RuntimeError, _cmd_publish prints and returns 1 (lines 151-153).
    asset = tmp_path / "CLAUDE.md"
    asset.write_text("x", encoding="utf-8")
    monkeypatch.setenv("GH_TOKEN", "t")
    monkeypatch.setenv("REPO", "o/r")
    monkeypatch.setattr(pir, "_github_apply_call", lambda **kw: (200, "bad-json"))
    monkeypatch.setattr(pir, "_github_upload_asset", _ok_upload([]))
    rc = pir.main(["publish", "--tag", "t", "--asset", str(asset)])
    assert rc == 1
    assert "Error" in capsys.readouterr().err
