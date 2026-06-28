"""Tests for ``scripts/scan_retro_followup_drift.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the structure of ``tests/test_auto_retro.py`` and
``tests/test_scan_non_ascii.py``: pure functions get table-driven tests
and the REST boundary (:func:`scan_retro_followup_drift.gh_api`) is
monkeypatched. Refs #558.
"""

from __future__ import annotations

from typing import Any

import pytest
import scan_retro_followup_drift as srfd
from _github_api import GitHubApiError
from _retro_labels import (
    ALL_RETRO_LABELS,
    RETRO_FP,
    RETRO_FP_CANDIDATE,
    RETRO_TENTATIVE,
    RETRO_TP,
)

pytestmark = pytest.mark.shard_ci_ops_2

# ---------------------------------------------------------------------------
# Label SoT
# ---------------------------------------------------------------------------


class TestLabelSoT:
    def test_four_labels_present(self) -> None:
        assert {
            RETRO_TP,
            RETRO_FP,
            RETRO_FP_CANDIDATE,
            RETRO_TENTATIVE,
        } == ALL_RETRO_LABELS

    def test_label_strings_are_namespaced(self) -> None:
        for label in ALL_RETRO_LABELS:
            assert label.startswith("retro:"), label


# ---------------------------------------------------------------------------
# parse_followup_refs
# ---------------------------------------------------------------------------


class TestParseFollowupRefs:
    def test_single_unchecked_bullet(self) -> None:
        body = "- [ ] feat(harness): add gate; needed because #500"
        assert srfd.parse_followup_refs(body) == [500]

    def test_checked_bullet_also_matches(self) -> None:
        body = "- [x] fix(scripts): close #501 once landed"
        assert srfd.parse_followup_refs(body) == [501]

    def test_multiple_bullets_sorted_unique(self) -> None:
        body = (
            "## Proposed work\n"
            "\n"
            "- [ ] follow-up A #602\n"
            "- [x] follow-up B #601\n"
            "- [ ] dup #602\n"
        )
        assert srfd.parse_followup_refs(body) == [601, 602]

    def test_html_comment_bullets_ignored(self) -> None:
        body = "<!-- - [ ] commented #999 -->\n- [ ] real #1\n"
        assert srfd.parse_followup_refs(body) == [1]

    def test_carriage_returns_normalised(self) -> None:
        body = "- [ ] crlf #7\r\n- [ ] lf #8\n"
        assert srfd.parse_followup_refs(body) == [7, 8]

    def test_no_bullets_returns_empty(self) -> None:
        assert srfd.parse_followup_refs("plain prose with #1 but no bullet") == []

    def test_bullet_without_ref_ignored(self) -> None:
        assert srfd.parse_followup_refs("- [ ] no number here") == []

    def test_acceptance_criteria_checkboxes_ignored(self) -> None:
        """The retro template's Acceptance criteria bullets have no #N so
        they must not surface as follow-ups."""
        body = (
            "## Acceptance criteria\n"
            "\n"
            "- [ ] Repair history table complete.\n"
            "- [ ] Each repair classified with the section 3 taxonomy.\n"
        )
        assert srfd.parse_followup_refs(body) == []


# ---------------------------------------------------------------------------
# days_between
# ---------------------------------------------------------------------------


class TestDaysBetween:
    def test_same_day(self) -> None:
        assert srfd.days_between("2026-05-01T00:00:00Z", "2026-05-01") == 0

    def test_thirty_days(self) -> None:
        assert (
            srfd.days_between("2026-04-01T00:00:00Z", "2026-05-01T00:00:00Z")
            == 30
        )

    def test_unparseable_updated_at_returns_zero(self) -> None:
        assert srfd.days_between("not-a-date", "2026-05-01") == 0

    def test_unparseable_today_returns_zero(self) -> None:
        assert srfd.days_between("2026-05-01T00:00:00Z", "garbage") == 0

    def test_negative_delta_allowed(self) -> None:
        assert (
            srfd.days_between("2026-05-10T00:00:00Z", "2026-05-01") == -9
        )


# ---------------------------------------------------------------------------
# classify_followup_drift (the 5 drift rules)
# ---------------------------------------------------------------------------


