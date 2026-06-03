from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dependabot_automerge as da
import pytest

pytestmark = pytest.mark.shard_ci_ops_2
POLICY = {
    "enabled": False,
    "allow": [
        {
            "ecosystem": "github-actions",
            "update_types": ["patch", "minor"],
            "paths": [".github/workflows/*"],
        },
        {
            "ecosystem": "uv",
            "update_types": ["patch"],
            "paths": ["pyproject.toml", "uv.lock"],
        },
    ],
}


def event(
    *,
    author: str = "dependabot[bot]",
    ref: str = "dependabot/github_actions/actions-checkout-6.0.2",
    title: str = "chore(deps): bump actions/checkout from 5.0.1 to 5.1.0",
    labels: list[str] | None = None,
    draft: bool = False,
) -> dict[str, object]:
    return {
        "pull_request": {
            "title": title,
            "draft": draft,
            "user": {"login": author},
            "head": {"ref": ref},
            "labels": [{"name": label} for label in labels or []],
        }
    }


def test_classify_update_type() -> None:
    assert da.classify_update_type("bump x from 1.2.3 to 1.2.4") == "patch"
    assert da.classify_update_type("bump x from v1.2.3 to v1.3.0") == "minor"
    assert da.classify_update_type("bump x from 1.2.3 to 2.0.0") == "major"
    assert da.classify_update_type("manual dependency update") is None


def test_infer_ecosystem() -> None:
    assert da.infer_ecosystem([".github/workflows/ci.yml"]) == "github-actions"
    assert da.infer_ecosystem(["pyproject.toml", "uv.lock"]) == "uv"
    assert da.infer_ecosystem(["README.md"]) is None


def test_audit_eligible_but_not_enabled() -> None:
    result = da.audit(event(), POLICY, [".github/workflows/verify.yml"])
    assert result.eligible is True
    assert result.enabled is False
    assert result.should_enable is False
    assert result.reasons == []


def test_enabled_policy_requests_automerge() -> None:
    policy = dict(POLICY, enabled=True)
    result = da.audit(event(), policy, [".github/workflows/verify.yml"])
    assert result.should_enable is True


def test_major_update_is_blocked() -> None:
    result = da.audit(
        event(title="chore(deps): bump actions/checkout from 5.0.1 to 6.0.2"),
        POLICY,
        [".github/workflows/verify.yml"],
    )
    assert result.eligible is False
    assert "github-actions major updates are not allowed" in result.reasons


def test_severity_label_blocks() -> None:
    result = da.audit(event(labels=["severity:security"]), POLICY, ["uv.lock"])
    assert result.eligible is False
    assert "manual-review label present: severity:security" in result.reasons


def test_advisory_non_ascii_label_does_not_block() -> None:
    # #1122: dependabot relays release notes whose @mentions carry zero-width
    # spaces, so scan_non_ascii applies severity:non-ascii-content (advisory
    # for trusted bots) on nearly every PR. It must not block auto-merge.
    result = da.audit(
        event(labels=["severity:non-ascii-content"]),
        POLICY,
        [".github/workflows/verify.yml"],
    )
    assert result.eligible is True
    assert not any("manual-review label present" in reason for reason in result.reasons)


def test_advisory_label_does_not_mask_real_severity_block() -> None:
    result = da.audit(
        event(labels=["severity:non-ascii-content", "severity:security"]),
        POLICY,
        [".github/workflows/verify.yml"],
    )
    assert result.eligible is False
    assert "manual-review label present: severity:security" in result.reasons


def test_unexpected_path_blocks() -> None:
    result = da.audit(event(), POLICY, [".github/workflows/verify.yml", "README.md"])
    assert result.eligible is False
    assert "changed files do not match an allowed ecosystem" in result.reasons


def test_non_dependabot_author_blocks() -> None:
    result = da.audit(event(author="octocat"), POLICY, [".github/workflows/verify.yml"])
    assert result.eligible is False
    assert "author is not trusted: octocat" in result.reasons


def test_classify_update_type_same_version_returns_patch() -> None:
    result = da.classify_update_type("bump x from 1.2.3 to 1.2.3")
    assert result == "patch"


def test_audit_no_pull_request_key_returns_ineligible() -> None:
    result = da.audit({}, POLICY, [".github/workflows/ci.yml"])
    assert result.eligible is False
    assert "event has no pull_request object" in result.reasons


