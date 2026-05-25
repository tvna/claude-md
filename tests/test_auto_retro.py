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

import auto_retro as ar
import body_policy as bp
import pytest

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
            # (retro) scope on a non-retro Conventional Commit type --
            # covers retro-closing PRs that title policy forces to use
            # docs/feat/fix/etc. as the primary type.
            "docs(retro): record PR 235 repair-free merge",
            "feat(retro): broaden auto-retro skip rule",
            "fix(retro): edge case",
            "  Docs(Retro): leading space + mixed case",
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
            # Precision guards: tokens that contain "retro" without
            # being a literal (retro) scope must not match.
            "docs(retrospective): foo",
            "chore(retro-bot): foo",
            # Description text mentions (retro) but it is NOT inside the
            # type(scope) token.
            "fix(harness): broaden auto-retro skip rule to cover docs(retro) PRs",
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

    def test_skip_when_pr_has_retro_scope(self) -> None:
        """docs(retro): ... is a retro-closing PR; must skip to avoid recursion."""
        pr = _make_pr(title="docs(retro): record PR 235 repair-free merge")
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
    def test_with_type_scope_strips_scope(self) -> None:
        """Source type(scope) must yield retro(type), not retro(type(scope))."""
        pr = _make_pr(number=42, title="feat(harness): do a thing")
        assert (
            ar.build_retro_title(pr)
            == "retro(feat): review PR #42 repair loops"
        )

    def test_with_retro_scope_avoids_nested_parens(self) -> None:
        """The motivating regression: docs(retro): ... must not nest into
        retro(docs(retro)): ... . See issue #245."""
        pr = _make_pr(number=240, title="docs(retro): record PR 235 repair-free merge")
        title = ar.build_retro_title(pr)
        assert title == "retro(docs): review PR #240 repair loops"
        # Hard regression guard: no double-open / double-close parens
        # in the generated title regardless of source PR shape.
        assert "((" not in title
        assert "))" not in title

    def test_without_scope(self) -> None:
        pr = _make_pr(number=7, title="chore: bump deps")
        assert ar.build_retro_title(pr) == "retro(chore): review PR #7 repair loops"

    def test_fallback_for_freeform_title(self) -> None:
        pr = _make_pr(number=9, title="Freeform title")
        assert (
            ar.build_retro_title(pr) == "retro(retro): review PR #9 repair loops"
        )

    @pytest.mark.parametrize(
        "source_title",
        [
            "feat(harness): foo",
            "docs(retro): bar",
            "chore(agent-rules): baz",
            "fix: no scope",
            "Freeform title",
            "",
        ],
    )
    def test_never_emits_nested_parens(self, source_title: str) -> None:
        """For any source title shape, the generated retro title contains
        exactly one (...) group -- never nested."""
        pr = _make_pr(number=1, title=source_title)
        title = ar.build_retro_title(pr)
        assert "((" not in title
        assert "))" not in title
        # Exactly one open and one close paren.
        assert title.count("(") == 1
        assert title.count(")") == 1


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
# _build_repair_history_table / build_retro_body table-and-marker contract
# (issue #343)
# ---------------------------------------------------------------------------