def _drift(**overrides: Any) -> str:
    defaults: dict[str, Any] = {
        "found": True,
        "is_pr": False,
        "state": "open",
        "state_reason": None,
        "merged": False,
        "updated_at": "2026-05-01T00:00:00Z",
        "today": "2026-05-02",
        "stale_days": 30,
    }
    defaults.update(overrides)
    return srfd.classify_followup_drift(**defaults)


class TestClassifyFollowupDrift:
    def test_rule_not_found(self) -> None:
        assert _drift(found=False) == "not_found"

    def test_rule_issue_closed_not_planned(self) -> None:
        assert (
            _drift(state="closed", state_reason="not_planned")
            == "fp_confirmed"
        )

    def test_issue_closed_completed_is_ok(self) -> None:
        assert (
            _drift(state="closed", state_reason="completed") == "ok"
        )

    def test_rule_pr_closed_unmerged(self) -> None:
        assert (
            _drift(is_pr=True, state="closed", merged=False)
            == "fp_confirmed"
        )

    def test_pr_closed_merged_is_ok(self) -> None:
        assert (
            _drift(is_pr=True, state="closed", merged=True) == "ok"
        )

    def test_rule_open_stale_30_days(self) -> None:
        assert (
            _drift(
                state="open",
                updated_at="2026-04-01T00:00:00Z",
                today="2026-05-01",
            )
            == "fp_candidate"
        )

    def test_open_fresh_is_ok(self) -> None:
        assert (
            _drift(
                state="open",
                updated_at="2026-05-01T00:00:00Z",
                today="2026-05-02",
            )
            == "ok"
        )

    def test_open_pr_stale_also_candidate(self) -> None:
        assert (
            _drift(
                is_pr=True,
                state="open",
                updated_at="2026-03-01T00:00:00Z",
                today="2026-05-01",
            )
            == "fp_candidate"
        )

    def test_stale_days_threshold_configurable(self) -> None:
        # 14-day threshold catches a 15-day-stale follow-up
        assert (
            _drift(
                state="open",
                updated_at="2026-04-15T00:00:00Z",
                today="2026-05-01",
                stale_days=14,
            )
            == "fp_candidate"
        )


# ---------------------------------------------------------------------------
# aggregate_drift
# ---------------------------------------------------------------------------


class TestAggregateDrift:
    def test_empty_returns_none(self) -> None:
        assert srfd.aggregate_drift([]) is None

    def test_all_ok_returns_ok(self) -> None:
        assert srfd.aggregate_drift(["ok", "ok"]) == "ok"

    def test_confirmed_wins_over_candidate(self) -> None:
        assert (
            srfd.aggregate_drift(["ok", "fp_candidate", "fp_confirmed"])
            == "fp_confirmed"
        )

    def test_candidate_wins_over_ok(self) -> None:
        assert (
            srfd.aggregate_drift(["ok", "fp_candidate", "ok"])
            == "fp_candidate"
        )

    def test_not_found_collapses_to_candidate(self) -> None:
        assert srfd.aggregate_drift(["ok", "not_found"]) == "fp_candidate"

    def test_not_found_below_confirmed(self) -> None:
        assert (
            srfd.aggregate_drift(["not_found", "fp_confirmed"])
            == "fp_confirmed"
        )


# ---------------------------------------------------------------------------
# decide_target_label
# ---------------------------------------------------------------------------


class TestDecideTargetLabel:
    def test_none_aggregate_returns_none(self) -> None:
        assert srfd.decide_target_label(None, []) is None

    def test_ok_aggregate_returns_none(self) -> None:
        assert srfd.decide_target_label("ok", []) is None

    def test_operator_tp_blocks_any_change(self) -> None:
        assert srfd.decide_target_label("fp_confirmed", [RETRO_TP]) is None
        assert (
            srfd.decide_target_label("fp_candidate", [RETRO_TP]) is None
        )

    def test_operator_fp_blocks_any_change(self) -> None:
        assert srfd.decide_target_label("fp_confirmed", [RETRO_FP]) is None
        assert (
            srfd.decide_target_label("fp_candidate", [RETRO_FP]) is None
        )

    def test_confirmed_adds_fp(self) -> None:
        assert (
            srfd.decide_target_label("fp_confirmed", []) == RETRO_FP
        )

    def test_confirmed_upgrades_from_candidate(self) -> None:
        assert (
            srfd.decide_target_label(
                "fp_confirmed", [RETRO_FP_CANDIDATE]
            )
            == RETRO_FP
        )

    def test_candidate_adds_when_missing(self) -> None:
        assert (
            srfd.decide_target_label("fp_candidate", [])
            == RETRO_FP_CANDIDATE
        )

    def test_candidate_idempotent_when_present(self) -> None:
        assert (
            srfd.decide_target_label(
                "fp_candidate", [RETRO_FP_CANDIDATE]
            )
            is None
        )