def test_audit_draft_pr_is_blocked() -> None:
    result = da.audit(event(draft=True), POLICY, [".github/workflows/ci.yml"])
    assert result.eligible is False
    assert "pull request is draft" in result.reasons


def test_audit_no_semver_in_title_blocked() -> None:
    result = da.audit(
        event(title="chore(deps): bump some-action"),
        POLICY,
        [".github/workflows/ci.yml"],
    )
    assert result.eligible is False
    assert "title does not expose a semver from/to update" in result.reasons


def test_audit_no_rule_for_ecosystem_blocked() -> None:
    policy_no_uv = {
        "enabled": False,
        "allow": [
            {
                "ecosystem": "github-actions",
                "update_types": ["patch"],
                "paths": [".github/workflows/*"],
            }
        ],
    }
    result = da.audit(
        event(
            ref="dependabot/pip/requests-2.28.0",
            title="chore(deps): bump requests from 2.27.0 to 2.28.0",
        ),
        policy_no_uv,
        ["pyproject.toml", "uv.lock"],
    )
    assert result.eligible is False
    assert any("no policy rule" in r for r in result.reasons)


def test_audit_unexpected_path_within_known_ecosystem() -> None:
    policy_narrow = {
        "enabled": False,
        "allow": [
            {
                "ecosystem": "github-actions",
                "update_types": ["patch", "minor"],
                "paths": [".github/workflows/ci.yml"],
            },
        ],
    }
    result = da.audit(
        event(),
        policy_narrow,
        [".github/workflows/ci.yml", ".github/workflows/extra.yml"],
    )
    assert result.eligible is False
    assert any("unexpected changed path" in r for r in result.reasons)


def test_render_markdown_no_reasons() -> None:
    from dependabot_automerge import AuditResult
    result = AuditResult(eligible=True, enabled=False, update_type="patch", ecosystem="uv", reasons=[])
    md = da.render_markdown(result)
    assert "No blocking reasons found." in md


def test_nested_str_non_dict_intermediate() -> None:
    result = da._nested_str({"user": "not-a-dict"}, "user", "login")
    assert result == ""


def test_label_names_non_list_returns_empty() -> None:
    result = da._label_names({"labels": "not-a-list"})
    assert result == set()


def test_matching_rule_non_list_rules_returns_none() -> None:
    result = da._matching_rule({"allow": "not-a-list"}, "uv")
    assert result is None


def test_matching_rule_no_match_returns_none() -> None:
    result = da._matching_rule({"allow": [{"ecosystem": "pip"}]}, "uv")
    assert result is None


def test_string_list_non_list_returns_empty() -> None:
    assert da._string_list("not-a-list") == []
    assert da._string_list(None) == []


def test_unexpected_paths_all_match_returns_empty() -> None:
    result = da._unexpected_paths(
        [".github/workflows/ci.yml"],
        [".github/workflows/*"],
    )
    assert result == []


def test_audit_non_dependabot_branch_blocked() -> None:
    result = da.audit(
        event(ref="feature/my-feature"),
        POLICY,
        [".github/workflows/ci.yml"],
    )
    assert result.eligible is False
    assert any("head branch is not dependabot/*" in r for r in result.reasons)


def test_render_markdown_with_reasons() -> None:
    from dependabot_automerge import AuditResult

    result = AuditResult(
        eligible=False,
        enabled=False,
        update_type=None,
        ecosystem=None,
        reasons=["title does not expose a semver from/to update"],
    )
    md = da.render_markdown(result)
    assert "### Blocking reasons" in md
    assert "title does not expose a semver from/to update" in md


def test_read_changed_files_empty_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        da._read_changed_files(empty)


def test_cmd_audit_missing_file_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    import argparse
    args = argparse.Namespace(
        event="/nonexistent/event.json",
        policy="/nonexistent/policy.json",
        changed_files="/nonexistent/changed.txt",
        summary_file=None,
        output=None,
    )
    rc = da._cmd_audit(args)
    assert rc == 1
    assert "::error::" in capsys.readouterr().out