class TestRepairHistoryTable:
    def test_ci_failure_row_from_check_runs(self) -> None:
        check_runs = [
            {
                "name": "verify-body-policy",
                "conclusion": "failure",
                "completed_at": "2026-05-24T14:36:21Z",
            }
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        assert "CI fail: verify-body-policy" in table
        assert "conclusion=failure" in table
        assert "2026-05-24T14:36:21Z" in table

    def test_check_runs_completed_at_null_uses_placeholder(self) -> None:
        check_runs = [
            {
                "name": "in-progress-check",
                "conclusion": "cancelled",
                "completed_at": None,
            }
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        assert "(no completed_at)" in table

    def test_check_runs_success_conclusions_are_dropped(self) -> None:
        """Only failure-class conclusions count as repair signals."""
        check_runs = [
            {"name": "pytest", "conclusion": "success", "completed_at": "x"},
            {"name": "ruff", "conclusion": "neutral", "completed_at": "x"},
            {"name": "mypy", "conclusion": "skipped", "completed_at": "x"},
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        assert "CI fail:" not in table
        # No other signals -> sentinel row.
        assert "(no automated repair signals detected)" in table

    def test_fixup_commit_rows(self) -> None:
        commits = [
            "fix(scripts): retry timeout",
            "fixup! feat(harness): earlier subject",
            "squash! fix typo",
            "feat(harness): unrelated",
        ]
        table = ar._build_repair_history_table(None, commits, len(commits))
        # Three iteration-commit rows from the three repair-prefix subjects.
        assert table.count("| Iteration commit |") == 3
        assert "fix(scripts): retry timeout" in table
        assert "fixup! feat(harness): earlier subject" in table
        assert "squash! fix typo" in table

    def test_merge_from_main_rows_both_prefix_variants(self) -> None:
        commits = [
            "Merge branch 'main' into feature",
            "Merge remote-tracking branch 'origin/main' into feature",
        ]
        table = ar._build_repair_history_table(None, commits, len(commits))
        assert table.count("| Merge from main |") == 2

    def test_multi_commit_summary_row(self) -> None:
        table = ar._build_repair_history_table(None, ["feat: a", "feat: b"], 4)
        assert "Multi-commit PR" in table
        assert "4 commits squash-merged" in table

    def test_multi_commit_single_commit_omits_summary(self) -> None:
        table = ar._build_repair_history_table(None, ["feat: only"], 1)
        assert "Multi-commit PR" not in table

    def test_sentinel_when_no_signals(self) -> None:
        table = ar._build_repair_history_table(None, ["feat(harness): plain"], 1)
        assert "(no automated repair signals detected)" in table
        assert "operator: investigate manually" in table
        # No numbered rows: only the "| -- |" sentinel.
        assert "| 1 |" not in table

    def test_sentinel_absent_when_any_signal_fires(self) -> None:
        table = ar._build_repair_history_table(None, ["fix(x): a"], 1)
        assert "(no automated repair signals detected)" not in table

    def test_pipe_in_commit_subject_is_escaped(self) -> None:
        """A '|' in a commit subject must be backslash-escaped so the
        table structure stays a 3-column grid."""
        table = ar._build_repair_history_table(
            None, ["fix(x): rename a|b to c"], 1
        )
        # The escaped pipe must appear, AND the rendered row line must
        # contain exactly 4 unescaped '|' characters (the 3 column
        # delimiters plus opening/closing).
        assert "a\\|b" in table
        row_line = next(
            line for line in table.splitlines() if "Iteration commit" in line
        )
        unescaped_pipes = row_line.replace("\\|", "")
        assert unescaped_pipes.count("|") == 4

    def test_table_uses_canonical_header(self) -> None:
        table = ar._build_repair_history_table(None, [], 1)
        first_line = table.splitlines()[0]
        assert first_line == "| # | Repair | What the reviewer / gate caught |"

    def test_row_ordering_is_deterministic(self) -> None:
        """Rows must appear in: CI failures, fix-ups, merge-from-main,
        multi-commit summary. Test all four classes at once."""
        check_runs = [
            {"name": "ci-job", "conclusion": "failure", "completed_at": "t"}
        ]
        commits = [
            "fix(x): repair",
            "Merge branch 'main' into f",
        ]
        table = ar._build_repair_history_table(check_runs, commits, 4)
        ci_idx = table.index("CI fail: ci-job")
        fixup_idx = table.index("Iteration commit")
        merge_idx = table.index("Merge from main")
        multi_idx = table.index("Multi-commit PR")
        assert ci_idx < fixup_idx < merge_idx < multi_idx


class TestBuildRetroBodyMarkers:
    """build_retro_body's marker contract for issue #343."""

    def test_auto_filled_markers_present(self) -> None:
        body = ar.build_retro_body(_make_pr(), [])
        assert body.count("<!-- auto-filled:repair-history -->") == 1
        assert body.count("<!-- /auto-filled:repair-history -->") == 1

    def test_operator_fill_markers_present(self) -> None:
        body = ar.build_retro_body(_make_pr(), [])
        assert body.count("<!-- operator-fill:remaining-steps -->") == 1
        assert body.count("<!-- /operator-fill:remaining-steps -->") == 1

    def test_marker_pairs_are_well_nested(self) -> None:
        body = ar.build_retro_body(_make_pr(), [])
        auto_open = body.index("<!-- auto-filled:repair-history -->")
        auto_close = body.index("<!-- /auto-filled:repair-history -->")
        op_open = body.index("<!-- operator-fill:remaining-steps -->")
        op_close = body.index("<!-- /operator-fill:remaining-steps -->")
        # Auto-filled block closes before operator-fill block opens.
        assert auto_open < auto_close < op_open < op_close

    def test_table_sits_inside_auto_filled_block(self) -> None:
        body = ar.build_retro_body(_make_pr(), [])
        auto_open = body.index("<!-- auto-filled:repair-history -->")
        auto_close = body.index("<!-- /auto-filled:repair-history -->")
        table_header = body.index(
            "| # | Repair | What the reviewer / gate caught |"
        )
        assert auto_open < table_header < auto_close

    def test_default_check_runs_none_emits_sentinel(self) -> None:
        """Backward-compat: legacy two-arg call must produce sentinel row
        when no commit signals fire."""
        body = ar.build_retro_body(_make_pr(commits=1), [])
        assert "(no automated repair signals detected)" in body

    def test_check_runs_argument_is_threaded_into_table(self) -> None:
        body = ar.build_retro_body(
            _make_pr(),
            [],
            check_runs=[
                {
                    "name": "verify-body-policy",
                    "conclusion": "failure",
                    "completed_at": "2026-05-24T14:36:21Z",
                }
            ],
        )
        assert "CI fail: verify-body-policy" in body

    def test_body_passes_body_policy_with_markers_and_table(self) -> None:
        """Regression: markers + table inside ## Proposed work must not
        break body_policy section detection. strip_html_comments handles
        the marker tolerance."""
        body = ar.build_retro_body(
            _make_pr(commits=3),
            ["fix(x): repair", "Merge branch 'main' into f", "feat: a"],
            check_runs=[
                {"name": "ci", "conclusion": "failure", "completed_at": "t"}
            ],
        )
        headings = bp.extract_headings(body)
        missing = bp.missing_sections(bp._ISSUE_COMMON_REQUIRED, headings)
        assert missing == [], f"verify-body-policy would fail: missing={missing}"

    def test_trailer_includes_merged_at_date(self) -> None:
        body = ar.build_retro_body(
            _make_pr(merged_at="2026-05-25T09:00:00Z"), []
        )
        assert "retro triage 2026-05-25" in body

    def test_body_is_pure_ascii(self) -> None:
        """Layer 2 scan-non-ascii.yml is the post-merge backstop; this
        belt-and-braces test catches non-ASCII drift at unit-test time."""
        body = ar.build_retro_body(_make_pr(commits=3), ["fix(x): a"])
        body.encode("ascii")  # raises UnicodeEncodeError on drift


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

    def test_matches_retro_colon_variant(self) -> None:
        """Success path for the ``retro:`` (no-scope) prefix variant."""
        items = [{"number": 3, "title": "retro: review PR #42 repair loops"}]
        assert ar.find_existing_retro(items, 42) == 3

    def test_rejects_pr_number_substring_collision(self) -> None:
        """A retro for #2490 must not be returned when looking up #249."""
        items = [
            {"number": 8, "title": "retro(fix): review PR #2490 repair loops"}
        ]
        assert ar.find_existing_retro(items, 249) is None

    def test_matches_case_insensitive_prefix(self) -> None:
        """``Retro(Fix):`` (mixed case) must still match -- prefix is lowered."""
        items = [
            {"number": 12, "title": "Retro(Fix): review PR #42 repair loops"}
        ]
        assert ar.find_existing_retro(items, 42) == 12


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

    def fake_run(cmd, **kwargs):
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
# search_retro_issues / has_review_comments / fetch_pr_commits / create_issue
# (API wrappers)
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


class TestHasReviewComments:
    def test_empty_list_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zero-repair signal: empty review-comments list -> False."""
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: json.dumps([]))
        assert ar.has_review_comments("o/r", 1) is False

    def test_non_empty_list_returns_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ar,
            "gh_api",
            lambda *_a, **_kw: json.dumps(
                [{"id": 1, "body": "needs fix", "path": "a.py"}]
            ),
        )
        assert ar.has_review_comments("o/r", 1) is True

    def test_empty_response_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Blank/empty body from gh api is treated as zero comments."""
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "")
        assert ar.has_review_comments("o/r", 1) is False

    def test_calls_correct_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            return json.dumps([])

        monkeypatch.setattr(ar, "gh_api", fake_api)
        ar.has_review_comments("owner/repo", 42)
        method, path, _ = seen[0]
        assert method == "GET"
        assert path == "/repos/owner/repo/pulls/42/comments?per_page=1"


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


class TestFetchCheckRuns:
    """fetch_check_runs (issue #343): two-step PR -> check-runs lookup."""

    def _staged_api(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        merge_commit_sha: str | None,
        check_runs: list[dict[str, Any]] | None,
    ) -> list[tuple[str, str]]:
        seen: list[tuple[str, str]] = []

        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            seen.append((method, path))
            if "/check-runs" in path:
                return json.dumps({"check_runs": check_runs or []})
            # First call: pull request detail.
            return json.dumps({"merge_commit_sha": merge_commit_sha})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        return seen

    def test_happy_path_returns_failed_runs_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = self._staged_api(
            monkeypatch,
            merge_commit_sha="abc123",
            check_runs=[
                {"name": "pytest", "conclusion": "success"},
                {"name": "ruff", "conclusion": "failure"},
                {"name": "mypy", "conclusion": "timed_out"},
                {"name": "preflight", "conclusion": "cancelled"},
                {"name": "label-gate", "conclusion": "action_required"},
                {"name": "neutral-check", "conclusion": "neutral"},
            ],
        )
        out = ar.fetch_check_runs("o/r", 42)
        names = [r["name"] for r in out]
        assert names == ["ruff", "mypy", "preflight", "label-gate"]
        # Two API calls in the right order.
        assert seen[0] == ("GET", "/repos/o/r/pulls/42")
        assert seen[1] == (
            "GET",
            "/repos/o/r/commits/abc123/check-runs?per_page=100",
        )

    def test_null_merge_commit_sha_short_circuits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns [] without making the second API call."""
        seen = self._staged_api(
            monkeypatch, merge_commit_sha=None, check_runs=None
        )
        assert ar.fetch_check_runs("o/r", 42) == []
        # Only the PR detail call must fire.
        assert len(seen) == 1
        assert seen[0] == ("GET", "/repos/o/r/pulls/42")

    def test_empty_pr_response_short_circuits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty body from the PR detail endpoint -> no SHA -> []."""
        seen: list[tuple[str, str]] = []

        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            seen.append((method, path))
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        assert ar.fetch_check_runs("o/r", 42) == []
        assert len(seen) == 1

    def test_empty_check_runs_response_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SHA present but check_runs endpoint returns blank -> []."""

        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            if "/check-runs" in path:
                return ""
            return json.dumps({"merge_commit_sha": "deadbeef"})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        assert ar.fetch_check_runs("o/r", 1) == []


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


class TestFindExistingBackLink:
    def test_returns_id_when_marker_at_body_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_api(method, path, body=None, **_kw):
            return json.dumps([
                {"id": 100, "body": "unrelated comment"},
                {"id": 101, "body": f"{ar._BACK_LINK_MARKER}\nRetrospective: #5"},
            ])

        monkeypatch.setattr(ar, "gh_api", fake_api)
        assert ar.find_existing_back_link_id("o/r", 42) == 101

    def test_returns_none_when_marker_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_api(method, path, body=None, **_kw):
            return json.dumps([
                {"id": 1, "body": "review note"},
                {"id": 2, "body": "another"},
            ])

        monkeypatch.setattr(ar, "gh_api", fake_api)
        assert ar.find_existing_back_link_id("o/r", 42) is None

    def test_marker_must_be_at_body_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A marker in the middle of a body must not match: that prevents a
        review quoting the marker from being treated as the back-link."""
        def fake_api(method, path, body=None, **_kw):
            return json.dumps([
                {"id": 7, "body": f"quoted earlier: {ar._BACK_LINK_MARKER}\n..."},
            ])

        monkeypatch.setattr(ar, "gh_api", fake_api)
        assert ar.find_existing_back_link_id("o/r", 42) is None

    def test_empty_response_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ar, "gh_api", lambda *a, **kw: "")
        assert ar.find_existing_back_link_id("o/r", 42) is None

    def test_calls_correct_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path))
            return json.dumps([])

        monkeypatch.setattr(ar, "gh_api", fake_api)
        ar.find_existing_back_link_id("o/r", 42)
        assert seen == [
            ("GET", "/repos/o/r/issues/42/comments?per_page=100"),
        ]


