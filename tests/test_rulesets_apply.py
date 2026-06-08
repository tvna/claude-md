"""Tests for ``scripts/rulesets_apply.py``."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest
import rulesets_apply as ra

pytestmark = pytest.mark.shard_ci_ops

class Response:
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self.body = (
            body
            if isinstance(body, bytes)
            else json.dumps(body).encode("utf-8")
        )

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        pass


def write_sot(path: Path, name: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "name": name,
                "target": "branch",
                "enforcement": "active",
                "conditions": {},
                "bypass_actors": [],
                "rules": [],
            }
        ),
        encoding="utf-8",
    )
    return path


class TestSelectTargets:
    def test_each_valid_choice(self) -> None:
        assert ra.select_targets("all-branches") == ["all-branches.json"]
        assert ra.select_targets("main") == ["main.json"]
        assert ra.select_targets("all") == [
            "all-branches.json",
            "main.json",
        ]

    def test_unknown_choice_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown ruleset input"):
            ra.select_targets("nope")  # type: ignore[arg-type]


class TestDecideAction:
    def test_post_when_no_match(self) -> None:
        assert ra.decide_action("main", []) == {
            "action": "POST",
            "live_id": None,
            "match_count": 0,
        }

    def test_put_when_one_match(self) -> None:
        assert ra.decide_action("main", [{"id": 42, "name": "main"}]) == {
            "action": "PUT",
            "live_id": 42,
            "match_count": 1,
        }

    def test_ambiguous_when_multiple_matches(self) -> None:
        live = [{"id": 1, "name": "main"}, {"id": 2, "name": "main"}]
        assert ra.decide_action("main", live) == {
            "action": "ambiguous",
            "live_id": None,
            "match_count": 2,
        }


class TestRendering:
    def test_canonical_projection_preserves_only_six_fields(self) -> None:
        ruleset = {
            "id": 1,
            "name": "n",
            "target": "branch",
            "enforcement": "active",
            "conditions": {},
            "bypass_actors": [],
            "rules": [],
        }
        assert list(ra.canonical_projection(ruleset)) == list(ra.PROJECTION_KEYS)
        assert "id" not in ra.canonical_projection(ruleset)

    def test_render_diff_section_shape(self) -> None:
        live = {
            "name": "n",
            "target": "branch",
            "enforcement": "evaluate",
            "conditions": {},
            "bypass_actors": [],
            "rules": [],
        }
        sot = {**live, "enforcement": "active"}
        out = ra.render_diff_section("n", 9, live, sot)
        assert "<details><summary>Diff for <code>n</code> (id 9)" in out
        assert "```diff" in out
        assert "--- live" in out
        assert "+++ sot" in out
        assert '-  "enforcement": "evaluate"' in out
        assert '+  "enforcement": "active"' in out

    def test_render_diff_section_identical_still_renders_block(self) -> None:
        ruleset = {
            "name": "n",
            "target": "branch",
            "enforcement": "active",
            "conditions": {},
            "bypass_actors": [],
            "rules": [],
        }
        out = ra.render_diff_section("n", 9, ruleset, ruleset)
        assert "<details><summary>" in out
        assert "```diff\n\n```" in out

    def test_render_summary_row_empty_id_uses_dash(self) -> None:
        assert (
            ra.render_summary_row("main.json", "main", 0, "plan-only (POST)", None)
            == "| main.json | main | 0 | plan-only (POST) | — |"
        )


class TestHttpWrappers:
    def test_fetch_live_rulesets_sends_auth_header(self) -> None:
        captured = {}

        def opener(request):
            captured["auth"] = request.headers["Authorization"]
            return Response(200, [{"id": 1, "name": "main"}])

        assert ra.fetch_live_rulesets("o/r", "tok", opener=opener) == [
            {"id": 1, "name": "main"}
        ]
        assert captured["auth"] == "Bearer tok"

    def test_fetch_live_rulesets_raises_on_401(self) -> None:
        def opener(request):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(b"bad token"),
            )

        with pytest.raises(RuntimeError, match="HTTP 401"):
            ra.fetch_live_rulesets("o/r", "tok", opener=opener)

    def test_apply_call_happy_path(self, tmp_path: Path) -> None:
        payload = write_sot(tmp_path / "main.json", "main")
        sleeps: list[int] = []

        def opener(request):
            assert request.get_method() == "PUT"
            assert json.loads(request.data)["name"] == "main"
            return Response(200, {"id": 42})

        code, body = ra.apply_call(
            method="PUT",
            url="https://example.test/rulesets/42",
            payload_path=payload,
            token="tok",
            opener=opener,
            sleeper=sleeps.append,
        )
        assert code == 200
        assert json.loads(body) == {"id": 42}
        assert sleeps == []

    def test_apply_call_retries_5xx_then_succeeds(self, tmp_path: Path) -> None:
        payload = write_sot(tmp_path / "main.json", "main")
        codes = [500, 500, 200]
        sleeps: list[int] = []

        def opener(request):
            code = codes.pop(0)
            if code >= 500:
                raise urllib.error.HTTPError(
                    request.full_url,
                    code,
                    "Server error",
                    {},
                    io.BytesIO(b"try again"),
                )
            return Response(code, {"id": 42})

        code, _body = ra.apply_call(
            method="PUT",
            url="https://example.test/rulesets/42",
            payload_path=payload,
            token="tok",
            opener=opener,
            sleeper=sleeps.append,
        )
        assert code == 200
        assert sleeps == [5, 10]

    def test_apply_call_breaks_on_4xx(self, tmp_path: Path) -> None:
        payload = write_sot(tmp_path / "main.json", "main")
        sleeps: list[int] = []
        calls = 0

        def opener(request):
            nonlocal calls
            calls += 1
            raise urllib.error.HTTPError(
                request.full_url,
                422,
                "Unprocessable",
                {},
                io.BytesIO(b"bad json"),
            )

        code, body = ra.apply_call(
            method="PUT",
            url="https://example.test/rulesets/42",
            payload_path=payload,
            token="tok",
            opener=opener,
            sleeper=sleeps.append,
        )
        assert code == 422
        assert body == "bad json"
        assert calls == 1
        assert sleeps == []

    def test_apply_call_breaks_on_429_rate_limit_like(self, tmp_path: Path) -> None:
        payload = write_sot(tmp_path / "main.json", "main")
        sleeps: list[int] = []
        calls = 0

        def opener(request):
            nonlocal calls
            calls += 1
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                {},
                io.BytesIO(b"rate limited"),
            )

        code, body = ra.apply_call(
            method="PUT",
            url="https://example.test/rulesets/42",
            payload_path=payload,
            token="tok",
            opener=opener,
            sleeper=sleeps.append,
        )
        assert code == 429
        assert body == "rate limited"
        assert calls == 1
        assert sleeps == []

    def test_apply_call_retries_curl_level_failure(self, tmp_path: Path) -> None:
        payload = write_sot(tmp_path / "main.json", "main")
        sleeps: list[int] = []
        calls = 0

        def opener(request):
            nonlocal calls
            calls += 1
            raise urllib.error.URLError("network down")

        code, body = ra.apply_call(
            method="PUT",
            url="https://example.test/rulesets/42",
            payload_path=payload,
            token="tok",
            opener=opener,
            sleeper=sleeps.append,
        )
        assert code == 0
        assert body == "network down"
        assert calls == 3
        assert sleeps == [5, 10]


class TestCliFlows:
    def test_plan_all_new_writes_post_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sot_dir = tmp_path / "rulesets"
        sot_dir.mkdir()
        write_sot(sot_dir / "all-branches.json", "all")
        write_sot(sot_dir / "main.json", "main")
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GH_TOKEN", "tok")

        monkeypatch.setattr(
            ra, "fetch_live_rulesets", lambda *_args, **_kwargs: []
        )
        assert (
            ra.main(
                [
                    "plan",
                    "--repo",
                    "o/r",
                    "--sot-dir",
                    str(sot_dir),
                    "--choice",
                    "all",
                    "--summary-file",
                    str(summary),
                ]
            )
            == 0
        )
        text = summary.read_text(encoding="utf-8")
        assert "| all-branches.json | all | 0 | plan-only (POST) | — |" in text
        assert "| main.json | main | 0 | plan-only (POST) | — |" in text

    def test_plan_ambiguous_exits_nonzero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sot_dir = tmp_path / "rulesets"
        sot_dir.mkdir()
        write_sot(sot_dir / "main.json", "main")
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GH_TOKEN", "tok")

        monkeypatch.setattr(
            ra,
            "fetch_live_rulesets",
            lambda *_args, **_kwargs: [{"name": "main"}, {"name": "main"}],
        )
        assert (
            ra.main(
                [
                    "plan",
                    "--repo",
                    "o/r",
                    "--sot-dir",
                    str(sot_dir),
                    "--choice",
                    "main",
                    "--summary-file",
                    str(summary),
                ]
            )
            == 1
        )
        assert "| main.json | main | 2 | abort | — |" in summary.read_text(
            encoding="utf-8"
        )

    def test_apply_uses_post_and_payload_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sot_dir = tmp_path / "rulesets"
        sot_dir.mkdir()
        write_sot(sot_dir / "main.json", "main")
        summary = tmp_path / "summary.md"
        calls: list[tuple[str, str]] = []

        def opener(request):
            calls.append((request.get_method(), request.full_url))
            if request.get_method() == "GET":
                return Response(200, [])
            assert json.loads(request.data)["name"] == "main"
            return Response(201, {"id": 99})

        ra.apply_rulesets(
            repo="o/r",
            sot_dir=sot_dir,
            choice="main",
            summary_file=summary,
            token="tok",
            enable_auto_delete=False,
            opener=opener,
            sleeper=lambda _seconds: None,
        )
        assert calls == [
            ("GET", "https://api.github.com/repos/o/r/rulesets"),
            ("POST", "https://api.github.com/repos/o/r/rulesets"),
        ]
        text = summary.read_text(encoding="utf-8")
        assert "| main.json | main | 0 | POST applied | 99 |" in text
        assert "plan-only" not in text

    def test_auto_delete_dry_run_and_apply(
        self, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        methods: list[str] = []

        def opener(request):
            methods.append(request.get_method())
            if request.get_method() == "PATCH":
                return Response(200, {"delete_branch_on_merge": True})
            value = len(methods) > 1
            return Response(200, {"delete_branch_on_merge": value})

        ra.auto_delete(
            repo="o/r",
            dry_run=True,
            summary_file=summary,
            token="tok",
            opener=opener,
        )
        ra.auto_delete(
            repo="o/r",
            dry_run=False,
            summary_file=summary,
            token="tok",
            opener=opener,
        )

        text = summary.read_text(encoding="utf-8")
        assert "delete_branch_on_merge` (dry-run)" in text
        assert "- Planned: PATCH to `true`" in text
        assert "- Before: `true`" in text
        assert "- After: `true`" in text
        assert methods == ["GET", "GET", "PATCH", "GET"]


def write_wfperm_sot(
    path: Path, *, perm: str = "read", approve: bool = True
) -> Path:
    path.write_text(
        json.dumps(
            {
                "default_workflow_permissions": perm,
                "can_approve_pull_request_reviews": approve,
            }
        ),
        encoding="utf-8",
    )
    return path


class TestWorkflowPermissions:
    def test_diff_empty_when_in_sync_ignoring_extra_keys(self) -> None:
        sot = {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": True,
        }
        live = {**sot, "an_unrelated_future_field": 1}
        assert ra.workflow_permissions_diff(sot=sot, live=live) == ""

    def test_diff_nonempty_on_drift(self) -> None:
        sot = {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": True,
        }
        live = {
            "default_workflow_permissions": "write",
            "can_approve_pull_request_reviews": False,
        }
        diff = ra.workflow_permissions_diff(sot=sot, live=live)
        assert '-  "can_approve_pull_request_reviews": false' in diff
        assert '+  "can_approve_pull_request_reviews": true' in diff
        assert '-  "default_workflow_permissions": "write"' in diff
        assert '+  "default_workflow_permissions": "read"' in diff

    def test_get_sends_auth_and_endpoint(self) -> None:
        captured: dict[str, str] = {}

        def opener(request):
            captured["url"] = request.full_url
            captured["auth"] = request.headers["Authorization"]
            return Response(
                200,
                {
                    "default_workflow_permissions": "read",
                    "can_approve_pull_request_reviews": True,
                },
            )

        out = ra.get_workflow_permissions("o/r", "tok", opener=opener)
        assert out["default_workflow_permissions"] == "read"
        assert (
            captured["url"]
            == "https://api.github.com/repos/o/r/actions/permissions/workflow"
        )
        assert captured["auth"] == "Bearer tok"

    def test_plan_renders_drift_status_rc0(self, tmp_path: Path) -> None:
        sot = write_wfperm_sot(tmp_path / "workflow.json")
        summary = tmp_path / "s.md"

        def opener(request):
            assert request.get_method() == "GET"
            return Response(
                200,
                {
                    "default_workflow_permissions": "write",
                    "can_approve_pull_request_reviews": False,
                },
            )

        rc = ra.apply_workflow_permissions(
            repo="o/r",
            sot_path=sot,
            mode="plan",
            summary_file=summary,
            token="tok",
            opener=opener,
        )
        assert rc == 0
        text = summary.read_text(encoding="utf-8")
        assert "workflow permissions (plan)" in text
        assert "Status: `drift`" in text

    def test_drift_mode_rc_reflects_divergence(self, tmp_path: Path) -> None:
        sot = write_wfperm_sot(tmp_path / "workflow.json")
        summary = tmp_path / "s.md"

        def drift_opener(request):
            return Response(
                200,
                {
                    "default_workflow_permissions": "write",
                    "can_approve_pull_request_reviews": True,
                },
            )

        def sync_opener(request):
            return Response(
                200,
                {
                    "default_workflow_permissions": "read",
                    "can_approve_pull_request_reviews": True,
                },
            )

        assert (
            ra.apply_workflow_permissions(
                repo="o/r",
                sot_path=sot,
                mode="drift",
                summary_file=summary,
                token="tok",
                opener=drift_opener,
            )
            == 1
        )
        assert (
            ra.apply_workflow_permissions(
                repo="o/r",
                sot_path=sot,
                mode="drift",
                summary_file=summary,
                token="tok",
                opener=sync_opener,
            )
            == 0
        )

    def test_apply_puts_on_drift_then_reads_back(self, tmp_path: Path) -> None:
        sot = write_wfperm_sot(tmp_path / "workflow.json")
        summary = tmp_path / "s.md"
        methods: list[str] = []

        def opener(request):
            methods.append(request.get_method())
            if request.get_method() == "PUT":
                assert json.loads(request.data) == {
                    "default_workflow_permissions": "read",
                    "can_approve_pull_request_reviews": True,
                }
                return Response(200, {})
            value = "read" if len(methods) > 1 else "write"
            return Response(
                200,
                {
                    "default_workflow_permissions": value,
                    "can_approve_pull_request_reviews": True,
                },
            )

        rc = ra.apply_workflow_permissions(
            repo="o/r",
            sot_path=sot,
            mode="apply",
            summary_file=summary,
            token="tok",
            opener=opener,
        )
        assert rc == 0
        assert methods == ["GET", "PUT", "GET"]
        assert "Applied PUT" in summary.read_text(encoding="utf-8")

    def test_apply_noops_when_in_sync(self, tmp_path: Path) -> None:
        sot = write_wfperm_sot(tmp_path / "workflow.json")
        summary = tmp_path / "s.md"
        methods: list[str] = []

        def opener(request):
            methods.append(request.get_method())
            return Response(
                200,
                {
                    "default_workflow_permissions": "read",
                    "can_approve_pull_request_reviews": True,
                },
            )

        rc = ra.apply_workflow_permissions(
            repo="o/r",
            sot_path=sot,
            mode="apply",
            summary_file=summary,
            token="tok",
            opener=opener,
        )
        assert rc == 0
        assert methods == ["GET"]
        assert "No change" in summary.read_text(encoding="utf-8")

    def test_sot_validation_rejects_bad_shapes(self, tmp_path: Path) -> None:
        bad = tmp_path / "b.json"
        bad.write_text(
            json.dumps({"default_workflow_permissions": "read"}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required keys"):
            ra._read_workflow_permissions_sot(bad)

        bad.write_text(
            json.dumps(
                {
                    "default_workflow_permissions": "nope",
                    "can_approve_pull_request_reviews": True,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="must be 'read' or 'write'"):
            ra._read_workflow_permissions_sot(bad)

        bad.write_text(
            json.dumps(
                {
                    "default_workflow_permissions": "read",
                    "can_approve_pull_request_reviews": "yes",
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="must be a boolean"):
            ra._read_workflow_permissions_sot(bad)

        bad.write_text(
            json.dumps(
                {
                    "default_workflow_permissions": "read",
                    "can_approve_pull_request_reviews": True,
                    "x": 1,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unexpected keys"):
            ra._read_workflow_permissions_sot(bad)

    def test_cli_drift_mode_returns_exit_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sot = write_wfperm_sot(tmp_path / "workflow.json")
        summary = tmp_path / "s.md"
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setattr(
            ra,
            "get_workflow_permissions",
            lambda *_a, **_k: {
                "default_workflow_permissions": "write",
                "can_approve_pull_request_reviews": True,
            },
        )
        rc = ra.main(
            [
                "workflow-permissions",
                "--repo",
                "o/r",
                "--sot-file",
                str(sot),
                "--mode",
                "drift",
                "--summary-file",
                str(summary),
            ]
        )
        assert rc == 1

    def test_repo_sot_file_matches_governed_shape(self) -> None:
        repo_sot = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "actions-permissions"
            / "workflow.json"
        )
        data = ra._read_workflow_permissions_sot(repo_sot)
        assert data == {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": True,
        }
