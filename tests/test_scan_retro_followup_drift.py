"""Tests for ``scripts/scan_retro_followup_drift.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the structure of ``tests/test_auto_retro.py`` and
``tests/test_scan_non_ascii.py``: pure functions get table-driven tests
and the subprocess boundary (:func:`scan_retro_followup_drift.gh_api`) is
monkeypatched. Refs #558.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
import scan_retro_followup_drift as srfd
from _retro_labels import (
    ALL_RETRO_LABELS,
    RETRO_FP,
    RETRO_FP_CANDIDATE,
    RETRO_TENTATIVE,
    RETRO_TP,
)

pytestmark = pytest.mark.shard_ci_ops

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
        body = "- [ ] feat(harness): add gate -- needed because #500"
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


def _called_process_error(stderr: str, stdout: str = "") -> subprocess.CalledProcessError:
    exc = subprocess.CalledProcessError(returncode=1, cmd=["gh"])
    exc.stderr = stderr
    exc.stdout = stdout
    return exc


class TestIs404Error:
    def test_http_404_stderr(self) -> None:
        assert srfd.is_404_error(_called_process_error("HTTP 404: Not Found")) is True

    def test_404_not_found_stderr(self) -> None:
        assert srfd.is_404_error(_called_process_error("404 Not Found")) is True

    def test_case_insensitive(self) -> None:
        assert srfd.is_404_error(_called_process_error("http 404: not found")) is True

    def test_other_error_returns_false(self) -> None:
        assert srfd.is_404_error(_called_process_error("HTTP 502 Bad Gateway")) is False


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
            raise _called_process_error("HTTP 500: Server Error")
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