def test_cli_writes_summary_and_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event_path = tmp_path / "event.json"
    policy_path = tmp_path / "policy.json"
    changed_files_path = tmp_path / "changed-files.txt"
    summary_path = tmp_path / "summary.md"
    output_path = tmp_path / "output.txt"

    event_path.write_text(json.dumps(event()), encoding="utf-8")
    policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
    changed_files_path.write_text(".github/workflows/verify.yml\n", encoding="utf-8")

    rc = da.main(
        [
            "audit",
            "--event",
            str(event_path),
            "--policy",
            str(policy_path),
            "--changed-files",
            str(changed_files_path),
            "--summary-file",
            str(summary_path),
            "--output",
            str(output_path),
        ]
    )

    assert rc == 0
    assert "Dependabot auto-merge audit" in capsys.readouterr().out
    assert "eligible: `true`" in summary_path.read_text(encoding="utf-8")
    assert "should_enable=false" in output_path.read_text(encoding="utf-8")


def test_main_block_raises_system_exit(tmp_path: Path) -> None:
    import runpy

    event_path = tmp_path / "event.json"
    policy_path = tmp_path / "policy.json"
    changed_files_path = tmp_path / "changed-files.txt"

    event_path.write_text(json.dumps(event()), encoding="utf-8")
    policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
    changed_files_path.write_text(".github/workflows/verify.yml\n", encoding="utf-8")

    import sys

    original_argv = sys.argv[:]
    sys.argv = [
        "dependabot_automerge.py",
        "audit",
        "--event", str(event_path),
        "--policy", str(policy_path),
        "--changed-files", str(changed_files_path),
    ]
    try:
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(
                str(Path(__file__).parent.parent / "scripts" / "dependabot_automerge.py"),
                run_name="__main__",
            )
        assert exc_info.value.code == 0
    finally:
        sys.argv = original_argv


# ---------------------------------------------------------------------------
# _list_pr_files() and _cmd_list_files() / list-files subcommand
# ---------------------------------------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


class TestListPrFiles:
    def _make_apply_call(self, status: int, filenames: list[str]) -> Callable[..., tuple[int, str]]:
        body = json.dumps([{"filename": f} for f in filenames]).encode("utf-8")

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            assert method == "GET"
            assert "pulls" in url and "files" in url
            return status, body.decode("utf-8")

        return apply_call

    def test_returns_filenames_from_api(self) -> None:
        apply_call = self._make_apply_call(200, ["uv.lock", "pyproject.toml"])
        result = da._list_pr_files(repo="owner/repo", pr_number=7, token="tok", apply_call=apply_call)
        assert result == ["uv.lock", "pyproject.toml"]

    def test_includes_pr_number_in_url(self) -> None:
        captured_urls: list[str] = []

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            captured_urls.append(url)
            return 200, json.dumps([{"filename": "a.txt"}])

        da._list_pr_files(repo="owner/repo", pr_number=42, token="tok", apply_call=apply_call)
        assert "42" in captured_urls[0]

    def test_http_error_raises_runtime_error(self) -> None:
        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            return 422, '{"message":"error"}'

        with pytest.raises(RuntimeError, match="422"):
            da._list_pr_files(repo="owner/repo", pr_number=1, token="tok", apply_call=apply_call)

    def test_malformed_json_raises_runtime_error(self) -> None:
        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            return 200, "not-json"

        with pytest.raises(RuntimeError):
            da._list_pr_files(repo="owner/repo", pr_number=1, token="tok", apply_call=apply_call)

    def test_non_array_response_raises_runtime_error(self) -> None:
        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            return 200, '{"number": 1}'

        with pytest.raises(RuntimeError):
            da._list_pr_files(repo="owner/repo", pr_number=1, token="tok", apply_call=apply_call)

    def test_empty_file_list(self) -> None:
        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            return 200, "[]"

        assert da._list_pr_files(repo="owner/repo", pr_number=1, token="tok", apply_call=apply_call) == []


class TestCmdListFiles:
    def test_writes_filenames_to_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setattr(
            da, "_list_pr_files", lambda **kw: ["uv.lock", "pyproject.toml"]
        )
        out = tmp_path / "files.txt"
        assert da.main(["list-files", "--pr-number", "7", "--output", str(out)]) == 0
        assert out.read_text(encoding="utf-8") == "uv.lock\npyproject.toml\n"

    def test_missing_token_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("REPO", "owner/repo")
        assert da.main(["list-files", "--pr-number", "1", "--output", "/dev/null"]) == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_missing_repo_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.delenv("REPO", raising=False)
        assert da.main(["list-files", "--pr-number", "1", "--output", "/dev/null"]) == 1
        assert "REPO" in capsys.readouterr().err

    def test_invalid_pr_number_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        assert da.main(["list-files", "--pr-number", "bad", "--output", "/dev/null"]) == 1
        assert "PR number" in capsys.readouterr().err

    def test_api_error_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setattr(da, "_list_pr_files", lambda **kw: (_ for _ in ()).throw(RuntimeError("HTTP 500")))
        assert da.main(["list-files", "--pr-number", "1", "--output", str(tmp_path / "f.txt")]) == 1
        assert "HTTP 500" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _enable_auto_merge() and _cmd_request_automerge() / request-automerge subcommand