# ---------------------------------------------------------------------------
# is_pr_payload
# ---------------------------------------------------------------------------


class TestIsPrPayload:
    def test_pr_payload(self) -> None:
        assert srfd.is_pr_payload({"pull_request": {"url": "..."}}) is True

    def test_issue_payload(self) -> None:
        assert srfd.is_pr_payload({"state": "open"}) is False

    def test_pr_payload_empty_subobject_is_falsy(self) -> None:
        assert srfd.is_pr_payload({"pull_request": {}}) is False


# ---------------------------------------------------------------------------
# is_404_error
# ---------------------------------------------------------------------------


def _api_error(code: int) -> GitHubApiError:
    return GitHubApiError(code, "GET", "/repos/x/y/issues/1", "body")


class TestIs404Error:
    def test_http_404(self) -> None:
        assert srfd.is_404_error(_api_error(404)) is True

    def test_other_error_returns_false(self) -> None:
        assert srfd.is_404_error(_api_error(502)) is False


# ---------------------------------------------------------------------------
# run() orchestrator
# ---------------------------------------------------------------------------


class _FakeApi:
    """Records calls to monkeypatched scan_retro_followup_drift functions."""

    def __init__(
        self,
        retros: list[dict[str, Any]],
        followups: dict[int, dict[str, Any] | None],
        merged_prs: dict[int, bool] | None = None,
        followup_errors: set[int] | None = None,
    ) -> None:
        self.retros = retros
        self.followups = followups
        self.merged_prs = merged_prs or {}
        self.followup_errors = followup_errors or set()
        self.label_calls: list[tuple[int, str]] = []

    def search_retro_issues(self, repo: str) -> list[dict[str, Any]]:
        return self.retros

    def fetch_issue_or_pr(self, repo: str, number: int) -> dict[str, Any] | None:
        if number in self.followup_errors:
            raise _api_error(500)
        return self.followups.get(number)

    def fetch_pr_merged(self, repo: str, number: int) -> bool:
        return self.merged_prs.get(number, False)

    def apply_label(self, repo: str, number: int, label: str) -> None:
        self.label_calls.append((number, label))


def _install_fakes(monkeypatch: pytest.MonkeyPatch, fake: _FakeApi) -> None:
    monkeypatch.setattr(srfd, "search_retro_issues", fake.search_retro_issues)
    monkeypatch.setattr(srfd, "fetch_issue_or_pr", fake.fetch_issue_or_pr)
    monkeypatch.setattr(srfd, "fetch_pr_merged", fake.fetch_pr_merged)
    monkeypatch.setattr(srfd, "apply_label", fake.apply_label)


def _retro(
    number: int,
    body: str,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "body": body,
        "labels": [{"name": name} for name in (labels or [])],
    }


