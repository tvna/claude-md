"""Tests for ``scripts/preflight_replacement_pr.py``.

The guard is meant to run before an agent opens a replacement PR. Unit tests
exercise the pure decision logic and the CLI fixture path so the live GitHub
API path is not needed for deterministic verification.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import preflight_replacement_pr as gate
import pytest

pytestmark = pytest.mark.shard_preflight

_COMPLETE_NOTE = """Root cause:
The prior branch state was stale.

Existing PR cannot be repaired in place:
The remote branch is protected from force-push repair.

Replacement is lower risk because:
The candidate set has no merged PR and the replacement avoids waiting on a wedged branch.
"""


def _candidate(number: int, *, state: str = "open", merged: bool = False, created_at: str | None = None):
    return {
        "number": number,
        "state": state,
        "merged": merged,
        "created_at": created_at or f"2026-05-28T12:{number % 60:02d}:00Z",
        "html_url": f"https://github.com/tvna/claude-md/pull/{number}",
        "title": f"PR {number}",
    }


class TestParseCandidates:
    def test_parses_list_shape(self) -> None:
        parsed = gate.parse_candidates([_candidate(624)])
        assert parsed == [
            gate.CandidatePR(
                number=624,
                state="open",
                merged=False,
                created_at="2026-05-28T12:24:00Z",
                html_url="https://github.com/tvna/claude-md/pull/624",
                title="PR 624",
            )
        ]

    def test_parses_search_items_shape_and_merged_at(self) -> None:
        parsed = gate.parse_candidates({"items": [_candidate(638, state="closed") | {"pull_request": {"merged_at": "x"}}]})
        assert parsed[0].merged is True

    def test_rejects_missing_number(self) -> None:
        with pytest.raises(ValueError, match="invalid number"):
            gate.parse_candidates([{"state": "open", "created_at": "2026-05-28T00:00:00Z"}])


class TestRootCauseNote:
    def test_complete_note_passes(self) -> None:
        assert gate.has_complete_root_cause_note(_COMPLETE_NOTE) is True

    def test_missing_heading_fails(self) -> None:
        assert gate.has_complete_root_cause_note("Root cause:\nOnly one section.\n") is False


class TestDecideReplacement:
    def test_no_prior_candidate_allows_first_pr(self) -> None:
        decision = gate.decide_replacement([], root_cause_note="")
        assert decision.kind == "allow"
        assert decision.metrics.replacement_count == 0

    def test_single_prior_candidate_allows_first_replacement(self) -> None:
        decision = gate.decide_replacement([gate.parse_candidate(_candidate(624))], root_cause_note="")
        assert decision.kind == "allow"
        assert decision.metrics.replacement_count == 0

    def test_second_replacement_requires_root_cause_note(self) -> None:
        candidates = gate.parse_candidates([
            _candidate(624, state="closed"),
            _candidate(625, state="open"),
        ])
        decision = gate.decide_replacement(candidates, root_cause_note="")
        assert decision.kind == "require_root_cause"
        assert decision.metrics.replacement_count == 1
        assert decision.metrics.closed_superseded_count == 1
        assert "Root cause:" in decision.reasons[1]

    def test_complete_root_cause_note_allows_second_replacement(self) -> None:
        candidates = gate.parse_candidates([
            _candidate(624, state="closed"),
            _candidate(625, state="open"),
        ])
        decision = gate.decide_replacement(candidates, root_cause_note=_COMPLETE_NOTE)
        assert decision.kind == "allow"

    def test_merged_candidate_hard_stops_even_with_root_cause_note(self) -> None:
        candidates = gate.parse_candidates([
            _candidate(633, state="closed"),
            _candidate(638, state="closed", merged=True),
        ])
        decision = gate.decide_replacement(candidates, root_cause_note=_COMPLETE_NOTE)
        assert decision.kind == "hard_stop_already_merged"
        assert decision.metrics.merged_numbers == (638,)
        assert "already merged" in decision.reasons[0]

    def test_elapsed_seconds_is_recorded_when_now_is_provided(self) -> None:
        candidates = gate.parse_candidates([
            _candidate(633, created_at="2026-05-28T12:31:55Z"),
            _candidate(636, created_at="2026-05-28T12:45:59Z"),
        ])
        now = gate.parse_iso8601("2026-05-28T13:01:00Z")
        decision = gate.decide_replacement(candidates, root_cause_note=_COMPLETE_NOTE, now=now)
        assert decision.metrics.elapsed_seconds == 1745


class TestCloseMarker:
    def test_marker_without_replacement(self) -> None:
        assert gate.format_close_marker(superseded_pr=624, issue=632) == (
            "<!-- repair-loop:replacement-pr --> superseded_pr=#624 issue=#632"
        )

    def test_marker_with_replacement(self) -> None:
        assert gate.format_close_marker(superseded_pr=624, issue=632, replacement_pr=625) == (
            "<!-- repair-loop:replacement-pr --> superseded_pr=#624 issue=#632 replacement_pr=#625"
        )


class TestFetchCandidates:
    def test_fetch_candidates_reads_pr_detail_for_merged_at(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def fake_apply_call(*, method: str, url: str, payload: dict[str, Any] | None, token: str):
            del method, payload, token
            calls.append(url)
            if url.startswith("https://api.github.com/search/issues"):
                return 200, json.dumps({"items": [_candidate(638, state="closed")]})
            if url == "https://api.github.com/repos/tvna/claude-md/pulls/638":
                detail = _candidate(638, state="closed") | {"merged_at": "2026-05-28T13:01:00Z"}
                return 200, json.dumps(detail)
            raise AssertionError(f"unexpected URL: {url}")

        monkeypatch.setattr(gate, "apply_call", fake_apply_call)
        candidates = gate.fetch_candidates("tvna/claude-md", 632, token="t")
        assert candidates[0].merged is True
        assert calls == [
            "https://api.github.com/search/issues?q=repo%3Atvna%2Fclaude-md%20type%3Apr%20%23632",
            "https://api.github.com/repos/tvna/claude-md/pulls/638",
        ]


class TestCli:
    def test_verify_allows_fixture(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        fixture = tmp_path / "candidates.json"
        fixture.write_text(json.dumps([_candidate(624)]), encoding="utf-8")
        exit_code = gate.main([
            "verify",
            "--repo",
            "tvna/claude-md",
            "--issue",
            "632",
            "--candidates-json",
            str(fixture),
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "OK: replacement PR preflight passed" in captured.out
        assert "candidate_count: 1" in captured.out

    def test_verify_blocks_fixture(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        fixture = tmp_path / "candidates.json"
        fixture.write_text(json.dumps([_candidate(633), _candidate(638, merged=True)]), encoding="utf-8")
        exit_code = gate.main([
            "verify",
            "--repo",
            "tvna/claude-md",
            "--issue",
            "632",
            "--candidates-json",
            str(fixture),
        ])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "hard_stop_already_merged" in captured.err
        assert "merged_prs: #638" in captured.err

    def test_missing_fixture_returns_error_without_traceback(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = gate.main([
            "verify",
            "--repo",
            "tvna/claude-md",
            "--issue",
            "632",
            "--candidates-json",
            str(tmp_path / "missing.json"),
        ])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "::error::preflight_replacement_pr:" in captured.err
        assert "Traceback" not in captured.err

    def test_close_marker_cli(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = gate.main([
            "close-marker",
            "--issue",
            "632",
            "--superseded-pr",
            "624",
            "--replacement-pr",
            "625",
        ])
        assert exit_code == 0
        assert "replacement_pr=#625" in capsys.readouterr().out
