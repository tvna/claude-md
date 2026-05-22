"""Tests for ``scripts/ruleset_drift.py``."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ruleset_drift


SOT_MAIN: dict[str, Any] = {
    "name": "main-protection",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "bypass_actors": [
        {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    ],
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

    def __enter__(self) -> "Response":
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

    def test_preserves_rules_list_order(self) -> None:
        ruleset = {**SOT_MAIN, "rules": [{"type": "b"}, {"type": "a"}, {"type": "c"}]}

        projected = ruleset_drift.canonical_projection(ruleset)

        assert [rule["type"] for rule in projected["rules"]] == ["b", "a", "c"]


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

    def test_rules_reorder_shows_drift(self) -> None:
        live = {
            **SOT_MAIN,
            "rules": list(reversed(SOT_MAIN["rules"])),
        }

        diff = ruleset_drift.diff_canonical(
            sot=SOT_MAIN, live=live, sot_path="a", live_path="b"
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
            "[ruleset-drift] SoT vs live drift detected (2026-05-22)",
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
                "[ruleset-drift] SoT vs live drift detected (2026-05-22)",
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

    def test_file_sot_issue_invokes_gh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = tmp_path / "sot.md"
        body.write_text("Parent: #30\n", encoding="utf-8")
        calls: list[dict[str, Any]] = []

        def fake_file_issue(
            repo: str, title: str, body_file: Path, *_args: Any, **_kwargs: Any
        ) -> None:
            calls.append({"repo": repo, "title": title, "body_file": body_file})

        monkeypatch.setattr(ruleset_drift, "file_issue", fake_file_issue)

        rc = ruleset_drift.main(
            [
                "file-sot-issue",
                "--repo",
                "owner/repo",
                "--run-date",
                "2026-05-22",
                "--body-file",
                str(body),
            ]
        )

        assert rc == 0
        assert calls == [
            {
                "repo": "owner/repo",
                "title": "[ruleset-drift] SoT vs live drift detected (2026-05-22)",
                "body_file": body,
            }
        ]

    def test_file_unknown_issue_title(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = tmp_path / "unk.md"
        body.write_text("Parent: #30\n", encoding="utf-8")
        captured: list[str] = []

        def fake_file_issue(
            _repo: str, title: str, _body_file: Path, *_args: Any, **_kwargs: Any
        ) -> None:
            captured.append(title)

        monkeypatch.setattr(ruleset_drift, "file_issue", fake_file_issue)

        rc = ruleset_drift.main(
            [
                "file-unknown-issue",
                "--repo",
                "owner/repo",
                "--run-date",
                "2026-05-22",
                "--body-file",
                str(body),
            ]
        )

        assert rc == 0
        assert captured == ["[ruleset-drift] unknown ruleset detected (2026-05-22)"]