class TestRunOrchestrator:
    def test_no_retros_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(retros=[], followups={})
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == []

    def test_open_stale_issue_yields_candidate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[_retro(230, "- [ ] follow #500")],
            followups={
                500: {
                    "state": "open",
                    "updated_at": "2026-04-01T00:00:00Z",
                },
            },
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == [(230, RETRO_FP_CANDIDATE)]

    def test_closed_not_planned_yields_fp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[_retro(231, "- [ ] follow #501")],
            followups={
                501: {
                    "state": "closed",
                    "state_reason": "not_planned",
                    "updated_at": "2026-05-01T00:00:00Z",
                },
            },
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == [(231, RETRO_FP)]

    def test_pr_closed_unmerged_yields_fp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[_retro(232, "- [ ] follow PR #502")],
            followups={
                502: {
                    "state": "closed",
                    "pull_request": {"url": "..."},
                    "updated_at": "2026-05-01T00:00:00Z",
                },
            },
            merged_prs={502: False},
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == [(232, RETRO_FP)]

    def test_pr_merged_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[_retro(233, "- [ ] follow PR #503")],
            followups={
                503: {
                    "state": "closed",
                    "pull_request": {"url": "..."},
                    "updated_at": "2026-05-01T00:00:00Z",
                },
            },
            merged_prs={503: True},
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == []

    def test_not_found_yields_candidate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[_retro(234, "- [ ] missing #999")],
            followups={999: None},
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == [(234, RETRO_FP_CANDIDATE)]

    def test_operator_tp_skipped_without_api_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[
                _retro(235, "- [ ] follow #504", labels=[RETRO_TP]),
            ],
            followups={
                504: {
                    "state": "open",
                    "updated_at": "2026-03-01T00:00:00Z",
                },
            },
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == []

    def test_operator_fp_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[_retro(236, "- [ ] follow #505", labels=[RETRO_FP])],
            followups={505: {"state": "closed", "state_reason": "not_planned"}},
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == []

    def test_candidate_idempotent_on_rerun(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A retro already labelled retro:fp-candidate must not be
        relabelled on the next scan when the drift remains candidate."""
        fake = _FakeApi(
            retros=[
                _retro(
                    237,
                    "- [ ] follow #506",
                    labels=[RETRO_FP_CANDIDATE],
                )
            ],
            followups={
                506: {
                    "state": "open",
                    "updated_at": "2026-04-01T00:00:00Z",
                },
            },
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == []

    def test_candidate_upgrades_to_fp_on_confirmation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[
                _retro(
                    238,
                    "- [ ] follow #507",
                    labels=[RETRO_FP_CANDIDATE],
                )
            ],
            followups={
                507: {
                    "state": "closed",
                    "state_reason": "not_planned",
                    "updated_at": "2026-05-01T00:00:00Z",
                },
            },
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == [(238, RETRO_FP)]

    def test_no_followups_in_body_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeApi(
            retros=[_retro(239, "## Acceptance criteria\n\n- [ ] item")],
            followups={},
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == []

    def test_transient_followup_error_does_not_abort_scan(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One followup raising a non-404 CalledProcessError must not stop
        the rest of the scan. The bad followup is skipped, others
        continue."""
        fake = _FakeApi(
            retros=[
                _retro(240, "- [ ] dies #800\n- [ ] open stale #801"),
            ],
            followups={
                801: {
                    "state": "open",
                    "updated_at": "2026-04-01T00:00:00Z",
                },
            },
            followup_errors={800},
        )
        _install_fakes(monkeypatch, fake)
        # 800 raises a 500; 801 is candidate; aggregate is candidate.
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == [(240, RETRO_FP_CANDIDATE)]


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_summary_contains_counts(self) -> None:
        out = srfd.build_summary(
            retros_scanned=7,
            labels_applied={RETRO_FP_CANDIDATE: 3, RETRO_FP: 1},
            errors=0,
        )
        assert "Retros scanned | 7" in out
        assert f"`{RETRO_FP_CANDIDATE}` applied | 3" in out
        assert f"`{RETRO_FP}` applied | 1" in out
        assert "fetch errors | 0" in out

    def test_summary_is_ascii(self) -> None:
        out = srfd.build_summary(0, {}, 0)
        out.encode("ascii")  # raises UnicodeEncodeError on any non-ASCII


# ---------------------------------------------------------------------------
# _parse_iso(); empty string branch (line 108)
# ---------------------------------------------------------------------------


class TestParseIso:
    def test_empty_string_returns_none(self) -> None:
        assert srfd._parse_iso("") is None

    def test_date_without_tz_gets_utc(self) -> None:
        result = srfd._parse_iso("2026-05-01")
        assert result is not None
        assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# decide_target_label(); unknown aggregate returns None (line 220)
# ---------------------------------------------------------------------------


class TestDecideTargetLabelUnknownAggregate:
    def test_unknown_aggregate_returns_none(self) -> None:
        assert srfd.decide_target_label("unexpected_value", []) is None


# ---------------------------------------------------------------------------
# gh_api(); mock apply_call
# ---------------------------------------------------------------------------


class TestGhApi:
    def test_delegates_to_rest_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[Any, ...]] = []

        def fake_rest_text(method: str, path: str, payload: Any = None) -> str:
            calls.append((method, path, payload))
            return '{"items":[]}'

        monkeypatch.setattr(srfd, "rest_text", fake_rest_text)
        assert srfd.gh_api("GET", "/repos/test/test/issues/1") == '{"items":[]}'
        assert calls[0] == ("GET", "/repos/test/test/issues/1", None)
        assert srfd.gh_api("POST", "/path", {"labels": ["x"]}) == '{"items":[]}'
        assert calls[1] == ("POST", "/path", {"labels": ["x"]})