class TestPostBackLinkComment:
    def test_creates_when_no_existing_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET":
                return json.dumps([])
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        result = ar.post_back_link_comment("o/r", 42, 99)
        assert result == "created"
        assert seen[1] == (
            "POST",
            "/repos/o/r/issues/42/comments",
            {"body": f"{ar._BACK_LINK_MARKER}\nRetrospective: #99"},
        )

    def test_patches_when_marker_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET":
                return json.dumps([
                    {"id": 500, "body": f"{ar._BACK_LINK_MARKER}\nold"},
                ])
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        result = ar.post_back_link_comment("o/r", 42, 99)
        assert result == "updated 500"
        assert seen[1] == (
            "PATCH",
            "/repos/o/r/issues/comments/500",
            {"body": f"{ar._BACK_LINK_MARKER}\nRetrospective: #99"},
        )
        # Must not POST a duplicate when patching.
        assert not any(
            method == "POST" and path.endswith("/comments")
            for method, path, _ in seen
        )

    def test_loud_failure_on_post_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gh_api raises CalledProcessError; post_back_link_comment must
        propagate so the orchestrator can decide its fail-soft policy."""
        def fake_api(method, path, body=None, **_kw):
            if method == "GET":
                return json.dumps([])
            raise subprocess.CalledProcessError(1, "gh", stderr="boom")

        monkeypatch.setattr(ar, "gh_api", fake_api)
        with pytest.raises(subprocess.CalledProcessError):
            ar.post_back_link_comment("o/r", 42, 99)


# ---------------------------------------------------------------------------
# apply_terminal_label
# ---------------------------------------------------------------------------


class TestApplyTerminalLabel:
    def test_posts_terminal_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        ar.apply_terminal_label("o/r", 42)
        assert seen == [
            (
                "POST",
                "/repos/o/r/issues/42/labels",
                {"labels": [ar._TERMINAL_LABEL]},
            )
        ]

    def test_loud_failure_on_post_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gh_api raises CalledProcessError; apply_terminal_label must
        propagate so the orchestrator can decide its fail-soft policy."""
        def fake_api(method, path, body=None, **_kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="boom")

        monkeypatch.setattr(ar, "gh_api", fake_api)
        with pytest.raises(subprocess.CalledProcessError):
            ar.apply_terminal_label("o/r", 42)


