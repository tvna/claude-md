"""Tests for ``scripts/auto_retro.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the structure of ``tests/test_scan_non_ascii.py``: pure functions
get table-driven tests; the REST boundary (:func:`auto_retro.gh_api`)
is monkeypatched. Refs #234.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

import _retro_labels as rl
import auto_retro as ar
import body_policy as bp
import pytest
from _github_api import GitHubApiError
from hypothesis import given
from hypothesis import strategies as st

pytestmark = pytest.mark.shard_ci_ops_2

# The label set the .gitapex/ssot.json registry entry for scripts/auto_retro.py
# carries (registry order): the create-time identity labels, the retired
# layer:meta kept only for discovery (#1041, #2313), then the ops:/harness:
# terminal open-state labels. Mirrored here so every consumer resolves a known
# set via a mocked _ssot.consumer_labels rather than reading (or asserting
# against) the live registry file. Derivation-specific tests below override the
# mock with synthetic labels to prove the code reads the registry.
_REGISTRY_LABELS = (
    "type:docs",
    "layer:p3-harness",
    "area:ci-ops",
    "layer:meta",
    "ops:retro-opened",
    "harness:retro-opened",
)
_TERMINAL_PRIMARY = "ops:retro-opened"
_TERMINAL_LEGACY = "harness:retro-opened"


@pytest.fixture(autouse=True)
def _stub_registry_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a known label set for scripts/auto_retro.py so every consumer
    (issue_labels' base labels, both discovery-search queries, the terminal
    label) resolves deterministically without reading the live registry. Tests
    that exercise the registry-derivation or drift paths override this with
    their own monkeypatch.setattr, which wins because it runs inside the test
    body after this fixture.
    """
    monkeypatch.setattr(
        ar._ssot, "consumer_labels", lambda path: _REGISTRY_LABELS
    )


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
            # (auto-retro) scope; covers the auto-opened retro shape and
            # retro-closing PRs that title policy forces to use an allowed
            # Conventional Commit type with the auto-retro scope.
            "fix(auto-retro): review PR #234 repair loops",
            "docs(auto-retro): record PR 235 repair-free merge",
            "feat(auto-retro): broaden auto-retro skip rule",
            "  Docs(Auto-Retro): leading space + mixed case",
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
            # Legacy retro shapes are no longer recognized; existing retro
            # issues are migrated to the fix(auto-retro) prefix.
            "retro(feat-harness): review PR #234 repair loops",
            "retro: ad-hoc retrospective",
            "docs(retro): record PR 235 repair-free merge",
            # Precision guards: tokens that contain "retro" without being a
            # literal (auto-retro) scope must not match.
            "docs(retrospective): foo",
            "chore(retro-bot): foo",
            # Description text mentions (auto-retro) but it is NOT inside
            # the type(scope) token.
            "fix(harness): broaden the auto-retro skip rule for (auto-retro) PRs",
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
        pr = _make_pr(title="fix(auto-retro): review PR #200 repair loops")
        skip, reason = ar.should_skip(pr)
        assert skip is True
        assert "recursion" in reason

    def test_skip_when_pr_has_retro_scope(self) -> None:
        """docs(auto-retro): ... is a retro-closing PR; must skip recursion."""
        pr = _make_pr(title="docs(auto-retro): record PR 235 repair-free merge")
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
    @pytest.mark.parametrize(
        "number, source_title",
        [
            (42, "feat(harness): do a thing"),
            (240, "docs(auto-retro): record PR 235 repair-free merge"),
            (7, "chore: bump deps"),
            (9, "Freeform title"),
        ],
    )
    def test_emits_canonical_chore_auto_retro_title(
        self, number: int, source_title: str
    ) -> None:
        """The retro title is a fixed chore(auto-retro) token regardless of
        the source PR's own type(scope). The neutral chore prefix avoids the
        fix(...) reading that invited direct PRs off un-triaged retros
        (Refs #1069)."""
        pr = _make_pr(number=number, title=source_title)
        assert (
            ar.build_retro_title(pr)
            == f"chore(auto-retro): review PR #{number} repair loops"
        )

    @pytest.mark.parametrize(
        "source_title",
        [
            "feat(harness): foo",
            "docs(auto-retro): bar",
            "chore(agent-rules): baz",
            "fix: no scope",
            "Freeform title",
            "",
        ],
    )
    def test_emits_single_paren_group(self, source_title: str) -> None:
        """For any source title shape, the generated retro title contains
        exactly one (...) group; never nested."""
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
        assert "recorded as empty" in body

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

    def test_pr_368_historical_canonical_fix_does_not_produce_iteration_row(
        self,
    ) -> None:
        """Issue #413 historical re-render: PR #368 (`fix(ci): close
        verify skip bypass`) landed one merge-from-main commit and one
        canonical fix commit. The historical retro mis-flagged that
        canonical commit as Iteration commit. After the fix the body
        must render it as Fix commit and not duplicate it into the
        iteration class."""
        pr = _make_pr(
            number=368,
            title="fix(ci): close verify skip bypass",
        )
        commits = [
            "Merge branch 'main' into fix/verify-skip",
            "fix(ci): close verify skip bypass (#366)",
        ]
        body = ar.build_retro_body(pr, commits)
        assert "| Fix commit |" in body
        assert "canonical fix commit on fix-typed PR" in body
        # The canonical subject must not also appear with the
        # iteration-commit narration.
        assert (
            "`fix(ci): close verify skip bypass (#366)`; signals"
            not in body
        )


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

    # Issue #413 regression suite: canonical fix on fix-typed PR must not
    # be flagged as Iteration commit.
    def test_canonical_fix_commit_on_fix_typed_pr_emits_fix_commit_row(
        self,
    ) -> None:
        commits = ["fix(ci): close verify skip bypass (#366)"]
        table = ar._build_repair_history_table(
            None, commits, len(commits), pr_type="fix"
        )
        assert "| Fix commit |" in table
        assert "| Iteration commit |" not in table
        assert "canonical fix commit on fix-typed PR" in table

    def test_canonical_fix_skips_leading_merge_from_main(self) -> None:
        commits = [
            "Merge branch 'main' into branch",
            "fix(ci): close verify skip bypass",
        ]
        table = ar._build_repair_history_table(
            None, commits, len(commits), pr_type="fix"
        )
        assert "| Fix commit |" in table
        assert "| Merge from main |" in table
        assert "| Iteration commit |" not in table

    def test_intermediate_work_before_fix_keeps_iteration_classification(
        self,
    ) -> None:
        commits = [
            "feat(harness): groundwork",
            "fix(harness): correct earlier groundwork",
        ]
        table = ar._build_repair_history_table(
            None, commits, len(commits), pr_type="fix"
        )
        assert "| Fix commit |" not in table
        assert table.count("| Iteration commit |") == 1

    def test_multi_fix_pr_only_first_is_canonical(self) -> None:
        commits = [
            "fix(a): primary fix",
            "fix(b): follow-up after CI failure",
        ]
        table = ar._build_repair_history_table(
            None, commits, len(commits), pr_type="fix"
        )
        assert table.count("| Fix commit |") == 1
        assert table.count("| Iteration commit |") == 1
        assert "fix(a): primary fix" in table
        assert "fix(b): follow-up after CI failure" in table

    def test_non_fix_typed_pr_keeps_iteration_classification(self) -> None:
        commits = ["fix(x): emergency fix in a feat PR"]
        table = ar._build_repair_history_table(
            None, commits, len(commits), pr_type="feat"
        )
        assert "| Fix commit |" not in table
        assert "| Iteration commit |" in table

    def test_fixup_and_squash_prefixes_unaffected_by_pr_type(self) -> None:
        commits = [
            "fixup! feat(x): earlier",
            "squash! fix typo",
        ]
        table = ar._build_repair_history_table(
            None, commits, len(commits), pr_type="fix"
        )
        assert "| Fix commit |" not in table
        assert table.count("| Iteration commit |") == 2

    def test_unparsed_pr_title_defaults_preserve_iteration_classification(
        self,
    ) -> None:
        commits = ["fix(x): a fix"]
        table = ar._build_repair_history_table(
            None, commits, len(commits), pr_type=""
        )
        assert "| Fix commit |" not in table
        assert "| Iteration commit |" in table

    def test_merge_from_main_rows_both_prefix_variants(self) -> None:
        commits = [
            "Merge branch 'main' into feature",
            "Merge remote-tracking branch 'origin/main' into feature",
        ]
        table = ar._build_repair_history_table(None, commits, len(commits))
        assert table.count("| Merge from main |") == 2

    def test_merge_from_main_rows_carry_policy_artifact_marker(self) -> None:
        commits = [
            "Merge branch 'main' into feature",
            "Merge remote-tracking branch 'origin/main' into feature",
        ]
        table = ar._build_repair_history_table(None, commits, len(commits))
        merge_lines = [
            line for line in table.splitlines() if "Merge from main" in line
        ]
        assert len(merge_lines) == 2
        for line in merge_lines:
            assert "[policy-artifact]" in line

    def test_policy_artifact_footnote_emitted_when_merge_row_present(
        self,
    ) -> None:
        table = ar._build_repair_history_table(
            None, ["Merge branch 'main' into feature"], 1
        )
        assert "[policy-artifact] rows are forced by the squash" in table
        assert ".github/rulesets/main.json" in table
        assert "CLAUDE.md section 3" in table

    def test_no_marker_or_footnote_when_no_synthetic_rows(self) -> None:
        """Marker and footnote stay out when no squash/linear-history
        artifact row fires (no merge-from-main, no iteration commit, no
        canonical fix, no multi-commit summary). Refs #453."""
        commits = ["feat(harness): unrelated", "feat(harness): another"]
        # pr_commit_count=1 keeps the Multi-commit PR synthetic row out.
        table = ar._build_repair_history_table(None, commits, 1)
        assert "[policy-artifact]" not in table
        assert "rows are forced by the squash" not in table

    def test_no_footnote_on_sentinel_row(self) -> None:
        table = ar._build_repair_history_table(None, ["feat(harness): plain"], 1)
        assert "(no automated repair signals detected)" in table
        assert "[policy-artifact]" not in table

    def test_fix_commit_row_carries_policy_artifact_marker(self) -> None:
        """Refs #453: synthetic Fix commit row must carry the marker."""
        commits = ["fix(harness): canonical repair"]
        table = ar._build_repair_history_table(
            None, commits, len(commits), pr_type="fix"
        )
        fix_lines = [
            line for line in table.splitlines() if "| Fix commit |" in line
        ]
        assert len(fix_lines) == 1
        assert "[policy-artifact]" in fix_lines[0]

    def test_iteration_commit_row_carries_policy_artifact_marker(self) -> None:
        """Refs #453: synthetic Iteration commit row must carry the marker."""
        commits = ["fixup! earlier change"]
        table = ar._build_repair_history_table(None, commits, len(commits))
        iter_lines = [
            line
            for line in table.splitlines()
            if "| Iteration commit |" in line
        ]
        assert len(iter_lines) == 1
        assert "[policy-artifact]" in iter_lines[0]

    def test_multi_commit_row_carries_policy_artifact_marker(self) -> None:
        """Refs #453: synthetic Multi-commit PR row must carry the marker."""
        table = ar._build_repair_history_table(
            None, ["feat: a", "feat: b"], 3
        )
        multi_lines = [
            line for line in table.splitlines() if "| Multi-commit PR |" in line
        ]
        assert len(multi_lines) == 1
        assert "[policy-artifact]" in multi_lines[0]

    def test_revert_row_carries_policy_artifact_marker(self) -> None:
        """Refs #1287: synthetic Revert commit row carries the marker and
        prompts co-fire correlation."""
        table = ar._build_repair_history_table(
            None, ['Revert "feat: x"'], 1
        )
        revert_lines = [
            line for line in table.splitlines() if "| Revert commit |" in line
        ]
        assert len(revert_lines) == 1
        assert "[policy-artifact]" in revert_lines[0]
        assert "co-firing" in revert_lines[0]

    def test_policy_artifact_footnote_for_synthetic_rows_without_merge(
        self,
    ) -> None:
        """Footnote fires even when only synthetic rows (no Merge from
        main) are present. Refs #453."""
        # Iteration commit alone with single PR commit; no merge row,
        # no multi-commit row, but the synthetic Iteration row exists.
        table = ar._build_repair_history_table(None, ["fixup! prior"], 1)
        assert "Iteration commit" in table
        assert "Merge from main" not in table
        assert "[policy-artifact] rows are forced by the squash" in table

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
        assert "positive-control" in table
        assert "repair taxonomy classification requested" in table
        # No numbered rows: only the "|; |" sentinel.
        assert "| 1 |" not in table

    def test_sentinel_absent_when_any_signal_fires(self) -> None:
        table = ar._build_repair_history_table(None, ["fix(x): a"], 1)
        assert "(no automated repair signals detected)" not in table

    def test_pipe_in_commit_subject_is_escaped(self) -> None:
        """A '|' in a commit subject must be backslash-escaped so the
        table structure stays a 4-column grid."""
        table = ar._build_repair_history_table(
            None, ["fix(x): rename a|b to c"], 1
        )
        # The escaped pipe must appear, AND the rendered row line must
        # contain exactly 5 unescaped '|' characters (the 4 column
        # delimiters plus opening/closing).
        assert "a\\|b" in table
        row_line = next(
            line for line in table.splitlines() if "Iteration commit" in line
        )
        unescaped_pipes = row_line.replace("\\|", "")
        assert unescaped_pipes.count("|") == 5

    def test_table_uses_canonical_header(self) -> None:
        table = ar._build_repair_history_table(None, [], 1)
        first_line = table.splitlines()[0]
        assert first_line == "| # | Repair | Cause | Next action |"

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


