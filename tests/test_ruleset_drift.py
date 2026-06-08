"""Tests for ``scripts/ruleset_drift.py``."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ruleset_drift

pytestmark = pytest.mark.shard_ci_ops
SOT_MAIN: dict[str, Any] = {
    "name": "main-protection",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "bypass_actors": [],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
    ],
}

SOT_ALL: dict[str, Any] = {
    "name": "all-branches-no-force-push",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~ALL"], "exclude": ["~DEFAULT_BRANCH"]}},
    "bypass_actors": [],
    "rules": [{"type": "non_fast_forward"}],
}


class Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class _RunResult:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


# ---------------------------------------------------------------------------

class TestCanonicalProjection:
    def test_includes_only_six_keys(self) -> None:
        projected = ruleset_drift.canonical_projection({**SOT_MAIN, "id": 99, "source": "Repository"})

        assert set(projected.keys()) == set(ruleset_drift.SOT_PROJECTION_KEYS)
        assert "id" not in projected
        assert "source" not in projected

    def test_missing_optional_key_is_none(self) -> None:
        sparse = {"name": "x", "target": "branch"}

        projected = ruleset_drift.canonical_projection(sparse)

        assert projected["name"] == "x"
        assert projected["target"] == "branch"
        assert projected["enforcement"] is None
        assert projected["rules"] is None

    def test_sorts_rules_into_canonical_order(self) -> None:
        # #1004: GitHub re-orders rules on PUT (#1036), so the projection sorts
        # them by type to keep the comparison stable.
        ruleset = {**SOT_MAIN, "rules": [{"type": "b"}, {"type": "a"}, {"type": "c"}]}

        projected = ruleset_drift.canonical_projection(ruleset)

        assert [rule["type"] for rule in projected["rules"]] == ["a", "b", "c"]

    def test_strips_server_default_parameters(self) -> None:
        # #1004: GitHub echoes required_reviewers=[] / do_not_enforce_on_create=false
        # onto live; stripping the documented defaults keeps the projection equal
        # to the SoT shape that omits them.
        ruleset = {
            **SOT_MAIN,
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {
                        "require_code_owner_review": True,
                        "required_reviewers": [],
                    },
                },
                {
                    "type": "required_status_checks",
                    "parameters": {"do_not_enforce_on_create": False},
                },
            ],
        }

        projected = ruleset_drift.canonical_projection(ruleset)
        by_type = {rule["type"]: rule for rule in projected["rules"]}

        assert by_type["pull_request"]["parameters"] == {"require_code_owner_review": True}
        # parameters emptied by pruning is dropped to match the bare-type SoT shape.
        assert "parameters" not in by_type["required_status_checks"]

    def test_keeps_parameter_that_diverges_from_default(self) -> None:
        # A non-default value is genuine drift and must NOT be stripped.
        ruleset = {
            **SOT_MAIN,
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {"required_reviewers": [{"reviewer_id": 7}]},
                }
            ],
        }

        projected = ruleset_drift.canonical_projection(ruleset)

        assert projected["rules"][0]["parameters"]["required_reviewers"] == [
            {"reviewer_id": 7}
        ]


class TestCanonicalJson:
    def test_keys_sorted_recursively(self) -> None:
        text = ruleset_drift.canonical_json(SOT_MAIN)
        first_lines = text.splitlines()[:3]

        assert first_lines[0] == "{"
        assert '"bypass_actors":' in first_lines[1]

    def test_uses_two_space_indent(self) -> None:
        text = ruleset_drift.canonical_json(SOT_MAIN)

        assert '\n  "name":' in text

    def test_unicode_emitted_raw(self) -> None:
        text = ruleset_drift.canonical_json({**SOT_MAIN, "name": "ルール"})

        assert "ルール" in text
        assert "\\u30eb" not in text

    def test_trailing_newline(self) -> None:
        assert ruleset_drift.canonical_json(SOT_MAIN).endswith("}\n")


class TestClassify:
    def test_matched_returns_live_id(self) -> None:
        live = [{"id": 42, "name": "main-protection"}]

        result = ruleset_drift.classify(SOT_MAIN, live)

        assert result == {"status": "matched", "live_id": 42, "match_count": 1}

    def test_missing_on_live(self) -> None:
        result = ruleset_drift.classify(SOT_MAIN, [{"id": 1, "name": "other"}])

        assert result == {"status": "missing-on-live", "live_id": None, "match_count": 0}

    def test_empty_live(self) -> None:
        result = ruleset_drift.classify(SOT_MAIN, [])

        assert result["status"] == "missing-on-live"

    def test_ambiguous(self) -> None:
        live = [
            {"id": 1, "name": "main-protection"},
            {"id": 2, "name": "main-protection"},
        ]

        result = ruleset_drift.classify(SOT_MAIN, live)

        assert result == {"status": "ambiguous", "live_id": None, "match_count": 2}


class TestDiffCanonical:
    def test_equal_returns_empty(self) -> None:
        assert ruleset_drift.diff_canonical(
            sot=SOT_MAIN, live=SOT_MAIN, sot_path="a", live_path="b"
        ) == ""

    def test_drift_returns_unified_diff(self) -> None:
        live = {**SOT_MAIN, "enforcement": "disabled"}

        diff = ruleset_drift.diff_canonical(
            sot=SOT_MAIN,
            live=live,
            sot_path=".github/rulesets/main.json",
            live_path="/tmp/live-main.json",
        )

        assert diff.startswith("--- /tmp/live-main.json\n+++ .github/rulesets/main.json\n")
        assert '-  "enforcement": "disabled",\n' in diff
        assert '+  "enforcement": "active",\n' in diff

    def test_rules_reorder_is_not_drift(self) -> None:
        # #1004 / #1036: a rule reorder applied by GitHub on PUT canonicalizes
        # to the same order and must not read as drift.
        live = {
            **SOT_MAIN,
            "rules": list(reversed(SOT_MAIN["rules"])),
        }

        diff = ruleset_drift.diff_canonical(
            sot=SOT_MAIN, live=live, sot_path="a", live_path="b"
        )

        assert diff == ""

    def test_server_default_parameters_are_not_drift(self) -> None:
        # #1004: live carrying GitHub's server defaults while SoT omits them is
        # in-sync, not drift.
        sot = {
            **SOT_MAIN,
            "rules": [
                {"type": "pull_request", "parameters": {"require_code_owner_review": True}},
            ],
        }
        live = {
            **SOT_MAIN,
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {
                        "require_code_owner_review": True,
                        "required_reviewers": [],
                    },
                },
            ],
        }

        diff = ruleset_drift.diff_canonical(
            sot=sot, live=live, sot_path="a", live_path="b"
        )

        assert diff == ""

    def test_diverging_parameter_value_shows_drift(self) -> None:
        sot = {
            **SOT_MAIN,
            "rules": [{"type": "pull_request", "parameters": {"required_reviewers": []}}],
        }
        live = {
            **SOT_MAIN,
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {"required_reviewers": [{"reviewer_id": 7}]},
                }
            ],
        }

        diff = ruleset_drift.diff_canonical(
            sot=sot, live=live, sot_path="a", live_path="b"
        )

        assert diff != ""

    def test_unicode_passes_through(self) -> None:
        live = {**SOT_MAIN, "name": "ルールA"}
        sot = {**SOT_MAIN, "name": "ルールB"}

        diff = ruleset_drift.diff_canonical(
            sot=sot, live=live, sot_path="a", live_path="b"
        )

        assert "ルールA" in diff
        assert "ルールB" in diff


class TestFindUnknown:
    def test_empty_when_all_known(self) -> None:
        live = [
            {"id": 1, "name": "main-protection", "target": "branch", "enforcement": "active"},
            {"id": 2, "name": "all-branches-no-force-push", "target": "branch", "enforcement": "active"},
        ]

        assert ruleset_drift.find_unknown({"main-protection", "all-branches-no-force-push"}, live) == []

    def test_returns_minimal_projection(self) -> None:
        live = [
            {
                "id": 7,
                "name": "ghost",
                "target": "branch",
                "enforcement": "active",
                "conditions": {"ref_name": {"include": ["~ALL"]}},
            },
        ]

        result = ruleset_drift.find_unknown(set(), live)

        assert result == [
            {"id": 7, "name": "ghost", "target": "branch", "enforcement": "active"}
        ]

    def test_preserves_live_order(self) -> None:
        live = [
            {"id": i, "name": f"r{i}", "target": "branch", "enforcement": "active"}
            for i in (3, 1, 2)
        ]

        names = [entry["name"] for entry in ruleset_drift.find_unknown(set(), live)]

        assert names == ["r3", "r1", "r2"]


class TestRenderSotIssueHeader:
    def test_includes_parent_30(self) -> None:
        body = ruleset_drift.render_sot_issue_header(
            run_date="2026-05-22", run_url="https://x/y", repo="owner/repo"
        )

        assert body.startswith("Parent: #30\n")
        assert "https://x/y" in body
        assert "2026-05-22" in body
        assert "GET /repos/owner/repo/rulesets" in body


class TestRenderDiffBlock:
    def test_wraps_diff_in_details(self) -> None:
        block = ruleset_drift.render_diff_block(name="r", live_id=7, diff_text="--- a\n+++ b\n")

        assert block.startswith("\n<details><summary>Diff for <code>r</code> (id 7)</summary>\n")
        assert "```diff\n--- a\n+++ b\n```\n" in block
        assert block.endswith("</details>\n")


class TestRenderUnknownIssue:
    def test_header_includes_parent_30(self) -> None:
        header = ruleset_drift.render_unknown_issue_header(
            run_date="2026-05-22", run_url="https://x/y"
        )

        assert header.startswith("Parent: #30\n")
        assert "2026-05-22" in header

    def test_remediation_links_to_rollback_section(self) -> None:
        text = ruleset_drift.render_unknown_issue_remediation(repo="owner/repo")

        assert "gh api -X DELETE /repos/owner/repo/rulesets/<id>" in text
        assert "Rollback" in text


class TestFetchLiveRulesetsList:
    def test_happy_path_url_and_auth(self) -> None:
        captured: list[urllib.request.Request] = []

        def opener(request: urllib.request.Request) -> Response:
            captured.append(request)
            return Response([{"id": 1, "name": "x"}])

        result = ruleset_drift.fetch_live_rulesets_list("owner/repo", "tkn", opener=opener)

        assert result == [{"id": 1, "name": "x"}]
        assert captured[0].full_url == "https://api.github.com/repos/owner/repo/rulesets"
        assert captured[0].headers["Authorization"] == "Bearer tkn"
        assert captured[0].headers["X-github-api-version"] == "2022-11-28"

    def test_propagates_http_403(self) -> None:
        # The function does not trap HTTPError. The orchestrator (detect)
        # and main()'s except clause surface the error as "::error::..."
        # without echoing the token (token never appears in the print path).
        def opener(request: urllib.request.Request) -> Response:
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                "Forbidden",
                Message(),
                io.BytesIO(b'{"message":"Resource not accessible"}'),
            )

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            ruleset_drift.fetch_live_rulesets_list("owner/repo", "tkn", opener=opener)

        assert exc_info.value.code == 403


class TestFetchLiveRuleset:
    def test_url_includes_id(self) -> None:
        captured: list[urllib.request.Request] = []

        def opener(request: urllib.request.Request) -> Response:
            captured.append(request)
            return Response({"id": 7, "name": "r"})

        result = ruleset_drift.fetch_live_ruleset("owner/repo", 7, "tkn", opener=opener)

        assert result == {"id": 7, "name": "r"}
        assert captured[0].full_url == "https://api.github.com/repos/owner/repo/rulesets/7"


class TestFileIssue:
    def test_runner_invocation_matches_legacy_shell(self) -> None:
        calls: list[list[str]] = []

        def runner(cmd: list[str], **_kwargs: Any) -> _RunResult:
            calls.append(cmd)
            return _RunResult()

        ruleset_drift.file_issue(
            "owner/repo",
            "fix(ruleset-drift): SoT vs live drift detected (2026-05-22)",
            Path("/tmp/x.md"),
            runner=runner,
        )

        assert calls == [
            [
                "gh",
                "issue",
                "create",
                "--repo",
                "owner/repo",
                "--title",
                "fix(ruleset-drift): SoT vs live drift detected (2026-05-22)",
                "--body-file",
                "/tmp/x.md",
                "--label",
                "layer:meta",
                "--label",
                "type:fix",
            ]
        ]


# ---------------------------------------------------------------------------

def _write_sot(tmp_path: Path, files: dict[str, dict[str, Any]]) -> Path:
    sot_dir = tmp_path / "rulesets"
    sot_dir.mkdir()
    for name, content in files.items():
        (sot_dir / name).write_text(json.dumps(content), encoding="utf-8")
    return sot_dir


def _detect(
    tmp_path: Path,
    *,
    sot_files: dict[str, dict[str, Any]],
    live_list: list[dict[str, Any]],
    live_by_id: dict[int, dict[str, Any]] | None = None,
) -> tuple[int, int, str, str | None, str | None]:
    sot_dir = _write_sot(tmp_path, sot_files)
    summary = tmp_path / "summary.md"
    sot_body = tmp_path / "sot.md"
    unknown_body = tmp_path / "unknown.md"

    drift_count, unknown_count = ruleset_drift.detect(
        repo="owner/repo",
        sot_dir=sot_dir,
        sot_files=tuple(sot_files.keys()),
        run_url="https://x/y/runs/1",
        run_date="2026-05-22",
        token="tkn",
        summary_file=summary,
        sot_body_file=sot_body,
        unknown_body_file=unknown_body,
        list_fetcher=lambda _r, _t: live_list,
        ruleset_fetcher=lambda _r, i, _t: (live_by_id or {})[i],
    )

    return (
        drift_count,
        unknown_count,
        summary.read_text(encoding="utf-8"),
        sot_body.read_text(encoding="utf-8") if sot_body.exists() else None,
        unknown_body.read_text(encoding="utf-8") if unknown_body.exists() else None,
    )


class TestDetect:
    def test_clean_tree(self, tmp_path: Path) -> None:
        live = [
            {"id": 1, **SOT_MAIN},
            {"id": 2, **SOT_ALL},
        ]
        drift, unknown, summary, sot_body, unknown_body = _detect(
            tmp_path,
            sot_files={"main.json": SOT_MAIN, "all-branches.json": SOT_ALL},
            live_list=live,
            live_by_id={1: SOT_MAIN, 2: SOT_ALL},
        )

        assert drift == 0
        assert unknown == 0
        assert "in-sync" in summary
        assert "_None._" in summary
        assert sot_body is None
        assert unknown_body is None

    def test_sot_drift_only(self, tmp_path: Path) -> None:
        live_main = {**SOT_MAIN, "enforcement": "disabled"}
        drift, unknown, summary, sot_body, unknown_body = _detect(
            tmp_path,
            sot_files={"main.json": SOT_MAIN, "all-branches.json": SOT_ALL},
            live_list=[{"id": 1, **SOT_MAIN}, {"id": 2, **SOT_ALL}],
            live_by_id={1: live_main, 2: SOT_ALL},
        )

        assert drift == 1
        assert unknown == 0
        assert "drift" in summary
        assert sot_body is not None
        assert sot_body.startswith("Parent: #30\n")
        assert "## Diffs" in sot_body
        assert "## Remediation" in sot_body
        assert "<details><summary>Diff for <code>main-protection</code>" in sot_body
        assert unknown_body is None

    def test_drift_when_live_retains_admin_bypass(self, tmp_path: Path) -> None:
        live_main = {
            **SOT_MAIN,
            "bypass_actors": [
                {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
            ],
        }
        drift, _, _, sot_body, _ = _detect(
            tmp_path,
            sot_files={"main.json": SOT_MAIN, "all-branches.json": SOT_ALL},
            live_list=[{"id": 1, **SOT_MAIN}, {"id": 2, **SOT_ALL}],
            live_by_id={1: live_main, 2: SOT_ALL},
        )

        assert drift == 1
        assert sot_body is not None
        assert "actor_id" in sot_body
        assert "RepositoryRole" in sot_body

    def test_live_server_defaults_and_reorder_are_in_sync(self, tmp_path: Path) -> None:
        # #1004 regression: live echoes GitHub server defaults and re-orders the
        # rules array; the SoT omits the defaults and uses a different order.
        # Normalization must report in-sync (drift=0), not a recurring false drift.
        sot_main = {
            **SOT_MAIN,
            "rules": [
                {"type": "required_linear_history"},
                {"type": "non_fast_forward"},
                {
                    "type": "pull_request",
                    "parameters": {"require_code_owner_review": True},
                },
            ],
        }
        live_main = {
            **sot_main,
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {
                        "require_code_owner_review": True,
                        "required_reviewers": [],
                    },
                },
                {"type": "non_fast_forward"},
                {"type": "required_linear_history"},
            ],
        }
        drift, unknown, summary, sot_body, _u = _detect(
            tmp_path,
            sot_files={"main.json": sot_main, "all-branches.json": SOT_ALL},
            live_list=[{"id": 1, **sot_main}, {"id": 2, **SOT_ALL}],
            live_by_id={1: live_main, 2: SOT_ALL},
        )

        assert drift == 0
        assert "in-sync" in summary
        assert sot_body is None

    def test_unknown_only(self, tmp_path: Path) -> None:
        ghost = {"id": 99, "name": "ghost", "target": "branch", "enforcement": "active"}
        drift, unknown, summary, sot_body, unknown_body = _detect(
            tmp_path,
            sot_files={"main.json": SOT_MAIN, "all-branches.json": SOT_ALL},
            live_list=[{"id": 1, **SOT_MAIN}, {"id": 2, **SOT_ALL}, ghost],
            live_by_id={1: SOT_MAIN, 2: SOT_ALL},
        )

        assert drift == 0
        assert unknown == 1
        assert "| 99 | `ghost` | branch | active |" in summary
        assert sot_body is None
        assert unknown_body is not None
        assert unknown_body.startswith("Parent: #30\n")
        assert "| 99 | `ghost` | branch | active |" in unknown_body

    def test_missing_on_live_counts_as_drift(self, tmp_path: Path) -> None:
        drift, unknown, summary, sot_body, _u = _detect(
            tmp_path,
            sot_files={"main.json": SOT_MAIN},
            live_list=[],
        )

        assert drift == 1
        assert unknown == 0
        assert "missing-on-live" in summary
        assert sot_body is not None
        assert "missing-on-live" in sot_body

    def test_ambiguous_raises(self, tmp_path: Path) -> None:
        live = [
            {"id": 1, **SOT_MAIN},
            {"id": 2, **SOT_MAIN},
        ]
        with pytest.raises(RuntimeError, match="Multiple existing rulesets named 'main-protection'"):
            _detect(
                tmp_path,
                sot_files={"main.json": SOT_MAIN},
                live_list=live,
                live_by_id={1: SOT_MAIN, 2: SOT_MAIN},
            )

    def test_both_drift_and_unknown(self, tmp_path: Path) -> None:
        live_main = {**SOT_MAIN, "enforcement": "disabled"}
        ghost = {"id": 99, "name": "ghost", "target": "branch", "enforcement": "active"}
        drift, unknown, _s, sot_body, unknown_body = _detect(
            tmp_path,
            sot_files={"main.json": SOT_MAIN, "all-branches.json": SOT_ALL},
            live_list=[{"id": 1, **SOT_MAIN}, {"id": 2, **SOT_ALL}, ghost],
            live_by_id={1: live_main, 2: SOT_ALL},
        )

        assert drift == 1
        assert unknown == 1
        assert sot_body is not None
        assert unknown_body is not None


class TestCli:
    def test_detect_prints_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sot_dir = _write_sot(tmp_path, {"main.json": SOT_MAIN})
        summary = tmp_path / "summary.md"

        monkeypatch.setattr(
            ruleset_drift,
            "fetch_live_rulesets_list",
            lambda _repo, _token: [{"id": 1, **SOT_MAIN}],
        )
        monkeypatch.setattr(
            ruleset_drift,
            "fetch_live_ruleset",
            lambda _repo, _id, _token: SOT_MAIN,
        )
        monkeypatch.setenv("GH_TOKEN_API", "tkn")

        rc = ruleset_drift.main(
            [
                "detect",
                "--repo",
                "owner/repo",
                "--sot-dir",
                str(sot_dir),
                "--sot-file",
                "main.json",
                "--run-url",
                "https://x/y",
                "--run-date",
                "2026-05-22",
                "--summary-file",
                str(summary),
                "--sot-body-file",
                str(tmp_path / "sot.md"),
                "--unknown-body-file",
                str(tmp_path / "unknown.md"),
            ]
        )

        out = capsys.readouterr().out
        assert rc == 0
        assert "run_date=2026-05-22" in out
        assert "drift_count=0" in out
        assert "unknown_count=0" in out

    def test_detect_missing_token_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sot_dir = _write_sot(tmp_path, {"main.json": SOT_MAIN})
        monkeypatch.delenv("GH_TOKEN_API", raising=False)

        rc = ruleset_drift.main(
            [
                "detect",
                "--repo",
                "owner/repo",
                "--sot-dir",
                str(sot_dir),
                "--sot-file",
                "main.json",
                "--run-url",
                "https://x/y",
                "--summary-file",
                str(tmp_path / "s.md"),
                "--sot-body-file",
                str(tmp_path / "sot.md"),
                "--unknown-body-file",
                str(tmp_path / "unk.md"),
            ]
        )

        assert rc == 1

    def test_reconcile_maps_kind_and_parses_detected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = tmp_path / "sot.md"
        body.write_text("Parent: #30\n", encoding="utf-8")
        captured: dict[str, Any] = {}

        def fake_reconcile(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "create"

        monkeypatch.setattr(ruleset_drift, "reconcile", fake_reconcile)

        rc = ruleset_drift.main(
            [
                "reconcile",
                "--repo",
                "owner/repo",
                "--kind",
                "sot",
                "--detected",
                "true",
                "--body-file",
                str(body),
            ]
        )

        assert rc == 0
        assert captured["repo"] == "owner/repo"
        assert captured["title"] == ruleset_drift.SOT_ISSUE_TITLE
        assert captured["detected"] is True
        assert captured["body_file"] == body
        assert captured["close_comment"] == ruleset_drift.SOT_RESOLVED_COMMENT
        assert "action=create" in capsys.readouterr().out

    def test_reconcile_unknown_kind_false_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_reconcile(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "close"

        monkeypatch.setattr(ruleset_drift, "reconcile", fake_reconcile)

        rc = ruleset_drift.main(
            [
                "reconcile",
                "--repo",
                "owner/repo",
                "--kind",
                "unknown",
                "--detected",
                "false",
                "--body-file",
                str(tmp_path / "missing.md"),
            ]
        )

        assert rc == 0
        assert captured["title"] == ruleset_drift.UNKNOWN_ISSUE_TITLE
        assert captured["detected"] is False

    def test_reconcile_invalid_detected_exits_one(self, tmp_path: Path) -> None:
        rc = ruleset_drift.main(
            [
                "reconcile",
                "--repo",
                "owner/repo",
                "--kind",
                "sot",
                "--detected",
                "maybe",
                "--body-file",
                str(tmp_path / "x.md"),
            ]
        )
        assert rc == 1


class TestDriftHashAndMarker:
    def test_hash_is_deterministic_and_short(self) -> None:
        assert ruleset_drift.drift_hash("abc") == ruleset_drift.drift_hash("abc")
        assert len(ruleset_drift.drift_hash("abc")) == 16

    def test_hash_differs_on_content_change(self) -> None:
        assert ruleset_drift.drift_hash("abc") != ruleset_drift.drift_hash("abd")

    def test_marker_roundtrips(self) -> None:
        body = ruleset_drift.embed_hash_marker("body text", "deadbeef")
        assert ruleset_drift.extract_hash_marker(body) == "deadbeef"

    def test_extract_returns_none_when_absent(self) -> None:
        assert ruleset_drift.extract_hash_marker("no marker here\n") is None


class TestDecideIssueAction:
    def test_detected_no_issue_creates(self) -> None:
        assert (
            ruleset_drift.decide_issue_action(
                detected=True, existing_issue=None, content_changed=True
            )
            == "create"
        )

    def test_detected_changed_content_appends(self) -> None:
        assert (
            ruleset_drift.decide_issue_action(
                detected=True, existing_issue={"number": 7}, content_changed=True
            )
            == "append"
        )

    def test_detected_same_content_silent(self) -> None:
        assert (
            ruleset_drift.decide_issue_action(
                detected=True, existing_issue={"number": 7}, content_changed=False
            )
            == "silent"
        )

    def test_resolved_with_issue_closes(self) -> None:
        assert (
            ruleset_drift.decide_issue_action(
                detected=False, existing_issue={"number": 7}, content_changed=False
            )
            == "close"
        )

    def test_resolved_without_issue_silent(self) -> None:
        assert (
            ruleset_drift.decide_issue_action(
                detected=False, existing_issue=None, content_changed=False
            )
            == "silent"
        )


class TestReconcile:
    """reconcile() calls module-level gh wrappers; tests monkeypatch them so no
    process ever runs and the chosen action is the only assertion surface."""

    def _body_with_hash(self, tmp_path: Path, content_hash: str) -> Path:
        body = tmp_path / "body.md"
        body.write_text(
            ruleset_drift.embed_hash_marker("Parent: #30\n", content_hash),
            encoding="utf-8",
        )
        return body

    def _wire(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        existing: dict[str, Any] | None,
        open_hash: str | None = None,
    ) -> dict[str, list[Any]]:
        calls: dict[str, list[Any]] = {"create": [], "comment": [], "close": []}
        monkeypatch.setattr(ruleset_drift, "find_rolling_issue", lambda _r, _t: existing)
        monkeypatch.setattr(
            ruleset_drift,
            "fetch_issue_body",
            lambda _r, _n: ruleset_drift.embed_hash_marker("old", open_hash or ""),
        )
        monkeypatch.setattr(
            ruleset_drift, "file_issue",
            lambda r, t, _b, _l: calls["create"].append((r, t)),
        )
        monkeypatch.setattr(
            ruleset_drift, "comment_on_issue",
            lambda _r, n, _b: calls["comment"].append(n),
        )
        monkeypatch.setattr(
            ruleset_drift, "close_issue_with_comment",
            lambda _r, n, c: calls["close"].append((n, c)),
        )
        return calls

    def _reconcile(self, *, detected: bool, body_file: Path) -> str:
        return ruleset_drift.reconcile(
            repo="owner/repo",
            title=ruleset_drift.SOT_ISSUE_TITLE,
            detected=detected,
            body_file=body_file,
            close_comment="resolved comment",
        )

    def test_create_when_no_open_issue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._wire(monkeypatch, existing=None)
        action = self._reconcile(detected=True, body_file=self._body_with_hash(tmp_path, "abc123"))
        assert action == "create"
        assert calls["create"] == [("owner/repo", ruleset_drift.SOT_ISSUE_TITLE)]

    def test_silent_when_same_hash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._wire(monkeypatch, existing={"number": 42}, open_hash="samehash")
        action = self._reconcile(detected=True, body_file=self._body_with_hash(tmp_path, "samehash"))
        assert action == "silent"
        assert calls == {"create": [], "comment": [], "close": []}

    def test_append_when_hash_changed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._wire(monkeypatch, existing={"number": 42}, open_hash="oldhash")
        action = self._reconcile(detected=True, body_file=self._body_with_hash(tmp_path, "newhash"))
        assert action == "append"
        assert calls["comment"] == [42]

    def test_close_when_resolved_and_issue_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._wire(monkeypatch, existing={"number": 99})
        action = self._reconcile(detected=False, body_file=tmp_path / "absent.md")
        assert action == "close"
        assert calls["close"] == [(99, "resolved comment")]

    def test_silent_when_resolved_and_no_issue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._wire(monkeypatch, existing=None)
        action = self._reconcile(detected=False, body_file=tmp_path / "absent.md")
        assert action == "silent"
        assert calls == {"create": [], "comment": [], "close": []}


class TestDetectEmbedsHash:
    def test_sot_body_carries_hash_marker(self, tmp_path: Path) -> None:
        live = {**SOT_MAIN, "id": 5, "enforcement": "disabled"}
        _, _, _, sot_body, _ = _detect(
            tmp_path,
            sot_files={"main.json": SOT_MAIN},
            live_list=[{"id": 5, "name": "main-protection"}],
            live_by_id={5: live},
        )
        assert sot_body is not None
        assert ruleset_drift.extract_hash_marker(sot_body) is not None