def test_terminal_label_aligned_with_labels_json() -> None:
    """``_TERMINAL_LABEL`` must exist as a ``name`` entry in the declarative
    ``.github/labels.json`` SoT so ``apply-labels.yml`` reconciles it onto
    the repository before any merge fires ``apply_terminal_label``.
    """
    repo_root = Path(__file__).resolve().parent.parent
    sot = json.loads(
        (repo_root / ".github" / "labels.json").read_text(encoding="utf-8")
    )
    assert any(entry.get("name") == ar._TERMINAL_LABEL for entry in sot), (
        f"_TERMINAL_LABEL {ar._TERMINAL_LABEL!r} missing from .github/labels.json"
    )


# ---------------------------------------------------------------------------
# run (orchestrator)
# ---------------------------------------------------------------------------


def _orchestrator_recorder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: list[dict[str, Any]] | None = None,
    commits: list[dict[str, Any]] | None = None,
    review_comments: list[dict[str, Any]] | None = None,
    created_response: dict[str, Any] | None = None,
    comments_error: bool = False,
    pr_detail: dict[str, Any] | None = None,
    check_runs: list[dict[str, Any]] | None = None,
    check_runs_error: bool = False,
    back_link_comments: list[dict[str, Any]] | None = None,
    back_link_post_error: bool = False,
    terminal_label_post_error: bool = False,
) -> list[tuple]:
    """Replace ar.gh_api with a recorder that returns canned data per path.

    Defaults ``review_comments`` to a single non-empty entry so existing
    happy-path tests still reach the issue-creation branch. New tests
    that exercise the zero-review-comments skip pass ``review_comments=[]``.
    Set ``comments_error=True`` to make the comments endpoint raise the
    same ``CalledProcessError`` that gh_api raises in production -- used
    to test the fail-safe fallback in run().

    ``pr_detail`` controls the response of ``GET /repos/{repo}/pulls/{n}``
    (used by ``fetch_check_runs`` to read ``merge_commit_sha``); defaults
    to ``{"merge_commit_sha": None}`` so no check-runs lookup fires and
    the Repair history table degrades to commit-subject signals only.
    ``check_runs`` controls the second-call response; ``check_runs_error``
    makes the PR-detail call raise to exercise the fail-soft path.
    """
    seen: list[tuple] = []
    existing = existing or []
    commits = commits or []
    if review_comments is None:
        review_comments = [{"id": 1, "body": "default repair signal"}]
    created_response = created_response or {
        "number": 999,
        "html_url": "https://x/i/999",
    }
    if pr_detail is None:
        pr_detail = {"merge_commit_sha": None}
    check_runs = check_runs or []
    back_link_comments = back_link_comments or []

    def fake_api(method, path, body=None, **_kw):
        seen.append((method, path, body))
        if method == "GET" and path.startswith("/search/issues"):
            return json.dumps({"items": existing})
        if method == "GET" and "/pulls/" in path and "/comments" in path:
            if comments_error:
                raise subprocess.CalledProcessError(
                    1, "gh", stderr="comments endpoint boom"
                )
            return json.dumps(review_comments)
        if method == "GET" and "/pulls/" in path and "/commits" in path:
            return json.dumps(commits)
        if method == "GET" and "/check-runs" in path:
            return json.dumps({"check_runs": check_runs})
        if method == "GET" and "/pulls/" in path:
            if check_runs_error:
                raise subprocess.CalledProcessError(
                    1, "gh", stderr="pulls endpoint boom"
                )
            return json.dumps(pr_detail)
        # Back-link search/post on the source PR (issues/{n}/comments).
        if (
            method == "GET"
            and "/issues/" in path
            and path.split("?", 1)[0].endswith("/comments")
        ):
            return json.dumps(back_link_comments)
        if (
            method == "POST"
            and "/issues/" in path
            and path.endswith("/comments")
        ):
            if back_link_post_error:
                raise subprocess.CalledProcessError(
                    1, "gh", stderr="back-link post boom"
                )
            return ""
        if (
            method == "POST"
            and "/issues/" in path
            and path.endswith("/labels")
        ):
            if terminal_label_post_error:
                raise subprocess.CalledProcessError(
                    1, "gh", stderr="terminal-label post boom"
                )
            return ""
        if method == "PATCH" and "/issues/comments/" in path:
            return ""
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

    def test_skip_when_zero_review_comments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive-control merge: no inline review comments -> no retro."""
        seen = _orchestrator_recorder(monkeypatch, review_comments=[])
        assert ar.run(_merged_event(number=42), "o/r") == 0
        # Comments endpoint must have been queried.
        assert any(
            method == "GET" and "/comments" in path
            for method, path, _ in seen
        )
        # No commits fetch, no issue creation.
        assert not any(
            method == "GET" and "/commits" in path
            for method, path, _ in seen
        )
        assert not any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_fail_safe_creates_when_comments_endpoint_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient API failure on the comments lookup must NOT silently
        skip the retro. Fall back to creating the issue."""
        seen = _orchestrator_recorder(monkeypatch, comments_error=True)
        assert ar.run(_merged_event(number=42), "o/r") == 0
        # Issue creation must still happen (fail-safe path).
        assert any(
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
            "retro(feat): review PR #42 repair loops"
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

    def test_fail_soft_creates_when_check_runs_endpoint_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient API failure on the check-runs lookup must NOT block
        retro creation. Issue #343 fail-soft contract."""
        seen = _orchestrator_recorder(monkeypatch, check_runs_error=True)
        assert ar.run(_merged_event(number=42), "o/r") == 0
        # Issue creation must still happen.
        assert any(
            method == "POST" and path == "/repos/o/r/issues"
            for method, path, _ in seen
        )

    def test_check_runs_threaded_into_body_when_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: a failing check_run on the merge SHA produces a
        ``CI fail:`` row inside the created issue body."""
        seen = _orchestrator_recorder(
            monkeypatch,
            pr_detail={"merge_commit_sha": "deadbeef"},
            check_runs=[
                {
                    "name": "verify-body-policy",
                    "conclusion": "failure",
                    "completed_at": "2026-05-24T14:36:21Z",
                }
            ],
        )
        assert ar.run(_merged_event(number=42), "o/r") == 0
        post_calls = [
            (m, p, b)
            for m, p, b in seen
            if m == "POST" and p == "/repos/o/r/issues"
        ]
        assert len(post_calls) == 1
        body = post_calls[0][2]["body"]
        assert "CI fail: verify-body-policy" in body
        assert "<!-- auto-filled:repair-history -->" in body

    def test_back_link_comment_posted_after_create(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() must POST the back-link comment on the source PR after
        create_issue returns. Ordering matters: the back-link references
        the retro number, so the retro must exist first."""
        seen = _orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
        )
        assert ar.run(_merged_event(number=42), "o/r") == 0
        create_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues"
        )
        back_link_post_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues/42/comments"
        )
        assert create_idx < back_link_post_idx, (
            "back-link must be posted after the retro issue is created"
        )
        back_link_call = seen[back_link_post_idx]
        assert back_link_call[2] == {
            "body": f"{ar._BACK_LINK_MARKER}\nRetrospective: #777",
        }

    def test_back_link_failure_does_not_abort_retro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the back-link POST fails, run() must still return 0 -- the
        retro issue is already created and rolling it back would be
        worse than a missing back-link."""
        seen = _orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
            back_link_post_error=True,
        )
        assert ar.run(_merged_event(number=42), "o/r") == 0
        # Issue creation happened.
        assert any(
            m == "POST" and p == "/repos/o/r/issues"
            for m, p, _b in seen
        )

    def test_back_link_patched_when_marker_already_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A re-run on the same merged PR finds an existing back-link
        marker and PATCHes it instead of creating a duplicate."""
        seen = _orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
            back_link_comments=[
                {"id": 8675309, "body": f"{ar._BACK_LINK_MARKER}\nold"},
            ],
        )
        assert ar.run(_merged_event(number=42), "o/r") == 0
        assert any(
            m == "PATCH" and p == "/repos/o/r/issues/comments/8675309"
            for m, p, _b in seen
        )
        # No POST to /issues/{n}/comments when patching.
        assert not any(
            m == "POST" and p.endswith("/issues/42/comments")
            for m, p, _b in seen
        )

    def test_terminal_label_applied_after_back_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() must POST the terminal label to the source PR after the
        back-link comment lands. Ordering matters: a subscribed session
        consumes the labeled webhook as the terminal-state signal, so the
        back-link comment (the human-visible reverse pointer) must already
        be in place by the time the label fires."""
        seen = _orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
        )
        assert ar.run(_merged_event(number=42), "o/r") == 0
        back_link_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues/42/comments"
        )
        label_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues/42/labels"
        )
        assert back_link_idx < label_idx, (
            "terminal label must be POSTed after the back-link comment"
        )
        assert seen[label_idx][2] == {"labels": [ar._TERMINAL_LABEL]}

    def test_terminal_label_failure_does_not_abort_retro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the label POST fails, run() must still return 0 -- the retro
        issue and back-link comment are already in place; the label is a
        secondary signal and must not roll back the audit trail."""
        seen = _orchestrator_recorder(
            monkeypatch,
            created_response={"number": 777, "html_url": "https://x/i/777"},
            terminal_label_post_error=True,
        )
        assert ar.run(_merged_event(number=42), "o/r") == 0
        # Retro creation and back-link both landed before the failing label.
        assert any(
            m == "POST" and p == "/repos/o/r/issues"
            for m, p, _b in seen
        )
        assert any(
            m == "POST" and p == "/repos/o/r/issues/42/comments"
            for m, p, _b in seen
        )