# ---------------------------------------------------------------------------


class TestEnableAutoMerge:
    def _make_apply_call(self, pr_node_id: str, pr_status: int = 200) -> Callable[..., tuple[int, str]]:
        pr_body = json.dumps({"node_id": pr_node_id, "number": 42})

        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            assert method == "GET"
            return pr_status, pr_body

        return apply_call

    def _make_graphql_call(self, http_status: int = 200, errors: list | None = None) -> Callable[..., tuple[int, dict[str, Any]]]:
        def graphql_call(*, query: str, variables: dict, token: str) -> tuple[int, dict]:
            body: dict = {"data": {"enablePullRequestAutoMerge": {"pullRequest": {"number": 42}}}}
            if errors is not None:
                body["errors"] = errors
            return http_status, body

        return graphql_call

    def test_calls_graphql_with_node_id(self) -> None:
        captured_vars: list[dict] = []

        def graphql_call(*, query: str, variables: dict, token: str) -> tuple[int, dict]:
            captured_vars.append(variables)
            return 200, {"data": {}}

        da._enable_auto_merge(
            repo="owner/repo",
            pr_number=42,
            merge_method="SQUASH",
            token="tok",
            apply_call=self._make_apply_call("PR_node_123"),
            graphql_call=graphql_call,
        )
        assert captured_vars[0]["pullRequestId"] == "PR_node_123"
        assert captured_vars[0]["mergeMethod"] == "SQUASH"

    def test_pr_get_http_error_raises(self) -> None:
        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            return 404, '{"message":"not found"}'

        with pytest.raises(RuntimeError, match="404"):
            da._enable_auto_merge(
                repo="owner/repo",
                pr_number=1,
                merge_method="SQUASH",
                token="tok",
                apply_call=apply_call,
                graphql_call=self._make_graphql_call(),
            )

    def test_missing_node_id_raises(self) -> None:
        def apply_call(*, method: str, url: str, payload: object, token: str) -> tuple[int, str]:
            return 200, '{"number": 1}'

        with pytest.raises(RuntimeError, match="node_id"):
            da._enable_auto_merge(
                repo="owner/repo",
                pr_number=1,
                merge_method="SQUASH",
                token="tok",
                apply_call=apply_call,
                graphql_call=self._make_graphql_call(),
            )

    def test_graphql_http_error_raises(self) -> None:
        with pytest.raises(RuntimeError, match="HTTP 401"):
            da._enable_auto_merge(
                repo="owner/repo",
                pr_number=42,
                merge_method="SQUASH",
                token="tok",
                apply_call=self._make_apply_call("node_abc"),
                graphql_call=self._make_graphql_call(http_status=401),
            )

    def test_graphql_errors_raise(self) -> None:
        with pytest.raises(RuntimeError, match="errors"):
            da._enable_auto_merge(
                repo="owner/repo",
                pr_number=42,
                merge_method="SQUASH",
                token="tok",
                apply_call=self._make_apply_call("node_abc"),
                graphql_call=self._make_graphql_call(errors=[{"message": "bad"}]),
            )


class TestCmdRequestAutomerge:
    def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setattr(da, "_enable_auto_merge", lambda **kw: None)
        assert da.main(["request-automerge", "--pr-number", "7"]) == 0

    def test_missing_token_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("REPO", "owner/repo")
        assert da.main(["request-automerge", "--pr-number", "1"]) == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_missing_repo_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.delenv("REPO", raising=False)
        assert da.main(["request-automerge", "--pr-number", "1"]) == 1
        assert "REPO" in capsys.readouterr().err

    def test_runtime_error_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setattr(
            da, "_enable_auto_merge", lambda **kw: (_ for _ in ()).throw(RuntimeError("GraphQL error"))
        )
        assert da.main(["request-automerge", "--pr-number", "1"]) == 1
        assert "GraphQL error" in capsys.readouterr().err
