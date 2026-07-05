from __future__ import annotations

import base64
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _pr_commit_batch as pcb
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
        oid = pcb._create_commit_on_branch(
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

        pcb._create_commit_on_branch(
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

        pcb._create_commit_on_branch(
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
            pcb._create_commit_on_branch(
                repo="o/r", branch="b", expected_head_oid="s", headline="h", body="", additions=[],
                token="tok", graphql_call=graphql_call,
            )

    def test_graphql_errors_raise(self) -> None:
        graphql_call = _make_graphql_call(200, {"errors": [{"message": "stale expectedHeadOid"}]})
        with pytest.raises(RuntimeError, match="createCommitOnBranch errors"):
            pcb._create_commit_on_branch(
                repo="o/r", branch="b", expected_head_oid="s", headline="h", body="", additions=[],
                token="tok", graphql_call=graphql_call,
            )

    def test_empty_oid_raises(self) -> None:
        graphql_call = _make_graphql_call(200, {"data": {"createCommitOnBranch": {"commit": {"oid": ""}}}})
        with pytest.raises(RuntimeError, match="missing commit oid"):
            pcb._create_commit_on_branch(
                repo="o/r", branch="b", expected_head_oid="s", headline="h", body="", additions=[],
                token="tok", graphql_call=graphql_call,
            )

    def test_malformed_response_raises(self) -> None:
        graphql_call = _make_graphql_call(200, {"data": {"createCommitOnBranch": {"commit": {}}}})
        with pytest.raises(RuntimeError, match="unexpected response"):
            pcb._create_commit_on_branch(
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


class TestUpsertFilesPrBatching:
    def test_large_addition_set_publishes_in_chained_commits(self) -> None:
        # Integration: a backlog larger than _MAX_BATCH_FILES must publish as
        # several chained signed commits instead of one overflowing mutation
        # (#1578). The first addition is absent on base, so the base-drift probe
        # short-circuits to drift after a single contents call.
        additions = [(f"docs/generated/scripts/ast/f{i:03d}.md", b"x\n") for i in range(pcb._MAX_BATCH_FILES + 1)]
        router = _Router([
            ("GET", "/contents/docs/generated/scripts/ast/f000.md?ref=main", 404, {"message": "Not Found"}),
            ("GET", "/git/ref/heads/chore/update-generated-docs", 404, {"message": "Not Found"}),
            ("GET", "/git/ref/heads/main", 200, {"object": {"sha": "basesha"}}),
            ("POST", "/git/refs", 201, {}),
            ("GET", "/pulls?", 200, []),
            ("POST", "/pulls", 201, {"number": 7}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_files_pr(
            repo="o/r", additions=additions, deletions=[], base="main",
            branch="chore/update-generated-docs", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "created:7"
        # 41 files at 40/batch -> two chained commits, second anchored to the first.
        assert len(gql.calls) == 2
        assert gql.calls[0]["input"]["expectedHeadOid"] == "basesha"
        assert gql.calls[1]["input"]["expectedHeadOid"] == "newoid"


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

    def test_recreate_deletes_branch_and_recommits_off_base(self) -> None:
        # #1560: with recreate=True, drift, and no PR open on the branch, the
        # reused branch is deleted and the commit lands on a fresh branch cut off
        # base (a single signed commit anchored to the base sha -> no inherited
        # unsigned ancestor). A delete is not a force-push, so the all-branches
        # non_fast_forward ruleset holds.
        router = _Router([
            ("GET", "/contents/docs/r.md?ref=main", 200, _contents_response(b"# stale main\n")),
            ("GET", "/pulls?", 200, []),
            ("DELETE", "/git/refs/heads/chore/refresh", 200, {}),
            ("GET", "/git/ref/heads/chore/refresh", 404, {"message": "Not Found"}),
            ("GET", "/git/ref/heads/main", 200, {"object": {"sha": "basesha"}}),
            ("POST", "/git/refs", 201, {}),
            ("POST", "/pulls", 201, {"number": 9}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_single_file_pr(
            repo="o/r", path="docs/r.md", content=self._CONTENT, base="main",
            branch="chore/refresh", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            recreate=True, apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "created:9"
        # The reused branch ref was deleted before the fresh commit.
        assert any(m == "DELETE" and "/git/refs/heads/chore/refresh" in u for m, u, _ in router.log)
        # The commit anchors to the base sha, not a stale branch tip.
        assert gql.calls[0]["input"]["expectedHeadOid"] == "basesha"
        # A fresh branch ref was cut off base.
        assert any(m == "POST" and "/git/refs" in u for m, u, _ in router.log)

    def test_recreate_skipped_when_pr_already_open(self) -> None:
        # #2382: with recreate=True, drift, but an open PR already exists for the
        # branch, the delete must be skipped. Deleting the branch out from under
        # an open PR auto-closes it on GitHub, and the next PR opened for the
        # recreated branch gets a new number instead of reusing the closed one.
        # If base keeps advancing faster than the open PR can be merged, that
        # cycle repeats forever and no PR in the series ever merges. The commit
        # must instead append onto the existing branch tip and reconcile the
        # same open PR.
        router = _Router([
            ("GET", "/contents/docs/r.md?ref=main", 200, _contents_response(b"# stale main\n")),
            ("GET", "/pulls?", 200, [{"number": 7}]),
            ("GET", "/git/ref/heads/chore/refresh", 200, {"object": {"sha": "branchtip"}}),
            ("GET", "/contents/docs/r.md?ref=chore/refresh", 200, _contents_response(b"# stale branch\n")),
            ("PATCH", "/pulls/7", 200, {"number": 7}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_single_file_pr(
            repo="o/r", path="docs/r.md", content=self._CONTENT, base="main",
            branch="chore/refresh", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            recreate=True, apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "committed:7"
        # The branch was never deleted; the open PR stays alive across the run.
        assert not any(m == "DELETE" for m, _u, _ in router.log)
        # The commit appends onto the existing branch tip, not a fresh base cut.
        assert gql.calls[0]["input"]["expectedHeadOid"] == "branchtip"
        # No new branch ref was created.
        assert not any(m == "POST" and "/git/refs" in u for m, u, _ in router.log)

    def test_recreate_no_drift_is_noop_and_keeps_branch(self) -> None:
        # No drift vs base: short-circuit before any delete, so recreate never
        # churns the branch when the snapshot is already current.
        router = _Router([("GET", "/contents/", 200, _contents_response(self._CONTENT))])
        gql = _RecordingGraphql()
        result = pu.upsert_single_file_pr(
            repo="o/r", path="docs/r.md", content=self._CONTENT, base="main",
            branch="chore/refresh", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            recreate=True, apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "up-to-date"
        assert not any(m == "DELETE" for m, _u, _ in router.log)
        assert gql.calls == []


# ---------------------------------------------------------------------------
# _create_commit_on_branch() deletions
# ---------------------------------------------------------------------------


class TestCreateCommitOnBranchDeletions:
    def test_includes_deletions_in_file_changes(self) -> None:
        captured: dict[str, Any] = {}

        def graphql_call(*, query: str, variables: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
            captured.update(variables)
            return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": "x"}}}}

        pcb._create_commit_on_branch(
            repo="o/r", branch="b", expected_head_oid="s", headline="subj", body="",
            additions=[{"path": "a.txt", "contents": "Zm9v"}],
            deletions=[{"path": "old.txt"}],
            token="tok", graphql_call=graphql_call,
        )
        assert captured["input"]["fileChanges"] == {
            "additions": [{"path": "a.txt", "contents": "Zm9v"}],
            "deletions": [{"path": "old.txt"}],
        }

    def test_empty_deletions_key_is_omitted(self) -> None:
        captured: dict[str, Any] = {}

        def graphql_call(*, query: str, variables: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
            captured.update(variables)
            return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": "x"}}}}

        pcb._create_commit_on_branch(
            repo="o/r", branch="b", expected_head_oid="s", headline="subj", body="",
            additions=[{"path": "a.txt", "contents": "Zm9v"}], deletions=[],
            token="tok", graphql_call=graphql_call,
        )
        assert "deletions" not in captured["input"]["fileChanges"]


# ---------------------------------------------------------------------------
# upsert_files_pr()  (multi-file generalisation)
# ---------------------------------------------------------------------------


class TestValidateCommitPaths:
    @pytest.mark.parametrize(
        "path",
        ["docs/generated/x.md", "CLAUDE.md", "a/b/c.txt"],
    )
    def test_valid_paths_accepted(self, path: str) -> None:
        assert pcb._is_valid_commit_path(path) is True

    @pytest.mark.parametrize(
        "path",
        ["", "   ", "docs/generated/graph/", "/abs/path.md", "a//b.md", "a/./b.md", "a/../b.md", "."],
    )
    def test_malformed_paths_rejected(self, path: str) -> None:
        assert pcb._is_valid_commit_path(path) is False

    def test_validate_lists_every_offending_entry(self) -> None:
        with pytest.raises(RuntimeError, match="invalid entries.*addition.*deletion"):
            pcb._validate_commit_paths([("bad/", b"x")], ["also/bad/"])

    def test_validate_passes_clean_payload(self) -> None:
        # A well-formed payload raises nothing (the function returns None).
        pcb._validate_commit_paths([("CLAUDE.md", b"x")], ["docs/gone.md"])


class TestUpsertFilesPr:
    def test_both_empty_is_noop(self) -> None:
        router = _Router([])
        gql = _RecordingGraphql()
        result = pu.upsert_files_pr(
            repo="o/r", additions=[], deletions=[], base="main", branch="chore/x",
            title="t", body="b", commit_subject="s", commit_body="", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "up-to-date"
        assert router.log == []

    def test_directory_level_deletion_path_fails_loud(self) -> None:
        # A directory-level path (trailing slash) is the #1772 payload GitHub
        # rejects with the generic "Something went wrong" error. It must fail
        # loud here, before any network or GraphQL call. Refs #1784.
        router = _Router([])
        gql = _RecordingGraphql()
        with pytest.raises(RuntimeError, match="concrete file paths"):
            pu.upsert_files_pr(
                repo="o/r", additions=[("CLAUDE.md", b"c\n")],
                deletions=["docs/generated/graph/"],
                base="main", branch="chore/x", title="t", body="b",
                commit_subject="s", commit_body="", token="tok",
                apply_call=router.apply_call, graphql_call=gql.graphql_call,
            )
        assert router.log == []
        assert gql.calls == []

    def test_empty_addition_path_fails_loud(self) -> None:
        router = _Router([])
        gql = _RecordingGraphql()
        with pytest.raises(RuntimeError, match="concrete file paths"):
            pu.upsert_files_pr(
                repo="o/r", additions=[("", b"c\n")], deletions=[],
                base="main", branch="chore/x", title="t", body="b",
                commit_subject="s", commit_body="", token="tok",
                apply_call=router.apply_call, graphql_call=gql.graphql_call,
            )
        assert router.log == []
        assert gql.calls == []

    def test_no_drift_across_all_files_is_noop(self) -> None:
        router = _Router([
            ("GET", "/contents/CLAUDE.md?ref=main", 200, _contents_response(b"c\n")),
            ("GET", "/contents/AGENTS.md?ref=main", 200, _contents_response(b"a\n")),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_files_pr(
            repo="o/r", additions=[("CLAUDE.md", b"c\n"), ("AGENTS.md", b"a\n")], deletions=[],
            base="main", branch="chore/x", title="t", body="b",
            commit_subject="s", commit_body="", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "up-to-date"
        assert gql.calls == []

    def test_branch_absent_creates_with_additions_and_deletions(self) -> None:
        router = _Router([
            ("GET", "/contents/CLAUDE.md?ref=main", 200, _contents_response(b"stale\n")),
            ("GET", "/git/ref/heads/chore/x", 404, {"message": "Not Found"}),
            ("GET", "/git/ref/heads/main", 200, {"object": {"sha": "basesha"}}),
            ("POST", "/git/refs", 201, {}),
            ("GET", "/pulls?", 200, []),
            ("POST", "/pulls", 201, {"number": 88}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_files_pr(
            repo="o/r", additions=[("CLAUDE.md", b"new\n")], deletions=["docs/generated/gone.md"],
            base="main", branch="chore/x", title="t", body="b",
            commit_subject="s", commit_body="Refs #1", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "created:88"
        inp = gql.calls[0]["input"]
        assert inp["expectedHeadOid"] == "basesha"
        assert inp["fileChanges"]["additions"][0]["path"] == "CLAUDE.md"
        assert inp["fileChanges"]["deletions"] == [{"path": "docs/generated/gone.md"}]

    def test_reused_branch_appends_when_branch_drifts(self) -> None:
        router = _Router([
            ("GET", "/contents/CLAUDE.md?ref=main", 200, _contents_response(b"stale main\n")),
            ("GET", "/git/ref/heads/chore/x", 200, {"object": {"sha": "branchtip"}}),
            ("GET", "/contents/CLAUDE.md?ref=chore/x", 200, _contents_response(b"stale branch\n")),
            ("GET", "/pulls?", 200, [{"number": 9}]),
            ("PATCH", "/pulls/9", 200, {"number": 9}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_files_pr(
            repo="o/r", additions=[("CLAUDE.md", b"new\n")], deletions=[],
            base="main", branch="chore/x", title="t", body="b",
            commit_subject="s", commit_body="", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "committed:9"
        assert gql.calls[0]["input"]["expectedHeadOid"] == "branchtip"
        assert not any(m == "POST" and "/git/refs" in u for m, u, _ in router.log)

    def test_reused_branch_current_skips_commit(self) -> None:
        router = _Router([
            ("GET", "/contents/CLAUDE.md?ref=main", 200, _contents_response(b"stale main\n")),
            ("GET", "/git/ref/heads/chore/x", 200, {"object": {"sha": "branchtip"}}),
            ("GET", "/contents/CLAUDE.md?ref=chore/x", 200, _contents_response(b"new\n")),
            ("GET", "/pulls?", 200, [{"number": 9}]),
            ("PATCH", "/pulls/9", 200, {"number": 9}),
        ])
        gql = _RecordingGraphql()
        result = pu.upsert_files_pr(
            repo="o/r", additions=[("CLAUDE.md", b"new\n")], deletions=[],
            base="main", branch="chore/x", title="t", body="b",
            commit_subject="s", commit_body="", token="tok",
            apply_call=router.apply_call, graphql_call=gql.graphql_call,
        )
        assert result == "branch-current:9"
        assert gql.calls == []


# ---------------------------------------------------------------------------
# _collect_worktree_changes() / upsert-files subcommand
# ---------------------------------------------------------------------------


class _FakeGitStatus:
    """Stand-in for ``run_git`` returning a canned ``git status --porcelain`` body."""

    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, args: list[str], **kwargs: Any) -> _FakeGitStatus:
        return self


class TestCollectWorktreeChanges:
    def test_explicit_add_reads_worktree_bytes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CLAUDE.md").write_bytes(b"hello\n")
        additions, deletions = pu._collect_worktree_changes(adds=["CLAUDE.md"], diff_prefixes=[])
        assert additions == [("CLAUDE.md", b"hello\n")]
        assert deletions == []

    def test_missing_explicit_add_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RuntimeError, match="readable file"):
            pu._collect_worktree_changes(adds=["nope.md"], diff_prefixes=[])

    def test_from_diff_classifies_add_modify_delete(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        gen = tmp_path / "docs" / "generated"
        gen.mkdir(parents=True)
        (gen / "new.md").write_bytes(b"new\n")
        (gen / "mod.md").write_bytes(b"mod\n")
        # gone.md intentionally absent on disk -> classified as a deletion.
        status = "?? docs/generated/new.md\n M docs/generated/mod.md\n D docs/generated/gone.md\n"
        monkeypatch.setattr(pu, "run_git", _FakeGitStatus(status))
        additions, deletions = pu._collect_worktree_changes(adds=[], diff_prefixes=["docs/generated/"])
        assert dict(additions) == {"docs/generated/new.md": b"new\n", "docs/generated/mod.md": b"mod\n"}
        assert deletions == ["docs/generated/gone.md"]

    def test_from_diff_untracked_directory_expands_to_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # git porcelain shows "?? docs/generated/graph/" (directory, not individual
        # files) when the entire directory is new and has no tracked parent.
        # Passing that directory path as a deletion to createCommitOnBranch is
        # invalid and causes a "Something went wrong" GraphQL error (Refs #1772).
        # The fix: is_dir() -> use git ls-files to expand, respecting .gitignore.
        monkeypatch.chdir(tmp_path)
        graph_dir = tmp_path / "docs" / "generated" / "graph"
        graph_dir.mkdir(parents=True)
        (graph_dir / "doc-dependency-graph.md").write_bytes(b"graph\n")
        (graph_dir / "sub" / "nested.md").parent.mkdir()
        (graph_dir / "sub" / "nested.md").write_bytes(b"nested\n")

        def fake_run_git(args: list[str], **kwargs: object) -> _FakeGitStatus:
            if args[0] == "status":
                return _FakeGitStatus("?? docs/generated/graph/\n")
            # ls-files --others --exclude-standard: return non-ignored files only.
            return _FakeGitStatus(
                "docs/generated/graph/doc-dependency-graph.md\n"
                "docs/generated/graph/sub/nested.md\n"
            )

        monkeypatch.setattr(pu, "run_git", fake_run_git)
        additions, deletions = pu._collect_worktree_changes(adds=[], diff_prefixes=["docs/generated/"])
        assert dict(additions) == {
            "docs/generated/graph/doc-dependency-graph.md": b"graph\n",
            "docs/generated/graph/sub/nested.md": b"nested\n",
        }
        assert deletions == []

    def test_from_diff_untracked_directory_excludes_gitignored_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # git ls-files --others --exclude-standard omits gitignored paths.
        # Verify that _collect_worktree_changes does NOT add ignored files even
        # when they exist on disk inside the untracked directory (Refs #1772).
        monkeypatch.chdir(tmp_path)
        graph_dir = tmp_path / "docs" / "generated" / "graph"
        graph_dir.mkdir(parents=True)
        (graph_dir / "doc.md").write_bytes(b"doc\n")
        (graph_dir / ".DS_Store").write_bytes(b"ignored\n")  # exists on disk

        def fake_run_git(args: list[str], **kwargs: object) -> _FakeGitStatus:
            if args[0] == "status":
                return _FakeGitStatus("?? docs/generated/graph/\n")
            # ls-files honours .gitignore and omits .DS_Store.
            return _FakeGitStatus("docs/generated/graph/doc.md\n")

        monkeypatch.setattr(pu, "run_git", fake_run_git)
        additions, deletions = pu._collect_worktree_changes(adds=[], diff_prefixes=["docs/generated/"])
        assert dict(additions) == {"docs/generated/graph/doc.md": b"doc\n"}
        assert deletions == []

    def test_from_diff_git_failure_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(pu, "run_git", _FakeGitStatus("", returncode=128, stderr="fatal: boom"))
        with pytest.raises(RuntimeError, match="git status failed"):
            pu._collect_worktree_changes(adds=[], diff_prefixes=["docs/generated/"])


class TestCmdUpsertFiles:
    def test_success_invokes_upsert_files_pr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("PR body", encoding="utf-8")
        monkeypatch.setattr(pu, "_collect_worktree_changes", lambda **kw: ([("CLAUDE.md", b"x\n")], []))
        monkeypatch.setattr(pu, "_verify_base_currency", lambda **kw: None)
        captured: dict[str, Any] = {}

        def fake_upsert(**kw: Any) -> str:
            captured.update(kw)
            return "created:42"

        monkeypatch.setattr(pu, "upsert_files_pr", fake_upsert)
        rc = pu.main([
            "upsert-files", "--head", "chore/x", "--base", "main", "--title", "t",
            "--body-file", str(body_file), "--add", "CLAUDE.md", "--commit-body", "Refs #1",
        ])
        assert rc == 0
        assert captured["commit_subject"] == "t"  # defaults to --title
        assert captured["commit_body"] == "Refs #1"
        assert captured["recreate"] is False  # absent flag defaults to append mode
        assert "created:42" in capsys.readouterr().err

    def test_recreate_flag_threads_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # --recreate (the post-merge decision-tree shape, #1574) must reach
        # upsert_files_pr so the fixed branch is recreated off base rather than
        # appended onto its stale tip.
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("PR body", encoding="utf-8")
        monkeypatch.setattr(pu, "_collect_worktree_changes", lambda **kw: ([("CLAUDE.md", b"x\n")], []))
        monkeypatch.setattr(pu, "_verify_base_currency", lambda **kw: None)
        captured: dict[str, Any] = {}

        def fake_upsert(**kw: Any) -> str:
            captured.update(kw)
            return "created:7"

        monkeypatch.setattr(pu, "upsert_files_pr", fake_upsert)
        rc = pu.main([
            "upsert-files", "--head", "chore/update-generated-docs", "--base", "main",
            "--title", "t", "--body-file", str(body_file),
            "--from-diff", "docs/generated/", "--recreate",
        ])
        assert rc == 0
        assert captured["recreate"] is True

    def test_no_changes_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("b", encoding="utf-8")
        monkeypatch.setattr(pu, "_collect_worktree_changes", lambda **kw: ([], []))
        called = {"n": 0}

        def fake_upsert(**kw: Any) -> str:
            called["n"] += 1
            return "x"

        monkeypatch.setattr(pu, "upsert_files_pr", fake_upsert)
        rc = pu.main([
            "upsert-files", "--head", "chore/x", "--base", "main", "--title", "t",
            "--body-file", str(body_file), "--from-diff", "docs/generated/",
        ])
        assert rc == 0
        assert called["n"] == 0
        assert "No file changes" in capsys.readouterr().err

    def test_missing_token_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("b", encoding="utf-8")
        rc = pu.main([
            "upsert-files", "--head", "x", "--base", "main", "--title", "t",
            "--body-file", str(body_file), "--add", "CLAUDE.md",
        ])
        assert rc == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_missing_body_file_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        rc = pu.main([
            "upsert-files", "--head", "x", "--base", "main", "--title", "t",
            "--body-file", str(tmp_path / "nope.md"), "--add", "CLAUDE.md",
        ])
        assert rc == 1
        assert "body" in capsys.readouterr().err.lower()

    def test_stale_base_blocks_and_skips_upsert(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A stale local base must block the commit before any branch is touched,
        # so the #2311 unintended-revert cannot ship.
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("PR body", encoding="utf-8")
        monkeypatch.setattr(pu, "_collect_worktree_changes", lambda **kw: ([(".github/dependabot.yml", b"x\n")], []))

        def raise_stale(**kw: Any) -> None:
            raise RuntimeError("Local base is stale for: .github/dependabot.yml. ...")

        monkeypatch.setattr(pu, "_verify_base_currency", raise_stale)
        called = {"n": 0}

        def count_upsert(**kw: Any) -> str:
            called["n"] += 1
            return "x"

        monkeypatch.setattr(pu, "upsert_files_pr", count_upsert)
        rc = pu.main([
            "upsert-files", "--head", "chore/x", "--base", "main", "--title", "t",
            "--body-file", str(body_file), "--add", ".github/dependabot.yml",
        ])
        assert rc == 1
        assert called["n"] == 0
        assert "stale" in capsys.readouterr().err.lower()

    def test_allow_stale_base_flag_skips_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # With --allow-stale-base the check is not consulted at all; the operator
        # has reconciled the file against the real base by hand.
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        body_file = tmp_path / "body.md"
        body_file.write_text("PR body", encoding="utf-8")
        monkeypatch.setattr(pu, "_collect_worktree_changes", lambda **kw: ([("CLAUDE.md", b"x\n")], []))

        def fail_if_called(**kw: Any) -> None:
            raise AssertionError("_verify_base_currency must not run under --allow-stale-base")

        monkeypatch.setattr(pu, "_verify_base_currency", fail_if_called)
        monkeypatch.setattr(pu, "upsert_files_pr", lambda **kw: "created:9")
        rc = pu.main([
            "upsert-files", "--head", "chore/x", "--base", "main", "--title", "t",
            "--body-file", str(body_file), "--add", "CLAUDE.md", "--allow-stale-base",
        ])
        assert rc == 0
