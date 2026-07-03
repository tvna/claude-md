from __future__ import annotations

import json
import subprocess
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


def _fake_git(*, tag_lines: str = "", log_lines: str = "", tag_rc: int = 0, log_rc: int = 0, stderr: str = "") -> Any:
    """Return a git Runner seam that answers ``tag --list`` and ``log`` from canned text.

    Keeps release-body tests off a real repository: ``tag_lines`` feeds
    previous-tag selection, ``log_lines`` feeds subject collection, and the ``_rc``
    knobs exercise the fail-loud paths.
    """

    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["tag", "--list"]:
            return subprocess.CompletedProcess(args, tag_rc, tag_lines, stderr)
        if args and args[0] == "log":
            return subprocess.CompletedProcess(args, log_rc, log_lines, stderr)
        return subprocess.CompletedProcess(args, 0, "", "")

    return _run


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
        run=_fake_git(),
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
        pir.publish(repo="o/r", tag="t", asset_paths=[str(asset)], token="t", apply_call=_bad_create, upload_asset=_ok_upload([]), run=_fake_git())


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
            run=_fake_git(),
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
    monkeypatch.setattr(pir, "make_runner", lambda: _fake_git())

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
                    apply_call=_non_json, upload_asset=_ok_upload([]), run=_fake_git())


def test_create_release_missing_id_fails_loud(tmp_path: Path) -> None:
    # HTTP 200, valid JSON but missing "id" key -> line 91.
    asset = tmp_path / "CLAUDE.md"
    asset.write_text("x", encoding="utf-8")

    def _no_id(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
        return 200, json.dumps({"html_url": "https://x/r"})

    with pytest.raises(RuntimeError, match="no release id"):
        pir.publish(repo="o/r", tag="t", asset_paths=[str(asset)], token="t",
                    apply_call=_no_id, upload_asset=_ok_upload([]), run=_fake_git())


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
    monkeypatch.setattr(pir, "make_runner", lambda: _fake_git())
    rc = pir.main(["publish", "--tag", "t", "--asset", str(asset)])
    assert rc == 1
    assert "Error" in capsys.readouterr().err


# --- release-notes generation (#2193) ---------------------------------------


def test_semver_key_parses_and_rejects() -> None:
    assert pir._semver_key("v0.9.0") == (0, 9, 0)
    assert pir._semver_key("v1.10.2") == (1, 10, 2)
    assert pir._semver_key("v1") is None
    assert pir._semver_key("v1.2") is None
    assert pir._semver_key("vfoo") is None
    assert pir._semver_key("1.2.3") is None


def test_list_semver_tags_filters_non_semver() -> None:
    run = _fake_git(tag_lines="v1.0.0\nv0.9.0\nv1\nvfoo\n\n")
    assert pir._list_semver_tags(run) == ["v1.0.0", "v0.9.0"]


def test_list_semver_tags_fails_loud_on_git_error() -> None:
    run = _fake_git(tag_rc=128, stderr="fatal: not a git repository")
    with pytest.raises(RuntimeError, match="git tag --list failed"):
        pir._list_semver_tags(run)


def test_previous_tag_selects_highest_below_current_numerically() -> None:
    # v0.10.0 must rank above v0.9.0 (numeric, not lexical).
    tags = ["v0.9.0", "v0.10.0", "v1.0.0", "v2.0.0"]
    assert pir._previous_tag("v1.0.0", tags) == "v0.10.0"


def test_previous_tag_none_when_no_lower_tag() -> None:
    assert pir._previous_tag("v1.0.0", ["v1.0.0", "v2.0.0"]) is None
    assert pir._previous_tag("v1.0.0", []) is None


def test_previous_tag_none_when_current_not_semver() -> None:
    assert pir._previous_tag("nightly", ["v1.0.0"]) is None


def test_log_subjects_collects_and_trims() -> None:
    run = _fake_git(log_lines="feat: a\n\nfix: b\n")
    assert pir._log_subjects("v0.9.0", "v1.0.0", run) == ["feat: a", "fix: b"]


def test_log_subjects_fails_loud_on_git_error() -> None:
    run = _fake_git(log_rc=128, stderr="fatal: bad revision")
    with pytest.raises(RuntimeError, match="git log v0.9.0..v1.0.0 failed"):
        pir._log_subjects("v0.9.0", "v1.0.0", run)


def test_release_notes_initial_when_no_previous_tag() -> None:
    assert pir._release_notes(None, []) == "Initial release."


def test_release_notes_bullets_subjects() -> None:
    assert pir._release_notes("v0.9.0", ["feat: a", "fix: b"]) == "- feat: a\n- fix: b"


def test_release_notes_no_changes_when_previous_tag_but_empty() -> None:
    assert pir._release_notes("v0.9.0", []) == "No changes since v0.9.0."


def test_build_release_body_initial_release() -> None:
    body = pir.build_release_body(tag="v1.0.0", run=_fake_git())
    # Asset verification instructions preserved verbatim.
    assert pir._RELEASE_BODY in body
    assert "## Release notes" in body
    assert "Initial release." in body


def test_build_release_body_lists_commit_subjects() -> None:
    run = _fake_git(tag_lines="v0.9.0\nv1.0.0\n", log_lines="feat: new thing\nfix: a bug\n")
    body = pir.build_release_body(tag="v1.0.0", run=run)
    assert pir._RELEASE_BODY in body
    assert "## Release notes" in body
    assert "- feat: new thing" in body
    assert "- fix: a bug" in body
    assert "Initial release." not in body


def test_publish_payload_body_carries_release_notes(tmp_path: Path) -> None:
    # The GitHub API payload body must carry the generated notes, not the static body.
    asset = tmp_path / "CLAUDE.md"
    asset.write_text("x", encoding="utf-8")
    release_calls: list[dict[str, Any]] = []
    run = _fake_git(tag_lines="v0.9.0\nv1.0.0\n", log_lines="feat: shipped\n")

    pir.publish(
        repo="o/r",
        tag="v1.0.0",
        asset_paths=[str(asset)],
        token="t",
        apply_call=_release_apply_call(release_calls),
        upload_asset=_ok_upload([]),
        run=run,
    )

    body = release_calls[0]["payload"]["body"]
    assert "## Release notes" in body
    assert "- feat: shipped" in body