class TestRepairHistoryTableCheckRunContext:
    """Failed check_run rows must carry html_url + annotation summary.

    Acceptance criterion 1 + 2 of issue #381: an operator must be able to
    reconstruct a CI failure from the retro body alone after Actions log
    retention expires, and the body must stay within GitHub's 65,536-char
    limit even with a CI fanout.
    """

    def test_html_url_appears_in_row(self) -> None:
        check_runs = [
            {
                "name": "gate",
                "conclusion": "failure",
                "completed_at": "2026-05-25T03:48:28Z",
                "html_url": "https://github.com/o/r/runs/77653399942",
                "_annotation_summary": None,
            }
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        assert "logs: https://github.com/o/r/runs/77653399942" in table

    def test_annotation_summary_appears_in_row(self) -> None:
        check_runs = [
            {
                "name": "gate",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "https://example/run/1",
                "_annotation_summary": "Process failed: exit code 1",
            }
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        assert "annotation: Process failed: exit code 1" in table

    def test_omits_annotation_section_when_summary_is_none(self) -> None:
        """Acceptance criterion 3: annotation-less rows still emit the base
        conclusion / completed_at signal; no `annotation:` token."""
        check_runs = [
            {
                "name": "gate",
                "conclusion": "failure",
                "completed_at": "2026-05-25T03:48:28Z",
                "html_url": "https://example/run/1",
                "_annotation_summary": None,
            }
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        assert "conclusion=failure at 2026-05-25T03:48:28Z" in table
        assert "annotation:" not in table

    def test_omits_logs_section_when_html_url_missing(self) -> None:
        """Missing html_url -> no `logs:` token (back-compat for legacy
        check_run shapes that may lack the field)."""
        check_runs = [
            {
                "name": "gate",
                "conclusion": "failure",
                "completed_at": "t",
                "_annotation_summary": "summary text",
            }
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        assert "logs:" not in table
        assert "annotation: summary text" in table

    def test_overflow_row_emitted_when_more_than_cap_failed(self) -> None:
        """Body-size defence: more than _CHECK_RUN_DISPLAY_CAP failed runs
        collapse to the cap + one overflow row."""
        cap = ar._CHECK_RUN_DISPLAY_CAP
        check_runs = [
            {
                "name": f"job-{i}",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": f"https://example/{i}",
                "_annotation_summary": None,
            }
            for i in range(cap + 3)
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        # cap rows of detail + 1 overflow row.
        assert table.count("| CI fail: job-") == cap
        assert "CI fail: + 3 more failures" in table
        assert "see PR check-run list (truncated)" in table

    def test_overflow_row_absent_when_at_or_below_cap(self) -> None:
        cap = ar._CHECK_RUN_DISPLAY_CAP
        check_runs = [
            {
                "name": f"job-{i}",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": f"https://example/{i}",
                "_annotation_summary": None,
            }
            for i in range(cap)
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        assert "more failures" not in table

    def test_row_columns_remain_four_when_url_present(self) -> None:
        """Defence: html_url must be safe inside one markdown-table cell
        (the URL contains no pipes, but _escape_table_cell is still in the
        path; this test guards against a future refactor that bypasses it)."""
        check_runs = [
            {
                "name": "gate",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "https://example/run/1?x=a|b",
                "_annotation_summary": "msg|with|pipes",
            }
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        row_line = next(
            line for line in table.splitlines() if "CI fail: gate" in line
        )
        # 5 unescaped '|' delimiters keep the row a 4-column grid even
        # when the URL/summary contain literal pipes.
        unescaped = row_line.replace("\\|", "")
        assert unescaped.count("|") == 5


class TestBuildRetroBodyMarkers:
    """build_retro_body's marker contract for issue #343."""

    def test_auto_filled_markers_present(self) -> None:
        body = ar.build_retro_body(_make_pr(), [])
        assert body.count("<!-- auto-filled:repair-history -->") == 1
        assert body.count("<!-- /auto-filled:repair-history -->") == 1

    def test_operator_fill_markers_absent_for_positive_control(self) -> None:
        body = ar.build_retro_body(_make_pr(), [])
        assert "<!-- operator-fill:remaining-steps -->" not in body
        assert "<!-- /operator-fill:remaining-steps -->" not in body
        assert "Positive-control outcome" in body
        assert "no repair taxonomy classification is requested" in body

    def test_operator_fill_markers_present_when_repair_rows_exist(self) -> None:
        body = ar.build_retro_body(_make_pr(), ["fix(x): repair"])
        assert body.count("<!-- operator-fill:remaining-steps -->") == 1
        assert body.count("<!-- /operator-fill:remaining-steps -->") == 1

    def test_marker_pairs_are_well_nested(self) -> None:
        body = ar.build_retro_body(_make_pr(), ["fix(x): repair"])
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
            "| # | Repair | Cause | Next action |"
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
            {"number": 11, "title": "fix(auto-retro): review PR #42 repair loops"},
        ]
        assert ar.find_existing_retro(items, 42) == 11

    def test_no_match_returns_none(self) -> None:
        items = [{"number": 1, "title": "fix(auto-retro): review PR #99 repair loops"}]
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
                "title": "fix(auto-retro): review PR #42 repair loops",
                "state": "closed",
            }
        ]
        assert ar.find_existing_retro(items, 42) == 7

    def test_rejects_legacy_retro_prefix(self) -> None:
        """Legacy ``retro(`` / ``retro:`` titles are migrated to
        fix(auto-retro); the new-only detection must not match them."""
        items = [
            {"number": 3, "title": "retro: review PR #42 repair loops"},
            {"number": 4, "title": "retro(fix): review PR #42 repair loops"},
        ]
        assert ar.find_existing_retro(items, 42) is None

    def test_rejects_pr_number_substring_collision(self) -> None:
        """A retro for #2490 must not be returned when looking up #249."""
        items = [
            {"number": 8, "title": "fix(auto-retro): review PR #2490 repair loops"}
        ]
        assert ar.find_existing_retro(items, 249) is None

    def test_matches_case_insensitive_prefix(self) -> None:
        """``Fix(Auto-Retro):`` (mixed case) must still match; prefix is lowered."""
        items = [
            {"number": 12, "title": "Fix(Auto-Retro): review PR #42 repair loops"}
        ]
        assert ar.find_existing_retro(items, 42) == 12

    def test_matches_new_chore_prefix(self) -> None:
        """New auto-retros use the chore(auto-retro) prefix (Refs #1069)."""
        items = [
            {"number": 13, "title": "chore(auto-retro): review PR #42 repair loops"}
        ]
        assert ar.find_existing_retro(items, 42) == 13

    def test_matches_hand_authored_chore_retro_scope(self) -> None:
        """A hand-authored ``chore(retro): ... PR #N`` retro must dedup against
        the auto path so the post-merge run does not open a second retro for the
        same PR. Regression for the confirmed #1939/#1941 duplicate (PR #1933).
        Refs #1995."""
        items = [
            {
                "number": 1941,
                "title": "chore(retro): post-merge retrospective for PR #1933",
            }
        ]
        assert ar.find_existing_retro(items, 1933) == 1941

    def test_matches_hand_authored_retro_scope_any_type(self) -> None:
        """The scope, not the type, marks the retro family: ``docs(retro)`` and
        ``fix(retro)`` per-PR retros also dedup. Refs #1995."""
        items = [
            {"number": 21, "title": "docs(retro): repairs for PR #42"},
            {"number": 22, "title": "fix(retro): follow-ups from PR #43 merge"},
        ]
        assert ar.find_existing_retro(items, 42) == 21
        assert ar.find_existing_retro(items, 43) == 22

    def test_ignores_retro_suffixed_non_retro_scopes(self) -> None:
        """``retro-visibility`` (gate escape hatch) and ``retro-dedup`` (issue
        #1995's own scope) are NON-retro tracking issues; they must NOT be
        treated as a per-PR retro or dedup would suppress a legitimate issue.
        Refs #1995."""
        items = [
            {"number": 31, "title": "chore(retro-visibility): tracking for PR #42"},
            {"number": 32, "title": "fix(retro-dedup): unify dedup for PR #42"},
        ]
        assert ar.find_existing_retro(items, 42) is None

    def test_ignores_noncanonical_auto_retro_scopes(self) -> None:
        """``feat(auto-retro)`` / ``docs(auto-retro)`` are NOT retro issues
        (is_retro_issue_title rejects them by design). The per-PR dedup
        predicate must not widen all ``(auto-retro)`` scopes, or dedup would
        skip opening the real retro. Regression for the Codex P2 on PR #1998."""
        items = [
            {"number": 41, "title": "feat(auto-retro): something for PR #42"},
            {"number": 42, "title": "docs(auto-retro): record outcome PR #42"},
        ]
        assert ar.find_existing_retro(items, 42) is None


class TestIsRetroIssueTitle:
    @pytest.mark.parametrize(
        "title",
        [
            "chore(auto-retro): review PR #42 repair loops",
            "fix(auto-retro): review PR #42 repair loops",
            "Chore(Auto-Retro): review PR #42 repair loops",
            "  chore(auto-retro): leading whitespace",
        ],
    )
    def test_matches_current_and_legacy_prefix(self, title: str) -> None:
        """Both the new chore prefix and the legacy fix prefix are
        recognized so dedup and the gate keep covering unrenamed closed
        retros (Refs #1069)."""
        assert ar.is_retro_issue_title(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "retro: review PR #42 repair loops",
            "retro(fix): review PR #42 repair loops",
            "feat(auto-retro): not a retro issue shape",
            "docs(auto-retro): record repair-free merge",
            "feat: unrelated",
            "",
        ],
    )
    def test_rejects_non_retro_titles(self, title: str) -> None:
        assert ar.is_retro_issue_title(title) is False


class TestIsPerPrRetroTitle:
    """The dedup-only retro-family predicate (Refs #1995)."""

    @pytest.mark.parametrize(
        "title",
        [
            "chore(retro): post-merge retrospective for PR #1933",
            "docs(retro): repairs for PR #42",
            "Chore(Retro): mixed case PR #42",
            "  chore(retro): leading whitespace PR #42",
        ],
    )
    def test_matches_retro_scope_only(self, title: str) -> None:
        assert ar.is_per_pr_retro_title(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            # auto-retro scopes are covered by is_retro_issue_title, NOT here;
            # widening to all (auto-retro) would dedup non-retro feat/docs
            # (auto-retro) issues. Refs #1998 (Codex P2).
            "chore(auto-retro): review PR #42 repair loops",
            "fix(auto-retro): close retro #42",
            "feat(auto-retro): not a retro issue shape",
            "docs(auto-retro): record repair-free merge",
            # suffixed scopes are NON-retro tracking issues
            "chore(retro-visibility): tracking issue",
            "fix(retro-dedup): unify dedup",
            # legacy no-type / type-as-retro shapes stay excluded
            "retro: review PR #42 repair loops",
            "retro(fix): review PR #42 repair loops",
            # unrelated, and the no-scope / empty cases
            "feat: unrelated",
            "chore: no scope at all",
            "",
        ],
    )
    def test_rejects_non_retro_scope(self, title: str) -> None:
        assert ar.is_per_pr_retro_title(title) is False

    def test_does_not_widen_is_retro_issue_title(self) -> None:
        """The new predicate must not leak into is_retro_issue_title, which
        stays auto-retro-only for the no-direct-PR gate / sentinel / label
        prior. A chore(retro) title is a per-PR retro for dedup but NOT a
        reserved auto-retro issue title."""
        title = "chore(retro): post-merge retrospective for PR #1933"
        assert ar.is_per_pr_retro_title(title) is True
        assert ar.is_retro_issue_title(title) is False


class TestRetroDedupAutoRetroInvariant:
    """Property guard (Refs #1999 row 1): no predicate ORed into
    ``find_existing_retro`` may dedup an ``(auto-retro)``-scoped title that
    ``is_retro_issue_title`` rejects.

    The Codex P2 on PR #1998 had ``is_per_pr_retro_title`` match every
    ``(auto-retro)`` scope (``endswith("(auto-retro)")``), so a non-retro
    ``feat/docs(auto-retro)`` issue would dedup and suppress opening the real
    retro. The example regression is ``test_ignores_noncanonical_auto_retro_scopes``;
    these properties generalize it across the whole Conventional-Commit type
    space so any future predicate that re-widens the auto-retro family is
    caught, not just the two shapes the example pins.
    """

    # A Conventional-Commit type token: lowercase, may carry hyphens, bounded
    # length. Covers chore/fix (the canonical retro types) and every other
    # type (feat/docs/perf/build/...) that must NOT dedup under an auto-retro
    # scope.
    _CC_TYPE = st.from_regex(r"[a-z][a-z0-9-]{0,12}", fullmatch=True)

    @given(cc_type=_CC_TYPE)
    def test_auto_retro_scope_deduped_iff_is_retro_issue_title(
        self, cc_type: str
    ) -> None:
        """find_existing_retro dedups an ``<type>(auto-retro): ... PR #N`` title
        if and only if ``is_retro_issue_title`` accepts it. The ORed per-PR
        predicate must add nothing for the auto-retro scope family."""
        title = f"{cc_type}(auto-retro): review PR #42 repair loops"
        items = [{"number": 7, "title": title}]
        deduped = ar.find_existing_retro(items, 42) is not None
        assert deduped is ar.is_retro_issue_title(title)

    @given(cc_type=_CC_TYPE)
    def test_per_pr_predicate_never_accepts_auto_retro_scope(
        self, cc_type: str
    ) -> None:
        """The dedup-only predicate must never accept an ``(auto-retro)`` scope;
        those titles are governed by ``is_retro_issue_title`` (type-filtered to
        chore/fix), not by the per-PR predicate."""
        title = f"{cc_type}(auto-retro): review PR #42"
        assert ar.is_per_pr_retro_title(title) is False


class TestIssueLabels:
    # issue_labels is the pure renderer: it starts from the caller-injected
    # base (identity) labels and merges the inherited layer labels. The base is
    # passed explicitly here (not read from the registry) so these tests stay
    # self-contained; the IO layer's registry wiring is covered separately.
    _BASE: ClassVar[list[str]] = ["type:docs", "layer:meta"]

    def test_no_inherited_labels(self) -> None:
        assert ar.issue_labels((), self._BASE) == ["type:docs", "layer:meta"]

    def test_dedupes_layer_meta(self) -> None:
        out = ar.issue_labels(("layer:meta",), self._BASE)
        assert out == ["type:docs", "layer:meta"]

    def test_appends_extra_layer_labels(self) -> None:
        out = ar.issue_labels(("layer:p3-harness", "layer:meta"), self._BASE)
        assert out == ["type:docs", "layer:meta", "layer:p3-harness"]

    def test_filters_empty_names(self) -> None:
        out = ar.issue_labels(("", "layer:p4-safety-boundary"), self._BASE)
        assert out == ["type:docs", "layer:meta", "layer:p4-safety-boundary"]

    def test_base_labels_are_injected_not_hardcoded(self) -> None:
        # The base labels come from the caller, not a literal inside the pure
        # renderer: a synthetic base flows straight through, deduped/ordered.
        out = ar.issue_labels(("layer:x",), ["id:a", "id:b"])
        assert out == ["id:a", "id:b", "layer:x"]


# ---------------------------------------------------------------------------
# gh_api (REST boundary)
# ---------------------------------------------------------------------------


class TestGhApi:
    def test_delegates_to_rest_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[Any, ...]] = []

        def fake_rest_text(method, path, payload=None):
            calls.append((method, path, payload))
            return "OK"

        monkeypatch.setattr(ar, "rest_text", fake_rest_text)
        assert ar.gh_api("GET", "/repos/o/r/issues") == "OK"
        assert calls[0] == ("GET", "/repos/o/r/issues", None)
        assert ar.gh_api("POST", "/repos/o/r/issues", {"title": "T"}) == "OK"
        assert calls[1] == ("POST", "/repos/o/r/issues", {"title": "T"})


# ---------------------------------------------------------------------------
# search_retro_issues / has_review_comments / fetch_pr_commits / create_issue
# (API wrappers)
# ---------------------------------------------------------------------------


class TestSearchRetroIssues:
    def test_passes_url_encoded_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple[str, str, Any]] = []

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
                {"items": [{"number": 1, "title": "fix(auto-retro): review PR #42 ..."}]}
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
        seen: list[tuple[str, str, Any]] = []

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
        merge_commit_sha: str | None = None,
        check_runs: list[dict[str, Any]] | None = None,
        sha_sequence: list[str | None] | None = None,
    ) -> list[tuple[str, str]]:
        seen: list[tuple[str, str]] = []
        # Index lives in a single-element list so the closure can mutate
        # it without needing nonlocal; matches the in-tree pattern for
        # hand-rolled counters in _orchestrator_recorder.
        idx = [0]

        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            seen.append((method, path))
            if "/check-runs" in path:
                return json.dumps({"check_runs": check_runs or []})
            # First call (and any retry): pull request detail.
            if sha_sequence is not None:
                i = idx[0]
                idx[0] = i + 1
                sha = sha_sequence[i] if i < len(sha_sequence) else None
                return json.dumps({"merge_commit_sha": sha})
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
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """All-null SHA path: retries N times, sleeps with backoff,
        emits a ``::warning::`` line, and returns ``[]`` without ever
        calling the check-runs endpoint. Refs issue #380.
        """
        attempts = ar._MERGE_SHA_RETRY_ATTEMPTS
        backoff = list(ar._MERGE_SHA_RETRY_BACKOFF)
        sleeps: list[float] = []
        seen = self._staged_api(
            monkeypatch,
            sha_sequence=[None] * attempts,
            check_runs=None,
        )
        result = ar.fetch_check_runs(
            "o/r", 42, sleeper=sleeps.append
        )
        assert result == []
        # PR-detail call fires exactly `attempts` times; check-runs
        # endpoint must never be hit when SHA stays null.
        assert len(seen) == attempts
        assert all(
            path == "/repos/o/r/pulls/42" for _, path in seen
        )
        assert sleeps == backoff
        err = capsys.readouterr().err
        assert "::warning::" in err
        assert "merge_commit_sha still null" in err
        assert "issue #380" in err

    def test_sha_resolves_on_second_attempt(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """First PR-detail returns null, second resolves to a SHA.
        Sleeper fires once with the first backoff value; check-runs
        endpoint is hit exactly once against the resolved SHA; no
        warning emitted. Refs issue #380.
        """
        sleeps: list[float] = []
        seen = self._staged_api(
            monkeypatch,
            sha_sequence=[None, "abc123"],
            check_runs=[{"name": "gate", "conclusion": "failure"}],
        )
        result = ar.fetch_check_runs(
            "o/r", 42, sleeper=sleeps.append
        )
        names = [r["name"] for r in result]
        assert names == ["gate"]
        # Two PR-detail calls plus one check-runs call.
        assert seen[0] == ("GET", "/repos/o/r/pulls/42")
        assert seen[1] == ("GET", "/repos/o/r/pulls/42")
        assert seen[2] == (
            "GET",
            "/repos/o/r/commits/abc123/check-runs?per_page=100",
        )
        assert sleeps == [ar._MERGE_SHA_RETRY_BACKOFF[0]]
        assert "::warning::" not in capsys.readouterr().err

    def test_sha_resolves_on_final_attempt(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Null on every attempt except the final one. Full backoff
        sequence is consumed and the check-runs endpoint is still hit.
        Refs issue #380.
        """
        attempts = ar._MERGE_SHA_RETRY_ATTEMPTS
        backoff = list(ar._MERGE_SHA_RETRY_BACKOFF)
        sleeps: list[float] = []
        sha_sequence: list[str | None] = [None] * (attempts - 1) + [
            "deadbeef"
        ]
        seen = self._staged_api(
            monkeypatch,
            sha_sequence=sha_sequence,
            check_runs=[{"name": "gate", "conclusion": "failure"}],
        )
        result = ar.fetch_check_runs(
            "o/r", 42, sleeper=sleeps.append
        )
        names = [r["name"] for r in result]
        assert names == ["gate"]
        # `attempts` PR-detail calls + one check-runs call.
        pr_detail_calls = [
            path for _, path in seen if "/pulls/" in path
        ]
        assert len(pr_detail_calls) == attempts
        check_runs_calls = [
            path for _, path in seen if "/check-runs" in path
        ]
        assert check_runs_calls == [
            "/repos/o/r/commits/deadbeef/check-runs?per_page=100"
        ]
        assert sleeps == backoff
        assert "::warning::" not in capsys.readouterr().err

    def test_all_attempts_null_emits_warning_and_returns_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Exhaustion path duplicates the short-circuit test from the
        warning-emission angle: stderr names the issue ref and the
        check-runs endpoint stays untouched. Refs issue #380.
        """
        attempts = ar._MERGE_SHA_RETRY_ATTEMPTS
        sleeps: list[float] = []
        seen = self._staged_api(
            monkeypatch,
            sha_sequence=[None] * attempts,
            check_runs=[{"name": "gate", "conclusion": "failure"}],
        )
        result = ar.fetch_check_runs(
            "o/r", 42, sleeper=sleeps.append
        )
        assert result == []
        assert not any("/check-runs" in path for _, path in seen)
        assert len(sleeps) == attempts - 1
        err = capsys.readouterr().err
        assert "issue #380" in err
        assert f"{attempts} attempts" in err

    def test_empty_pr_response_short_circuits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty body from the PR detail endpoint -> no SHA. Treated
        identically to a null SHA: the retry loop runs to exhaustion
        before soft-failing to ``[]``. Refs issue #380.
        """
        seen: list[tuple[str, str]] = []

        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            seen.append((method, path))
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        sleeps: list[float] = []
        assert ar.fetch_check_runs("o/r", 42, sleeper=sleeps.append) == []
        assert len(seen) == ar._MERGE_SHA_RETRY_ATTEMPTS
        assert not any("/check-runs" in path for _, path in seen)

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


class TestFetchCheckRunsAnnotationEnrichment:
    """fetch_check_runs attaches _annotation_summary to each failed run.

    Refs issue #381. Three behaviours are pinned here:

    * happy path: failure-level annotation summary populates the field
    * notice / warning entries skipped in favour of the first failure
    * annotation API error -> _annotation_summary is None, no exception
    """

    def _stage(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        check_runs: list[dict[str, Any]],
        annotations_by_id: Mapping[int, list[dict[str, Any]] | str],
        raise_for_ids: tuple[int, ...] = (),
    ) -> list[tuple[str, str]]:
        """Stage the three-step API: PR detail -> check-runs -> annotations.

        ``annotations_by_id`` maps each ``check_run.id`` to a list of
        annotation dicts (returned as JSON) or to the raw string the
        ``gh_api`` mock should return verbatim (lets a test exercise the
        ``raw == ""`` / non-list branches of ``fetch_check_run_annotations``).

        ``raise_for_ids`` lists check_run ids that should make the
        annotation lookup raise :class:`_github_api.GitHubApiError`.
        """
        seen: list[tuple[str, str]] = []

        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            seen.append((method, path))
            if "/annotations" in path:
                # /repos/{repo}/check-runs/{id}/annotations?...
                rest = path.split("/check-runs/", 1)[1]
                id_str = rest.split("/annotations", 1)[0]
                run_id = int(id_str)
                if run_id in raise_for_ids:
                    raise GitHubApiError(500, "GET", "/x", "HTTP 502")
                payload = annotations_by_id.get(run_id, [])
                if isinstance(payload, str):
                    return payload
                return json.dumps(payload)
            if "/check-runs" in path:
                return json.dumps({"check_runs": check_runs})
            return json.dumps({"merge_commit_sha": "abc123"})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        return seen

    def test_failure_annotation_summary_populates_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        check_runs = [
            {
                "id": 111,
                "name": "gate",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "https://example/run/111",
            }
        ]
        annotations_by_id = {
            111: [
                {
                    "annotation_level": "failure",
                    "title": "Process failed",
                    "message": "exit code 1\nfull log truncated",
                }
            ]
        }
        self._stage(
            monkeypatch,
            check_runs=check_runs,
            annotations_by_id=annotations_by_id,
        )
        out = ar.fetch_check_runs("o/r", 42)
        assert len(out) == 1
        assert out[0]["_annotation_summary"] == "Process failed: exit code 1"

    def test_notice_level_annotation_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Notice / warning levels are not repair signals; the first
        failure-level entry wins."""
        check_runs = [
            {
                "id": 222,
                "name": "gate",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "u",
            }
        ]
        annotations_by_id = {
            222: [
                {
                    "annotation_level": "notice",
                    "title": "Deprecation",
                    "message": "ignore me",
                },
                {
                    "annotation_level": "warning",
                    "title": "Style",
                    "message": "also ignored",
                },
                {
                    "annotation_level": "failure",
                    "title": "Real failure",
                    "message": "this is the cause",
                },
            ]
        }
        self._stage(
            monkeypatch,
            check_runs=check_runs,
            annotations_by_id=annotations_by_id,
        )
        out = ar.fetch_check_runs("o/r", 42)
        assert out[0]["_annotation_summary"] == "Real failure: this is the cause"

    def test_annotation_fetch_error_degrades_gracefully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance criterion 3 of issue #381: a transient annotation API
        error must not break the retro; the row falls back to
        summary-less and other runs still get their summaries."""
        check_runs = [
            {
                "id": 333,
                "name": "broken",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "u",
            },
            {
                "id": 444,
                "name": "ok",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "u",
            },
        ]
        annotations_by_id = {
            444: [
                {
                    "annotation_level": "failure",
                    "title": "Other",
                    "message": "still here",
                }
            ]
        }
        self._stage(
            monkeypatch,
            check_runs=check_runs,
            annotations_by_id=annotations_by_id,
            raise_for_ids=(333,),
        )
        out = ar.fetch_check_runs("o/r", 42)
        assert len(out) == 2
        # First run degrades to None; second run still picks up the summary.
        by_id = {entry["id"]: entry for entry in out}
        assert by_id[333]["_annotation_summary"] is None
        assert by_id[444]["_annotation_summary"] == "Other: still here"

    def test_no_failure_level_entry_yields_none_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A check_run with zero failure-level annotations (e.g. timeout)
        gets _annotation_summary=None and the row stays summary-less."""
        check_runs = [
            {
                "id": 555,
                "name": "timeout",
                "conclusion": "timed_out",
                "completed_at": "t",
                "html_url": "u",
            }
        ]
        # Only notice-level entries.
        annotations_by_id: dict[int, list[dict[str, Any]] | str] = {
            555: [
                {
                    "annotation_level": "notice",
                    "title": "Deprecation",
                    "message": "ignore",
                }
            ]
        }
        self._stage(
            monkeypatch,
            check_runs=check_runs,
            annotations_by_id=annotations_by_id,
        )
        out = ar.fetch_check_runs("o/r", 42)
        assert out[0]["_annotation_summary"] is None

    def test_missing_id_skips_annotation_fetch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defensive: a check_run without an integer id (legacy / partial
        payload) must not crash; the row gets _annotation_summary=None."""
        check_runs = [
            {
                "name": "no-id-run",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "u",
            }
        ]
        seen = self._stage(
            monkeypatch,
            check_runs=check_runs,
            annotations_by_id={},
        )
        out = ar.fetch_check_runs("o/r", 42)
        assert out[0]["_annotation_summary"] is None
        # No annotation call should have been issued for this run.
        assert not any("/annotations" in path for _, path in seen)

    def test_long_annotation_is_truncated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Body-size defence: a long annotation message is truncated to
        :data:`_ANNOTATION_SUMMARY_MAX` chars with an ASCII ellipsis."""
        long_msg = "x" * 1000
        check_runs = [
            {
                "id": 666,
                "name": "verbose",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "u",
            }
        ]
        annotations_by_id = {
            666: [
                {
                    "annotation_level": "failure",
                    "title": "T",
                    "message": long_msg,
                }
            ]
        }
        self._stage(
            monkeypatch,
            check_runs=check_runs,
            annotations_by_id=annotations_by_id,
        )
        out = ar.fetch_check_runs("o/r", 42)
        summary = out[0]["_annotation_summary"]
        assert isinstance(summary, str)
        assert len(summary) == ar._ANNOTATION_SUMMARY_MAX
        assert summary.endswith("...")

    def test_enrichment_capped_to_display_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Annotation fetch is only attempted for the first
        :data:`_CHECK_RUN_DISPLAY_CAP` failed runs (rate-limit defence).
        Beyond the cap, _annotation_summary stays None."""
        cap = ar._CHECK_RUN_DISPLAY_CAP
        check_runs = [
            {
                "id": 1000 + i,
                "name": f"job-{i}",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "u",
            }
            for i in range(cap + 3)
        ]
        annotations_by_id: dict[int, list[dict[str, Any]] | str] = {
            1000 + i: [
                {
                    "annotation_level": "failure",
                    "title": f"T{i}",
                    "message": f"m{i}",
                }
            ]
            for i in range(cap + 3)
        }
        seen = self._stage(
            monkeypatch,
            check_runs=check_runs,
            annotations_by_id=annotations_by_id,
        )
        out = ar.fetch_check_runs("o/r", 42)
        # First cap runs enriched, remainder are None.
        for i in range(cap):
            assert out[i]["_annotation_summary"] == f"T{i}: m{i}"
        for i in range(cap, cap + 3):
            assert out[i]["_annotation_summary"] is None
        # Exactly cap annotation calls were issued.
        annotation_calls = [path for _, path in seen if "/annotations" in path]
        assert len(annotation_calls) == cap

    def test_empty_annotations_response_yields_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Blank body from the annotations endpoint -> []
        -> _annotation_summary=None (no crash)."""
        check_runs = [
            {
                "id": 777,
                "name": "x",
                "conclusion": "failure",
                "completed_at": "t",
                "html_url": "u",
            }
        ]
        self._stage(
            monkeypatch,
            check_runs=check_runs,
            annotations_by_id={777: ""},
        )
        out = ar.fetch_check_runs("o/r", 42)
        assert out[0]["_annotation_summary"] is None


class TestFetchCheckRunAnnotations:
    """Thin gh_api wrapper. Refs issue #381."""

    def test_returns_parsed_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = [{"annotation_level": "failure", "title": "T", "message": "m"}]

        def fake_api(method: str, path: str, body: Any = None, **_kw: Any) -> str:
            assert (
                path
                == "/repos/o/r/check-runs/123/annotations?per_page=5"
            )
            return json.dumps(payload)

        monkeypatch.setattr(ar, "gh_api", fake_api)
        assert ar.fetch_check_run_annotations("o/r", 123, limit=5) == payload

    def test_empty_body_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "")
        assert ar.fetch_check_run_annotations("o/r", 1) == []

    def test_non_list_payload_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pathological non-list payload must not raise (e.g. an API
        proxy that wraps the response). Caller still gets [] and the
        repair row degrades to summary-less."""
        monkeypatch.setattr(
            ar, "gh_api", lambda *_a, **_kw: json.dumps({"unexpected": True})
        )
        assert ar.fetch_check_run_annotations("o/r", 1) == []


class TestCreateIssue:
    def test_posts_title_body_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple[str, str, Any]] = []

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
        seen: list[tuple[str, str, Any]] = []

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
        seen: list[tuple[str, str, Any]] = []

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
        seen: list[tuple[str, str, Any]] = []

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
        """gh_api raises GitHubApiError; post_back_link_comment must
        propagate so the orchestrator can decide its fail-soft policy."""
        def fake_api(method, path, body=None, **_kw):
            if method == "GET":
                return json.dumps([])
            raise GitHubApiError(500, "GET", "/x", "boom")

        monkeypatch.setattr(ar, "gh_api", fake_api)
        with pytest.raises(GitHubApiError):
            ar.post_back_link_comment("o/r", 42, 99)


# ---------------------------------------------------------------------------
# apply_terminal_label
# ---------------------------------------------------------------------------


class TestApplyTerminalLabel:
    def test_posts_terminal_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple[str, str, Any]] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        ar.apply_terminal_label("o/r", 42)
        assert seen == [
            (
                "POST",
                "/repos/o/r/issues/42/labels",
                {"labels": [_TERMINAL_PRIMARY]},
            )
        ]

    def test_terminal_label_derived_from_registry_not_hardcoded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The primary/legacy labels come from _ssot.consumer_labels, not a
        hardcoded literal: a synthetic registry set is POSTed verbatim."""
        seen: list[tuple[str, str, Any]] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            return ""

        monkeypatch.setattr(
            ar._ssot,
            "consumer_labels",
            lambda path: (
                "id:a",
                "id:b",
                "ops:test-retro-opened",
                "harness:test-retro-opened",
            ),
        )
        monkeypatch.setattr(ar, "gh_api", fake_api)
        ar.apply_terminal_label("o/r", 42)
        assert seen == [
            (
                "POST",
                "/repos/o/r/issues/42/labels",
                {"labels": ["ops:test-retro-opened"]},
            )
        ]

    def test_loud_failure_on_post_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gh_api raises GitHubApiError; apply_terminal_label must
        propagate so the orchestrator can decide its fail-soft policy."""
        def fake_api(method, path, body=None, **_kw):
            raise GitHubApiError(500, "GET", "/x", "boom")

        monkeypatch.setattr(ar, "gh_api", fake_api)
        with pytest.raises(GitHubApiError):
            ar.apply_terminal_label("o/r", 42)

    def test_falls_back_to_legacy_label_on_422(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Migration window (#2139): the new label may not exist yet (HTTP
        422). apply_terminal_label retries once with the legacy name so the
        terminal signal survives regardless of code-merge vs. live-rename
        ordering."""
        seen: list[tuple[str, str, Any]] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if body == {"labels": [_TERMINAL_PRIMARY]}:
                raise GitHubApiError(422, "POST", path, "label does not exist")
            return ""

        monkeypatch.setattr(ar, "gh_api", fake_api)
        ar.apply_terminal_label("o/r", 42)
        assert seen == [
            ("POST", "/repos/o/r/issues/42/labels", {"labels": [_TERMINAL_PRIMARY]}),
            ("POST", "/repos/o/r/issues/42/labels", {"labels": [_TERMINAL_LEGACY]}),
        ]

    def test_non_422_does_not_fall_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-422 error is not a missing-label signal; it must propagate
        without a legacy retry so real failures stay loud."""
        calls = 0

        def fake_api(method, path, body=None, **_kw):
            nonlocal calls
            calls += 1
            raise GitHubApiError(500, "POST", path, "boom")

        monkeypatch.setattr(ar, "gh_api", fake_api)
        with pytest.raises(GitHubApiError):
            ar.apply_terminal_label("o/r", 42)
        assert calls == 1

    def test_legacy_retry_failure_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If neither the new nor the legacy label exists (both 422), the
        error propagates to the orchestrator's fail-soft handler."""
        def fake_api(method, path, body=None, **_kw):
            raise GitHubApiError(422, "POST", path, "label does not exist")

        monkeypatch.setattr(ar, "gh_api", fake_api)
        with pytest.raises(GitHubApiError):
            ar.apply_terminal_label("o/r", 42)

    def test_drifted_registry_missing_terminal_labels_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A registry entry that carries only identity labels (no ops:/harness:
        *retro-opened) is schema-valid but must fail loud rather than POST a
        None label."""
        monkeypatch.setattr(
            ar._ssot, "consumer_labels", lambda path: ("type:docs", "layer:meta")
        )
        monkeypatch.setattr(ar, "gh_api", lambda *a, **kw: "")
        with pytest.raises(RuntimeError, match="auto-retro registry labels"):
            ar.apply_terminal_label("o/r", 42)

    def test_drifted_registry_key_error_wrapped_as_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise_key_error(path: str) -> tuple[str, ...]:
            raise KeyError(f"no label_consumers entry for path {path!r}")

        monkeypatch.setattr(ar._ssot, "consumer_labels", _raise_key_error)
        monkeypatch.setattr(ar, "gh_api", lambda *a, **kw: "")
        with pytest.raises(RuntimeError, match="auto-retro registry labels"):
            ar.apply_terminal_label("o/r", 42)


def test_terminal_primary_label_aligned_with_labels_json() -> None:
    """The registry's ``ops:`` terminal label must exist as a ``name`` entry in
    the declarative ``.github/labels.json`` SoT so ``apply-labels.yml``
    reconciles it onto the repository before any merge fires
    ``apply_terminal_label``.

    Reads both SoT files directly (not through the autouse-mocked
    ``ar._ssot``) so it is a genuine cross-registry drift guard: it derives the
    label value from the live registry rather than asserting a hardcoded
    literal.
    """
    repo_root = Path(__file__).resolve().parent.parent
    registry = json.loads(
        (repo_root / ".gitapex" / "ssot.json").read_text(encoding="utf-8")
    )
    entry = next(
        e
        for e in registry["label_consumers"]
        if e.get("path") == "scripts/auto_retro.py"
    )
    primary = next(
        label
        for label in entry["labels"]
        if label.endswith("retro-opened") and label.startswith("ops:")
    )
    labels_sot = json.loads(
        (repo_root / ".github" / "labels.json").read_text(encoding="utf-8")
    )
    assert any(lbl.get("name") == primary for lbl in labels_sot), (
        f"terminal label {primary!r} missing from .github/labels.json"
    )


def test_main_maps_runtime_error_to_error_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """A RuntimeError (e.g. a drifted SSoT registry surfaced by the label
    resolution helpers) routes through main()'s ::error::/exit-1 path rather
    than a raw traceback. GitHubApiError, a RuntimeError subclass, keeps its
    own HTTP-specific arm ahead of this one.
    """
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(_merged_event()), encoding="utf-8")

    def _raise(event: dict[str, Any], repo: str) -> int:
        raise RuntimeError("auto-retro registry labels: boom")

    monkeypatch.setattr(ar, "run", _raise)
    rc = ar.main(["run", "--repo", "o/r", "--event-file", str(event_file)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "::error::" in err
    assert "auto-retro registry labels" in err


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
    pr_detail_sequence: list[dict[str, Any]] | None = None,
    check_runs: list[dict[str, Any]] | None = None,
    check_runs_error: bool = False,
    back_link_comments: list[dict[str, Any]] | None = None,
    back_link_post_error: bool = False,
    terminal_label_post_error: bool = False,
) -> list[tuple[str, str, Any]]:
    """Replace ar.gh_api with a recorder that returns canned data per path.

    Defaults ``review_comments`` to a single non-empty entry so existing
    happy-path tests still reach the issue-creation branch. New tests
    that exercise the zero-review-comments skip pass ``review_comments=[]``.
    Set ``comments_error=True`` to make the comments endpoint raise the
    same ``GitHubApiError`` that gh_api raises in production; used
    to test the fail-safe fallback in run().

    ``pr_detail`` controls the response of ``GET /repos/{repo}/pulls/{n}``
    (used by ``fetch_check_runs`` to read ``merge_commit_sha``); defaults
    to ``{"merge_commit_sha": None}`` so no check-runs lookup fires and
    the Repair history table degrades to commit-subject signals only.
    ``check_runs`` controls the second-call response; ``check_runs_error``
    makes the PR-detail call raise to exercise the fail-soft path.
    """
    seen: list[tuple[str, str, Any]] = []
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
    # Index lives in a single-element list so the closure can mutate it
    # without requiring nonlocal. Refs issue #380: the
    # ``pr_detail_sequence`` knob exercises fetch_check_runs's retry
    # loop end-to-end through the orchestrator.
    pr_detail_idx = [0]

    def fake_api(method, path, body=None, **_kw):
        seen.append((method, path, body))
        if method == "GET" and path.startswith("/search/issues"):
            return json.dumps({"items": existing})
        if method == "GET" and "/pulls/" in path and "/comments" in path:
            if comments_error:
                raise GitHubApiError(500, "GET", "/x", "comments endpoint boom")
            return json.dumps(review_comments)
        if method == "GET" and "/pulls/" in path and "/commits" in path:
            return json.dumps(commits)
        if method == "GET" and "/check-runs" in path:
            return json.dumps({"check_runs": check_runs})
        if method == "GET" and "/pulls/" in path:
            if check_runs_error:
                raise GitHubApiError(500, "GET", "/x", "pulls endpoint boom")
            if pr_detail_sequence is not None:
                i = pr_detail_idx[0]
                pr_detail_idx[0] = i + 1
                if i < len(pr_detail_sequence):
                    return json.dumps(pr_detail_sequence[i])
                return json.dumps(pr_detail_sequence[-1])
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
                raise GitHubApiError(500, "GET", "/x", "back-link post boom")
            return ""
        if (
            method == "POST"
            and "/issues/" in path
            and path.endswith("/labels")
        ):
            if terminal_label_post_error:
                raise GitHubApiError(500, "GET", "/x", "terminal-label post boom")
            return ""
        if method == "PATCH" and "/issues/comments/" in path:
            return ""
        if method == "POST" and path.endswith("/issues"):
            return json.dumps(created_response)
        return ""

    monkeypatch.setattr(ar, "gh_api", fake_api)
    return seen


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
            "fix_typed_title": False,
            "multi_commit_pr": False,
        }

    def test_body_cites_refs_signal_is_retired(self) -> None:
        # Retired as a standalone trigger in #1227: a PR whose only
        # evidence is a Refs line fires no signal.
        out = ar.compute_repair_signals(
            self._pr(body="Refs #287\nRefs #298"), has_inline_comments=False
        )
        assert "body_cites_refs" not in out
        assert not any(out.values())

    def test_post_merge_signal_removed(self) -> None:
        """Per #418, `post_merge_unchecked` is no longer returned at merge time."""
        out = ar.compute_repair_signals(self._pr(), has_inline_comments=False)
        assert "post_merge_unchecked" not in out

    def test_unchecked_post_merge_items_do_not_fire_any_signal(self) -> None:
        """A body with only unchecked Post-merge items must not fire any signal."""
        body = (
            "## Checklist\n\n### Post-merge\n\n"
            "- [ ] linked issue closed\n"
            "- [ ] auto-retro opened\n"
        )
        out = ar.compute_repair_signals(
            self._pr(body=body), has_inline_comments=False
        )
        assert not any(out.values())

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

    def test_multi_commit_signal_excludes_git_standard_revert(self) -> None:
        # A revert-only multi-commit PR must not fire on its own (#1287).
        out = ar.compute_repair_signals(
            self._pr(commits=2),
            has_inline_comments=False,
            commit_subjects=[
                'Revert "feat(x): add x"',
                "feat(x): add x",
            ],
        )
        assert out["multi_commit_pr"] is False

    def test_multi_commit_signal_excludes_conventional_revert(self) -> None:
        for revert_subject in [
            "revert(automerge): restore exemption",
            "revert: restore exemption",
            "revert!: restore exemption",
            "revert(automerge)!: restore exemption",
        ]:
            out = ar.compute_repair_signals(
                self._pr(commits=2),
                has_inline_comments=False,
                commit_subjects=[revert_subject, "feat(x): add x"],
            )
            assert out["multi_commit_pr"] is False, revert_subject

    def test_multi_commit_signal_fires_when_pure_commits_exceed_one_with_revert(
        self,
    ) -> None:
        out = ar.compute_repair_signals(
            self._pr(commits=3),
            has_inline_comments=False,
            commit_subjects=[
                'Revert "feat(x): add x"',
                "feat(x): add a",
                "feat(x): add b",
            ],
        )
        assert out["multi_commit_pr"] is True

    def test_multi_commit_signal_double_revert_counts_once(self) -> None:
        out = ar.compute_repair_signals(
            self._pr(commits=2),
            has_inline_comments=False,
            commit_subjects=[
                'Revert "Revert "feat(x): add x""',
                "feat(x): add x",
            ],
        )
        assert out["multi_commit_pr"] is False

    def test_multi_commit_signal_revert_in_scope_slot_not_subtracted(
        self,
    ) -> None:
        # `fix(revert): ...` is a real fix commit, not a rollback: revert
        # appears only in the scope slot, so it must NOT be subtracted.
        out = ar.compute_repair_signals(
            self._pr(commits=2),
            has_inline_comments=False,
            commit_subjects=[
                "fix(revert): correct the revert helper",
                "feat(x): add x",
            ],
        )
        assert out["multi_commit_pr"] is True


class TestCountRevert:
    def test_counts_git_standard_and_conventional(self) -> None:
        count = ar._count_revert(
            [
                'Revert "feat(x): add x"',
                "feat(x): add x",
                "revert(automerge): restore exemption",
                "revert: plain revert",
                "fix(scripts): tweak",
            ]
        )
        assert count == 3

    def test_returns_zero_when_no_revert_subjects(self) -> None:
        count = ar._count_revert(["feat(x): a", "fix(y): b", "docs(z): c"])
        assert count == 0

    def test_double_revert_counts_once(self) -> None:
        count = ar._count_revert(['Revert "Revert "feat: x""'])
        assert count == 1

    def test_handles_leading_whitespace(self) -> None:
        count = ar._count_revert(['   Revert "feat: x"'])
        assert count == 1

    def test_lowercase_git_standard_does_not_count(self) -> None:
        # Neither Git-standard (capital `Revert "`) nor Conventional.
        count = ar._count_revert(['revert "feat: x"'])
        assert count == 0

    def test_revert_without_colon_does_not_count(self) -> None:
        count = ar._count_revert(["revert this thing", "reverted earlier work"])
        assert count == 0

    def test_revert_in_scope_slot_does_not_count(self) -> None:
        count = ar._count_revert(["fix(revert): correct helper"])
        assert count == 0


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
            {"inline_review_comments": True, "multi_commit_pr": False}
        )
        assert "inline_review_comments=true" in text
        assert "multi_commit_pr=false" in text


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

    def test_passed_when_result_is_numeric_count(self) -> None:
        """Pure numeric result (e.g. `grep -c` output) treated as pass. Refs #417."""
        body = (
            "## Verification\n\n"
            "- command: `grep -c '^foo' file`\n"
            "  result: `2`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_passed_when_result_is_negative_numeric(self) -> None:
        body = (
            "## Verification\n\n"
            "- command: `echo -1`\n"
            "  result: `-1`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_passed_when_result_starts_with_all_hooks(self) -> None:
        """prek-style natural-language pass marker. Refs #417."""
        body = (
            "## Verification\n\n"
            "- command: `uvx prek run --files foo.md`\n"
            "  result: `all hooks Passed or Skipped`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_passed_when_result_starts_with_all_checks(self) -> None:
        body = (
            "## Verification\n\n"
            "- command: `gh pr checks 1`\n"
            "  result: `all checks have passed`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_passed_when_result_starts_with_all_tests(self) -> None:
        body = (
            "## Verification\n\n"
            "- command: `pytest`\n"
            "  result: `all tests passed`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_non_numeric_failure_prose_still_fails(self) -> None:
        """Free-form text that does not match the allowlist remains a fail."""
        body = (
            "## Verification\n\n"
            "- command: `pytest`\n"
            "  result: `traceback (most recent call last)`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is False

    def test_partial_numeric_with_suffix_is_not_passing(self) -> None:
        """`2 failed` should NOT be treated as numeric pass. Refs #417."""
        body = (
            "## Verification\n\n"
            "- command: `pytest`\n"
            "  result: `2 failed`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is False

    def test_passed_when_count_word_between_all_and_hooks(self) -> None:
        """`all six hooks Passed` reproduces the #410 row 3 misread. Refs #411."""
        body = (
            "## Verification\n\n"
            "- command: `uvx prek run --all-files`\n"
            "  result: `all six hooks Passed or Skipped`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_passed_when_numeric_between_all_and_checks(self) -> None:
        """`all 3 checks have passed` (gh pr checks shape). Refs #411."""
        body = (
            "## Verification\n\n"
            "- command: `gh pr checks 1`\n"
            "  result: `all 3 checks have passed`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_all_unit_pattern_requires_hooks_checks_or_tests(self) -> None:
        """False-positive guard: `all six widgets failed` must not pass. Refs #411."""
        body = (
            "## Verification\n\n"
            "- command: `pytest`\n"
            "  result: `all six widgets failed badly`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is False

    def test_passed_when_result_is_pytest_count_passed_in_time(self) -> None:
        """pytest summary `N passed in Ts` is a pass. Refs #453."""
        body = (
            "## Verification\n\n"
            "- command: `uv run pytest tests/test_auto_retro.py -v`\n"
            "  result: `246 passed in 198.59s`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_passed_when_result_is_pytest_count_with_coverage(self) -> None:
        """pytest summary `N passed, coverage ...` is a pass. Refs #453."""
        body = (
            "## Verification\n\n"
            "- command: `uv run pytest --cov`\n"
            "  result: `1476 passed, Total coverage: 94.24% (gate 92.71%)`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_passed_when_trailing_ok_word_inside_backticks_with_paren(
        self,
    ) -> None:
        """Backticked primary + trailing operator-commentary paren
        (`` `yaml syntax ok` (parsed without exception) ``). Refs #453."""
        body = (
            "## Verification\n\n"
            "- command: `python3 -c 'import yaml'`\n"
            "  result: `yaml syntax ok` (parsed without exception)\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_passed_when_trailing_ok_word_bare(self) -> None:
        """Bare trailing `ok` word marker is a pass. Refs #453."""
        body = (
            "## Verification\n\n"
            "- command: `lint config`\n"
            "  result: `config ok`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_failed_when_pytest_count_includes_failed(self) -> None:
        """`0 passed, 3 failed` must remain a fail even though it
        contains the pytest pass-count shape. Refs #453."""
        body = (
            "## Verification\n\n"
            "- command: `pytest`\n"
            "  result: `0 passed, 3 failed in 1.2s`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is False

    @pytest.mark.parametrize(
        "result",
        [
            "`Compilation completed successfully; "
            "CLAUDE.md / AGENTS.md regenerated`",
            "`docs/runbooks/rulesets.md | 17 +++++++++++++++++` "
            "(one file, 17 insertions, 0 deletions)",
            "`non_ascii= 0`",
            "`Compilation completed successfully` and "
            "`git diff --exit-code CLAUDE.md AGENTS.md` exits 0",
            "`(no hits) exit 1`",
            "only the intentional Rollback log entry remains.",
            "`378 passed in 200.38s`.",
            "Required test coverage of 92.71 percent reached. "
            "Total coverage 94.41 percent.",
            "`OK: every workflow uses: entry is SHA-pinned with a tag comment.` exit 0",
            "parses; `jobs.measure.steps` length = 11; "
            "triggers = `schedule`, `workflow_dispatch`. exit 0",
            "no matches; both files are ASCII-clean",
            "pytest 1828 passed in 203.91s; ruff / mypy / prek pass;",
            "one commit on the branch",
            "`::error file=/tmp/synthetic.md,line=2::assertive-existence "
            "phrase` and exit 1; gate trips as designed",
        ],
    )
    def test_issue_596_g3_success_observations_are_passing(
        self, result: str
    ) -> None:
        body = "## Verification\n\n- command: `verify`\n  result: " + result + "\n"
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    def test_issue_596_plain_exit_1_still_fails(self) -> None:
        body = (
            "## Verification\n\n"
            "- command: `pytest`\n"
            "  result: `exit 1`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is False

    @pytest.mark.parametrize(
        "result",
        [
            "`blocked: ModuleNotFoundError: No module named 'hypothesis'`",
            "`blocked: required uv ==0.11.11, local uv is 0.11.16`",
            "`not completed locally after rebase; direct local environment lacks hypothesis`",
            "`not run; local uv 0.11.16 does not match repository required-version ==0.11.11`",
        ],
    )
    def test_issue_592_environment_mismatch_still_fails(
        self, result: str
    ) -> None:
        body = (
            "## Verification\n\n"
            "- command: `representative`\n"
            f"  result: {result}\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is False

    @pytest.mark.parametrize(
        "result",
        [
            # #742 corpus: nix eval quoted-string output. nix eval on a
            # string-typed attribute wraps the value in double-quotes;
            # evaluation errors use the un-quoted `error: ...` prefix.
            '`"0.11.11"`',
            '`"sha256-p2eEglQ5GFXJbfJx6cqLf3LdFy0xBGBEeFPSXZB7muA="`',
            '`"sha256-FV/k07PLS/zhGKtLE4D3FRWuh00T2YWBcbT5wm4WaE0="`',
            # #742 corpus: tarball content observation.
            "`tarball contains uv-x86_64-unknown-linux-gnu/uv and uv-x86_64-unknown-linux-gnu/uvx`",
            # #788 corpus: nix eval --raw output (package name-version, shell name).
            "`bubblewrap-0.11.0`",
            "`nix-shell`",
            # #802 corpus: grep -n match output (line-number:content).
            "`18:aka.ms`",
            # #807 corpus: sha256sum output and nix sha256 hash prefix.
            "`a0b896e8cbdd10441125e989aa19d180c62052eda7c8aa850feb367805d1256f  apm-linux-x86_64.tar.gz`",
            "`364a651b8e383331cf0ae996d3d57b7f164b38de345634ae08fe7114c4f9e3a7  apm-linux-arm64.tar.gz`",
            "`sha256-oLiW6MvdEEQRJemJqhm+FakeTestHashValue=`",
            # #810 corpus: grep output with "guard block present" observation.
            (
                'guard block present; `if [[ ! -x "/usr/local/bin/apm" ]];'
                " then install_nix_binary apm-cli apm;"
                " else echo apm already present; fi`"
            ),
            # #829 corpus: "compiled successfully" short form and "all gates pass".
            "`compiled successfully; CLAUDE.md and AGENTS.md regenerated from the edited master source.`",
            "all gates pass except preflight_pr_single_commit (expected before squash-commit)",
            # #900 corpus: truncated hex hash from python hashlib output.
            "`15e7b5dfd8e654725ff0`",
        ],
    )
    def test_issue_927_corpus_observations_are_passing(
        self, result: str
    ) -> None:
        """#927 corpus: successful verification observations must not be Verification fail.

        Each result string is taken from retros #742, #788, #802, #807,
        #810, #829, #900 where the auto-retro generator incorrectly
        emitted Verification-fail rows for passing verifications. Refs #927.
        """
        body = "## Verification\n\n- command: `verify`\n  result: " + result + "\n"
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is True

    @pytest.mark.parametrize(
        "result",
        [
            "`error: attribute 'foo' missing`",
            "`fatal: not a git repository`",
            "`exit 1`",
            "`3 failed in 0.5s`",
        ],
    )
    def test_issue_927_canonical_failures_still_fail(
        self, result: str
    ) -> None:
        """Canonical failure results must remain False after the #927 fixes."""
        body = (
            "## Verification\n\n"
            "- command: `verify`\n"
            f"  result: {result}\n"
        )
        pairs = ar.extract_verification_pairs(body)
        assert pairs and pairs[0].passed is False


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
        table = ar._build_repair_history_table(None, [], 1, pairs)
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
        table = ar._build_repair_history_table(None, [], 1, pairs)
        assert "Verification fail" not in table

    def test_post_merge_rows_never_emitted(self) -> None:
        """Per #418, Post-merge items are no longer rendered at merge time."""
        # Even a body-derived list of unchecked Post-merge items cannot reach
        # the table builder anymore: the parameter was removed. Confirm the
        # row marker text is absent for a representative call.
        table = ar._build_repair_history_table(
            None, [], 1, [ar.VerificationPair("`x`", "`exit 1`", False)]
        )
        assert "Post-merge gate unchecked" not in table

    def test_row_ordering_existing_classes_before_verification(self) -> None:
        pairs = [
            ar.VerificationPair("`a`", "`exit 1`", False),
        ]
        table = ar._build_repair_history_table(
            None, ["fix(harness): patch"], 2, pairs
        )
        # Iteration commit appears before the trailing Verification row.
        iter_idx = table.find("Iteration commit")
        verif_idx = table.find("Verification fail")
        assert 0 < iter_idx < verif_idx

    def test_default_args_keep_legacy_callsite(self) -> None:
        # Legacy three-arg callers still work, no extra rows produced.
        table = ar._build_repair_history_table(None, [], 1)
        assert "Verification fail" not in table
        assert "Post-merge gate unchecked" not in table

    def test_issue_410_row_3_no_longer_misreports(self) -> None:
        """End-to-end regression for #411: feed the body shape that produced
        the misread row in retro #410 row 3 through extract_verification_pairs
        and assert the rebuilt table emits no `Verification fail` row.
        """
        body = (
            "## Verification\n\n"
            "- command: `uvx prek run --all-files`\n"
            "  result: `all six hooks Passed or Skipped`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        table = ar._build_repair_history_table(None, [], 1, pairs)
        assert "Verification fail" not in table

    def test_mixed_pass_fail_pairs_only_fail_row_emitted(self) -> None:
        """Smoke fixture from issue #453 Verification section: one
        passing and one failing verification pair. Passing pair must
        NOT render a `Verification fail:` row; failing pair must."""
        pairs = [
            ar.VerificationPair(
                command="`uv run pytest -v`",
                result="`246 passed in 198.59s`",
                passed=True,
            ),
            ar.VerificationPair(
                command="`ruff check .`",
                result="`exit 1`",
                passed=False,
            ),
        ]
        table = ar._build_repair_history_table(None, [], 1, pairs)
        # Failing pair retains the Verification fail: prefix.
        assert "Verification fail: `ruff check .`" in table
        # Passing pair leaves no row; in particular not a fail row.
        assert "Verification fail: `uv run pytest -v`" not in table
        assert "246 passed in 198.59s" not in table

    def test_issue_596_g3_success_observations_leave_no_fail_rows(self) -> None:
        body = (
            "## Verification\n\n"
            "- command: `apm compile`\n"
            "  result: `Compilation completed successfully` and "
            "`git diff --exit-code CLAUDE.md AGENTS.md` exits 0\n"
            "- command: `grep removed-term`\n"
            "  result: `(no hits) exit 1`\n"
            "- command: `pytest --cov`\n"
            "  result: Required test coverage of 92.71 percent reached. "
            "Total coverage 94.41 percent.\n"
            "- command: `scan ascii`\n"
            "  result: no matches; both files are ASCII-clean\n"
            "- command: `negative fixture`\n"
            "  result: `::error file=/tmp/synthetic.md,line=2::"
            "assertive-existence phrase` and exit 1; gate trips as designed\n"
            "- command: `ruff check .`\n"
            "  result: `exit 1`\n"
        )
        pairs = ar.extract_verification_pairs(body)
        table = ar._build_repair_history_table(None, [], 1, pairs)
        assert "Verification fail: `ruff check .`" in table
        assert "Verification fail: `apm compile`" not in table
        assert "Verification fail: `grep removed-term`" not in table
        assert "Verification fail: `pytest --cov`" not in table
        assert "Verification fail: `scan ascii`" not in table
        assert "Verification fail: `negative fixture`" not in table


class TestIssue592Corpus:
    """Stable #592 corpus summary for the #593 false-positive repair."""

    _BASE_SIGNALS: ClassVar[dict[str, bool]] = {
        "inline_review_comments": False,
        "body_cites_refs": False,
        "fix_typed_title": False,
        "multi_commit_pr": False,
    }

    @staticmethod
    def _pair(result: str) -> ar.VerificationPair:
        passed = ar.extract_verification_pairs(
            "## Verification\n\n"
            "- command: `representative`\n"
            f"  result: {result}\n"
        )[0].passed
        return ar.VerificationPair("`representative`", result, passed)

    @pytest.mark.parametrize(
        "issue,group,signals,commits,results,pr_type,expected",
        [
            (576, "G1", {"body_cites_refs": True}, ["docs: x", "Merge branch 'main' into f"], [], "", False),
            (588, "G1", {"body_cites_refs": True}, ["docs: x", "Merge branch 'main' into f"], [], "", False),
            (589, "G1", {"body_cites_refs": True}, ["feat: x", "Merge branch 'main' into f"], [], "", False),
            (590, "G1", {"body_cites_refs": True}, ["perf: x", "Merge branch 'main' into f"], [], "", False),
            (565, "G1", {"body_cites_refs": True}, ["feat: x", "Merge branch 'main' into f"], [], "", False),
            (563, "G1", {"body_cites_refs": True}, ["feat: x", "Merge branch 'main' into f"], [], "", False),
            (585, "G2", {}, ["docs: x"], [], "", False),
            (555, "G2", {}, ["feat: x"], [], "", False),
            (546, "G2", {}, ["feat: x"], [], "", False),
            (521, "G3", {}, ["docs: x"], ["`Compilation completed successfully`"], "", False),
            (526, "G3", {}, ["docs: x"], ["`non_ascii= 0`"], "", False),
            (532, "G3", {}, ["docs: x"], ["`(no hits) exit 1`"], "", False),
            (539, "G3", {}, ["docs: x"], ["`hashref_56= 3 non_ascii= 0`"], "", False),
            (540, "G3", {}, ["docs: x"], ["shows Chapter 3 ending at the Chapter 4 heading"], "", False),
            (544, "G3", {}, ["feat: x", "Merge branch 'main' into f"], ["Required test coverage reached."], "", False),
            (550, "G3", {}, ["docs: x"], ["matches the new H2 heading"], "", False),
            (551, "G3", {}, ["docs: x"], ["`yaml syntax ok`"], "", False),
            (553, "G3", {}, ["docs: x"], ["all checks have passed"], "", False),
            (557, "G3", {}, ["ci: x", "Merge branch 'main' into f"], ["`OK: no direct pip install.` exit 0"], "", False),
            (561, "G3", {}, ["ci: x"], ["pytest 1828 passed in 203.91s"], "", False),
            # G4 (#1236): verification-prose failures are now non-actionable
            # policy-artifact anomaly hints, so a verification-only PR skips.
            # The genuine local failures these encode would still open a retro
            # when a CI failure / iteration commit co-fires; prose alone no
            # longer does.
            (567, "G4", {}, ["ci: x"], ["`not run; local uv 0.11.16 does not match repository required-version ==0.11.11`"], "", False),
            (570, "G4", {}, ["feat: x"], ["`blocked: ModuleNotFoundError: No module named 'hypothesis'`"], "", False),
            (543, "G5", {"fix_typed_title": True}, ["fix(harness): remove gate"], ["`378 passed in 200.38s`"], "fix", False),
        ],
    )
    def test_corpus_standalone_work_disposition(
        self,
        issue: int,
        group: str,
        signals: dict[str, bool],
        commits: list[str],
        results: list[str],
        pr_type: str,
        expected: bool,
    ) -> None:
        # `signals` is retained for corpus documentation of what fired on
        # the historical retro; the live disposition is now derived purely
        # from the rendered rows (verification_pairs_failed retired in #1236).
        pairs = [self._pair(result) for result in results]
        rows = ar._repair_history_rows([], commits, len(commits), pairs, pr_type)
        standalone = bool(rows) and not ar._has_only_exempt_policy_artifact_rows(
            rows
        )
        assert standalone is expected, f"issue #{issue} ({group})"


class TestIssue927Corpus:
    """#927 corpus: verification false-positive repair.

    Each case encodes a retro from the open-retro set referenced in issue
    #927 (#742, #788, #802, #807, #810, #829, #900). Before the #927 fix,
    ``_result_is_passing`` returned False for the verification result strings
    listed below, causing the generator to emit spurious Verification-fail
    rows. After the fix each result must be classified as passing, which
    changes the standalone-work disposition from True to False for the
    cases where the false-positive was the only non-policy-artifact row.

    #788 is included to document that its retro was CORRECTLY created (the
    source PR had an Iteration commit on a build-typed PR), even though the
    Verification rows in the table were false positives.

    Refs #927.
    """

    _BASE_SIGNALS: ClassVar[dict[str, bool]] = {
        "inline_review_comments": False,
        "body_cites_refs": False,
        "fix_typed_title": False,
        "multi_commit_pr": False,
    }

    @staticmethod
    def _pair(result: str) -> ar.VerificationPair:
        passed = ar.extract_verification_pairs(
            "## Verification\n\n"
            "- command: `representative`\n"
            f"  result: {result}\n"
        )[0].passed
        return ar.VerificationPair("`representative`", result, passed)

    @pytest.mark.parametrize(
        "issue,group,signals,commits,results,pr_type,expected",
        [
            # #742 (PR #736 fix(devcontainer)): nix eval quoted hash + tarball.
            # After fix: verification pairs pass → only policy-artifact rows → skip.
            (
                742,
                "G3-927",
                {"body_cites_refs": True, "fix_typed_title": True},
                [
                    "fix(devcontainer): pin nix uv to repo version (#734)",
                    "Merge remote-tracking branch 'origin/main' into codex/fix-devcontainer-uv-pin",
                ],
                [
                    '`"0.11.11"`',
                    '`"sha256-p2eEglQ5GFXJbfJx6cqLf3LdFy0xBGBEeFPSXZB7muA="`',
                    "`tarball contains uv-x86_64-unknown-linux-gnu/uv`",
                ],
                "fix",
                False,
            ),
            # #788 (PR #778 build(devcontainer)): nix eval --raw output.
            # Retro was CORRECTLY created: fix(devcontainer) commit on build-typed
            # PR is an Iteration commit (not a policy artifact). After fix:
            # verification pairs pass but Iteration commit row remains → standalone.
            (
                788,
                "G4-927-correct",
                {"body_cites_refs": True},
                [
                    "fix(devcontainer): provide Codex bubblewrap",
                    "Merge branch 'main' into codex/fix-codex-bubblewrap",
                ],
                ["`bubblewrap-0.11.0`", "`nix-shell`"],
                "build",
                True,
            ),
            # #802 (PR #801 build(devcontainer)): grep -n match output.
            # After fix: verification pair passes → no rows → skip.
            (
                802,
                "G3-927",
                {"body_cites_refs": True},
                ["build(devcontainer): allowlist aka.ms for microsoft/apm installer"],
                ["`18:aka.ms`"],
                "build",
                False,
            ),
            # #807 (PR #806 feat(nix)): sha256sum output + nix sha256 prefix.
            # After fix: verification pairs pass → no rows → skip.
            (
                807,
                "G3-927",
                {"body_cites_refs": True},
                ["feat(nix): add microsoft/apm as pinned Nix derivation (#804)"],
                [
                    "`a0b896e8cbdd10441125e989aa19d180c62052eda7c8aa850feb367805d1256f  apm-linux-x86_64.tar.gz`",
                    "`sha256-oLiW6MvdEEQRJemJqhm+FakeTestHashValue=`",
                ],
                "feat",
                False,
            ),
            # #810 (PR #809 build(devcontainer)): grep "guard block present" output.
            # After fix: verification pair passes → no rows → skip.
            (
                810,
                "G3-927",
                {"body_cites_refs": True},
                ["build(devcontainer): skip apm install when already baked into image (#805)"],
                [
                    'guard block present; `if [[ ! -x "/usr/local/bin/apm" ]];'
                    " then install_nix_binary apm-cli apm;"
                    " else echo apm already present; fi`"
                ],
                "build",
                False,
            ),
            # #829 (PR #825 fix(language)): "compiled successfully" + "all gates pass".
            # After fix: verification pairs pass → only policy-artifact rows → skip.
            (
                829,
                "G3-927",
                {"body_cites_refs": True, "fix_typed_title": True},
                [
                    "fix(language): bind operator-facing chat to owner language in every mode (#817)",
                    "Merge branch 'main' into claude/claude-md-pr-812-wjih3",
                ],
                [
                    "`compiled successfully; CLAUDE.md and AGENTS.md regenerated from the edited master source.`",
                    "all gates pass except preflight_pr_single_commit (expected before squash-commit)",
                ],
                "fix",
                False,
            ),
            # #900 (PR #898 fix(non-ascii)): truncated hex hash.
            # After fix: verification pair passes → only policy-artifact rows → skip.
            (
                900,
                "G3-927",
                {"body_cites_refs": True, "fix_typed_title": True},
                [
                    "fix(non-ascii): update translations.json issue #9 original to match live body drift",
                    "Merge branch 'main' into claude/zealous-pascal-TbCXe",
                ],
                ["`15e7b5dfd8e654725ff0`"],
                "fix",
                False,
            ),
        ],
    )
    def test_corpus_standalone_work_disposition(
        self,
        issue: int,
        group: str,
        signals: dict[str, bool],
        commits: list[str],
        results: list[str],
        pr_type: str,
        expected: bool,
    ) -> None:
        # `signals` is retained for corpus documentation of what fired on
        # the historical retro; the live disposition is now derived purely
        # from the rendered rows (verification_pairs_failed retired in #1236).
        pairs = [self._pair(result) for result in results]
        rows = ar._repair_history_rows([], commits, len(commits), pairs, pr_type)
        standalone = bool(rows) and not ar._has_only_exempt_policy_artifact_rows(
            rows
        )
        assert standalone is expected, f"issue #{issue} ({group})"


class TestIssue1227VerificationSkipCorpus:
    """#1227 corpus: exit=0 / environment-skip false-positive repair.

    Each result below was scored as a verification FAILURE before the
    #1227 fix, firing ``verification_pairs_failed`` on a merged PR that
    did no repair work (the dominant open-retro false positive). After
    the fix the exit-zero and environment-skip forms classify as passing,
    while genuine local failures keep failing. Refs #1227, #851, #1071,
    #1074, #1110, #1216.
    """

    @pytest.mark.parametrize(
        "result",
        [
            "total preflight exit=0 (skill_quality_gate skipped on missing"
            " local prereqs: bin:waza, env:GH_TOKEN_API)",
            "PREFLIGHT_EXIT=0 ... all pass; verify_ruleset_sync skipped",
            "skip: PR is a retro-close PR (rc=0)",
            "blocked: GH_TOKEN unset in this environment",
            "exit code 0",
            "rc=0",
            "not applicable",
        ],
    )
    def test_passing_results_no_longer_fire(self, result: str) -> None:
        assert ar._result_is_passing(result) is True

    @pytest.mark.parametrize(
        "result",
        [
            "blocked: ModuleNotFoundError: No module named 'hypothesis'",
            "not run; local uv 0.11.16 does not match repository"
            " required-version ==0.11.11",
            "failed: 3 tests broken",
            "exit 1",
            "0 passed, 3 failed",
        ],
    )
    def test_genuine_failures_still_fail(self, result: str) -> None:
        assert ar._result_is_passing(result) is False


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
        titles = {40: "fix(auto-retro): review PR #20 repair loops"}
        assert ar.find_target_retro_from_refs(pr, titles) == 40

    def test_returns_none_for_non_fix_typed_title(self) -> None:
        pr = self._pr(title="feat(harness): new thing")
        titles = {40: "fix(auto-retro): review PR #20 repair loops"}
        assert ar.find_target_retro_from_refs(pr, titles) is None

    def test_returns_none_when_ref_does_not_resolve_to_retro(self) -> None:
        pr = self._pr()
        titles = {40: "feat(harness): not a retro"}
        assert ar.find_target_retro_from_refs(pr, titles) is None

    def test_returns_first_matching_retro(self) -> None:
        pr = self._pr(body="Refs #40\nRefs #50\n")
        titles = {
            40: "feat: ordinary",
            50: "fix(auto-retro): review",
        }
        assert ar.find_target_retro_from_refs(pr, titles) == 50

    def test_returns_none_when_no_refs(self) -> None:
        pr = self._pr(body="no refs at all")
        assert ar.find_target_retro_from_refs(pr, {}) is None

    def test_ignores_html_commented_refs(self) -> None:
        pr = self._pr(body="<!-- Refs #40 -->\n")
        titles = {40: "fix(auto-retro): review"}
        assert ar.find_target_retro_from_refs(pr, titles) is None


class TestRepairHistoryFourColumnSchema:
    """Cause + Next action columns and per-row sentinel contract. Refs #1058."""

    def test_header_has_cause_and_next_action(self) -> None:
        table = ar._build_repair_history_table(None, [], 1)
        header = table.splitlines()[0]
        assert header == "| # | Repair | Cause | Next action |"

    def test_non_artifact_row_carries_next_action_sentinel(self) -> None:
        check_runs = [
            {"name": "gate", "conclusion": "failure", "completed_at": "t"}
        ]
        table = ar._build_repair_history_table(check_runs, [], 1)
        row_line = next(
            line for line in table.splitlines() if "CI fail: gate" in line
        )
        assert ar._REPAIR_NEXT_ACTION_FILL in row_line

    def test_verification_fail_row_is_exempt_policy_artifact(self) -> None:
        # Refs #1236: prose Verification rows are non-actionable anomaly
        # hints, marked policy-artifact with a dash next-action like the
        # Revert / Multi-commit rows, so a verification-only PR skips.
        pairs = [
            ar.VerificationPair(command="pytest", result="1 failed", passed=False)
        ]
        table = ar._build_repair_history_table(
            None, [], 1, verification_pairs=pairs
        )
        row_line = next(
            line
            for line in table.splitlines()
            if "Verification fail: pytest" in line
        )
        assert ar._POLICY_ARTIFACT_MARKER in row_line
        cells = [c.strip() for c in row_line.strip()[1:-1].split("|")]
        assert cells[3] == "--"

    def test_artifact_row_next_action_is_dash(self) -> None:
        # Multi-commit PR is a policy-artifact row.
        table = ar._build_repair_history_table(None, [], 3)
        row_line = next(
            line for line in table.splitlines() if "Multi-commit PR" in line
        )
        cells = [c.strip() for c in row_line.strip()[1:-1].split("|")]
        assert cells[3] == "--"

    def test_positive_control_row_is_four_columns(self) -> None:
        table = ar._build_repair_history_table(None, [], 1)
        row_line = next(
            line
            for line in table.splitlines()
            if "no automated repair signals detected" in line
        )
        cells = [c.strip() for c in row_line.strip()[1:-1].split("|")]
        assert len(cells) == 4
        assert cells[0] == "n/a"
        assert cells[3] == "n/a"

    def test_render_appended_row_returns_three_cells(self) -> None:
        pr = _make_pr(number=88, title="fix(x): y", merged_at="2026-06-01T00:00:00Z")
        repair, cause, next_action = ar.render_appended_row(pr)
        assert repair == "Follow-up fix PR: #88"
        assert "merged at 2026-06-01T00:00:00Z" in cause
        assert next_action == ar._REPAIR_NEXT_ACTION_FILL


class TestVerifyRetroRepairCompleteness:
    """Pure-function gate over the auto-filled repair-history block."""

    def _wrap(self, table_rows: str) -> str:
        return (
            "## Proposed work\n\n"
            "<!-- auto-filled:repair-history -->\n"
            "| # | Repair | Cause | Next action |\n"
            "|---|--------|-------|-------------|\n"
            f"{table_rows}"
            "<!-- /auto-filled:repair-history -->\n"
        )

    def test_unfilled_next_action_flagged(self) -> None:
        body = self._wrap(
            f"| 1 | CI fail: gate | something broke | "
            f"{ar._REPAIR_NEXT_ACTION_FILL} |\n"
        )
        errors = ar.verify_retro_repair_completeness(body)
        assert errors
        assert any("Next action" in e for e in errors)
        assert all(e.startswith("::error::") for e in errors)

    def test_unfilled_cause_flagged(self) -> None:
        body = self._wrap(
            f"| 1 | CI fail: gate | {ar._REPAIR_CAUSE_FILL} | add a gate |\n"
        )
        errors = ar.verify_retro_repair_completeness(body)
        assert errors
        assert any("Cause" in e for e in errors)

    def test_filled_row_passes(self) -> None:
        body = self._wrap(
            "| 1 | CI fail: gate | the lint gate failed | add ruff rule |\n"
        )
        assert ar.verify_retro_repair_completeness(body) == []

    def test_artifact_only_passes(self) -> None:
        body = self._wrap(
            f"| 1 | Multi-commit PR | {ar._POLICY_ARTIFACT_MARKER} 3 commits "
            f"|; |\n"
        )
        assert ar.verify_retro_repair_completeness(body) == []

    def test_positive_control_passes(self) -> None:
        body = self._wrap(
            "|; | (no automated repair signals detected) | "
            "positive-control: no repair taxonomy classification requested "
            "|; |\n"
        )
        assert ar.verify_retro_repair_completeness(body) == []

    def test_missing_auto_filled_block_passes(self) -> None:
        body = "## Scope\n\nno auto-filled block here.\n"
        assert ar.verify_retro_repair_completeness(body) == []

    def test_malformed_row_flagged(self) -> None:
        body = self._wrap("| 1 | CI fail: gate | only three cells |\n")
        errors = ar.verify_retro_repair_completeness(body)
        assert errors
        assert any("malformed" in e for e in errors)

    def test_escaped_pipe_in_cell_does_not_shift_columns(self) -> None:
        # _escape_table_cell renders an in-cell pipe (e.g. a verification
        # command like `grep x | wc -l`) as ``\|``. The verify must split
        # on UNescaped pipes only; a naive split("|") would over-split the
        # row, shift the Cause / Next action columns, and silently pass an
        # unfilled retro. Refs #1058.
        body = self._wrap(
            f"| 1 | Verification fail: grep x \\| wc -l "
            f"| observed: 3 failed | {ar._REPAIR_NEXT_ACTION_FILL} |\n"
        )
        errors = ar.verify_retro_repair_completeness(body)
        assert errors
        assert any("Next action" in e for e in errors)

    def test_real_build_retro_body_with_signal_fails_until_filled(self) -> None:
        pr = _make_pr(number=900, title="fix(x): patch", commits=1)
        check_runs = [
            {"name": "gate", "conclusion": "failure", "completed_at": "t"}
        ]
        body = ar.build_retro_body(pr, ["fix(x): patch"], check_runs=check_runs)
        # The freshly generated body has unfilled next-action sentinels.
        assert ar.verify_retro_repair_completeness(body)

    def test_real_positive_control_body_passes(self) -> None:
        pr = _make_pr(number=901, title="feat(x): add", commits=1)
        body = ar.build_retro_body(pr, [])
        assert ar.verify_retro_repair_completeness(body) == []


class TestVerifyRetroCompletenessCli:
    """The verify-retro-completeness subcommand skip/fail/pass paths."""

    _RETRO_TITLE = "fix(auto-retro): review PR #900 repair loops"

    def test_skip_when_not_retro_pr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = ar.main(
            [
                "verify-retro-completeness",
                "--repo",
                "o/r",
                "--pr-title",
                "feat(x): add",
                "--pr-body-file",
                "/dev/null",
            ]
        )
        assert rc == 0
        assert "skip: not a retro-close PR" in capsys.readouterr().out

    def test_skip_when_no_linked_retro(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text("Refs #5\n", encoding="utf-8")

        def fake_api(method, path, body=None, **_kw):
            return json.dumps({"title": "feat(x): not a retro"})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        rc = ar.main(
            [
                "verify-retro-completeness",
                "--repo",
                "o/r",
                "--pr-title",
                "fix(auto-retro): close",
                "--pr-body-file",
                str(body_file),
            ]
        )
        assert rc == 0
        assert "skip: no linked retro issue" in capsys.readouterr().out

    def test_fail_when_retro_incomplete(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text("Refs #900\n", encoding="utf-8")
        retro_body = (
            "<!-- auto-filled:repair-history -->\n"
            "| # | Repair | Cause | Next action |\n"
            "|---|--------|-------|-------------|\n"
            f"| 1 | CI fail: gate | cause | {ar._REPAIR_NEXT_ACTION_FILL} |\n"
            "<!-- /auto-filled:repair-history -->\n"
        )

        def fake_api(method, path, body=None, **_kw):
            if path.endswith("/900"):
                return json.dumps(
                    {"title": self._RETRO_TITLE, "body": retro_body}
                )
            return json.dumps({"title": self._RETRO_TITLE})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        rc = ar.main(
            [
                "verify-retro-completeness",
                "--repo",
                "o/r",
                "--pr-title",
                "fix(auto-retro): close",
                "--pr-body-file",
                str(body_file),
            ]
        )
        assert rc == 1
        assert "::error::" in capsys.readouterr().out

    def test_pass_when_retro_complete(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text("Refs #900\n", encoding="utf-8")
        retro_body = (
            "<!-- auto-filled:repair-history -->\n"
            "| # | Repair | Cause | Next action |\n"
            "|---|--------|-------|-------------|\n"
            "| 1 | CI fail: gate | gate failed | add a ruff rule |\n"
            "<!-- /auto-filled:repair-history -->\n"
        )

        def fake_api(method, path, body=None, **_kw):
            if path.endswith("/900"):
                return json.dumps(
                    {"title": self._RETRO_TITLE, "body": retro_body}
                )
            return json.dumps({"title": self._RETRO_TITLE})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        rc = ar.main(
            [
                "verify-retro-completeness",
                "--repo",
                "o/r",
                "--pr-title",
                "fix(auto-retro): close",
                "--pr-body-file",
                str(body_file),
            ]
        )
        assert rc == 0
        assert "OK:" in capsys.readouterr().out

    def test_skip_when_retro_body_unavailable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text("Refs #900\n", encoding="utf-8")

        def fake_api(method, path, body=None, **_kw):
            # Title resolves as a retro, but the body fetch yields nothing.
            return json.dumps({"title": self._RETRO_TITLE})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        rc = ar.main(
            [
                "verify-retro-completeness",
                "--repo",
                "o/r",
                "--pr-title",
                "fix(auto-retro): close",
                "--pr-body-file",
                str(body_file),
            ]
        )
        assert rc == 0
        assert "body unavailable" in capsys.readouterr().out


class TestFindLinkedRetroRefs:
    def test_returns_retro_refs_only(self) -> None:
        body = "Closes #5\nRefs #900\n"
        titles = {
            5: "feat(x): unrelated follow-up",
            900: "chore(auto-retro): review PR #898 repair loops",
        }
        assert ar.find_linked_retro_refs(body, titles) == [900]

    def test_matches_legacy_fix_prefix(self) -> None:
        body = "Closes #900\n"
        titles = {900: "fix(auto-retro): review PR #898 repair loops"}
        assert ar.find_linked_retro_refs(body, titles) == [900]

    def test_skips_unfetched_titles(self) -> None:
        body = "Closes #900\n"
        assert ar.find_linked_retro_refs(body, {}) == []

    def test_empty_when_no_retro(self) -> None:
        body = "Closes #5\n"
        titles = {5: "feat(x): real work"}
        assert ar.find_linked_retro_refs(body, titles) == []


class TestVerifyNoDirectRetroPrCli:
    """The verify-no-direct-retro-pr subcommand skip/fail/pass paths (Refs #1069)."""

    _RETRO_TITLE = "chore(auto-retro): review PR #900 repair loops"

    def test_skip_when_pr_is_retro_close(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = ar.main(
            [
                "verify-no-direct-retro-pr",
                "--repo",
                "o/r",
                "--pr-title",
                "docs(auto-retro): record repair-free merge",
                "--pr-body-file",
                "/dev/null",
            ]
        )
        assert rc == 0
        assert "skip: PR is a retro-close PR" in capsys.readouterr().out

    def test_skip_when_no_linked_issue(
        self, tmp_path: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text("No issue link here.\n", encoding="utf-8")
        rc = ar.main(
            [
                "verify-no-direct-retro-pr",
                "--repo",
                "o/r",
                "--pr-title",
                "fix(x): real work",
                "--pr-body-file",
                str(body_file),
            ]
        )
        assert rc == 0
        assert "links no issue" in capsys.readouterr().out

    def test_skip_when_linked_issue_not_retro(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text("Closes #5\n", encoding="utf-8")

        def fake_api(method, path, body=None, **_kw):
            return json.dumps({"title": "feat(x): a normal issue"})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        rc = ar.main(
            [
                "verify-no-direct-retro-pr",
                "--repo",
                "o/r",
                "--pr-title",
                "fix(x): real work",
                "--pr-body-file",
                str(body_file),
            ]
        )
        assert rc == 0
        assert "skip: no linked retro issue" in capsys.readouterr().out

    def test_fail_when_normal_pr_links_retro(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text("Closes #900\n", encoding="utf-8")

        def fake_api(method, path, body=None, **_kw):
            return json.dumps({"title": self._RETRO_TITLE})

        monkeypatch.setattr(ar, "gh_api", fake_api)
        rc = ar.main(
            [
                "verify-no-direct-retro-pr",
                "--repo",
                "o/r",
                "--pr-title",
                "fix(x): directly fix the retro",
                "--pr-body-file",
                str(body_file),
            ]
        )
        assert rc == 1
        out = capsys.readouterr().out
        assert "::error::" in out
        assert "#900" in out

    def test_fail_when_legacy_fix_retro_linked(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text("Refs #900\n", encoding="utf-8")

        def fake_api(method, path, body=None, **_kw):
            return json.dumps(
                {"title": "fix(auto-retro): review PR #898 repair loops"}
            )

        monkeypatch.setattr(ar, "gh_api", fake_api)
        rc = ar.main(
            [
                "verify-no-direct-retro-pr",
                "--repo",
                "o/r",
                "--pr-title",
                "feat(x): build on the retro",
                "--pr-body-file",
                str(body_file),
            ]
        )
        assert rc == 1
        assert "#900" in capsys.readouterr().out


class TestInsertAppendedRow:
    _SAMPLE = (
        "## Proposed work\n"
        "\n"
        "<!-- auto-filled:repair-history -->\n"
        "1. Repair history\n"
        "\n"
        "| # | Repair | Cause | Next action |\n"
        "|---|--------|-------|-------------|\n"
        "| 1 | A | B | C |\n"
        "<!-- /auto-filled:repair-history -->\n"
        "\n"
        "more text\n"
    )

    def test_appends_row_with_next_index(self) -> None:
        new_body, changed = ar._insert_appended_row(
            self._SAMPLE,
            ("Follow-up fix PR: #50", "`fix(x): y` merged at T", "next"),
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
        body = self._SAMPLE.replace(
            "| 1 | A | B | C |", "| 1 | Follow-up #50 | x | y |"
        )
        _, changed = ar._insert_appended_row(body, ("x", "y", "z"), 50)
        assert changed is False

    def test_no_change_when_markers_missing(self) -> None:
        body = "## Proposed work\n\nno markers here\n"
        new_body, changed = ar._insert_appended_row(body, ("x", "y", "z"), 50)
        assert changed is False
        assert new_body == body

    def test_next_index_falls_back_to_one_with_empty_table(self) -> None:
        body = (
            "<!-- auto-filled:repair-history -->\n"
            "no rows\n"
            "<!-- /auto-filled:repair-history -->\n"
        )
        new_body, changed = ar._insert_appended_row(body, ("x", "y", "z"), 99)
        assert changed is True
        assert "| 1 | x | y | z |" in new_body

    def test_pr_number_prefix_collision_not_idempotent(self) -> None:
        body = self._SAMPLE.replace(
            "| 1 | A | B | C |", "| 1 | Follow-up #500 | x | y |"
        )
        # PR #50 must NOT match an existing #500 row.
        _, changed = ar._insert_appended_row(body, ("a", "b", "c"), 50)
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
        seen: list[tuple[str, str, Any]] = []

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
        seen: list[tuple[str, str, Any]] = []

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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Strategy B retro sentinel (issue #414)
# ---------------------------------------------------------------------------


def _retro_body(checked: int = 0) -> str:
    """Return a retro body with ``checked`` of the 5 acceptance criteria flipped.

    Mirrors the literal section emitted by :func:`auto_retro.build_retro_body`
    so the slicer reads it the same way it would read a real auto-opened
    retro. Keeping the section text byte-aligned with the production
    body protects against drift; a future template change that breaks
    the slice would also break these fixtures, surfacing the regression.
    """
    boxes = ["[ ]"] * 5
    for i in range(checked):
        boxes[i] = "[x]"
    return (
        "## Scope\n\nx\n\n"
        "## Facts\n\n- a\n\n"
        "## Proposed work\n\n"
        "<!-- auto-filled:repair-history -->\n"
        "1. Repair history\n\n"
        "| # | Repair | What |\n"
        "|---|--------|------|\n"
        "| 1 | Iteration commit | x |\n"
        "<!-- /auto-filled:repair-history -->\n\n"
        "## Verification\n\n- v\n\n"
        "## Acceptance criteria\n\n"
        f"- {boxes[0]} Repair history table complete.\n"
        f"- {boxes[1]} Each repair classified.\n"
        f"- {boxes[2]} Each repair has an earliest prevention point.\n"
        f"- {boxes[3]} No-repair reproduction path stated.\n"
        f"- {boxes[4]} `## Follow-up issues` filed.\n"
    )


class TestIsRetroUntouched:
    def test_all_unchecked_and_no_comments_returns_true(self) -> None:
        assert ar.is_retro_untouched(_retro_body(checked=0), []) is True

    def test_any_checkbox_checked_returns_false(self) -> None:
        assert ar.is_retro_untouched(_retro_body(checked=1), []) is False

    def test_all_checkboxes_checked_returns_false(self) -> None:
        assert ar.is_retro_untouched(_retro_body(checked=5), []) is False

    def test_non_bot_comment_returns_false(self) -> None:
        comments = [{"user": {"login": "tvna"}, "body": "triaged"}]
        assert ar.is_retro_untouched(_retro_body(checked=0), comments) is False

    def test_dependabot_comment_does_not_count(self) -> None:
        comments = [{"user": {"login": "dependabot[bot]"}, "body": "x"}]
        assert ar.is_retro_untouched(_retro_body(checked=0), comments) is True

    def test_github_actions_comment_does_not_count(self) -> None:
        comments = [{"user": {"login": "github-actions[bot]"}, "body": "x"}]
        assert ar.is_retro_untouched(_retro_body(checked=0), comments) is True

    def test_mix_of_bot_and_human_returns_false(self) -> None:
        comments = [
            {"user": {"login": "github-actions[bot]"}, "body": "x"},
            {"user": {"login": "tvna"}, "body": "triaged"},
        ]
        assert ar.is_retro_untouched(_retro_body(checked=0), comments) is False

    def test_missing_acceptance_section_returns_false(self) -> None:
        """Defensive: an unparseable body must not be auto-closed."""
        body = "## Scope\n\nx\n\n## Facts\n\n- a\n"
        assert ar.is_retro_untouched(body, []) is False

    def test_empty_body_returns_false(self) -> None:
        assert ar.is_retro_untouched("", []) is False

    def test_acceptance_section_without_checkboxes_returns_false(self) -> None:
        body = (
            "## Acceptance criteria\n"
            "\n"
            "All criteria are met per the upstream issue.\n"
        )
        assert ar.is_retro_untouched(body, []) is False

    def test_comment_without_user_login_does_not_count(self) -> None:
        """A malformed comment with no login field is treated as no engagement.

        Fail-safe: missing login means we cannot attribute the comment,
        so we err on the side of letting the sentinel proceed rather than
        blocking the close on an unreadable comment.
        """
        comments = [{"body": "ghost"}]
        assert ar.is_retro_untouched(_retro_body(checked=0), comments) is True


class TestIsRetroAgeExceeded:
    def test_15_days_old_exceeds_14(self) -> None:
        assert ar.is_retro_age_exceeded(
            "2026-05-01T00:00:00Z", "2026-05-16T00:00:00Z", 14
        ) is True

    def test_14_days_old_does_not_exceed_14(self) -> None:
        """Boundary: exactly N days old is NOT past the threshold yet."""
        assert ar.is_retro_age_exceeded(
            "2026-05-01T00:00:00Z", "2026-05-15T00:00:00Z", 14
        ) is False

    def test_13_days_old_does_not_exceed_14(self) -> None:
        assert ar.is_retro_age_exceeded(
            "2026-05-01T00:00:00Z", "2026-05-14T00:00:00Z", 14
        ) is False

    def test_custom_days_threshold(self) -> None:
        assert ar.is_retro_age_exceeded(
            "2026-05-01T00:00:00Z", "2026-05-08T00:00:00Z", 7
        ) is False
        assert ar.is_retro_age_exceeded(
            "2026-05-01T00:00:00Z", "2026-05-09T00:00:00Z", 7
        ) is True

    def test_malformed_created_at_returns_false(self) -> None:
        """Fail-safe: unparseable timestamp must NOT auto-close."""
        assert ar.is_retro_age_exceeded(
            "not-a-date", "2026-05-16T00:00:00Z", 14
        ) is False

    def test_malformed_now_returns_false(self) -> None:
        assert ar.is_retro_age_exceeded(
            "2026-05-01T00:00:00Z", "not-a-date", 14
        ) is False

    def test_naive_timestamp_treated_as_utc(self) -> None:
        """ISO 8601 without timezone is read as UTC (fail-safe contract).

        GitHub API responses always carry the trailing ``Z``, but a
        test fixture or operator command might omit it; the sentinel
        should still produce a deterministic verdict.
        """
        assert ar.is_retro_age_exceeded(
            "2026-05-01T00:00:00", "2026-05-16T00:00:00", 14
        ) is True


class TestHasSentinelMarker:
    def test_returns_true_when_marker_present(self) -> None:
        comments = [
            {"body": f"{ar._SENTINEL_CLOSE_MARKER}\nclosed"},
        ]
        assert ar.has_sentinel_marker(comments) is True

    def test_returns_false_when_marker_absent(self) -> None:
        comments = [{"body": "regular operator comment"}]
        assert ar.has_sentinel_marker(comments) is False

    def test_returns_false_on_empty_list(self) -> None:
        assert ar.has_sentinel_marker([]) is False

    def test_marker_in_any_position_matches(self) -> None:
        comments = [
            {"body": "operator note"},
            {"body": f"prefix {ar._SENTINEL_CLOSE_MARKER} suffix"},
        ]
        assert ar.has_sentinel_marker(comments) is True


def _sentinel_recorder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    open_retros: list[dict[str, Any]] | None = None,
    comments_by_number: dict[int, list[dict[str, Any]]] | None = None,
    search_error: bool = False,
    comments_error_for: set[int] | None = None,
    post_error_for: set[int] | None = None,
    label_error_for: set[int] | None = None,
    patch_error_for: set[int] | None = None,
) -> list[tuple[str, str, Any]]:
    """Record gh_api calls for sentinel_run tests.

    Mirrors :func:`_orchestrator_recorder` for the run() flow. Each
    ``*_error_for`` set lists the retro issue numbers whose endpoints
    should raise :class:`_github_api.GitHubApiError` so the fail-soft
    contract can be exercised per-retro.
    """
    open_retros = open_retros or []
    comments_by_number = comments_by_number or {}
    comments_error_for = comments_error_for or set()
    post_error_for = post_error_for or set()
    label_error_for = label_error_for or set()
    patch_error_for = patch_error_for or set()
    seen: list[tuple[str, str, Any]] = []

    def _number_from_path(path: str) -> int:
        # Paths look like /repos/o/r/issues/123/comments or
        # /repos/o/r/issues/123; split and grab the integer segment.
        for part in path.split("?", 1)[0].split("/"):
            if part.isdigit():
                return int(part)
        return -1

    def fake_api(method, path, body=None, **_kw):
        seen.append((method, path, body))
        if method == "GET" and path.startswith("/search/issues"):
            if search_error:
                raise GitHubApiError(500, "GET", "/x", "search boom")
            return json.dumps({"items": open_retros})
        if method == "GET" and path.endswith("/comments?per_page=100"):
            number = _number_from_path(path)
            if number in comments_error_for:
                raise GitHubApiError(500, "GET", "/x", "comments boom")
            return json.dumps(comments_by_number.get(number, []))
        if method == "POST" and path.endswith("/comments"):
            number = _number_from_path(path)
            if number in post_error_for:
                raise GitHubApiError(500, "GET", "/x", "post boom")
            return ""
        if method == "POST" and path.endswith("/labels"):
            number = _number_from_path(path)
            if number in label_error_for:
                raise GitHubApiError(500, "GET", "/x", "label boom")
            return ""
        if method == "PATCH" and "/issues/" in path:
            number = _number_from_path(path)
            if number in patch_error_for:
                raise GitHubApiError(500, "GET", "/x", "patch boom")
            return ""
        return ""

    monkeypatch.setattr(ar, "gh_api", fake_api)
    return seen


def _open_retro(
    number: int,
    *,
    title: str = "fix(auto-retro): review PR #99 repair loops",
    created_at: str = "2026-05-01T00:00:00Z",
    body: str | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "created_at": created_at,
        "body": body if body is not None else _retro_body(checked=0),
    }


class TestSearchOpenRetroIssues:
    """The sentinel discovery query is built from the registry identity labels,
    mirroring :func:`auto_retro.fetch_past_retro_labels`."""

    def test_query_built_from_registry_identity_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[str] = []

        def fake(method: str, path: str, *_a: Any, **_kw: Any) -> str:
            captured.append(path)
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake)
        ar.search_open_retro_issues("o/r")
        assert len(captured) == 1
        path = captured[0]
        assert path.startswith("/search/issues?q=")
        assert "label%3Atype%3Adocs" in path
        # layer:p3-harness and the retired layer:meta OR together (comma-joined
        # within one label: qualifier) so retros from either era are found;
        # area:ci-ops is excluded from discovery (new-era-only, no old
        # counterpart; see _discovery_labels).
        assert "label%3Alayer%3Ap3-harness%2Clayer%3Ameta" in path
        assert "area%3Aci-ops" not in path
        assert "retro-opened" not in path
        assert "is%3Aopen" in path

    def test_drifted_registry_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise_key_error(path: str) -> tuple[str, ...]:
            raise KeyError(f"no label_consumers entry for path {path!r}")

        monkeypatch.setattr(ar._ssot, "consumer_labels", _raise_key_error)
        monkeypatch.setattr(
            ar, "gh_api", lambda *_a, **_kw: json.dumps({"items": []})
        )
        with pytest.raises(RuntimeError, match="auto-retro registry labels"):
            ar.search_open_retro_issues("o/r")


class TestSentinelRun:
    def test_closes_untouched_retro_past_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance #414 #3: time-based close path on the no-repair fixture."""
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(700)],
            comments_by_number={700: []},
        )
        assert ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14) == 0
        # retro:expired labelled, then comment posted, then issue patched
        # closed/not_planned.
        post = [
            (m, p, b) for m, p, b in seen
            if m == "POST" and p == "/repos/o/r/issues/700/comments"
        ]
        label = [
            (m, p, b) for m, p, b in seen
            if m == "POST" and p == "/repos/o/r/issues/700/labels"
        ]
        patch = [
            (m, p, b) for m, p, b in seen
            if m == "PATCH" and p == "/repos/o/r/issues/700"
        ]
        assert len(post) == 1
        assert ar._SENTINEL_CLOSE_MARKER in post[0][2]["body"]
        assert "14 days" in post[0][2]["body"]
        assert "#414" in post[0][2]["body"]
        assert len(label) == 1
        assert label[0][2] == {"labels": [rl.RETRO_EXPIRED]}
        assert len(patch) == 1
        assert patch[0][2] == {"state": "closed", "state_reason": "not_planned"}

    def test_label_precedes_post_precedes_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The retro:expired label must land before the sentinel comment,
        which must land before the close patch.

        Label-first is deliberate: the idempotency gate
        (:func:`ar.has_sentinel_marker`) keys on the comment marker, not
        the label, so a label failure leaves no marker behind and the
        next cron tick retries this retro from scratch instead of
        getting stuck (Refs #2439 review)."""
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(701)],
            comments_by_number={701: []},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        label_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues/701/labels"
        )
        post_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "POST" and p == "/repos/o/r/issues/701/comments"
        )
        patch_idx = next(
            i for i, (m, p, _b) in enumerate(seen)
            if m == "PATCH" and p == "/repos/o/r/issues/701"
        )
        assert label_idx < post_idx < patch_idx

    def test_skips_retro_inside_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[
                _open_retro(702, created_at="2026-05-19T00:00:00Z"),
            ],
            comments_by_number={702: []},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        # Inside window: never fetched comments, never posted, never patched.
        assert not any(
            "/issues/702" in p for _m, p, _b in seen
        )

    def test_skips_retro_with_operator_checkbox(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance #414 #2: actionable repair case (operator engaged).

        Mirrors the #399 real-repair fixture pattern: operator has
        flipped acceptance criteria, so the sentinel must not auto-close.
        """
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[
                _open_retro(703, body=_retro_body(checked=5)),
            ],
            comments_by_number={703: []},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        assert not any(
            m == "PATCH" and p == "/repos/o/r/issues/703"
            for m, p, _b in seen
        )
        assert not any(
            m == "POST" and p == "/repos/o/r/issues/703/comments"
            for m, p, _b in seen
        )

    def test_skips_retro_with_operator_comment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(704)],
            comments_by_number={
                704: [{"user": {"login": "tvna"}, "body": "triaged"}]
            },
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        assert not any(
            m == "PATCH" and p == "/repos/o/r/issues/704"
            for m, p, _b in seen
        )

    def test_idempotent_when_sentinel_marker_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Re-running the cron on an already-closed retro is a no-op.

        The marker check fires before the close PATCH so the sentinel
        cannot double-close (and the retro state is preserved if it
        was reopened by the operator after the first close).
        """
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(705)],
            comments_by_number={
                705: [
                    {
                        "user": {"login": "github-actions[bot]"},
                        "body": f"{ar._SENTINEL_CLOSE_MARKER}\nold",
                    }
                ]
            },
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        assert not any(
            m == "PATCH" and p == "/repos/o/r/issues/705"
            for m, p, _b in seen
        )
        assert not any(
            m == "POST" and p == "/repos/o/r/issues/705/comments"
            for m, p, _b in seen
        )

    def test_one_retro_failure_does_not_block_others(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail-soft: a GitHubApiError on retro #706 must NOT stop
        the sentinel from processing #707 on the same tick."""
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(706), _open_retro(707)],
            comments_by_number={706: [], 707: []},
            comments_error_for={706},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        # #707 still gets posted + patched even though #706's comments fetch raised.
        assert any(
            m == "POST" and p == "/repos/o/r/issues/707/comments"
            for m, p, _b in seen
        )
        assert any(
            m == "PATCH" and p == "/repos/o/r/issues/707"
            for m, p, _b in seen
        )
        # #706 never reached its close PATCH (the failure short-circuited).
        assert not any(
            m == "PATCH" and p == "/repos/o/r/issues/706"
            for m, p, _b in seen
        )

    def test_close_failure_after_comment_does_not_re_post(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the close PATCH fails after the comment landed, the next
        cron tick must rely on the sentinel marker check to avoid
        re-posting (no comment double-post on retry).
        """
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(708)],
            comments_by_number={708: []},
            patch_error_for={708},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        # Comment was posted on this tick; close failed; sentinel logs
        # but does not crash.
        post = [
            (m, p, b) for m, p, b in seen
            if m == "POST" and p == "/repos/o/r/issues/708/comments"
        ]
        assert len(post) == 1

    def test_post_failure_does_not_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the sentinel comment POST fails, the close must NOT fire
        (operator would see a silent close without explanation). The
        label step runs first and already succeeded on this tick."""
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(709)],
            comments_by_number={709: []},
            post_error_for={709},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        assert not any(
            m == "PATCH" and p == "/repos/o/r/issues/709"
            for m, p, _b in seen
        )
        assert any(
            m == "POST" and p == "/repos/o/r/issues/709/labels"
            for m, p, _b in seen
        )

    def test_label_failure_does_not_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the retro:expired label POST fails, neither the sentinel
        comment nor the close must fire on this tick: label runs first
        (Refs #2439 review) so a failure here leaves no sentinel-comment
        marker behind, and the next cron tick retries this retro from
        scratch instead of getting stuck."""
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(715)],
            comments_by_number={715: []},
            label_error_for={715},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        assert not any(
            m == "PATCH" and p == "/repos/o/r/issues/715"
            for m, p, _b in seen
        )
        assert not any(
            m == "POST" and p == "/repos/o/r/issues/715/comments"
            for m, p, _b in seen
        )

    def test_search_failure_returns_zero_with_no_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Search-endpoint failure short-circuits the entire tick."""
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(710)],
            search_error=True,
        )
        assert ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14) == 0
        # No per-retro endpoints touched.
        assert not any(
            "/issues/710" in p for _m, p, _b in seen
        )

    def test_does_not_touch_source_pr_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance #414 #5: ops:retro-opened label gate preserved.

        The sentinel must never PATCH/POST/DELETE the SOURCE PR's
        labels; that label was applied at retro-create time and
        survives the sentinel close. The sentinel does POST to the
        retro ISSUE's own labels endpoint (to add retro:expired,
        Refs #2433); this test asserts every /labels call seen targets
        only the retro issue itself (#711), never any other number.
        """
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[_open_retro(711)],
            comments_by_number={711: []},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        label_calls = [(m, p, b) for m, p, b in seen if p.endswith("/labels")]
        assert label_calls == [
            ("POST", "/repos/o/r/issues/711/labels", {"labels": [rl.RETRO_EXPIRED]})
        ]

    def test_non_retro_titled_issue_is_filtered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Search-filter belt-and-braces: an issue that slips into the
        search result but is not a fix(auto-retro) title must NOT be
        processed. The client-side filter inside search_open_retro_issues
        is the second line of defence after the search query labels.
        """
        seen = _sentinel_recorder(
            monkeypatch,
            open_retros=[
                {
                    "number": 712,
                    "title": "feat(harness): not a retro at all",
                    "created_at": "2026-05-01T00:00:00Z",
                    "body": _retro_body(checked=0),
                },
            ],
            comments_by_number={712: []},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        assert not any("/issues/712" in p for _m, p, _b in seen)

    def test_step_summary_written(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        _sentinel_recorder(
            monkeypatch,
            open_retros=[
                _open_retro(713),
                _open_retro(714, created_at="2026-05-19T00:00:00Z"),
            ],
            comments_by_number={713: [], 714: []},
        )
        ar.sentinel_run("o/r", "2026-05-20T00:00:00Z", 14)
        text = summary.read_text(encoding="utf-8")
        assert "## auto-retro sentinel summary" in text
        assert "14 days" in text
        assert "#713" in text
        assert "#714" in text
        assert "inside inactivity window" in text


class TestBuildSentinelSummary:
    def test_reports_counts(self) -> None:
        text = ar._build_sentinel_summary(
            [11, 12], [(13, "inside inactivity window")], 14
        )
        assert "Closed: 2" in text
        assert "Skipped: 1" in text
        assert "#11" in text
        assert "#13 (inside inactivity window)" in text

    def test_long_closed_list_is_capped_with_overflow(self) -> None:
        text = ar._build_sentinel_summary(list(range(1, 9)), [], 14)
        assert "Closed: 8" in text
        assert "#5" in text
        assert "#6" not in text
        assert "(+3 more)" in text


class TestSentinelCli:
    def test_cli_missing_repo_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        assert ar.main(["sentinel"]) == 1
        assert "missing --repo" in capsys.readouterr().err

    def test_cli_invalid_days_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.setenv("AUTO_RETRO_SENTINEL_DAYS", "not-a-number")
        # Avoid the search call by stubbing gh_api.
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "")
        assert ar.main(["sentinel"]) == 1
        err = capsys.readouterr().err
        assert "invalid sentinel days" in err

    def test_cli_zero_days_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "")
        assert ar.main(["sentinel", "--days", "0"]) == 1
        assert "must be positive" in capsys.readouterr().err

    def test_cli_default_days_used_when_unset(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--days unset + env unset => _DEFAULT_SENTINEL_DAYS."""
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.delenv("AUTO_RETRO_SENTINEL_DAYS", raising=False)
        captured: dict[str, Any] = {}

        def fake_run(repo: str, now_iso: str, days: int) -> int:
            captured["days"] = days
            return 0

        monkeypatch.setattr(ar, "sentinel_run", fake_run)
        assert ar.main(["sentinel"]) == 0
        assert captured["days"] == ar._DEFAULT_SENTINEL_DAYS


def test_sentinel_workflow_file_exists_and_runs_sentinel_subcommand() -> None:
    """The schedule workflow that backs sentinel_run must exist and
    invoke the right CLI subcommand. Drift between the script and the
    workflow would silently disable the sentinel.

    The sentinel was consolidated into daily-maintenance.yml (issue #1319);
    its scan-and-close job preserves the original cron, permissions, and CLI
    invocation.
    """
    repo_root = Path(__file__).resolve().parent.parent
    workflow = repo_root / ".github" / "workflows" / "daily-maintenance.yml"
    assert workflow.exists(), (
        "Strategy B sentinel needs .github/workflows/daily-maintenance.yml "
        "(issue #414, consolidated in #1319)"
    )
    text = workflow.read_text(encoding="utf-8")
    assert "python3 scripts/auto_retro.py sentinel" in text
    assert "schedule:" in text
    # The label-touching pull-requests permission must NOT be granted:
    # the sentinel only acts on retro issues and the source-PR label was
    # already applied by .github/workflows/post-merge.yml.
    assert "pull-requests: write" not in text


class TestHistoricalRetroFixtures:
    """Acceptance #414 #4: re-evaluate one historical retro against the harness.

    Uses literal body snippets mirroring the shape of #399 (real
    repair, operator-triaged) and a generic noise retro (no
    operator engagement, all-unchecked). The assertion is the
    binary verdict (touched vs. untouched) the sentinel would compute.
    """

    def test_real_repair_fixture_is_touched(self) -> None:
        # Mirrors retro #399 after operator triage: all 5 acceptance
        # checkboxes flipped, classification table filled. The
        # sentinel must classify this as touched and therefore skip.
        body_399_like = (
            "## Acceptance criteria\n\n"
            "- [x] Repair history table complete.\n"
            "- [x] Each repair classified with the section 3 taxonomy.\n"
            "- [x] Each repair has an earliest prevention point.\n"
            "- [x] No-repair reproduction path stated.\n"
            "- [x] `## Follow-up issues` filed (or explicitly stated `(none)`).\n"
        )
        assert ar.is_retro_untouched(body_399_like, []) is False

    def test_noise_retro_fixture_is_untouched(self) -> None:
        # Mirrors a batch-closed noise retro: all 5 acceptance
        # checkboxes still unchecked, no operator comment landed
        # before the operator closed it manually. Had the sentinel
        # been in place, it would have closed this on the next tick.
        body_noise_like = (
            "## Acceptance criteria\n\n"
            "- [ ] Repair history table complete.\n"
            "- [ ] Each repair classified with the section 3 taxonomy.\n"
            "- [ ] Each repair has an earliest prevention point.\n"
            "- [ ] No-repair reproduction path stated.\n"
            "- [ ] `## Follow-up issues` filed (or explicitly stated `(none)`).\n"
        )
        assert ar.is_retro_untouched(body_noise_like, []) is True


# ---------------------------------------------------------------------------
# PR2: label-derived prior (refs #582)
# ---------------------------------------------------------------------------


class TestRetroLabelsPriorConstants:
    """The four prior thresholds must satisfy the documented relationships.

    Catches accidental edits to ``scripts/_retro_labels.py`` that would
    invert the band ordering (tentative >= skip) or zero out the
    sample-size safety net.
    """

    def test_skip_threshold_above_tentative(self) -> None:
        assert rl.PRIOR_SKIP_THRESHOLD > rl.PRIOR_TENTATIVE_THRESHOLD

    def test_tentative_threshold_in_unit_range(self) -> None:
        assert 0.0 < rl.PRIOR_TENTATIVE_THRESHOLD < 1.0

    def test_skip_threshold_in_unit_range(self) -> None:
        assert 0.0 < rl.PRIOR_SKIP_THRESHOLD <= 1.0

    def test_min_sample_size_is_positive(self) -> None:
        assert rl.PRIOR_MIN_SAMPLE_SIZE >= 1

    def test_fetch_limit_is_reasonable(self) -> None:
        # Anything outside [1, 100] would either neuter the prior or
        # exceed GitHub's search per_page max.
        assert 1 <= rl.PRIOR_FETCH_LIMIT <= 100


class TestRenderSignalsFiredLine:
    """``- Signals fired:`` line shape consumed by parse_signals_from_retro_body."""

    def test_empty_signals_dict_renders_none(self) -> None:
        assert ar.render_signals_fired_line({}) == "- Signals fired: (none)"

    def test_all_false_renders_none(self) -> None:
        signals = {name: False for name in ar._SIGNAL_NAMES}
        assert ar.render_signals_fired_line(signals) == "- Signals fired: (none)"

    def test_single_signal_fired(self) -> None:
        signals = {name: False for name in ar._SIGNAL_NAMES}
        signals["multi_commit_pr"] = True
        assert (
            ar.render_signals_fired_line(signals)
            == "- Signals fired: multi_commit_pr"
        )

    def test_preserves_signal_declaration_order(self) -> None:
        # Even if the dict is built out of order, the line follows the
        # canonical _SIGNAL_NAMES tuple. Required for byte-identical
        # bodies on re-run.
        signals = {
            "multi_commit_pr": True,
            "inline_review_comments": True,
            "body_cites_refs": False,
            "fix_typed_title": True,
            "verification_pairs_failed": False,
        }
        assert ar.render_signals_fired_line(signals) == (
            "- Signals fired: inline_review_comments, "
            "fix_typed_title, multi_commit_pr"
        )

    def test_unknown_signal_names_are_dropped(self) -> None:
        # An accidental extra key from a future signal added without
        # updating _SIGNAL_NAMES must not leak into the line.
        signals = {"future_unknown_signal": True, "multi_commit_pr": True}
        assert (
            ar.render_signals_fired_line(signals)
            == "- Signals fired: multi_commit_pr"
        )


class TestParseSignalsFromRetroBody:
    """Round-trip parser for the ``- Signals fired:`` Facts line."""

    def test_empty_body_returns_empty(self) -> None:
        assert ar.parse_signals_from_retro_body("") == frozenset()

    def test_body_without_signals_line_returns_empty(self) -> None:
        # Pre-#582 legacy retros must contribute zero observations.
        body = "## Facts\n\n- Source PR: #1; feat(x): hi\n"
        assert ar.parse_signals_from_retro_body(body) == frozenset()

    def test_none_sentinel_returns_empty(self) -> None:
        body = "## Facts\n\n- Signals fired: (none)\n"
        assert ar.parse_signals_from_retro_body(body) == frozenset()

    def test_single_signal_parses(self) -> None:
        body = "## Facts\n\n- Signals fired: multi_commit_pr\n"
        assert ar.parse_signals_from_retro_body(body) == frozenset(
            {"multi_commit_pr"}
        )

    def test_multi_signal_parses(self) -> None:
        body = (
            "## Facts\n\n- Signals fired: "
            "inline_review_comments, multi_commit_pr, fix_typed_title\n"
        )
        assert ar.parse_signals_from_retro_body(body) == frozenset(
            {"inline_review_comments", "multi_commit_pr", "fix_typed_title"}
        )

    def test_unknown_signal_names_are_filtered(self) -> None:
        # A retro body could be edited by hand to include a typo; the
        # parser refuses to populate the prior with names not in the
        # canonical _SIGNAL_NAMES tuple.
        body = (
            "## Facts\n\n- Signals fired: "
            "multi_commit_pr, made_up_signal_typo\n"
        )
        assert ar.parse_signals_from_retro_body(body) == frozenset(
            {"multi_commit_pr"}
        )

    def test_html_comment_signals_line_is_ignored(self) -> None:
        # An HTML-commented heading must NOT leak into the parser
        # output; the strip_html_comments boundary is exercised.
        body = (
            "## Facts\n\n<!-- - Signals fired: multi_commit_pr -->\n"
            "- Signals fired: fix_typed_title\n"
        )
        assert ar.parse_signals_from_retro_body(body) == frozenset(
            {"fix_typed_title"}
        )

    def test_render_and_parse_round_trip(self) -> None:
        for active in (
            set(),
            {"multi_commit_pr"},
            {"inline_review_comments", "fix_typed_title"},
            set(ar._SIGNAL_NAMES),
        ):
            signals = {name: name in active for name in ar._SIGNAL_NAMES}
            line = ar.render_signals_fired_line(signals)
            body = f"## Facts\n\n{line}\n"
            assert ar.parse_signals_from_retro_body(body) == frozenset(active)


class TestComputePriorFromLabels:
    """Per-signal FP rate computation from a population of past retros."""

    def test_empty_population_yields_zero_with_zero_sample(self) -> None:
        prior = ar.compute_prior_from_labels([])
        for name in ar._SIGNAL_NAMES:
            assert prior[name] == (0.0, 0)

    def test_single_fp_retro_yields_full_fp_rate(self) -> None:
        past = [
            ar.PastRetro(
                number=1,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_FP}),
            )
        ]
        prior = ar.compute_prior_from_labels(past)
        assert prior["multi_commit_pr"] == (1.0, 1)
        # Other signals untouched.
        assert prior["inline_review_comments"] == (0.0, 0)

    def test_single_tp_retro_yields_zero_fp_rate(self) -> None:
        past = [
            ar.PastRetro(
                number=2,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_TP}),
            )
        ]
        prior = ar.compute_prior_from_labels(past)
        assert prior["multi_commit_pr"] == (0.0, 1)

    def test_mixed_population_computes_fp_rate(self) -> None:
        # 3 fp, 2 tp over the same signal -> 0.6 / 5.
        past = [
            ar.PastRetro(
                number=i,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_FP if i < 3 else rl.RETRO_TP}),
            )
            for i in range(5)
        ]
        prior = ar.compute_prior_from_labels(past)
        rate, sample = prior["multi_commit_pr"]
        assert sample == 5
        assert abs(rate - 0.6) < 1e-9

    def test_signals_with_no_observations_yield_zero(self) -> None:
        # A retro with signal A only must not contribute to signal B.
        past = [
            ar.PastRetro(
                number=1,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_FP}),
            )
        ]
        prior = ar.compute_prior_from_labels(past)
        assert prior["fix_typed_title"] == (0.0, 0)

    def test_unlabelled_retros_count_toward_denominator_only(self) -> None:
        # A past retro with no retro:tp/fp label still observes the
        # signal; it just doesn't move the numerator. This is the
        # "operator hasn't closed yet" case.
        past = [
            ar.PastRetro(
                number=1,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset(),
            ),
            ar.PastRetro(
                number=2,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_FP}),
            ),
        ]
        prior = ar.compute_prior_from_labels(past)
        assert prior["multi_commit_pr"] == (0.5, 2)

    def test_epoch_cutoff_excludes_pre_epoch_retros(self) -> None:
        # Refs #1227, #1236: retros below the epoch boundary measured the old
        # signal semantics and must not drive the prior. With the cutoff,
        # only the post-epoch retro contributes; the pre-epoch fp retro
        # is dropped, so the signal degrades to the empty-prior net.
        past = [
            ar.PastRetro(
                number=900,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_FP}),
            ),
            ar.PastRetro(
                number=1300,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_TP}),
            ),
        ]
        # Pure tally (default epoch) sees both -> 1 fp of 2.
        assert ar.compute_prior_from_labels(past)[
            "multi_commit_pr"
        ] == (0.5, 2)
        # With the epoch boundary the pre-epoch fp retro is excluded.
        gated = ar.compute_prior_from_labels(past, epoch_min_number=1228)
        assert gated["multi_commit_pr"] == (0.0, 1)

    def test_expired_label_does_not_affect_fp_rate(self) -> None:
        """retro:expired is a weak signal only: it must never be counted
        as a false positive by compute_prior_from_labels (which keys on
        RETRO_FP alone), even though it is now part of ALL_RETRO_LABELS
        for triage-report display purposes. Refs #2433, #2439 review."""
        past = [
            ar.PastRetro(
                number=1,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_EXPIRED}),
            )
        ]
        prior = ar.compute_prior_from_labels(past)
        assert prior["multi_commit_pr"] == (0.0, 1)


class TestRetroExpiredTriageWiring:
    """RETRO_EXPIRED must be visible to the triage report so a
    sentinel-closed retro is distinguishable from evidence that was
    never labelled at all. Refs #2433, #2439 review."""

    def test_expired_only_retro_is_not_counted_as_unlabelled(self) -> None:
        past = [
            ar.PastRetro(
                number=1,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset({rl.RETRO_EXPIRED}),
            )
        ]
        report = ar.compute_triage_report(past)
        assert report.label_counts[rl.RETRO_EXPIRED] == 1
        assert report.label_counts["unlabelled"] == 0

    def test_truly_unlabelled_retro_still_counts_as_unlabelled(self) -> None:
        past = [
            ar.PastRetro(
                number=1,
                signals=frozenset({"multi_commit_pr"}),
                labels=frozenset(),
            )
        ]
        report = ar.compute_triage_report(past)
        assert report.label_counts[rl.RETRO_EXPIRED] == 0
        assert report.label_counts["unlabelled"] == 1

    def test_retro_status_reports_expired(self) -> None:
        assert ar._retro_status(frozenset({rl.RETRO_EXPIRED})) == rl.RETRO_EXPIRED

    def test_retro_status_prefers_operator_label_over_expired(self) -> None:
        # A retro the sentinel closed but an operator later triaged must
        # display the stronger, operator-set status, not the weak
        # sentinel signal.
        assert (
            ar._retro_status(frozenset({rl.RETRO_EXPIRED, rl.RETRO_TP}))
            == rl.RETRO_TP
        )


class TestShouldSkipByPrior:
    """Skip-band verdict over the active signal set."""

    def _signals_with(self, *active: str) -> dict[str, bool]:
        return {name: name in active for name in ar._SIGNAL_NAMES}

    def test_empty_prior_does_not_skip(self) -> None:
        skip, reason = ar.should_skip_by_prior(
            self._signals_with("multi_commit_pr"), {}
        )
        assert skip is False
        assert reason == ""

    def test_inactive_signal_with_high_fp_rate_does_not_skip(self) -> None:
        # multi_commit_pr is the high-FP signal, but it did NOT fire on
        # the current PR; the prior should not block.
        prior = {"multi_commit_pr": (0.9, 10)}
        skip, _reason = ar.should_skip_by_prior(
            self._signals_with("inline_review_comments"), prior
        )
        assert skip is False

    def test_active_signal_above_threshold_with_enough_sample_skips(
        self,
    ) -> None:
        prior = {"multi_commit_pr": (0.6, 10)}
        skip, reason = ar.should_skip_by_prior(
            self._signals_with("multi_commit_pr"), prior
        )
        assert skip is True
        assert "multi_commit_pr" in reason
        assert "0.60" in reason
        assert "n=10" in reason

    def test_active_signal_at_threshold_skips(self) -> None:
        # ``>=`` boundary: exactly at the threshold is the skip band.
        prior = {
            "multi_commit_pr": (rl.PRIOR_SKIP_THRESHOLD, rl.PRIOR_MIN_SAMPLE_SIZE)
        }
        skip, _reason = ar.should_skip_by_prior(
            self._signals_with("multi_commit_pr"), prior
        )
        assert skip is True

    def test_insufficient_sample_size_does_not_skip(self) -> None:
        # The empty-prior safety net: a tiny population must not
        # confidently skip even if the FP rate is high.
        prior = {"multi_commit_pr": (1.0, rl.PRIOR_MIN_SAMPLE_SIZE - 1)}
        skip, _reason = ar.should_skip_by_prior(
            self._signals_with("multi_commit_pr"), prior
        )
        assert skip is False

    def test_max_fp_signal_wins_over_lower_active(self) -> None:
        prior = {
            "multi_commit_pr": (0.6, 10),
            "fix_typed_title": (0.2, 10),
        }
        skip, reason = ar.should_skip_by_prior(
            self._signals_with("multi_commit_pr", "fix_typed_title"), prior
        )
        assert skip is True
        assert "multi_commit_pr" in reason


class TestIsTentativeByPrior:
    """Tentative-band verdict between tentative and skip thresholds."""

    def _signals_with(self, *active: str) -> dict[str, bool]:
        return {name: name in active for name in ar._SIGNAL_NAMES}

    def test_fp_rate_in_band_returns_true(self) -> None:
        # 0.4 sits in [0.3, 0.5).
        prior = {"multi_commit_pr": (0.4, 10)}
        assert (
            ar.is_tentative_by_prior(
                self._signals_with("multi_commit_pr"), prior
            )
            is True
        )

    def test_fp_rate_at_tentative_threshold_returns_true(self) -> None:
        prior = {
            "multi_commit_pr": (
                rl.PRIOR_TENTATIVE_THRESHOLD,
                rl.PRIOR_MIN_SAMPLE_SIZE,
            )
        }
        assert (
            ar.is_tentative_by_prior(
                self._signals_with("multi_commit_pr"), prior
            )
            is True
        )

    def test_fp_rate_at_skip_threshold_returns_false(self) -> None:
        # The skip threshold belongs to the skip band, not tentative.
        prior = {
            "multi_commit_pr": (
                rl.PRIOR_SKIP_THRESHOLD,
                rl.PRIOR_MIN_SAMPLE_SIZE,
            )
        }
        assert (
            ar.is_tentative_by_prior(
                self._signals_with("multi_commit_pr"), prior
            )
            is False
        )

    def test_fp_rate_below_tentative_returns_false(self) -> None:
        prior = {"multi_commit_pr": (0.1, 10)}
        assert (
            ar.is_tentative_by_prior(
                self._signals_with("multi_commit_pr"), prior
            )
            is False
        )

    def test_insufficient_sample_size_returns_false(self) -> None:
        prior = {"multi_commit_pr": (0.4, rl.PRIOR_MIN_SAMPLE_SIZE - 1)}
        assert (
            ar.is_tentative_by_prior(
                self._signals_with("multi_commit_pr"), prior
            )
            is False
        )


class TestIssueLabelsTentative:
    """``retro:tentative`` is added only when explicitly requested."""

    _BASE: ClassVar[list[str]] = ["type:docs", "layer:meta"]

    def test_default_no_tentative_label(self) -> None:
        labels = ar.issue_labels((), self._BASE)
        assert rl.RETRO_TENTATIVE not in labels

    def test_tentative_true_appends_label(self) -> None:
        labels = ar.issue_labels((), self._BASE, tentative=True)
        assert rl.RETRO_TENTATIVE in labels
        # Required labels still present in declared order.
        assert labels[0] == "type:docs"
        assert labels[1] == "layer:meta"

    def test_tentative_true_with_layer_labels(self) -> None:
        labels = ar.issue_labels(("layer:python",), self._BASE, tentative=True)
        assert "layer:python" in labels
        assert rl.RETRO_TENTATIVE in labels

    def test_tentative_is_keyword_only(self) -> None:
        # Refs #582: ``tentative`` must be keyword-only so positional
        # callers cannot accidentally pass a truthy layer-label tuple.
        import inspect

        sig = inspect.signature(ar.issue_labels)
        param = sig.parameters["tentative"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY


class TestBuildRetroBodyEmitsSignalsLine:
    """``build_retro_body`` writes the new ``Signals fired:`` line."""

    def _pr(self) -> ar.MergedPR:
        return ar.MergedPR(
            number=1,
            title="feat(x): hi",
            merged=True,
            merged_at="2026-05-28T00:00:00Z",
            merged_by_login="tvna",
            user_login="tvna",
            layer_labels=(),
            html_url="https://example/1",
            body="",
            commits=1,
        )

    def test_no_signals_arg_renders_none_sentinel(self) -> None:
        body = ar.build_retro_body(self._pr(), ["chore: x"])
        assert "- Signals fired: (none)" in body

    def test_signals_arg_renders_fired_names(self) -> None:
        signals = {name: False for name in ar._SIGNAL_NAMES}
        signals["multi_commit_pr"] = True
        signals["fix_typed_title"] = True
        body = ar.build_retro_body(self._pr(), ["fix: x"], signals=signals)
        # Canonical ordering from _SIGNAL_NAMES.
        assert (
            "- Signals fired: fix_typed_title, multi_commit_pr" in body
        )

    def test_signals_line_round_trips_via_parser(self) -> None:
        signals = {name: False for name in ar._SIGNAL_NAMES}
        signals["inline_review_comments"] = True
        body = ar.build_retro_body(self._pr(), ["x"], signals=signals)
        assert ar.parse_signals_from_retro_body(body) == frozenset(
            {"inline_review_comments"}
        )


class TestFetchPastRetroLabels:
    """Side-effect: search query shape and PastRetro reconstruction."""

    def test_search_query_matches_scanner_convention(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[str] = []

        def fake(method: str, path: str, *_a: Any, **_kw: Any) -> str:
            captured.append(path)
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake)
        ar.fetch_past_retro_labels("o/r")
        assert len(captured) == 1
        path = captured[0]
        assert path.startswith("/search/issues?q=")
        # The query must include the identity labels so PR1's scanner and PR2's
        # prior populate from the same set, and must NOT include the terminal
        # *retro-opened labels (those are excluded from the discovery query).
        assert "label%3Atype%3Adocs" in path
        # layer:p3-harness and the retired layer:meta OR together; area:ci-ops
        # is excluded from discovery (new-era-only; see _discovery_labels).
        assert "label%3Alayer%3Ap3-harness%2Clayer%3Ameta" in path
        assert "area%3Aci-ops" not in path
        assert "retro-opened" not in path
        assert "retro" in path

    def test_search_query_built_from_registry_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The label: clauses are derived from _ssot.consumer_labels (identity
        family only), not hardcoded: a synthetic registry set flows into the
        query and the *retro-opened terminal labels are dropped."""
        captured: list[str] = []

        def fake(method: str, path: str, *_a: Any, **_kw: Any) -> str:
            captured.append(path)
            return json.dumps({"items": []})

        monkeypatch.setattr(
            ar._ssot,
            "consumer_labels",
            lambda path: (
                "id:a",
                "layer:other",
                "ops:custom-retro-opened",
                "harness:custom-retro-opened",
            ),
        )
        monkeypatch.setattr(ar, "gh_api", fake)
        ar.fetch_past_retro_labels("o/r")
        path = captured[0]
        assert "label%3Aid%3Aa" in path
        assert "label%3Alayer%3Aother" in path
        assert "retro-opened" not in path

    def test_drifted_registry_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A drifted registry is a config error, not a transient search error:
        it propagates loud rather than soft-failing to an empty prior."""
        def _raise_key_error(path: str) -> tuple[str, ...]:
            raise KeyError(f"no label_consumers entry for path {path!r}")

        monkeypatch.setattr(ar._ssot, "consumer_labels", _raise_key_error)
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: json.dumps({"items": []}))
        with pytest.raises(RuntimeError, match="auto-retro registry labels"):
            ar.fetch_past_retro_labels("o/r")

    def test_all_labels_terminal_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A registry that leaves only terminal labels must fail loud rather
        than drop every label: clause and scan every issue titled retro."""
        monkeypatch.setattr(
            ar._ssot,
            "consumer_labels",
            lambda path: ("ops:retro-opened", "harness:retro-opened"),
        )
        monkeypatch.setattr(
            ar._ssot, "consumer_discovery_only_labels", lambda path: ()
        )
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: json.dumps({"items": []}))
        with pytest.raises(RuntimeError, match="auto-retro registry labels"):
            ar.fetch_past_retro_labels("o/r")

    def test_parses_items_into_past_retro_records(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = {
            "items": [
                {
                    "number": 100,
                    "labels": [
                        {"name": "type:docs"},
                        {"name": "layer:meta"},
                        {"name": rl.RETRO_FP},
                    ],
                    "body": (
                        "## Facts\n\n- Signals fired: multi_commit_pr\n"
                    ),
                },
                {
                    "number": 101,
                    "labels": [{"name": rl.RETRO_TP}],
                    "body": (
                        "## Facts\n\n- Signals fired: "
                        "inline_review_comments, fix_typed_title\n"
                    ),
                },
            ]
        }
        monkeypatch.setattr(
            ar, "gh_api", lambda *_a, **_kw: json.dumps(payload)
        )
        past = ar.fetch_past_retro_labels("o/r")
        assert len(past) == 2
        assert past[0].number == 100
        assert past[0].signals == frozenset({"multi_commit_pr"})
        assert rl.RETRO_FP in past[0].labels
        assert past[1].number == 101
        assert past[1].signals == frozenset(
            {"inline_review_comments", "fix_typed_title"}
        )

    def test_parses_state_and_title_with_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """state/title populate the #1386 dashboard; absent fields default."""
        payload = {
            "items": [
                {
                    "number": 100,
                    "labels": [],
                    "body": "",
                    "state": "closed",
                    "title": "chore(auto-retro): review PR #42 repair loops",
                },
                {"number": 101, "labels": [], "body": ""},
            ]
        }
        monkeypatch.setattr(
            ar, "gh_api", lambda *_a, **_kw: json.dumps(payload)
        )
        past = ar.fetch_past_retro_labels("o/r")
        assert past[0].state == "closed"
        assert past[0].title == "chore(auto-retro): review PR #42 repair loops"
        # Missing fields fall back to the pre-#1386 defaults.
        assert past[1].state == "open"
        assert past[1].title == ""

    def test_limit_truncates_items(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        items = [
            {"number": i, "labels": [], "body": ""} for i in range(10)
        ]
        monkeypatch.setattr(
            ar,
            "gh_api",
            lambda *_a, **_kw: json.dumps({"items": items}),
        )
        out = ar.fetch_past_retro_labels("o/r", limit=3)
        assert len(out) == 3

    def test_search_failure_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: Any, **_kw: Any) -> str:
            raise GitHubApiError(500, "GET", "/x", "boom")

        monkeypatch.setattr(ar, "gh_api", boom)
        # Soft-fail: the retro flow proceeds with empty prior.
        assert ar.fetch_past_retro_labels("o/r") == []

    def test_malformed_json_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: "not-json")
        assert ar.fetch_past_retro_labels("o/r") == []

    def test_legacy_body_without_signals_line_yields_empty_signals(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pre-#582 retros have no Signals fired line; they still
        # populate as PastRetro records but contribute zero
        # signal-observations to the prior. Refs #582.
        monkeypatch.setattr(
            ar,
            "gh_api",
            lambda *_a, **_kw: json.dumps(
                {
                    "items": [
                        {
                            "number": 50,
                            "labels": [{"name": rl.RETRO_FP}],
                            "body": "## Facts\n\n- Source PR: #1\n",
                        }
                    ]
                }
            ),
        )
        past = ar.fetch_past_retro_labels("o/r")
        assert past[0].signals == frozenset()
        assert rl.RETRO_FP in past[0].labels

    def test_query_sorted_by_created_desc(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The fetch must sample the most RECENT retros when the live
        population exceeds the fetch limit, not GitHub's best-match default
        order (issue #2413 defect b)."""
        captured: list[str] = []

        def fake(method: str, path: str, *_a: Any, **_kw: Any) -> str:
            captured.append(path)
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake)
        ar.fetch_past_retro_labels("o/r")
        assert "sort=created&order=desc" in captured[0]

    def test_discovery_query_includes_type_retrospective_family(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """type:retrospective is registered as a discovery-only label:
        hand-triaged in-session retros carry it WITHOUT type:docs, so the
        discovery query must OR it into the type: family clause instead of
        structurally excluding that population (issue #2413 defect c)."""
        captured: list[str] = []

        def fake(method: str, path: str, *_a: Any, **_kw: Any) -> str:
            captured.append(path)
            return json.dumps({"items": []})

        monkeypatch.setattr(ar, "gh_api", fake)
        ar.fetch_past_retro_labels("o/r")
        path = captured[0]
        assert "label%3Atype%3Adocs%2Ctype%3Aretrospective" in path

    def test_type_retrospective_only_retro_is_counted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A retro carrying type:retrospective + layer:p3-harness WITHOUT
        type:docs (the hand-triaged shape from #2011/#2114/#2121) must still
        parse into a PastRetro and count toward the triage totals. Refs
        #2413."""
        payload = {
            "total_count": 1,
            "items": [
                {
                    "number": 2011,
                    "labels": [
                        {"name": "type:retrospective"},
                        {"name": "layer:p3-harness"},
                        {"name": rl.RETRO_TP},
                    ],
                    "body": "## Facts\n\n- Signals fired: multi_commit_pr\n",
                }
            ],
        }
        monkeypatch.setattr(ar, "gh_api", lambda *_a, **_kw: json.dumps(payload))
        past, total = ar.fetch_past_retro_population("o/r")
        assert total == 1
        assert len(past) == 1
        report = ar.compute_triage_report(past, total_live=total)
        assert report.label_counts[rl.RETRO_TP] == 1

    def test_pagination_fetches_beyond_first_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A population larger than one 100-item page (issue #2413's silent
        PRIOR_FETCH_LIMIT=50 cap) must be paginated, not truncated to the
        first page, up to *limit*."""
        calls: list[str] = []

        def fake(method: str, path: str, *_a: Any, **_kw: Any) -> str:
            calls.append(path)
            if "page=2" in path:
                items = [
                    {"number": i, "labels": [], "body": ""}
                    for i in range(100, 150)
                ]
            else:
                items = [
                    {"number": i, "labels": [], "body": ""} for i in range(100)
                ]
            return json.dumps({"total_count": 150, "items": items})

        monkeypatch.setattr(ar, "gh_api", fake)
        past, total = ar.fetch_past_retro_population("o/r", limit=200)
        assert total == 150
        assert len(past) == 150
        assert len(calls) == 2

    def test_population_truncated_when_live_total_exceeds_search_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A live population larger than the search API's hard 1000-result
        ceiling must stop paginating and report the live total via
        fetch_past_retro_population rather than silently under-counting."""

        def fake(method: str, path: str, *_a: Any, **_kw: Any) -> str:
            items = [{"number": i, "labels": [], "body": ""} for i in range(100)]
            return json.dumps({"total_count": 1500, "items": items})

        monkeypatch.setattr(ar, "gh_api", fake)
        past, total = ar.fetch_past_retro_population(
            "o/r", limit=rl.TRIAGE_REPORT_FETCH_LIMIT
        )
        assert total == 1500
        assert len(past) == ar._SEARCH_API_MAX_RESULTS
        report = ar.compute_triage_report(past, total_live=total)
        assert report.truncated


class TestCompatibilityReexports:
    """The pure-layer split (#1725) must preserve auto_retro's public
    attribute surface. Callers and downstream repos use the documented
    ``import auto_retro as ar; ar.<name>`` shape, so a future re-split that
    drops a re-export would raise AttributeError for them. This locks the
    set of names that were auto_retro attributes before the split. Refs the
    PR #1727 review (re-export omission).
    """

    # Names that resolved on auto_retro before the split (label constants
    # originally imported from _retro_labels, the trusted-bot set, and the
    # parser result-classification constants moved to _auto_retro_parse).
    _COMPAT_NAMES: ClassVar[tuple[str, ...]] = (
        "ALL_RETRO_LABELS",
        "RETRO_FP",
        "RETRO_FP_CANDIDATE",
        "RETRO_TENTATIVE",
        "RETRO_TP",
        "PRIOR_MIN_SAMPLE_SIZE",
        "PRIOR_SKIP_THRESHOLD",
        "PRIOR_TENTATIVE_THRESHOLD",
        "_TRUSTED_BOT_LOGINS",
        "_TYPE_SCOPE_RE",
        "_SIGNALS_FIRED_LINE_RE",
        "_RESULT_PASSING_PREFIXES",
        "_RESULT_PASSING_OBSERVATION_PHRASES",
        "_RESULT_PASSING_NUMERIC_RE",
        "_RESULT_PASSING_ALL_UNIT_RE",
        "_RESULT_PASSING_COUNT_RE",
        "_RESULT_PASSING_TRAILING_OK_RE",
        "_RESULT_PASSING_NON_ASCII_ZERO_RE",
        "_RESULT_PASSING_NIX_QUOTED_RE",
        "_RESULT_PASSING_GREP_N_RE",
        "_RESULT_PASSING_SHASUM_RE",
        "_RESULT_PASSING_HEX_HASH_RE",
        "_RESULT_PASSING_PKG_VERSION_RE",
        "_RESULT_PASSING_NIX_TOOL_RE",
        "_RESULT_PASSING_EXIT_ZERO_RE",
        "_RESULT_FAILING_COUNT_RE",
    )

    @pytest.mark.parametrize("name", _COMPAT_NAMES)
    def test_compat_name_resolves_on_auto_retro(self, name: str) -> None:
        assert hasattr(ar, name), (
            f"auto_retro.{name} was dropped from the re-export facade; "
            "downstream 'import auto_retro as ar; ar.<name>' callers break"
        )
        assert name in ar.__all__, f"{name} re-exported but missing from __all__"

    def test_reexported_label_constant_is_canonical(self) -> None:
        # The re-export must be the same object as its _retro_labels source,
        # not a divergent copy.
        assert ar.RETRO_FP is rl.RETRO_FP
        assert ar.ALL_RETRO_LABELS is rl.ALL_RETRO_LABELS
