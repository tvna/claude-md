from __future__ import annotations

import base64
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pr_upsert as pu

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_apply_call(
    status: int,
    body: dict[str, Any] | list[Any],
) -> Callable[..., tuple[int, str]]:
    encoded = json.dumps(body)

    def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
        return status, encoded

    return apply_call


# ---------------------------------------------------------------------------
# _list_open_prs()
# ---------------------------------------------------------------------------


class TestListOpenPrs:
    def test_returns_pr_list(self) -> None:
        apply_call = _make_apply_call(200, [{"number": 7, "title": "chore: regen"}])
        result = pu._list_open_prs(repo="owner/repo", head="feat/x", token="tok", apply_call=apply_call)
        assert result == [{"number": 7, "title": "chore: regen"}]

    def test_includes_owner_and_head_in_url(self) -> None:
        captured: list[str] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.append(url)
            return 200, "[]"

        pu._list_open_prs(repo="myorg/myrepo", head="chore/regen", token="tok", apply_call=apply_call)
        assert "myorg:chore/regen" in captured[0]
        assert "state=open" in captured[0]

    def test_http_error_raises_runtime_error(self) -> None:
        apply_call = _make_apply_call(403, {"message": "forbidden"})
        with pytest.raises(RuntimeError, match="403"):
            pu._list_open_prs(repo="owner/repo", head="x", token="tok", apply_call=apply_call)

    def test_non_array_response_raises(self) -> None:
        apply_call = _make_apply_call(200, {"unexpected": "dict"})
        with pytest.raises(RuntimeError):
            pu._list_open_prs(repo="owner/repo", head="x", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _create_pr()
# ---------------------------------------------------------------------------


class TestCreatePr:
    def test_returns_pr_number(self) -> None:
        apply_call = _make_apply_call(201, {"number": 42, "html_url": "https://example.com/pr/42"})
        number = pu._create_pr(
            repo="owner/repo", head="feat/x", base="main",
            title="chore: regen", body="body text", token="tok",
            apply_call=apply_call,
        )
        assert number == 42

    def test_posts_correct_payload(self) -> None:
        captured_payloads: list[Any] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured_payloads.append(payload)
            return 201, json.dumps({"number": 1})

        pu._create_pr(
            repo="owner/repo", head="chore/regen", base="main",
            title="My PR", body="body", token="tok",
            apply_call=apply_call,
        )
        assert captured_payloads[0]["title"] == "My PR"
        assert captured_payloads[0]["head"] == "chore/regen"
        assert captured_payloads[0]["base"] == "main"
        assert captured_payloads[0]["body"] == "body"

    def test_http_error_raises_runtime_error(self) -> None:
        apply_call = _make_apply_call(422, {"message": "validation failed"})
        with pytest.raises(RuntimeError, match="422"):
            pu._create_pr(
                repo="owner/repo", head="x", base="main",
                title="t", body="b", token="tok",
                apply_call=apply_call,
            )


# ---------------------------------------------------------------------------
# _update_pr()
# ---------------------------------------------------------------------------


class TestUpdatePr:
    def test_patches_correct_payload(self) -> None:
        captured_payloads: list[Any] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured_payloads.append(payload)
            return 200, json.dumps({"number": 7})

        pu._update_pr(repo="owner/repo", number=7, title="new title", body="new body", token="tok", apply_call=apply_call)
        assert captured_payloads[0]["title"] == "new title"
        assert captured_payloads[0]["body"] == "new body"

    def test_includes_pr_number_in_url(self) -> None:
        captured_urls: list[str] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured_urls.append(url)
            return 200, json.dumps({"number": 99})

        pu._update_pr(repo="owner/repo", number=99, title="t", body="b", token="tok", apply_call=apply_call)
        assert "/pulls/99" in captured_urls[0]

    def test_http_error_raises_runtime_error(self) -> None:
        apply_call = _make_apply_call(404, {"message": "not found"})
        with pytest.raises(RuntimeError, match="404"):
            pu._update_pr(repo="owner/repo", number=1, title="t", body="b", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _upsert_pr()
# ---------------------------------------------------------------------------


class TestUpsertPr:
    def _make_list_call(self, prs: list[dict[str, Any]]) -> Callable[..., tuple[int, str]]:
        list_body = json.dumps(prs)
        create_or_update_body = json.dumps({"number": prs[0]["number"] if prs else 55})
        call_count = [0]

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            call_count[0] += 1
            if call_count[0] == 1:  # list call
                return 200, list_body
            return 200 if method == "PATCH" else 201, create_or_update_body

        return apply_call

    def test_creates_when_no_existing_pr(self) -> None:
        prs_returned: list[list[dict[str, Any]]] = [[]]
        create_result = {"number": 55}
        calls: list[tuple[str, str]] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            calls.append((method, url))
            if method == "GET":
                return 200, json.dumps(prs_returned.pop(0))
            return 201, json.dumps(create_result)

        action, number = pu._upsert_pr(
            repo="owner/repo", head="chore/x", base="main",
            title="t", body="b", token="tok",
            apply_call=apply_call,
        )
        assert action == "created"
        assert number == 55
        methods = [c[0] for c in calls]
        assert "GET" in methods
        assert "POST" in methods

    def test_updates_when_existing_pr(self) -> None:
        prs_returned: list[list[dict[str, Any]]] = [[{"number": 7}]]
        calls: list[tuple[str, str]] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            calls.append((method, url))
            if method == "GET":
                return 200, json.dumps(prs_returned.pop(0))
            return 200, json.dumps({"number": 7})

        action, number = pu._upsert_pr(
            repo="owner/repo", head="chore/x", base="main",
            title="t", body="b", token="tok",
            apply_call=apply_call,
        )
        assert action == "updated"
        assert number == 7
        methods = [c[0] for c in calls]
        assert "GET" in methods
        assert "PATCH" in methods


# ---------------------------------------------------------------------------
# _cmd_upsert() / upsert subcommand
# ---------------------------------------------------------------------------


class TestCmdUpsert:
    def test_success_create(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("PR body content", encoding="utf-8")
        monkeypatch.setattr(pu, "_upsert_pr", lambda **kw: ("created", 42))
        rc = pu.main(["upsert", "--head", "chore/x", "--base", "main", "--title", "t", "--body-file", str(body_file)])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "42"

    def test_success_update(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("body", encoding="utf-8")
        monkeypatch.setattr(pu, "_upsert_pr", lambda **kw: ("updated", 7))
        rc = pu.main(["upsert", "--head", "chore/x", "--base", "main", "--title", "t", "--body-file", str(body_file)])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "7"

    def test_missing_token_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("body", encoding="utf-8")
        rc = pu.main(["upsert", "--head", "x", "--base", "main", "--title", "t", "--body-file", str(body_file)])
        assert rc == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_missing_repo_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.delenv("REPO", raising=False)
        body_file = tmp_path / "body.md"
        body_file.write_text("body", encoding="utf-8")
        rc = pu.main(["upsert", "--head", "x", "--base", "main", "--title", "t", "--body-file", str(body_file)])
        assert rc == 1
        assert "REPO" in capsys.readouterr().err

    def test_missing_body_file_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        rc = pu.main(["upsert", "--head", "x", "--base", "main", "--title", "t", "--body-file", str(tmp_path / "nonexistent.md")])
        assert rc == 1
        assert "body" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# _cmd_find() / find subcommand
# ---------------------------------------------------------------------------


class TestCmdFind:
    def test_found_prints_pr_number(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setattr(pu, "_list_open_prs", lambda **kw: [{"number": 55}])
        rc = pu.main(["find", "--head", "chore/x"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "55"

    def test_not_found_prints_nothing(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setattr(pu, "_list_open_prs", lambda **kw: [])
        rc = pu.main(["find", "--head", "chore/x"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_missing_token_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("REPO", "owner/repo")
        rc = pu.main(["find", "--head", "chore/x"])
        assert rc == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_missing_repo_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.delenv("REPO", raising=False)
        rc = pu.main(["find", "--head", "chore/x"])
        assert rc == 1
        assert "REPO" in capsys.readouterr().err

    def test_api_error_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")

        def raise_error(**kw: object) -> list[dict[str, Any]]:
            raise RuntimeError("API failed")

        monkeypatch.setattr(pu, "_list_open_prs", raise_error)
        rc = pu.main(["find", "--head", "chore/x"])
        assert rc == 1
        assert "API failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _list_open_prs_by_prefix()
# ---------------------------------------------------------------------------


def _sequence_apply_call(
    responses: list[tuple[int, list[Any]]],
) -> Callable[..., tuple[int, str]]:
    """Return an apply_call yielding *responses* (status, body) per call, in order."""
    calls = {"n": 0}

    def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
        status, body = responses[calls["n"]]
        calls["n"] += 1
        return status, json.dumps(body)

    return apply_call


class TestListOpenPrsByPrefix:
    def test_filters_by_prefix(self) -> None:
        page = [
            {"number": 1, "head": {"ref": "codex/devcontainer-image-pins-aaa"}},
            {"number": 2, "head": {"ref": "claude/other"}},
            {"number": 3, "head": {"ref": "codex/devcontainer-image-pins-bbb"}},
        ]
        apply_call = _sequence_apply_call([(200, page)])
        result = pu._list_open_prs_by_prefix(
            repo="owner/repo", prefix="codex/devcontainer-image-pins-", token="tok", apply_call=apply_call
        )
        assert [p["number"] for p in result] == [1, 3]

    def test_paginates_until_short_page(self) -> None:
        full = [{"number": i, "head": {"ref": "codex/devcontainer-image-pins-x"}} for i in range(100)]
        tail = [{"number": 100, "head": {"ref": "codex/devcontainer-image-pins-y"}}]
        apply_call = _sequence_apply_call([(200, full), (200, tail)])
        result = pu._list_open_prs_by_prefix(
            repo="owner/repo", prefix="codex/devcontainer-image-pins-", token="tok", apply_call=apply_call
        )
        assert len(result) == 101

    def test_http_error_raises(self) -> None:
        apply_call = _make_apply_call(500, {"message": "boom"})
        with pytest.raises(RuntimeError, match="500"):
            pu._list_open_prs_by_prefix(repo="owner/repo", prefix="codex/", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _compare_behind()
# ---------------------------------------------------------------------------


class TestCompareBehind:
    def test_returns_behind_by(self) -> None:
        apply_call = _make_apply_call(200, {"behind_by": 4, "ahead_by": 1})
        n = pu._compare_behind(repo="owner/repo", base="main", head="feat/x", token="tok", apply_call=apply_call)
        assert n == 4

    def test_missing_field_raises(self) -> None:
        apply_call = _make_apply_call(200, {"ahead_by": 1})
        with pytest.raises(RuntimeError, match="behind_by"):
            pu._compare_behind(repo="owner/repo", base="main", head="x", token="tok", apply_call=apply_call)

    def test_http_error_raises(self) -> None:
        apply_call = _make_apply_call(404, {"message": "not found"})
        with pytest.raises(RuntimeError, match="404"):
            pu._compare_behind(repo="owner/repo", base="main", head="x", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _close_pr() / _delete_branch() / _comment_pr()
# ---------------------------------------------------------------------------


class TestCloseDeleteComment:
    def test_close_pr_sends_closed_state(self) -> None:
        captured: dict[str, Any] = {}

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.update(method=method, url=url, payload=payload)
            return 200, "{}"

        pu._close_pr(repo="owner/repo", number=7, token="tok", apply_call=apply_call)
        assert captured["method"] == "PATCH"
        assert captured["payload"] == {"state": "closed"}
        assert captured["url"].endswith("/pulls/7")

    def test_close_pr_http_error_raises(self) -> None:
        apply_call = _make_apply_call(422, {"message": "bad"})
        with pytest.raises(RuntimeError, match="422"):
            pu._close_pr(repo="owner/repo", number=7, token="tok", apply_call=apply_call)

    def test_delete_branch_success(self) -> None:
        captured: dict[str, Any] = {}

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.update(method=method, url=url)
            return 204, ""

        pu._delete_branch(repo="owner/repo", branch="codex/x", token="tok", apply_call=apply_call)
        assert captured["method"] == "DELETE"
        assert captured["url"].endswith("/git/refs/heads/codex/x")

    def test_delete_branch_already_gone_is_ok(self) -> None:
        for code in (404, 422):
            apply_call = _make_apply_call(code, {"message": "gone"})
            pu._delete_branch(repo="owner/repo", branch="codex/x", token="tok", apply_call=apply_call)

    def test_delete_branch_other_error_raises(self) -> None:
        apply_call = _make_apply_call(500, {"message": "boom"})
        with pytest.raises(RuntimeError, match="500"):
            pu._delete_branch(repo="owner/repo", branch="codex/x", token="tok", apply_call=apply_call)

    def test_comment_pr_posts_body(self) -> None:
        captured: dict[str, Any] = {}

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.update(method=method, url=url, payload=payload)
            return 201, "{}"

        pu._comment_pr(repo="owner/repo", number=9, body="hello", token="tok", apply_call=apply_call)
        assert captured["method"] == "POST"
        assert captured["payload"] == {"body": "hello"}
        assert captured["url"].endswith("/issues/9/comments")

    def test_comment_pr_http_error_raises(self) -> None:
        apply_call = _make_apply_call(403, {"message": "no"})
        with pytest.raises(RuntimeError, match="403"):
            pu._comment_pr(repo="owner/repo", number=9, body="x", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _get_pr()
# ---------------------------------------------------------------------------


class TestGetPr:
    def test_returns_pr_object(self) -> None:
        apply_call = _make_apply_call(200, {"number": 5, "mergeable_state": "clean"})
        pr = pu._get_pr(repo="owner/repo", number=5, token="tok", apply_call=apply_call)
        assert pr["mergeable_state"] == "clean"

    def test_includes_pr_number_in_url(self) -> None:
        captured: list[str] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.append(url)
            return 200, json.dumps({"number": 9})

        pu._get_pr(repo="owner/repo", number=9, token="tok", apply_call=apply_call)
        assert captured[0].endswith("/pulls/9")

    def test_http_error_raises(self) -> None:
        apply_call = _make_apply_call(404, {"message": "nope"})
        with pytest.raises(RuntimeError, match="404"):
            pu._get_pr(repo="owner/repo", number=5, token="tok", apply_call=apply_call)

    def test_non_object_raises(self) -> None:
        apply_call = _make_apply_call(200, [1, 2])
        with pytest.raises(RuntimeError):
            pu._get_pr(repo="owner/repo", number=5, token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _merge_pr()
# ---------------------------------------------------------------------------


class TestMergePr:
    def test_success_returns_true_and_pins_sha(self) -> None:
        captured: dict[str, Any] = {}

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.update(method=method, url=url, payload=payload)
            return 200, json.dumps({"merged": True})

        ok = pu._merge_pr(
            repo="owner/repo", number=7, sha="abc", merge_method="squash", token="tok", apply_call=apply_call
        )
        assert ok is True
        assert captured["method"] == "PUT"
        assert captured["url"].endswith("/pulls/7/merge")
        assert captured["payload"] == {"merge_method": "squash", "sha": "abc"}

    def test_405_not_mergeable_returns_false(self) -> None:
        apply_call = _make_apply_call(405, {"message": "not mergeable"})
        ok = pu._merge_pr(
            repo="owner/repo", number=7, sha="a", merge_method="squash", token="tok", apply_call=apply_call
        )
        assert ok is False

    def test_409_sha_mismatch_returns_false(self) -> None:
        apply_call = _make_apply_call(409, {"message": "head changed"})
        ok = pu._merge_pr(
            repo="owner/repo", number=7, sha="a", merge_method="squash", token="tok", apply_call=apply_call
        )
        assert ok is False

    def test_other_error_raises(self) -> None:
        apply_call = _make_apply_call(500, {"message": "boom"})
        with pytest.raises(RuntimeError, match="500"):
            pu._merge_pr(
                repo="owner/repo", number=7, sha="a", merge_method="squash", token="tok", apply_call=apply_call
            )


# ---------------------------------------------------------------------------
# _get_ref_sha()
# ---------------------------------------------------------------------------


class TestGetRefSha:
    def test_returns_object_sha(self) -> None:
        apply_call = _make_apply_call(200, {"object": {"sha": "deadbeef"}})
        sha = pu._get_ref_sha(repo="owner/repo", ref="heads/main", token="tok", apply_call=apply_call)
        assert sha == "deadbeef"

    def test_requests_single_ref_endpoint(self) -> None:
        captured: list[str] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.append(url)
            return 200, json.dumps({"object": {"sha": "s"}})

        pu._get_ref_sha(repo="o/r", ref="heads/main", token="tok", apply_call=apply_call)
        assert captured[0].endswith("/repos/o/r/git/ref/heads/main")

    def test_http_error_raises(self) -> None:
        apply_call = _make_apply_call(404, {"message": "not found"})
        with pytest.raises(RuntimeError, match="404"):
            pu._get_ref_sha(repo="owner/repo", ref="heads/main", token="tok", apply_call=apply_call)

    def test_missing_sha_raises(self) -> None:
        apply_call = _make_apply_call(200, {"object": {}})
        with pytest.raises(RuntimeError, match="missing object.sha"):
            pu._get_ref_sha(repo="owner/repo", ref="heads/main", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _create_branch_ref()
# ---------------------------------------------------------------------------


class TestCreateBranchRef:
    def test_posts_fully_qualified_ref(self) -> None:
        captured: dict[str, Any] = {}

        def apply_call(*, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
            captured["method"] = method
            captured["url"] = url
            captured["payload"] = payload
            return 201, "{}"

        pu._create_branch_ref(repo="o/r", branch="feat/x", sha="abc", token="tok", apply_call=apply_call)
        assert captured["method"] == "POST"
        assert captured["url"].endswith("/repos/o/r/git/refs")
        assert captured["payload"] == {"ref": "refs/heads/feat/x", "sha": "abc"}

    def test_http_error_raises(self) -> None:
        apply_call = _make_apply_call(422, {"message": "Reference already exists"})
        with pytest.raises(RuntimeError, match="422"):
            pu._create_branch_ref(repo="o/r", branch="feat/x", sha="abc", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _create_commit_on_branch()
# ---------------------------------------------------------------------------


def _make_graphql_call(
    status: int, response: dict[str, Any]
) -> Callable[..., tuple[int, dict[str, Any]]]:
    def graphql_call(*, query: str, variables: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
        return status, response

    return graphql_call


class TestCreateCommitOnBranch:
    def test_returns_commit_oid(self) -> None:
        graphql_call = _make_graphql_call(200, {"data": {"createCommitOnBranch": {"commit": {"oid": "c0ffee"}}}})
        oid = pu._create_commit_on_branch(
            repo="o/r",
            branch="feat/x",
            expected_head_oid="base",
            headline="subj",
            body="Refs #1",
            additions=[{"path": "a.txt", "contents": "Zm9v"}],
            token="tok",
            graphql_call=graphql_call,
        )
        assert oid == "c0ffee"

    def test_builds_expected_input_variables(self) -> None:
        captured: dict[str, Any] = {}

        def graphql_call(*, query: str, variables: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
            captured.update(variables)
            return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": "x"}}}}

        pu._create_commit_on_branch(
            repo="o/r",
            branch="feat/x",
            expected_head_oid="base-sha",
            headline="subj",
            body="Refs #1",
            additions=[{"path": "a.txt", "contents": "Zm9v"}],
            token="tok",
            graphql_call=graphql_call,
        )
        inp = captured["input"]
        assert inp["branch"] == {"repositoryNameWithOwner": "o/r", "branchName": "feat/x"}
        assert inp["expectedHeadOid"] == "base-sha"
        assert inp["message"] == {"headline": "subj", "body": "Refs #1"}
        assert inp["fileChanges"] == {"additions": [{"path": "a.txt", "contents": "Zm9v"}]}

    def test_omits_empty_message_body(self) -> None:
        captured: dict[str, Any] = {}

        def graphql_call(*, query: str, variables: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
            captured.update(variables)
            return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": "x"}}}}

        pu._create_commit_on_branch(
            repo="o/r",
            branch="b",
            expected_head_oid="s",
            headline="subj",
            body="",
            additions=[],
            token="tok",
            graphql_call=graphql_call,
        )
        assert captured["input"]["message"] == {"headline": "subj"}

    def test_http_error_raises(self) -> None:
        graphql_call = _make_graphql_call(500, {})
        with pytest.raises(RuntimeError, match="createCommitOnBranch HTTP 500"):
            pu._create_commit_on_branch(
                repo="o/r", branch="b", expected_head_oid="s", headline="h", body="", additions=[],
                token="tok", graphql_call=graphql_call,
            )

    def test_graphql_errors_raise(self) -> None:
        graphql_call = _make_graphql_call(200, {"errors": [{"message": "stale expectedHeadOid"}]})
        with pytest.raises(RuntimeError, match="createCommitOnBranch errors"):
            pu._create_commit_on_branch(
                repo="o/r", branch="b", expected_head_oid="s", headline="h", body="", additions=[],
                token="tok", graphql_call=graphql_call,
            )

    def test_empty_oid_raises(self) -> None:
        graphql_call = _make_graphql_call(200, {"data": {"createCommitOnBranch": {"commit": {"oid": ""}}}})
        with pytest.raises(RuntimeError, match="missing commit oid"):
            pu._create_commit_on_branch(
                repo="o/r", branch="b", expected_head_oid="s", headline="h", body="", additions=[],
                token="tok", graphql_call=graphql_call,
            )

    def test_malformed_response_raises(self) -> None:
        graphql_call = _make_graphql_call(200, {"data": {"createCommitOnBranch": {"commit": {}}}})
        with pytest.raises(RuntimeError, match="unexpected response"):
            pu._create_commit_on_branch(
                repo="o/r", branch="b", expected_head_oid="s", headline="h", body="", additions=[],
                token="tok", graphql_call=graphql_call,
            )


# ---------------------------------------------------------------------------
# _get_branch_head_oid()
# ---------------------------------------------------------------------------


class TestGetBranchHeadOid:
    def test_returns_object_sha(self) -> None:
        apply_call = _make_apply_call(200, {"object": {"sha": "feedface"}})
        sha = pu._get_branch_head_oid(repo="o/r", branch="chore/x", token="tok", apply_call=apply_call)
        assert sha == "feedface"

    def test_absent_branch_returns_none(self) -> None:
        apply_call = _make_apply_call(404, {"message": "Not Found"})
        sha = pu._get_branch_head_oid(repo="o/r", branch="chore/x", token="tok", apply_call=apply_call)
        assert sha is None

    def test_queries_branch_ref_endpoint(self) -> None:
        captured: list[str] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.append(url)
            return 200, json.dumps({"object": {"sha": "s"}})

        pu._get_branch_head_oid(repo="o/r", branch="chore/x", token="tok", apply_call=apply_call)
        assert captured[0].endswith("/repos/o/r/git/ref/heads/chore/x")

    def test_other_error_raises(self) -> None:
        apply_call = _make_apply_call(500, {"message": "boom"})
        with pytest.raises(RuntimeError, match="500"):
            pu._get_branch_head_oid(repo="o/r", branch="chore/x", token="tok", apply_call=apply_call)

    def test_missing_sha_raises(self) -> None:
        apply_call = _make_apply_call(200, {"object": {}})
        with pytest.raises(RuntimeError, match="missing object.sha"):
            pu._get_branch_head_oid(repo="o/r", branch="chore/x", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# _get_file_bytes()
# ---------------------------------------------------------------------------


def _contents_response(raw: bytes) -> dict[str, Any]:
    return {"encoding": "base64", "content": base64.b64encode(raw).decode("ascii")}


class TestGetFileBytes:
    def test_decodes_base64_content(self) -> None:
        apply_call = _make_apply_call(200, _contents_response(b"hello\nworld\n"))
        out = pu._get_file_bytes(repo="o/r", path="a/b.md", ref="main", token="tok", apply_call=apply_call)
        assert out == b"hello\nworld\n"

    def test_absent_path_returns_none(self) -> None:
        apply_call = _make_apply_call(404, {"message": "Not Found"})
        out = pu._get_file_bytes(repo="o/r", path="a/b.md", ref="main", token="tok", apply_call=apply_call)
        assert out is None

    def test_includes_ref_in_url(self) -> None:
        captured: list[str] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured.append(url)
            return 200, json.dumps(_contents_response(b"x"))

        pu._get_file_bytes(repo="o/r", path="a/b.md", ref="chore/x", token="tok", apply_call=apply_call)
        assert "/repos/o/r/contents/a/b.md?ref=chore/x" in captured[0]

    def test_non_base64_encoding_raises(self) -> None:
        # Blobs over 1 MB come back with encoding "none" and an empty body; a
        # truncated body must never masquerade as matching content.
        apply_call = _make_apply_call(200, {"encoding": "none", "content": ""})
        with pytest.raises(RuntimeError, match="unexpected encoding"):
            pu._get_file_bytes(repo="o/r", path="a/b.md", ref="main", token="tok", apply_call=apply_call)

    def test_http_error_raises(self) -> None:
        apply_call = _make_apply_call(403, {"message": "forbidden"})
        with pytest.raises(RuntimeError, match="403"):
            pu._get_file_bytes(repo="o/r", path="a/b.md", ref="main", token="tok", apply_call=apply_call)


# ---------------------------------------------------------------------------
# upsert_single_file_pr()  (the #1466 reuse-safe publish path)
# ---------------------------------------------------------------------------


class _Router:
    """Route apply_call requests by (method, url-substring) to canned responses.

    Records the ordered request log so tests can assert which endpoints were hit
    (e.g. that the reused-branch path never creates a ref or touches the base).
    """

    def __init__(self, routes: list[tuple[str, str, int, Any]]) -> None:
        # routes: (method, url_substring, status, body) matched in order.
        self._routes = routes
        self.log: list[tuple[str, str, Any]] = []

    def apply_call(self, *, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
        self.log.append((method, url, payload))
        for m, sub, status, body in self._routes:
            if m == method and sub in url:
                encoded = body if isinstance(body, str) else json.dumps(body)
                return status, encoded
        raise AssertionError(f"unrouted request: {method} {url}")


class _RecordingGraphql:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def graphql_call(self, *, query: str, variables: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
        self.calls.append(variables)
        return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": "newoid"}}}}


class TestUpsertSingleFilePr:
    _CONTENT = b"# report\nrow\n"

    def test_no_drift_vs_base_is_noop(self) -> None:
        router = _Router([("GET", "/contents/", 200, _contents_response(self._CONTENT))])
        gql = _RecordingGraphql()
        result = pu.upsert_single_file_pr(
            repo="o/r", path="docs/r.md", content=self._CONTENT, base="main",
            branch="chore/refresh", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "up-to-date"
        assert gql.calls == []
        # Only the base-drift probe ran; no branch ref / commit / PR calls.
        assert len(router.log) == 1

    def test_branch_absent_creates_branch_and_commit(self) -> None:
        router = _Router([
            ("GET", "/contents/docs/r.md?ref=main", 404, {"message": "Not Found"}),
            ("GET", "/git/ref/heads/chore/refresh", 404, {"message": "Not Found"}),
            ("GET", "/git/ref/heads/main", 200, {"object": {"sha": "basesha"}}),
            ("POST", "/git/refs", 201, {}),
            ("GET", "/pulls?", 200, []),
            ("POST", "/pulls", 201, {"number": 77}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_single_file_pr(
            repo="o/r", path="docs/r.md", content=self._CONTENT, base="main",
            branch="chore/refresh", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "created:77"
        # New branch was cut off main and the commit anchored to the base sha.
        assert gql.calls[0]["input"]["expectedHeadOid"] == "basesha"
        assert gql.calls[0]["input"]["fileChanges"]["additions"][0]["path"] == "docs/r.md"

    def test_reused_branch_appends_onto_tip_without_force_push(self) -> None:
        # Acceptance criterion (#1466): the fixed branch already exists with a
        # stale snapshot. The commit must append onto the branch tip
        # (expectedHeadOid = branch head), never create a ref or force-push.
        router = _Router([
            ("GET", "/contents/docs/r.md?ref=main", 200, _contents_response(b"# stale main\n")),
            ("GET", "/git/ref/heads/chore/refresh", 200, {"object": {"sha": "branchtip"}}),
            ("GET", "/contents/docs/r.md?ref=chore/refresh", 200, _contents_response(b"# stale branch\n")),
            ("GET", "/pulls?", 200, [{"number": 7}]),
            ("PATCH", "/pulls/7", 200, {"number": 7}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_single_file_pr(
            repo="o/r", path="docs/r.md", content=self._CONTENT, base="main",
            branch="chore/refresh", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "committed:7"
        assert gql.calls[0]["input"]["expectedHeadOid"] == "branchtip"
        # No branch ref was created and no force-push occurred.
        assert not any(method == "POST" and "/git/refs" in url for method, url, _ in router.log)

    def test_reused_branch_tip_already_current_skips_commit(self) -> None:
        router = _Router([
            ("GET", "/contents/docs/r.md?ref=main", 200, _contents_response(b"# stale main\n")),
            ("GET", "/git/ref/heads/chore/refresh", 200, {"object": {"sha": "branchtip"}}),
            ("GET", "/contents/docs/r.md?ref=chore/refresh", 200, _contents_response(self._CONTENT)),
            ("GET", "/pulls?", 200, [{"number": 7}]),
            ("PATCH", "/pulls/7", 200, {"number": 7}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_single_file_pr(
            repo="o/r", path="docs/r.md", content=self._CONTENT, base="main",
            branch="chore/refresh", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "branch-current:7"
        assert gql.calls == []