# ---------------------------------------------------------------------------
# search_retro_issues() / fetch_issue_or_pr() / fetch_pr_merged() / apply_label()
#; mock gh_api (lines 316-320, 330-336, 349-351, 356)
# ---------------------------------------------------------------------------


class TestBoundaryFunctions:
    def test_search_retro_issues_parses_items(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import json as _json
        payload = _json.dumps({"items": [{"number": 1, "body": "- [ ] follow #500", "labels": []}]})
        monkeypatch.setattr(srfd, "gh_api", lambda *a, **kw: payload)
        result = srfd.search_retro_issues("owner/repo")
        assert len(result) == 1
        assert result[0]["number"] == 1

    def test_search_retro_issues_handles_empty_raw(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(srfd, "gh_api", lambda *a, **kw: "  ")
        result = srfd.search_retro_issues("owner/repo")
        assert result == []

    def test_fetch_issue_or_pr_returns_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import json as _json
        payload = _json.dumps({"number": 42, "state": "open", "updated_at": "2026-05-01T00:00:00Z"})
        monkeypatch.setattr(srfd, "gh_api", lambda *a, **kw: payload)
        result = srfd.fetch_issue_or_pr("owner/repo", 42)
        assert result is not None
        assert result["number"] == 42

    def test_fetch_issue_or_pr_returns_none_on_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*a: Any, **kw: Any) -> Any:
            raise _api_error(404)

        monkeypatch.setattr(srfd, "gh_api", _raise)
        assert srfd.fetch_issue_or_pr("owner/repo", 999) is None

    def test_fetch_issue_or_pr_propagates_non_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*a: Any, **kw: Any) -> Any:
            raise _api_error(500)

        monkeypatch.setattr(srfd, "gh_api", _raise)
        with pytest.raises(GitHubApiError):
            srfd.fetch_issue_or_pr("owner/repo", 1)

    def test_fetch_pr_merged_returns_bool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import json as _json
        monkeypatch.setattr(srfd, "gh_api", lambda *a, **kw: _json.dumps({"merged": True}))
        assert srfd.fetch_pr_merged("owner/repo", 42) is True

    def test_apply_label_calls_post(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[Any, ...]] = []

        def fake_gh_api(method: str, path: str, body: Any = None, **kw: Any) -> str:
            calls.append((method, path, body))
            return "{}"

        monkeypatch.setattr(srfd, "gh_api", fake_gh_api)
        srfd.apply_label("owner/repo", 42, RETRO_FP_CANDIDATE)
        assert calls[0][0] == "POST"
        assert "42/labels" in calls[0][1]


# ---------------------------------------------------------------------------
# run(); non-int retro_number skip (line 443)
# ---------------------------------------------------------------------------


class TestRunNonIntRetroNumber:
    def test_non_int_retro_number_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeApi(
            retros=[{"number": "not-an-int", "body": "- [ ] follow #500", "labels": []}],
            followups={},
        )
        _install_fakes(monkeypatch, fake)
        assert srfd.run("o/r", today="2026-05-02") == 0
        assert fake.label_calls == []


# ---------------------------------------------------------------------------
# _cmd_run(); missing repo (lines 487-491)
# ---------------------------------------------------------------------------


class TestCmdRunMissingRepo:
    def test_missing_repo_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        rc = srfd.main(["run"])
        assert rc == 1
        assert "missing" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# main(); GitHubApiError handler
# ---------------------------------------------------------------------------


class TestMainExceptionHandlers:
    def test_main_catches_github_api_error_from_run(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _raise(repo: str, **kw: Any) -> int:
            raise _api_error(503)

        monkeypatch.setattr(srfd, "run", _raise)
        rc = srfd.main(["run", "--repo", "owner/repo"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "GitHub API failed" in err

    def test_main_catches_value_error_from_run(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _raise(repo: str, **kw: Any) -> int:
            raise ValueError("invalid config value")

        monkeypatch.setattr(srfd, "run", _raise)
        rc = srfd.main(["run", "--repo", "owner/repo"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "invalid config value" in err

    def test_main_block_exits_via_runpy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import runpy
        import sys

        monkeypatch.setattr(sys, "argv", ["scan_retro_followup_drift", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("scan_retro_followup_drift", run_name="__main__")
        assert exc_info.value.code == 0
