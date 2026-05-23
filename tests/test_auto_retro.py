"""Tests for ``scripts/auto_retro.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the structure of ``tests/test_scan_non_ascii.py``: pure functions
get table-driven tests; the subprocess boundary (:func:`auto_retro.gh_api`)
is monkeypatched. Refs #234.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import auto_retro as ar
import body_policy as bp


# ---------------------------------------------------------------------------
# Alignment: required sections must match body_policy
# ---------------------------------------------------------------------------


def test_required_sections_align_with_body_policy() -> None:
    """The retro body's section list must equal _ISSUE_COMMON_REQUIRED.

    Drift here means auto-opened retro issues would silently fail
    verify-body-policy on a future change to body_policy.py.
    """
    assert ar._REQUIRED_SECTIONS == bp._ISSUE_COMMON_REQUIRED


# ---------------------------------------------------------------------------
# parse_event
# ---------------------------------------------------------------------------


def _merged_event(**overrides: Any) -> dict[str, Any]:
    pr: dict[str, Any] = {
        "number": 42,
        "title": "feat(harness): do a thing",
        "merged": True,
        "merged_at": "2026-05-23T10:00:00Z",
        "merged_by": {"login": "tvna"},
        "user": {"login": "tvna"},
        "labels": [
            {"name": "type:feat"},
            {"name": "layer:p3-harness"},
            {"name": "layer:meta"},
        ],
        "html_url": "https://github.com/o/r/pull/42",
    }
    pr.update(overrides)
    return {"pull_request": pr}


class TestParseEvent:
    def test_happy_path(self) -> None:
        out = ar.parse_event(_merged_event())
        assert out.number == 42
        assert out.title == "feat(harness): do a thing"
        assert out.merged is True
        assert out.merged_at == "2026-05-23T10:00:00Z"
        assert out.merged_by_login == "tvna"
        assert out.user_login == "tvna"
        assert out.layer_labels == ("layer:p3-harness", "layer:meta")
        assert out.html_url == "https://github.com/o/r/pull/42"

    def test_missing_pr_raises(self) -> None:
        with pytest.raises(ValueError, match="no pull_request.number"):
            ar.parse_event({})

    def test_no_number_raises(self) -> None:
        with pytest.raises(ValueError, match="no pull_request.number"):
            ar.parse_event({"pull_request": {"title": "x"}})

    def test_merged_false_does_not_raise(self) -> None:
        """run() decides what to do with merged=false; parse_event must not."""
        out = ar.parse_event(_merged_event(merged=False))
        assert out.merged is False

    def test_missing_merged_by(self) -> None:
        out = ar.parse_event(_merged_event(merged_by=None))
        assert out.merged_by_login is None

    def test_missing_user(self) -> None:
        out = ar.parse_event(_merged_event(user=None))
        assert out.user_login is None

    def test_no_layer_labels(self) -> None:
        out = ar.parse_event(_merged_event(labels=[{"name": "type:feat"}]))
        assert out.layer_labels == ()

    def test_null_label_name(self) -> None:
        out = ar.parse_event(
            _merged_event(labels=[{"name": None}, {"name": "layer:meta"}])
        )
        assert out.layer_labels == ("layer:meta",)


# ---------------------------------------------------------------------------
# extract_type_scope
# ---------------------------------------------------------------------------


class TestExtractTypeScope:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("feat(harness): do a thing", "feat(harness)"),
            ("chore: bump deps", "chore"),
            ("docs(retro): define repair-free merge checks", "docs(retro)"),
            ("refactor(harness): backfill bodies", "refactor(harness)"),
            ("fix: typo", "fix"),
            ("feat(agent-rules): correct boundaries", "feat(agent-rules)"),
        ],
    )
    def test_matches(self, title: str, expected: str) -> None:
        assert ar.extract_type_scope(title) == expected

    @pytest.mark.parametrize(
        "title",
        [
            "Freeform title without colon",
            "Feat(harness): capital F is rejected",
            "feat (space-before-paren): no",
            "",
            "(scope-only): no",
        ],
    )
    def test_non_matches(self, title: str) -> None:
        assert ar.extract_type_scope(title) == ""


# ---------------------------------------------------------------------------
# is_retro_pr
# ---------------------------------------------------------------------------


class TestIsRetroPr:
    @pytest.mark.parametrize(
        "title",
        [
            "retro(feat-harness): review PR #234 repair loops",
            "retro: ad-hoc retrospective",
            "  RETRO(scope): leading space + uppercase",
        ],
    )
    def test_matches(self, title: str) -> None:
        assert ar.is_retro_pr(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "feat(harness): not a retro",
            "fix: also not",
            "retrospect: close but no",
            "",
        ],
    )
    def test_non_matches(self, title: str) -> None:
        assert ar.is_retro_pr(title) is False


# ---------------------------------------------------------------------------
# should_skip
# ---------------------------------------------------------------------------


def _make_pr(**overrides: Any) -> ar.MergedPR:
    defaults: dict[str, Any] = {
        "number": 1,
        "title": "feat(harness): x",
        "merged": True,
        "merged_at": "2026-05-23T10:00:00Z",
        "merged_by_login": "tvna",
        "user_login": "tvna",
        "layer_labels": (),
        "html_url": "https://example.com",
    }
    defaults.update(overrides)
    return ar.MergedPR(**defaults)


class TestShouldSkip:
    def test_happy_path_no_skip(self) -> None:
        skip, reason = ar.should_skip(_make_pr())
        assert skip is False
        assert reason == ""

    def test_skip_when_merged_by_dependabot(self) -> None:
        pr = _make_pr(merged_by_login="dependabot[bot]")
        skip, reason = ar.should_skip(pr)
        assert skip is True
        assert "merged by trusted bot" in reason
        assert "dependabot[bot]" in reason

    def test_skip_when_authored_by_dependabot(self) -> None:
        pr = _make_pr(user_login="dependabot[bot]", merged_by_login="tvna")
        skip, reason = ar.should_skip(pr)
        assert skip is True
        assert "authored by trusted bot" in reason

    def test_skip_when_pr_is_retro(self) -> None:
        pr = _make_pr(title="retro(feat-harness): review PR #200 repair loops")
        skip, reason = ar.should_skip(pr)
        assert skip is True
        assert "recursion" in reason

    def test_unknown_bot_does_not_skip(self) -> None:
        """The allowlist is exact-match; renovate[bot] is not on it."""
        pr = _make_pr(merged_by_login="renovate[bot]")
        skip, _ = ar.should_skip(pr)
        assert skip is False


# ---------------------------------------------------------------------------
# build_retro_title / build_retro_body
# ---------------------------------------------------------------------------


class TestBuildRetroTitle:
    def test_with_type_scope(self) -> None:
        pr = _make_pr(number=42, title="feat(harness): do a thing")
        assert (
            ar.build_retro_title(pr)
            == "retro(feat(harness)): review PR #42 repair loops"
        )

    def test_without_scope(self) -> None:
        pr = _make_pr(number=7, title="chore: bump deps")
        assert ar.build_retro_title(pr) == "retro(chore): review PR #7 repair loops"

    def test_fallback_for_freeform_title(self) -> None:
        pr = _make_pr(number=9, title="Freeform title")
        assert (
            ar.build_retro_title(pr) == "retro(retro): review PR #9 repair loops"
        )


class TestBuildRetroBody:
    def test_contains_all_required_sections(self) -> None:
        pr = _make_pr()
        body = ar.build_retro_body(pr, ["feat(harness): subject one"])
        for name in ar._REQUIRED_SECTIONS:
            assert f"## {name}\n" in body

    def test_body_passes_body_policy_extract(self) -> None:
        """End-to-end alignment: the generated body's headings cover
        every entry in body_policy._ISSUE_COMMON_REQUIRED."""
        pr = _make_pr()
        body = ar.build_retro_body(pr, ["feat(harness): subject"])
        headings = bp.extract_headings(body)
        missing = bp.missing_sections(bp._ISSUE_COMMON_REQUIRED, headings)
        assert missing == [], f"verify-body-policy would fail: missing={missing}"

    def test_body_is_not_tracking_shape(self) -> None:
        """The 'Initial child issues' marker MUST NOT appear; otherwise
        verify-body-policy switches to _ISSUE_TRACKING_REQUIRED and the
        retro body fails its own check."""
        pr = _make_pr()
        body = ar.build_retro_body(pr, [])
        assert bp._TRACKING_MARKER.lower() not in body.lower()

    def test_fallback_notice_present_for_freeform_title(self) -> None:
        pr = _make_pr(title="Freeform title")
        body = ar.build_retro_body(pr, [])
        assert "did not parse as a Conventional" in body
        assert ar.FALLBACK_TYPE_SCOPE in body

    def test_facts_include_commit_subjects(self) -> None:
        pr = _make_pr(number=10)
        body = ar.build_retro_body(
            pr, ["feat: one", "fix: two", "chore: three"]
        )
        assert "feat: one" in body
        assert "fix: two" in body
        assert "chore: three" in body

    def test_facts_include_pr_metadata(self) -> None:
        pr = _make_pr(
            number=99,
            title="feat(harness): demo",
            merged_at="2026-05-23T12:34:56Z",
            merged_by_login="tvna",
            user_login="alice",
            layer_labels=("layer:p3-harness", "layer:meta"),
            html_url="https://github.com/o/r/pull/99",
        )
        body = ar.build_retro_body(pr, [])
        assert "#99" in body
        assert "feat(harness): demo" in body
        assert "2026-05-23T12:34:56Z" in body
        assert "tvna" in body
        assert "alice" in body
        assert "layer:p3-harness" in body
        assert "https://github.com/o/r/pull/99" in body

    def test_empty_commit_list_shows_placeholder(self) -> None:
        body = ar.build_retro_body(_make_pr(), [])
        assert "no commit subjects fetched" in body

    def test_no_layer_labels_shows_placeholder(self) -> None:
        body = ar.build_retro_body(_make_pr(layer_labels=()), [])
        assert "(none on source PR)" in body


# ---------------------------------------------------------------------------
# find_existing_retro / issue_labels
# ---------------------------------------------------------------------------


class TestFindExistingRetro:
    def test_matches_by_pr_number(self) -> None:
        items = [
            {"number": 10, "title": "feat: unrelated"},
            {"number": 11, "title": "retro(feat-harness): review PR #42 repair loops"},
        ]
        assert ar.find_existing_retro(items, 42) == 11

    def test_no_match_returns_none(self) -> None:
        items = [{"number": 1, "title": "retro: review PR #99 repair loops"}]
        assert ar.find_existing_retro(items, 42) is None

    def test_empty_list_returns_none(self) -> None:
        assert ar.find_existing_retro([], 42) is None

    def test_ignores_non_retro_titles_even_with_matching_pr_ref(self) -> None:
        items = [
            {"number": 5, "title": "feat: relates to PR #42 but is not a retro"}
        ]
        assert ar.find_existing_retro(items, 42) is None

    def test_matches_closed_issue(self) -> None:
        """Search API returns open + closed by default; both must match."""
        items = [
            {
                "number": 7,
                "title": "retro(chore): review PR #42 repair loops",
                "state": "closed",
            }
        ]
        assert ar.find_existing_retro(items, 42) == 7


class TestIssueLabels:
    def test_no_inherited_labels(self) -> None:
        assert ar.issue_labels(()) == ["type:docs", "layer:meta"]

    def test_dedupes_layer_meta(self) -> None:
        out = ar.issue_labels(("layer:meta",))
        assert out == ["type:docs", "layer:meta"]

    def test_appends_extra_layer_labels(self) -> None:
        out = ar.issue_labels(("layer:p3-harness", "layer:meta"))
        assert out == ["type:docs", "layer:meta", "layer:p3-harness"]

    def test_filters_empty_names(self) -> None:
        out = ar.issue_labels(("", "layer:p4-artifact"))
        assert out == ["type:docs", "layer:meta", "layer:p4-artifact"]


# ---------------------------------------------------------------------------
# gh_api (subprocess boundary)
# ---------------------------------------------------------------------------


def _fake_run_capture():
    calls: list[dict[str, Any]] = []

    class _Result:
        def __init__(self, stdout: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode
            self.stderr = ""

    def fake_run(cmd, **kwargs):  # noqa: ANN001 — mirror subprocess.run
        calls.append({"cmd": cmd, **kwargs})
        return _Result(stdout="OK")

    return calls, fake_run


class TestGhApi:
    def test_get_no_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls, fake_run = _fake_run_capture()
        monkeypatch.setattr(subprocess, "run", fake_run)
        out = ar.gh_api("GET", "/repos/o/r/issues")
        assert out == "OK"
        assert calls[0]["cmd"] == [
            "gh", "api", "--method", "GET", "/repos/o/r/issues"
        ]
        assert "input" not in calls[0]

    def test_post_with_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls, fake_run = _fake_run_capture()
        monkeypatch.setattr(subprocess, "run", fake_run)
        ar.gh_api("POST", "/repos/o/r/issues", {"title": "T"})
        assert "--input" in calls[0]["cmd"]
        assert calls[0]["cmd"][-1] == "-"
        assert json.loads(calls[0]["input"]) == {"title": "T"}

    def test_nonzero_exit_raises_loudly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_a, **_kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="boom")

        monkeypatch.setattr(subprocess, "run", _raise)
        with pytest.raises(subprocess.CalledProcessError):
            ar.gh_api("GET", "/x")


# ---------------------------------------------------------------------------
# search_retro_issues / fetch_pr_commits / create_issue (API wrappers)
# ---------------------------------------------------------------------------


class TestSearchRetroIssues:
    def test_passes_url_encoded_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        ar.search_retro_issues("o/r", 42)
        method, path, _ = seen[0]
        assert method == "GET"
        assert path.startswith("/search/issues?q=")
        # The literal "PR #42" should be present (URL-encoded as "PR%20%2342").
        assert "%2342" in path

    def test_returns_items_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ar,
            "gh_api",
            lambda *_a, **_kw: json.dumps(
                {"items": [{"number": 1, "title": "retro(x): review PR #42 ..."}]}
            ),
        )
        out = ar.search_retro_issues("o/r", 42)
        assert len(out) == 1
        assert out[0]["number"] == 1

    def test_empty_response_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "")
        assert ar.search_retro_issues("o/r", 42) == []


class TestFetchPrCommits:
    def test_extracts_first_line_of_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ar,
            "gh_api",
            lambda *_a, **_kw: json.dumps(
                [
                    {"commit": {"message": "feat: one\n\nbody one"}},
                    {"commit": {"message": "fix: two"}},
                ]
            ),
        )
        assert ar.fetch_pr_commits("o/r", 1) == ["feat: one", "fix: two"]

    def test_handles_missing_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ar, "gh_api", lambda *_a, **_kw: json.dumps([{}, {"commit": {}}])
        )
        assert ar.fetch_pr_commits("o/r", 1) == ["", ""]

    def test_empty_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "")
        assert ar.fetch_pr_commits("o/r", 1) == []


class TestCreateIssue:
    def test_posts_title_body_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            return json.dumps({"number": 555, "html_url": "https://x/i/555"})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        out = ar.create_issue("o/r", "T", "B", ["type:docs", "layer:meta"])
        assert out == {"number": 555, "html_url": "https://x/i/555"}
        assert seen[0] == (
            "POST",
            "/repos/o/r/issues",
            {"title": "T", "body": "B", "labels": ["type:docs", "layer:meta"]},
        )


# ---------------------------------------------------------------------------
# run (orchestrator)
# ---------------------------------------------------------------------------


def _orchestrator_recorder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: list[dict[str, Any]] | None = None,
    commits: list[dict[str, Any]] | None = None,
    created_response: dict[str, Any] | None = None,
) -> list[tuple]:
    """Replace ar.gh_api with a recorder that returns canned data per path."""
    seen: list[tuple] = []
    existing = existing or []
    commits = commits or []
    created_response = created_response or {
        "number": 999,
        "html_url": "https://x/i/999",
    }

    def fake_api(method, path, body=None, **_kw):
        seen.append((method, path, body))
        if method == "GET" and path.startswith("/search/issues"):
            return json.dumps({"items": existing})
        if method == "GET" and "/pulls/" in path and "/commits" in path:
            return json.dumps(commits)
        if method == "POST" and path.endswith("/issues"):
            return json.dumps(created_response)
        return ""

    monkeypatch.setattr(ar, "gh_api", fake_api)
    return seen


class TestRun:
    def test_skip_when_not_merged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(monkeypatch)
        event = _merged_event(merged=False)
        assert ar.run(event, "o/r") == 0
        assert seen == []

    def test_skip_when_merged_by_dependabot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(monkeypatch)
        event = _merged_event(merged_by={"login": "dependabot[bot]"})
        assert ar.run(event, "o/r") == 0
        assert seen == []

    def test_skip_when_pr_is_retro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(monkeypatch)
        event = _merged_event(
            title="retro(feat-harness): review PR #200 repair loops"
        )
        assert ar.run(event, "o/r") == 0
        assert seen == []

    def test_skip_when_existing_retro_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(
            monkeypatch,
            existing=[
                {
                    "number": 100,
                    "title": "retro(feat-harness): review PR #42 repair loops",
                }
            ],
        )
        event = _merged_event(number=42)
        assert ar.run(event, "o/r") == 0
        # Only the search call should fire; no commits fetch, no create.
        methods_paths = [(c[0], c[1]) for c in seen]
        assert any("/search/issues" in p for _, p in methods_paths)
        assert not any("/commits" in p for _, p in methods_paths)
        assert not any(p == "/repos/o/r/issues" for _, p in methods_paths)

    def test_skip_when_existing_retro_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(
            monkeypatch,
            existing=[
                {
                    "number": 50,
                    "title": "retro(chore): review PR #42 repair loops",
                    "state": "closed",
                }
            ],
        )
        assert ar.run(_merged_event(number=42), "o/r") == 0
        assert not any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_happy_path_creates_issue(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(
            monkeypatch,
            commits=[
                {"commit": {"message": "feat(harness): step one\n\nbody"}},
                {"commit": {"message": "fix(harness): step two"}},
            ],
            created_response={"number": 777, "html_url": "https://x/i/777"},
        )
        event = _merged_event(
            number=42,
            title="feat(harness): centralize post-merge tracking",
            labels=[
                {"name": "type:feat"},
                {"name": "layer:p3-harness"},
                {"name": "layer:meta"},
            ],
        )
        assert ar.run(event, "o/r") == 0
        # Final POST is the issue creation; inspect its body.
        post_calls = [
            (m, p, b) for m, p, b in seen if m == "POST" and p == "/repos/o/r/issues"
        ]
        assert len(post_calls) == 1
        _, _, payload = post_calls[0]
        assert payload["title"] == (
            "retro(feat(harness)): review PR #42 repair loops"
        )
        assert "feat(harness): step one" in payload["body"]
        assert "fix(harness): step two" in payload["body"]
        assert payload["labels"] == [
            "type:docs", "layer:meta", "layer:p3-harness"
        ]

    def test_step_summary_written_on_create(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        _orchestrator_recorder(monkeypatch)
        ar.run(_merged_event(number=42), "o/r")
        text = summary.read_text(encoding="utf-8")
        assert "## auto-retro summary" in text
        assert "`created`" in text
        assert "#42" in text

    def test_step_summary_written_on_skip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        _orchestrator_recorder(monkeypatch)
        ar.run(_merged_event(merged=False), "o/r")
        text = summary.read_text(encoding="utf-8")
        assert "## auto-retro summary" in text
        assert "`skip`" in text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_run_reads_event_file_and_creates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        event = _merged_event(number=8)
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event))
        seen = _orchestrator_recorder(monkeypatch)
        exit_code = ar.main(
            ["run", "--event-file", str(event_file), "--repo", "o/r"]
        )
        assert exit_code == 0
        assert any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_run_uses_env_vars(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        event = _merged_event(number=9)
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("REPO", "o/r")
        _orchestrator_recorder(monkeypatch)
        assert ar.main(["run"]) == 0

    def test_run_missing_event_path_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
        monkeypatch.setenv("REPO", "o/r")
        assert ar.main(["run"]) == 1
        assert "GITHUB_EVENT_PATH" in capsys.readouterr().err

    def test_run_missing_repo_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{}")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        assert ar.main(["run"]) == 1
        assert "REPO" in capsys.readouterr().err

    def test_run_malformed_event_file_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{not json")
        exit_code = ar.main(
            ["run", "--event-file", str(event_file), "--repo", "o/r"]
        )
        assert exit_code == 1
        assert "cannot read event file" in capsys.readouterr().err

    def test_run_no_pr_in_event_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{}")
        exit_code = ar.main(
            ["run", "--event-file", str(event_file), "--repo", "o/r"]
        )
        assert exit_code == 1
        assert "no pull_request.number" in capsys.readouterr().err

    def test_run_gh_api_failure_is_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def _raise(*_a, **_kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="auth fail")

        monkeypatch.setattr(ar, "gh_api", _raise)
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(_merged_event()))
        exit_code = ar.main(
            ["run", "--event-file", str(event_file), "--repo", "o/r"]
        )
        assert exit_code == 1
        assert "gh api failed" in capsys.readouterr().err
