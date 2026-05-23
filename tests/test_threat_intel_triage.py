"""Tests for ``scripts/threat_intel_triage.py``."""

from __future__ import annotations

import json
from pathlib import Path

import threat_intel_triage as triage


class TestParseLabels:
    def test_empty(self) -> None:
        assert triage.parse_labels("") == set()

    def test_comma_and_newline_separated(self) -> None:
        assert triage.parse_labels("type:fix, severity:security\nlayer:meta") == {
            "type:fix",
            "severity:security",
            "layer:meta",
        }

    def test_repeated_args(self) -> None:
        assert triage.parse_labels(["type:fix,layer:meta", "severity:security"]) == {
            "type:fix",
            "layer:meta",
            "severity:security",
        }


class TestClassify:
    def test_no_security_signal_returns_no_labels(self) -> None:
        result = triage.classify(
            "feat: add threat intelligence triage rule",
            "Deterministic routing only.",
            {"type:feat", "layer:meta"},
        )
        assert result["intel_needed"] is False
        assert result["response_needed"] is False
        assert result["recommended_labels"] == []
        assert result["remove_labels"] == []

    def test_security_label_forces_collection_and_response(self) -> None:
        result = triage.classify(
            "fix: harden token handling",
            "No public advisory yet.",
            {"severity:security"},
        )
        assert result["intel_needed"] is True
        assert result["response_needed"] is True
        assert result["recommended_labels"] == [
            triage.INTEL_LABEL,
            triage.RESPONSE_LABEL,
        ]
        assert result["remove_labels"] == []

    def test_cve_requires_collection_only(self) -> None:
        result = triage.classify(
            "fix: evaluate CVE-2026-12345",
            "Need to determine whether this repo is affected.",
            {"type:fix"},
        )
        assert result["intel_needed"] is True
        assert result["response_needed"] is False
        assert result["recommended_labels"] == [triage.INTEL_LABEL]
        assert result["remove_labels"] == []
        assert result["matched_intel_indicators"] == ["cve"]

    def test_active_exploitation_requires_response(self) -> None:
        result = triage.classify(
            "fix: respond to GHSA-abcd-1234-wxyz",
            "Exploit available and active exploitation reported.",
            {"type:fix"},
        )
        assert result["intel_needed"] is True
        assert result["response_needed"] is True
        assert triage.INTEL_LABEL in result["recommended_labels"]
        assert triage.RESPONSE_LABEL in result["recommended_labels"]
        assert result["remove_labels"] == []
        assert "active-exploitation" in result["matched_response_indicators"]
        assert "exploit-available" in result["matched_response_indicators"]
        assert "ghsa" in result["matched_intel_indicators"]

    def test_secret_leak_requires_response(self) -> None:
        result = triage.classify(
            "fix: rotate token after exposure",
            "Credential exposure in a workflow log.",
            set(),
        )
        assert result["intel_needed"] is True
        assert result["response_needed"] is True
        assert "credential-action" in result["matched_response_indicators"]
        assert "secret-leak" in result["matched_response_indicators"]

    def test_stale_automation_labels_are_removed(self) -> None:
        result = triage.classify(
            "docs: update runbook",
            "No concrete security advisory.",
            {triage.INTEL_LABEL, triage.RESPONSE_LABEL},
        )
        assert result["intel_needed"] is True
        assert result["response_needed"] is False
        assert result["recommended_labels"] == [triage.INTEL_LABEL]
        assert result["remove_labels"] == [triage.RESPONSE_LABEL]


class TestCli:
    def test_json_output(self, capsys) -> None:
        rc = triage.main(
            [
                "classify",
                "--title",
                "fix: evaluate CVE-2026-12345",
                "--format",
                "json",
            ]
        )
        captured = capsys.readouterr()
        assert rc == 0
        result = json.loads(captured.out)
        assert result["intel_needed"] is True
        assert result["response_needed"] is False

    def test_github_output_file(self, tmp_path: Path) -> None:
        out = tmp_path / "github_output"
        body = tmp_path / "body.md"
        body.write_text("Public exploit available.", encoding="utf-8")

        rc = triage.main(
            [
                "classify",
                "--title",
                "fix: respond to CVE-2026-12345",
                "--body-file",
                str(body),
                "--github-output",
                str(out),
            ]
        )

        assert rc == 0
        assert out.read_text(encoding="utf-8").splitlines() == [
            "intel_needed=true",
            "response_needed=true",
            "recommended_labels=threat:intel-needed,threat:response-needed",
            "remove_labels=",
        ]