# ---------------------------------------------------------------------------
# Repair-signal aggregate (issue #298)
# ---------------------------------------------------------------------------


class TestComputeRepairSignals:
    def _pr(self, **overrides: Any) -> ar.MergedPR:
        defaults: dict[str, Any] = {
            "number": 1,
            "title": "feat(x): y",
            "merged": True,
            "merged_at": "2026-05-24T00:00:00Z",
            "merged_by_login": "tvna",
            "user_login": "tvna",
            "layer_labels": (),
            "html_url": "https://example/pr/1",
            "body": "",
            "commits": 0,
        }
        defaults.update(overrides)
        return ar.MergedPR(**defaults)

    def test_only_inline_comments_signal_fires(self) -> None:
        out = ar.compute_repair_signals(self._pr(), has_inline_comments=True)
        assert out == {
            "inline_review_comments": True,
            "body_cites_refs": False,
            "fix_typed_title": False,
            "multi_commit_pr": False,
            "verification_pairs_failed": False,
            "post_merge_unchecked": False,
        }

    def test_body_refs_signal_fires_for_refs(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(body="Refs #287\nRefs #298"), has_inline_comments=False
        )
        assert out["body_cites_refs"] is True

    def test_body_refs_signal_fires_for_closes_fixes_resolves(self) -> None:
        for keyword in ["Closes", "Fixes", "Resolves"]:
            out = ar.compute_repair_signals(
                self._pr(body=f"{keyword} #1"), has_inline_comments=False
            )
            assert out["body_cites_refs"] is True, keyword

    def test_body_refs_ignores_html_commented_refs(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(body="<!-- Refs #999 -->\nplain text"),
            has_inline_comments=False,
        )
        assert out["body_cites_refs"] is False

    def test_fix_typed_title_signal_fires(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(title="fix(harness): qualify gate names"),
            has_inline_comments=False,
        )
        assert out["fix_typed_title"] is True

    def test_fix_typed_title_case_insensitive(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(title="FIX(harness): caps"), has_inline_comments=False
        )
        assert out["fix_typed_title"] is True

    def test_fix_typed_title_does_not_fire_for_other_types(self) -> None:
        for title in ["feat(x): y", "docs(x): y", "chore: y", "ci: y"]:
            out = ar.compute_repair_signals(
                self._pr(title=title), has_inline_comments=False
            )
            assert out["fix_typed_title"] is False, title

    def test_multi_commit_signal_fires_for_two_commits(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(commits=2), has_inline_comments=False
        )
        assert out["multi_commit_pr"] is True

    def test_multi_commit_signal_does_not_fire_for_one_commit(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(commits=1), has_inline_comments=False
        )
        assert out["multi_commit_pr"] is False

    def test_all_signals_false_when_pr_is_a_clean_one_liner(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(title="docs: tweak", body="", commits=1),
            has_inline_comments=False,
        )
        assert not any(out.values())

    def test_multi_commit_signal_excludes_merge_branch_main_prefix(
        self,
    ) -> None:
        out = ar.compute_repair_signals(
            self._pr(commits=2),
            has_inline_comments=False,
            commit_subjects=[
                "Merge branch 'main' into feature",
                "feat(x): add x",
            ],
        )
        assert out["multi_commit_pr"] is False

    def test_multi_commit_signal_excludes_remote_tracking_main_prefix(
        self,
    ) -> None:
        out = ar.compute_repair_signals(
            self._pr(commits=2),
            has_inline_comments=False,
            commit_subjects=[
                "Merge remote-tracking branch 'origin/main' into feature",
                "feat(x): add y",
            ],
        )
        assert out["multi_commit_pr"] is False

    def test_multi_commit_signal_fires_when_pure_commits_exceed_one(
        self,
    ) -> None:
        out = ar.compute_repair_signals(
            self._pr(commits=3),
            has_inline_comments=False,
            commit_subjects=[
                "Merge branch 'main' into feature",
                "feat(x): add a",
                "feat(x): add b",
            ],
        )
        assert out["multi_commit_pr"] is True

    def test_multi_commit_signal_legacy_path_when_subjects_none(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(commits=2),
            has_inline_comments=False,
            commit_subjects=None,
        )
        assert out["multi_commit_pr"] is True


