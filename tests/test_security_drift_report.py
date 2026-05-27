"""Tests for ``scripts/security_drift_report.py``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import security_drift_report as sdr

pytestmark = pytest.mark.shard_ci_ops
# ---------------------------------------------------------------------------
# Input parsers
# ---------------------------------------------------------------------------

class TestParseDryRun:
    def test_true(self) -> None:
        assert sdr.parse_dry_run("true") is True

    def test_false(self) -> None:
        assert sdr.parse_dry_run("false") is False

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            sdr.parse_dry_run("yes")


class TestParseIntFlag:
    def test_valid(self) -> None:
        assert sdr.parse_int_flag("0", "--x") == 0
        assert sdr.parse_int_flag("42", "--x") == 42
        assert sdr.parse_int_flag("-1", "--x") == -1

    def test_invalid(self) -> None:
        with pytest.raises(ValueError, match="--x must be an integer"):
            sdr.parse_int_flag("nope", "--x")


class TestParseDetectOutput:
    def test_extracts_known_keys(self) -> None:
        text = "run_date=2026-05-23\ndrift_count=2\nunknown_count=1\n"
        assert sdr.parse_detect_output(text) == {
            "run_date": "2026-05-23",
            "drift_count": "2",
            "unknown_count": "1",
        }

    def test_ignores_unknown_lines(self) -> None:
        text = "noise=x\nrun_date=2026-05-23\nrandom warning\ndrift_count=0\nunknown_count=0\n"
        result = sdr.parse_detect_output(text)
        assert "noise" not in result
        assert result["drift_count"] == "0"

    def test_empty_returns_empty(self) -> None:
        assert sdr.parse_detect_output("") == {}


class TestLabelsPlanHasDrift:
    def test_plan_only_post_is_drift(self) -> None:
        text = "| `x` | plan-only (POST) | - | - | dry-run |\n"
        assert sdr.labels_plan_has_drift(text) is True

    def test_plan_only_delete_is_drift(self) -> None:
        text = "| `x` | plan-only (DELETE) | - | - | dry-run |\n"
        assert sdr.labels_plan_has_drift(text) is True

    def test_report_only_is_drift(self) -> None:
        text = "| `x` | report-only (not in SoT) | - | - | kept (prune=false) |\n"
        assert sdr.labels_plan_has_drift(text) is True

    def test_only_noops_is_clean(self) -> None:
        text = "| `x` | no-op | no | no | unchanged |\n"
        assert sdr.labels_plan_has_drift(text) is False

    def test_empty_is_clean(self) -> None:
        assert sdr.labels_plan_has_drift("") is False


class TestUvStaleHasWarning:
    def test_warning_present(self) -> None:
        text = "::warning::uv pin (0.11.10) trails upstream latest (0.11.11).\n"
        assert sdr.uv_stale_has_warning(text) is True

    def test_no_warning(self) -> None:
        text = "uv pin matches upstream latest (0.11.11).\n"
        assert sdr.uv_stale_has_warning(text) is False


# ---------------------------------------------------------------------------
# Family classifiers
# ---------------------------------------------------------------------------

class TestClassifyRulesets:
    def test_covered_when_all_zero(self) -> None:
        row = sdr.classify_rulesets(
            rc=0,
            detect_output="run_date=2026-05-23\ndrift_count=0\nunknown_count=0\n",
        )
        assert row.status == sdr.STATUS_COVERED
        assert row.family == "rulesets"

    def test_drift_when_drift_count_positive(self) -> None:
        row = sdr.classify_rulesets(
            rc=0,
            detect_output="run_date=2026-05-23\ndrift_count=2\nunknown_count=0\n",
        )
        assert row.status == sdr.STATUS_DRIFT
        assert "2 SoT-vs-live drift row" in row.action

    def test_drift_when_unknown_count_positive(self) -> None:
        row = sdr.classify_rulesets(
            rc=0,
            detect_output="run_date=2026-05-23\ndrift_count=0\nunknown_count=3\n",
        )
        assert row.status == sdr.STATUS_DRIFT
        assert "3 unknown ruleset" in row.action

    def test_error_when_rc_nonzero(self) -> None:
        row = sdr.classify_rulesets(rc=1, detect_output="")
        assert row.status == sdr.STATUS_ERROR
        assert "rc=1" in row.action


class TestClassifyLabels:
    def test_covered_when_noop_only(self) -> None:
        row = sdr.classify_labels(rc=0, summary_text="| `x` | no-op | no | no | unchanged |\n")
        assert row.status == sdr.STATUS_COVERED

    def test_drift_when_plan_only_present(self) -> None:
        row = sdr.classify_labels(
            rc=0, summary_text="| `x` | plan-only (PATCH) | yes | no | dry-run |\n"
        )
        assert row.status == sdr.STATUS_DRIFT
        assert "apply-labels.yml" in row.action

    def test_error_when_rc_nonzero(self) -> None:
        row = sdr.classify_labels(rc=2, summary_text="")
        assert row.status == sdr.STATUS_ERROR


class TestClassifyApm:
    def test_covered_when_rc_zero(self) -> None:
        row = sdr.classify_apm(rc=0)
        assert row.status == sdr.STATUS_COVERED

    def test_drift_when_rc_one(self) -> None:
        row = sdr.classify_apm(rc=1)
        assert row.status == sdr.STATUS_DRIFT
        assert "CLAUDE.md" in row.action

    def test_error_when_rc_other(self) -> None:
        row = sdr.classify_apm(rc=128)
        assert row.status == sdr.STATUS_ERROR


class TestClassifyUvPinLiteral:
    def test_covered_rc_zero(self) -> None:
        assert sdr.classify_uv_pin_literal(rc=0).status == sdr.STATUS_COVERED

    def test_drift_rc_one(self) -> None:
        row = sdr.classify_uv_pin_literal(rc=1)
        assert row.status == sdr.STATUS_DRIFT
        assert "pyproject.toml" in row.action

    def test_error_rc_other(self) -> None:
        assert sdr.classify_uv_pin_literal(rc=2).status == sdr.STATUS_ERROR


class TestClassifyUvPinStaleness:
    def test_covered_no_warning(self) -> None:
        row = sdr.classify_uv_pin_staleness(rc=0, stale_text="uv pin matches upstream latest.\n")
        assert row.status == sdr.STATUS_COVERED

    def test_drift_on_warning(self) -> None:
        row = sdr.classify_uv_pin_staleness(
            rc=0, stale_text="::warning::uv pin trails upstream\n"
        )
        assert row.status == sdr.STATUS_DRIFT

    def test_error_rc_nonzero(self) -> None:
        row = sdr.classify_uv_pin_staleness(rc=1, stale_text="")
        assert row.status == sdr.STATUS_ERROR


class TestStaticRows:
    def test_pr_gate_only_is_pending(self) -> None:
        row = sdr.pr_gate_only_row(family="title-policy", detector="x", evidence="y")
        assert row.status == sdr.STATUS_PENDING
        assert "PR-gate only" in row.action

    def test_out_of_scope_carries_message(self) -> None:
        row = sdr.out_of_scope_row(
            family="required-checks",
            detector="(tracked separately)",
            evidence=".github/rulesets/main.json",
            message="tracked by #120",
        )
        assert row.status == sdr.STATUS_PENDING
        assert "tracked by #120" in row.action


class TestFamilyRowValidation:
    def test_rejects_unknown_status(self) -> None:
        with pytest.raises(ValueError, match="FamilyRow.status"):
            sdr.FamilyRow(family="x", detector="d", status="weird", evidence="e", action="a")


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _covered_fixture() -> list[sdr.FamilyRow]:
    return [
        sdr.classify_rulesets(rc=0, detect_output="drift_count=0\nunknown_count=0\n"),
        sdr.classify_labels(rc=0, summary_text="| `x` | no-op | no | no | unchanged |\n"),
        sdr.classify_apm(rc=0),
        sdr.classify_uv_pin_literal(rc=0),
        sdr.classify_uv_pin_staleness(rc=0, stale_text=""),
    ]


class TestBuildReport:
    def test_all_covered_fixture(self) -> None:
        summary, body, drift = sdr.build_report(
            _covered_fixture(),
            run_url="https://x/runs/1",
            run_date="2026-05-23",
        )
        assert drift == 0
        assert "Families with drift: 0" in summary
        assert "Families with drift: 0" in body
        assert "covered" in summary

    def test_ruleset_drift_fixture(self) -> None:
        # Verification gate #2: a failing fixture produces an actionable summary.
        rows = [
            sdr.classify_rulesets(
                rc=0,
                detect_output="run_date=2026-05-23\ndrift_count=2\nunknown_count=0\n",
            )
        ]
        summary, body, drift = sdr.build_report(
            rows, run_url="https://x/runs/9", run_date="2026-05-23"
        )
        assert drift == 1
        assert "Families with drift: 1" in summary
        assert "drift" in summary
        # Actionable: cites the existing detector workflow + remediation doc.
        assert "ruleset-drift.yml" in summary
        assert "docs/runbooks/rulesets.md" in summary
        # Body carries the same payload + the marker.
        assert sdr.DEFAULT_MARKER in body
        assert "2 SoT-vs-live drift row" in body

    def test_detector_error_fixture(self) -> None:
        rows = [
            sdr.classify_labels(rc=1, summary_text=""),
            sdr.classify_apm(rc=0),
        ]
        summary, body, drift = sdr.build_report(
            rows, run_url="https://x/runs/3", run_date="2026-05-23"
        )
        assert drift == 0  # error rows are not counted as drift
        assert "Families with detector error: 1" in summary
        assert "error" in summary
        assert "rc=1" in body

    def test_marker_is_first_non_blank_line(self) -> None:
        _summary, body, _drift = sdr.build_report(
            _covered_fixture(), run_url="https://x", run_date="2026-05-23"
        )
        first = next(line for line in body.splitlines() if line.strip())
        assert first == sdr.DEFAULT_MARKER

    def test_table_has_five_columns(self) -> None:
        summary, _body, _drift = sdr.build_report(
            _covered_fixture(), run_url="https://x", run_date="2026-05-23"
        )
        header = next(
            line for line in summary.splitlines() if line.startswith("| Control family")
        )
        assert header.count("|") == 6  # 5 columns + leading | and trailing |

    def test_custom_marker(self) -> None:
        _s, body, _d = sdr.build_report(
            _covered_fixture(),
            run_url="https://x",
            run_date="2026-05-23",
            marker="<!-- custom -->",
        )
        assert body.startswith("<!-- custom -->\n")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one FamilyRow"):
            sdr.build_report([], run_url="https://x", run_date="2026-05-23")


# ---------------------------------------------------------------------------
# Comment-side helpers
# ---------------------------------------------------------------------------

class TestFindExistingComment:
    def test_returns_id_when_marker_present(self) -> None:
        comments = [
            {"id": 1, "body": "hello"},
            {"id": 2, "body": f"{sdr.DEFAULT_MARKER}\nrest"},
        ]
        assert sdr.find_existing_comment(comments) == 2

    def test_returns_none_when_no_match(self) -> None:
        comments = [{"id": 1, "body": "hello"}, {"id": 2, "body": "world"}]
        assert sdr.find_existing_comment(comments) is None

    def test_returns_none_when_body_missing(self) -> None:
        comments: list[dict[str, Any]] = [{"id": 1}]
        assert sdr.find_existing_comment(comments) is None

    def test_returns_none_when_id_not_int(self) -> None:
        comments: list[dict[str, Any]] = [{"id": "x", "body": sdr.DEFAULT_MARKER}]
        assert sdr.find_existing_comment(comments) is None

    def test_custom_marker(self) -> None:
        comments = [{"id": 7, "body": "<!-- custom -->\nbody"}]
        assert sdr.find_existing_comment(comments, marker="<!-- custom -->") == 7


# ---------------------------------------------------------------------------
# CLI: aggregate
# ---------------------------------------------------------------------------

def _aggregate_args(tmp_path: Path, **overrides: Any) -> list[str]:
    ruleset_out = tmp_path / "ruleset.out"
    ruleset_out.write_text(
        overrides.pop(
            "ruleset_output", "run_date=2026-05-23\ndrift_count=0\nunknown_count=0\n"
        ),
        encoding="utf-8",
    )
    labels_summary = tmp_path / "labels.md"
    labels_summary.write_text(
        overrides.pop("labels_summary", "| `x` | no-op | no | no | unchanged |\n"),
        encoding="utf-8",
    )
    uv_stale = tmp_path / "uv-stale.out"
    uv_stale.write_text(overrides.pop("uv_stale", ""), encoding="utf-8")
    return [
        "aggregate",
        "--ruleset-detect-output", str(ruleset_out),
        "--ruleset-detect-rc", overrides.pop("ruleset_rc", "0"),
        "--labels-plan-rc", overrides.pop("labels_rc", "0"),
        "--labels-summary-file", str(labels_summary),
        "--apm-diff-rc", overrides.pop("apm_rc", "0"),
        "--uv-drift-rc", overrides.pop("uv_drift_rc", "0"),
        "--uv-stale-rc", overrides.pop("uv_stale_rc", "0"),
        "--uv-stale-output", str(uv_stale),
        "--run-url", overrides.pop("run_url", "https://x/runs/1"),
        "--run-date", overrides.pop("run_date", "2026-05-23"),
        "--summary-file", str(tmp_path / "summary.md"),
        "--report-file", str(tmp_path / "report.md"),
        "--github-output", str(tmp_path / "out.txt"),
    ]


class TestCmdAggregate:
    def test_clean_path_exits_zero(self, tmp_path: Path) -> None:
        argv = _aggregate_args(tmp_path)
        rc = sdr.main(argv)
        assert rc == 0
        summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
        report = (tmp_path / "report.md").read_text(encoding="utf-8")
        gh_out = (tmp_path / "out.txt").read_text(encoding="utf-8")
        assert "Families with drift: 0" in summary
        assert sdr.DEFAULT_MARKER in report
        assert "families_with_drift=0" in gh_out
        assert "report_date=2026-05-23" in gh_out

    def test_drift_path_still_exits_zero(self, tmp_path: Path) -> None:
        argv = _aggregate_args(
            tmp_path,
            ruleset_output="run_date=2026-05-23\ndrift_count=1\nunknown_count=0\n",
        )
        rc = sdr.main(argv)
        assert rc == 0
        gh_out = (tmp_path / "out.txt").read_text(encoding="utf-8")
        assert "families_with_drift=1" in gh_out

    def test_invalid_rc_fails_loud(self, tmp_path: Path) -> None:
        argv = _aggregate_args(tmp_path, ruleset_rc="nope")
        assert sdr.main(argv) == 1


# ---------------------------------------------------------------------------
# CLI: post-comment
# ---------------------------------------------------------------------------

def _write_report(path: Path, marker: str = sdr.DEFAULT_MARKER) -> None:
    path.write_text(f"{marker}\n\nbody text\n", encoding="utf-8")


class TestCmdPostComment:
    def test_dry_run_does_not_call_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = tmp_path / "report.md"
        _write_report(report)
        calls: list[dict[str, Any]] = []

        def fake_apply(**kwargs: Any) -> tuple[int, str]:
            calls.append(kwargs)
            return 200, "[]"

        monkeypatch.setenv("GH_TOKEN", "tkn")
        rc = sdr.main(
            [
                "post-comment",
                "--repo", "owner/repo",
                "--issue", "178",
                "--report-file", str(report),
                "--dry-run", "true",
            ],
            apply_call=fake_apply,
        )
        assert rc == 0
        assert calls == []

    def test_apply_posts_new_when_no_marker_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = tmp_path / "report.md"
        _write_report(report)
        calls: list[dict[str, Any]] = []

        def fake_apply(**kwargs: Any) -> tuple[int, str]:
            calls.append(kwargs)
            if kwargs["method"] == "GET":
                return 200, json.dumps([{"id": 1, "body": "unrelated"}])
            return 201, "{}"

        monkeypatch.setenv("GH_TOKEN", "tkn")
        rc = sdr.main(
            [
                "post-comment",
                "--repo", "owner/repo",
                "--issue", "178",
                "--report-file", str(report),
                "--dry-run", "false",
            ],
            apply_call=fake_apply,
        )
        assert rc == 0
        assert [c["method"] for c in calls] == ["GET", "POST"]
        assert calls[1]["url"].endswith("/repos/owner/repo/issues/178/comments")
        assert calls[1]["payload"] == {"body": "<!-- security-control-drift-report -->\n\nbody text\n"}

    def test_apply_patches_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = tmp_path / "report.md"
        _write_report(report)
        calls: list[dict[str, Any]] = []

        def fake_apply(**kwargs: Any) -> tuple[int, str]:
            calls.append(kwargs)
            if kwargs["method"] == "GET":
                return 200, json.dumps(
                    [{"id": 42, "body": f"{sdr.DEFAULT_MARKER}\nold"}]
                )
            return 200, "{}"

        monkeypatch.setenv("GH_TOKEN", "tkn")
        rc = sdr.main(
            [
                "post-comment",
                "--repo", "owner/repo",
                "--issue", "178",
                "--report-file", str(report),
                "--dry-run", "false",
            ],
            apply_call=fake_apply,
        )
        assert rc == 0
        assert [c["method"] for c in calls] == ["GET", "PATCH"]
        assert calls[1]["url"].endswith("/repos/owner/repo/issues/comments/42")

    def test_missing_token_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = tmp_path / "report.md"
        _write_report(report)
        monkeypatch.delenv("GH_TOKEN", raising=False)

        def fake_apply(**_kwargs: Any) -> tuple[int, str]:
            raise AssertionError("should not be called")

        rc = sdr.main(
            [
                "post-comment",
                "--repo", "owner/repo",
                "--issue", "178",
                "--report-file", str(report),
                "--dry-run", "false",
            ],
            apply_call=fake_apply,
        )
        assert rc == 1

    def test_empty_body_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = tmp_path / "report.md"
        report.write_text("", encoding="utf-8")
        monkeypatch.setenv("GH_TOKEN", "tkn")

        def fake_apply(**_kwargs: Any) -> tuple[int, str]:
            raise AssertionError("should not be called")

        rc = sdr.main(
            [
                "post-comment",
                "--repo", "owner/repo",
                "--issue", "178",
                "--report-file", str(report),
                "--dry-run", "false",
            ],
            apply_call=fake_apply,
        )
        assert rc == 1

    def test_missing_marker_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = tmp_path / "report.md"
        report.write_text("no marker here\n", encoding="utf-8")
        monkeypatch.setenv("GH_TOKEN", "tkn")

        def fake_apply(**_kwargs: Any) -> tuple[int, str]:
            raise AssertionError("should not be called")

        rc = sdr.main(
            [
                "post-comment",
                "--repo", "owner/repo",
                "--issue", "178",
                "--report-file", str(report),
                "--dry-run", "true",
            ],
            apply_call=fake_apply,
        )
        assert rc == 1