class TestCountMergeFromMain:
    def test_counts_both_prefix_variants(self) -> None:
        count = ar._count_merge_from_main(
            [
                "Merge branch 'main' into feature",
                "feat(x): add x",
                "Merge remote-tracking branch 'origin/main' into feature",
                "fix(scripts): tweak",
            ]
        )
        assert count == 2

    def test_returns_zero_when_no_merge_subjects(self) -> None:
        count = ar._count_merge_from_main(
            ["feat(x): a", "fix(y): b", "docs(z): c"]
        )
        assert count == 0

    def test_ignores_unrelated_merge_subjects(self) -> None:
        count = ar._count_merge_from_main(
            [
                "Merge branch 'feature-a' into feature-b",
                "Merge pull request #123 from x/y",
            ]
        )
        assert count == 0

    def test_handles_leading_whitespace(self) -> None:
        count = ar._count_merge_from_main(
            ["   Merge branch 'main' into feature"]
        )
        assert count == 1


class TestRenderRepairSignals:
    def test_renders_each_signal(self) -> None:
        text = ar.render_repair_signals(
            {"inline_review_comments": True, "body_cites_refs": False}
        )
        assert "inline_review_comments=true" in text
        assert "body_cites_refs=false" in text


class TestRunAggregateSignals:
    """Coverage for the issue #298 aggregate-gate behavior on top of TestRun."""

    def test_creates_retro_when_zero_comments_but_body_has_refs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(monkeypatch, review_comments=[])
        event = _merged_event(number=300, body="Refs #287\nRefs #298")
        assert ar.run(event, "o/r") == 0
        assert any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_creates_retro_when_zero_comments_but_fix_typed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(monkeypatch, review_comments=[])
        event = _merged_event(
            number=301, title="fix(harness): qualify gate names"
        )
        assert ar.run(event, "o/r") == 0
        assert any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_creates_retro_when_zero_comments_but_multi_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _orchestrator_recorder(monkeypatch, review_comments=[])
        event = _merged_event(number=302, commits=3)
        assert ar.run(event, "o/r") == 0
        assert any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_skips_when_only_signal_is_rebase_debt_multi_commit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """multi_commit_pr must not fire on rebase debt alone.

        Event reports ``commits=2`` but the commit list contains one
        merge-from-main commit plus one real development commit, so
        ``pure_commits == 1`` and the gate stays False. With no other
        signal firing, run() must skip without creating a retro.
        """
        seen = _orchestrator_recorder(
            monkeypatch,
            review_comments=[],
            commits=[
                {
                    "commit": {
                        "message": "Merge branch 'main' into feature\n"
                    }
                },
                {"commit": {"message": "feat(x): add x"}},
            ],
        )
        event = _merged_event(
            number=304,
            title="feat(x): add x",
            body="",
            commits=2,
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        assert "multi_commit_pr=false" in capsys.readouterr().out

    def test_skips_with_detailed_reason_when_no_signal_fires(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        seen = _orchestrator_recorder(monkeypatch, review_comments=[])
        event = _merged_event(
            number=303, title="docs: tweak", body="", commits=1
        )
        assert ar.run(event, "o/r") == 0
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )
        printed = capsys.readouterr().out
        assert "no repair signal fired" in printed
        assert "inline_review_comments=false" in printed
        assert "body_cites_refs=false" in printed
        assert "fix_typed_title=false" in printed
        assert "multi_commit_pr=false" in printed
        # Step summary also carries the same reason for the audit trail.
        assert "no repair signal fired" in summary.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Post-2026-05-26 PR shape readers (issue #fluffy-bubble)
# ---------------------------------------------------------------------------


_NEW_SHAPE_BODY = """## Summary

x

## Verification

- command: `pytest -q`
  result: `exit 0 (684 passed)`
- command: `ruff check .`
  result: `exit 1 (4 errors)`

## Checklist

### Bootstrap

- [x] facts split honest
- [ ] risk assessed

### After-merge (CI)

- [x] CI green

### Post-merge (auto-retro signal)

- [x] linked issue closed
- [ ] auto-retro opened
- [ ] no follow-up fix
"""


class TestVerificationRegexAlign:
    def test_command_regex_pattern_matches_body_policy(self) -> None:
        assert (
            ar._VERIFICATION_COMMAND_RE.pattern
            == bp._VERIFICATION_COMMAND_RE.pattern
        )

    def test_result_regex_pattern_matches_body_policy(self) -> None:
        assert (
            ar._VERIFICATION_RESULT_RE.pattern
            == bp._VERIFICATION_RESULT_RE.pattern
        )


class TestExtractVerificationPairs:
    def test_empty_body_returns_empty(self) -> None:
        assert ar.extract_verification_pairs("") == []

    def test_missing_section_returns_empty(self) -> None:
        assert ar.extract_verification_pairs("## Summary\n\n- x\n") == []

    def test_pairs_parsed(self) -> None:
        pairs = ar.extract_verification_pairs(_NEW_SHAPE_BODY)
        assert len(pairs) == 2
        assert pairs[0].command == "`pytest -q`"
        assert pairs[0].passed is True
        assert pairs[1].command == "`ruff check .`"
        assert pairs[1].passed is False

    def test_passed_when_result_starts_with_ok(self) -> None:
        body = (
            "## Verification\n\n"
            "- command: `body_policy verify`\n"
            "  result: `OK: pull_request body contains all required sections.`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_failed_when_result_is_failure_prose(self) -> None:
        body = (
            "## Verification\n\n"
            "- command: `pytest`\n"
            "  result: `failed: 3 tests broken`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is False

    def test_orphan_command_does_not_yield_pair(self) -> None:
        body = "## Verification\n\n- command: `pytest`\nresult: `exit 0`\n"
        pairs = ar.extract_verification_pairs(body)
        assert pairs == []

    def test_html_commented_pairs_ignored(self) -> None:
        body = (
            "## Verification\n\n"
            "<!-- - command: `fake`\n  result: `fake` -->\n"
            "- command: `real`\n  result: `exit 0`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert len(pairs) == 1
        assert pairs[0].command == "`real`"


class TestExtractPostMergeChecklist:
    def test_empty_body_returns_empty(self) -> None:
        assert ar.extract_post_merge_checklist("") == []

    def test_missing_checklist_returns_empty(self) -> None:
        assert ar.extract_post_merge_checklist("## Summary\n") == []

    def test_extracts_post_merge_items_only(self) -> None:
        items = ar.extract_post_merge_checklist(_NEW_SHAPE_BODY)
        assert items == [
            ("linked issue closed", True),
            ("auto-retro opened", False),
            ("no follow-up fix", False),
        ]
        # Sanity: Bootstrap items must NOT leak in.
        labels = [item for item, _ in items]
        assert "facts split honest" not in labels
        assert "CI green" not in labels

    def test_tolerates_clarifier_in_heading(self) -> None:
        body = """## Checklist

### Post-merge

- [ ] x
"""
        assert ar.extract_post_merge_checklist(body) == [("x", False)]

    def test_distinguishes_checked_and_unchecked(self) -> None:
        body = """## Checklist

### Post-merge

- [x] done
- [ ] todo
- [X] also done
"""
        items = ar.extract_post_merge_checklist(body)
        assert items == [
            ("done", True),
            ("todo", False),
            ("also done", True),
        ]


class TestRepairHistoryTableNewRows:
    def test_verification_fail_row_emitted(self) -> None:
        pairs = [
            ar.VerificationPair(
                command="`pytest -q`",
                result="`exit 1`",
                passed=False,
            ),
        ]
        table = ar._build_repair_history_table(
            None, [], 1, pairs, []
        )
        assert "Verification fail" in table
        assert "`pytest -q`" in table
        assert "observed: `exit 1`" in table

    def test_passing_verification_pair_not_in_table(self) -> None:
        pairs = [
            ar.VerificationPair(
                command="`pytest -q`",
                result="`exit 0`",
                passed=True,
            ),
        ]
        table = ar._build_repair_history_table(
            None, [], 1, pairs, []
        )
        assert "Verification fail" not in table

    def test_post_merge_unchecked_row_emitted(self) -> None:
        table = ar._build_repair_history_table(
            None, [], 1, None, [("linked issue closed", False)]
        )
        assert "Post-merge gate unchecked" in table
        assert "linked issue closed" in table

    def test_checked_post_merge_item_not_in_table(self) -> None:
        table = ar._build_repair_history_table(
            None, [], 1, None, [("linked issue closed", True)]
        )
        assert "Post-merge gate unchecked" not in table

    def test_row_ordering_existing_classes_before_new(self) -> None:
        pairs = [
            ar.VerificationPair("`a`", "`exit 1`", False),
        ]
        post_merge = [("p", False)]
        table = ar._build_repair_history_table(
            None, ["fix(harness): patch"], 2, pairs, post_merge
        )
        # Existing class (Iteration commit) appears before new classes.
        iter_idx = table.find("Iteration commit")
        verif_idx = table.find("Verification fail")
        post_idx = table.find("Post-merge gate unchecked")
        assert 0 < iter_idx < verif_idx < post_idx

    def test_default_args_keep_legacy_callsite(self) -> None:
        # No new-arg callers still work, no new rows produced.
        table = ar._build_repair_history_table(None, [], 1)
        assert "Verification fail" not in table
        assert "Post-merge gate unchecked" not in table


# ---------------------------------------------------------------------------
# Post-2026-05-26 follow-up fix() append branch
# ---------------------------------------------------------------------------


class TestFindTargetRetroFromRefs:
    def _pr(self, **overrides: Any) -> ar.MergedPR:
        defaults: dict[str, Any] = {
            "number": 50,
            "title": "fix(harness): follow-up",
            "merged": True,
            "merged_at": "2026-05-27T10:00:00Z",
            "merged_by_login": "tvna",
            "user_login": "tvna",
            "layer_labels": (),
            "html_url": "https://x/pr/50",
            "body": "Refs #40\n",
            "commits": 1,
        }
        defaults.update(overrides)
        return ar.MergedPR(**defaults)

    def test_returns_retro_number_when_fix_typed_refs_a_retro(self) -> None:
        pr = self._pr()
        titles = {40: "retro(feat): review PR #20 repair loops"}
        assert ar.find_target_retro_from_refs(pr, titles) == 40

    def test_returns_none_for_non_fix_typed_title(self) -> None:
        pr = self._pr(title="feat(harness): new thing")
        titles = {40: "retro(feat): review PR #20 repair loops"}
        assert ar.find_target_retro_from_refs(pr, titles) is None

    def test_returns_none_when_ref_does_not_resolve_to_retro(self) -> None:
        pr = self._pr()
        titles = {40: "feat(harness): not a retro"}
        assert ar.find_target_retro_from_refs(pr, titles) is None

    def test_returns_first_matching_retro(self) -> None:
        pr = self._pr(body="Refs #40\nRefs #50\n")
        titles = {
            40: "feat: ordinary",
            50: "retro(feat): review",
        }
        assert ar.find_target_retro_from_refs(pr, titles) == 50

    def test_returns_none_when_no_refs(self) -> None:
        pr = self._pr(body="no refs at all")
        assert ar.find_target_retro_from_refs(pr, {}) is None

    def test_ignores_html_commented_refs(self) -> None:
        pr = self._pr(body="<!-- Refs #40 -->\n")
        titles = {40: "retro(feat): review"}
        assert ar.find_target_retro_from_refs(pr, titles) is None


class TestInsertAppendedRow:
    _SAMPLE = (
        "## Proposed work\n"
        "\n"
        "<!-- auto-filled:repair-history -->\n"
        "1. Repair history\n"
        "\n"
        "| # | Repair | What |\n"
        "|---|--------|------|\n"
        "| 1 | A | B |\n"
        "<!-- /auto-filled:repair-history -->\n"
        "\n"
        "more text\n"
    )

    def test_appends_row_with_next_index(self) -> None:
        new_body, changed = ar._insert_appended_row(
            self._SAMPLE,
            ("Follow-up fix PR: #50", "`fix(x): y` merged at T"),
            50,
        )
        assert changed is True
        assert "| 2 |" in new_body
        assert "Follow-up fix PR: #50" in new_body
        assert (
            new_body.index("Follow-up fix PR: #50")
            < new_body.index("<!-- /auto-filled:repair-history -->")
        )

    def test_idempotent_when_pr_already_recorded(self) -> None:
        body = self._SAMPLE.replace("| 1 | A | B |", "| 1 | Follow-up #50 | x |")
        _, changed = ar._insert_appended_row(body, ("x", "y"), 50)
        assert changed is False

    def test_no_change_when_markers_missing(self) -> None:
        body = "## Proposed work\n\nno markers here\n"
        new_body, changed = ar._insert_appended_row(body, ("x", "y"), 50)
        assert changed is False
        assert new_body == body

    def test_next_index_falls_back_to_one_with_empty_table(self) -> None:
        body = (
            "<!-- auto-filled:repair-history -->\n"
            "no rows\n"
            "<!-- /auto-filled:repair-history -->\n"
        )
        new_body, changed = ar._insert_appended_row(body, ("x", "y"), 99)
        assert changed is True
        assert "| 1 | x | y |" in new_body

    def test_pr_number_prefix_collision_not_idempotent(self) -> None:
        body = self._SAMPLE.replace(
            "| 1 | A | B |", "| 1 | Follow-up #500 | x |"
        )
        # PR #50 must NOT match an existing #500 row.
        _, changed = ar._insert_appended_row(body, ("a", "b"), 50)
        assert changed is True


class TestAppendRepairHistoryRowIntegration:
    """Tests ar.append_repair_history_row with gh_api monkeypatched."""

    _RETRO_BODY = (
        "## Scope\n\n"
        "x\n"
        "\n"
        "## Proposed work\n"
        "\n"
        "<!-- auto-filled:repair-history -->\n"
        "| # | Repair | What |\n"
        "|---|--------|------|\n"
        "| 1 | CI fail | x |\n"
        "<!-- /auto-filled:repair-history -->\n"
    )

    def _pr(self, **overrides: Any) -> ar.MergedPR:
        defaults: dict[str, Any] = {
            "number": 77,
            "title": "fix(harness): patch",
            "merged": True,
            "merged_at": "2026-05-27T10:00:00Z",
            "merged_by_login": "tvna",
            "user_login": "tvna",
            "layer_labels": (),
            "html_url": "https://x/pr/77",
            "body": "Refs #66\n",
            "commits": 1,
        }
        defaults.update(overrides)
        return ar.MergedPR(**defaults)

    def test_patches_retro_body_when_marker_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET":
                return json.dumps({"body": self._RETRO_BODY})
            if method == "PATCH":
                return json.dumps({"number": 66})
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        changed, detail = ar.append_repair_history_row("o/r", 66, self._pr())
        assert changed is True
        assert "appended" in detail.lower()
        patches = [s for s in seen if s[0] == "PATCH"]
        assert len(patches) == 1
        assert patches[0][1] == "/repos/o/r/issues/66"
        assert "Follow-up fix PR: #77" in patches[0][2]["body"]

    def test_no_patch_when_markers_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET":
                return json.dumps({"body": "## Scope\n\nno markers\n"})
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        changed, detail = ar.append_repair_history_row("o/r", 66, self._pr())
        assert changed is False
        assert "markers absent" in detail or "already records" in detail
        assert not any(s[0] == "PATCH" for s in seen)

    def test_idempotent_when_pr_already_in_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        retro_with_pr = self._RETRO_BODY.replace(
            "| 1 | CI fail | x |",
            "| 1 | Follow-up fix PR: #77 | x |",
        )

        def fake_api(method, path, body=None, **_kw):
            if method == "GET":
                return json.dumps({"body": retro_with_pr})
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        changed, _ = ar.append_repair_history_row("o/r", 66, self._pr())
        assert changed is False


class TestRunAppendBranch:
    """Tests run() routing a fix-typed PR to append rather than create."""

    _RETRO_BODY = (
        "## Scope\n\nx\n"
        "<!-- auto-filled:repair-history -->\n"
        "| # | Repair | What |\n"
        "|---|--------|------|\n"
        "<!-- /auto-filled:repair-history -->\n"
    )

    def _setup(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        retro_title: str,
        retro_body: str = "",
    ) -> list[tuple]:
        seen: list[tuple] = []
        retro_body = retro_body or self._RETRO_BODY

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET" and path.startswith("/search/issues"):
                return json.dumps({"items": []})
            if method == "GET" and path == "/repos/o/r/issues/66":
                return json.dumps(
                    {"title": retro_title, "body": retro_body}
                )
            if method == "GET" and "/pulls/" in path and "/comments" in path:
                return json.dumps([])
            if method == "GET" and "/pulls/" in path and "/commits" in path:
                return json.dumps([])
            if method == "GET" and "/check-runs" in path:
                return json.dumps({"check_runs": []})
            if method == "GET" and "/pulls/" in path:
                return json.dumps({"merge_commit_sha": None})
            if method == "POST" and path.endswith("/issues"):
                return json.dumps(
                    {"number": 999, "html_url": "https://x/i/999"}
                )
            if method == "PATCH":
                return json.dumps({"number": 66})
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        return seen

    def test_fix_pr_referencing_retro_triggers_append(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = self._setup(
            monkeypatch,
            retro_title="retro(feat): review PR #20 repair loops",
        )
        event = _merged_event(
            number=77,
            title="fix(harness): patch",
            body="Refs #66\n",
        )
        assert ar.run(event, "o/r") == 0
        assert any(m == "PATCH" for m, _, _ in seen)
        assert not any(
            m == "POST" and p == "/repos/o/r/issues" for m, p, _ in seen
        )

    def test_fix_pr_referencing_non_retro_creates_normally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = self._setup(
            monkeypatch,
            retro_title="feat(harness): not a retro",
        )
        event = _merged_event(
            number=78,
            title="fix(harness): patch",
            body="Refs #66\n",
        )
        # Without a retro target, run() falls through to create_issue
        # via the standard signal aggregate (multi_commit, fix_typed,
        # etc.). fix_typed_title fires for this title, so an issue is
        # created.
        assert ar.run(event, "o/r") == 0
        # PATCH must NOT fire because no retro was found.
        assert not any(m == "PATCH" for m, _, _ in seen)


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
