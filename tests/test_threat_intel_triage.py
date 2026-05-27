"""Tests for ``scripts/threat_intel_triage.py``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import threat_intel_triage as triage

pytestmark = pytest.mark.shard_ci_ops


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


class TestDependencyDiscovery:
    def test_parse_uv_lock(self, tmp_path: Path) -> None:
        lock = tmp_path / "uv.lock"
        lock.write_text(
            '[[package]]\nname = "pytest"\nversion = "8.3.5"\n\n'
            '[[package]]\nname = "pluggy"\nversion = "1.5.0"\n',
            encoding="utf-8",
        )

        assert triage.parse_uv_lock(lock) == [
            triage.Dependency("pytest", "8.3.5", "PyPI", str(lock)),
            triage.Dependency("pluggy", "1.5.0", "PyPI", str(lock)),
        ]

    def test_pyproject_only_uses_exact_pins(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[project]\n"
            'dependencies = ["requests==2.31.0", "pytest>=8,<9"]\n'
            "\n[dependency-groups]\n"
            'dev = ["pluggy==1.5.0"]\n',
            encoding="utf-8",
        )

        assert triage.parse_pyproject_pinned_dependencies(pyproject) == [
            triage.Dependency("requests", "2.31.0", "PyPI", str(pyproject)),
            triage.Dependency("pluggy", "1.5.0", "PyPI", str(pyproject)),
        ]

    def test_discover_dependencies_deduplicates(self, tmp_path: Path) -> None:
        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "pytest"\nversion = "8.3.5"\n',
            encoding="utf-8",
        )
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            'dependencies = ["pytest==8.3.5"]\n',
            encoding="utf-8",
        )

        assert triage.discover_dependencies(tmp_path) == [
            triage.Dependency("pytest", "8.3.5", "PyPI", str(tmp_path / "uv.lock")),
        ]


class TestExternalFindings:
    def test_parse_kev_cves(self) -> None:
        assert triage.parse_kev_cves(
            {"vulnerabilities": [{"cveID": "CVE-2026-1111"}, {"cveID": "CVE-2026-2222"}]}
        ) == {"CVE-2026-1111", "CVE-2026-2222"}

    def test_osv_finding_requires_intel(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        osv.write_text(
            json.dumps(
                {
                    "results": [{"vulns": [{"id": "GHSA-abcd-1234-wxyz"}]}],
                    "details": {"GHSA-abcd-1234-wxyz": {"aliases": ["CVE-2026-1111"]}},
                }
            ),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
        )
        result = triage.classify_findings(findings, set())

        assert result["intel_needed"] is True
        assert result["response_needed"] is False
        assert result["recommended_labels"] == [triage.INTEL_LABEL]
        assert result["finding_count"] == 1

    def test_cisa_kev_alias_requires_response(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        osv.write_text(
            json.dumps(
                {
                    "results": [{"vulns": [{"id": "GHSA-abcd-1234-wxyz"}]}],
                    "details": {"GHSA-abcd-1234-wxyz": {"aliases": ["CVE-2026-1111"]}},
                }
            ),
            encoding="utf-8",
        )
        kev.write_text(
            json.dumps({"vulnerabilities": [{"cveID": "CVE-2026-1111"}]}),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
        )
        result = triage.classify_findings(findings, {triage.INTEL_LABEL})

        assert findings[0].known_exploited is True
        assert result["intel_needed"] is True
        assert result["response_needed"] is True
        assert result["recommended_labels"] == [
            triage.INTEL_LABEL,
            triage.RESPONSE_LABEL,
        ]
        assert result["remove_labels"] == []

    def test_ghsa_finding_matches_locked_dependency(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        ghsa = tmp_path / "ghsa.json"
        osv.write_text(
            json.dumps({"results": [{"vulns": []}], "details": {}}),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        ghsa.write_text(
            json.dumps(
                {
                    "advisories": [
                        {
                            "ghsa_id": "GHSA-aaaa-bbbb-cccc",
                            "cve_id": "CVE-2026-3333",
                            "type": "reviewed",
                            "severity": "high",
                            "identifiers": [
                                {"type": "GHSA", "value": "GHSA-aaaa-bbbb-cccc"},
                                {"type": "CVE", "value": "CVE-2026-3333"},
                            ],
                            "vulnerabilities": [
                                {"package": {"ecosystem": "pip", "name": "demo"}},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            ghsa_file=ghsa,
        )
        result = triage.classify_findings(findings, set())

        assert len(findings) == 1
        assert findings[0].source == triage.SOURCE_GHSA
        assert findings[0].vuln_id == "GHSA-aaaa-bbbb-cccc"
        assert findings[0].advisory_type == "reviewed"
        assert "CVE-2026-3333" in findings[0].aliases
        assert result["intel_needed"] is True
        assert result["response_needed"] is False
        assert result["recommended_labels"] == [triage.INTEL_LABEL]

    def test_ghsa_malware_advisory_escalates_response(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        ghsa = tmp_path / "ghsa.json"
        osv.write_text(
            json.dumps({"results": [{"vulns": []}], "details": {}}),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        ghsa.write_text(
            json.dumps(
                {
                    "advisories": [
                        {
                            "ghsa_id": "GHSA-mmmm-nnnn-oooo",
                            "cve_id": None,
                            "type": "malware",
                            "severity": "critical",
                            "identifiers": [
                                {"type": "GHSA", "value": "GHSA-mmmm-nnnn-oooo"}
                            ],
                            "vulnerabilities": [
                                {"package": {"ecosystem": "pip", "name": "demo"}},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            ghsa_file=ghsa,
        )
        result = triage.classify_findings(findings, set())

        assert len(findings) == 1
        assert findings[0].advisory_type == triage.GHSA_MALWARE_TYPE
        assert findings[0].known_exploited is False
        assert result["intel_needed"] is True
        assert result["response_needed"] is True
        assert result["recommended_labels"] == [
            triage.INTEL_LABEL,
            triage.RESPONSE_LABEL,
        ]

    def test_ghsa_and_osv_dedupe_preserves_source_attribution(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        ghsa = tmp_path / "ghsa.json"
        osv.write_text(
            json.dumps(
                {
                    "results": [{"vulns": [{"id": "GHSA-aaaa-bbbb-cccc"}]}],
                    "details": {"GHSA-aaaa-bbbb-cccc": {"aliases": ["CVE-2026-3333"]}},
                }
            ),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        ghsa.write_text(
            json.dumps(
                {
                    "advisories": [
                        {
                            "ghsa_id": "GHSA-aaaa-bbbb-cccc",
                            "cve_id": "CVE-2026-3333",
                            "type": "reviewed",
                            "vulnerabilities": [
                                {"package": {"ecosystem": "pip", "name": "demo"}},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            ghsa_file=ghsa,
        )

        assert len(findings) == 1
        assert findings[0].vuln_id == "GHSA-aaaa-bbbb-cccc"
        assert triage.SOURCE_OSV in findings[0].source
        assert triage.SOURCE_GHSA in findings[0].source
        assert findings[0].advisory_type == "reviewed"
        assert "CVE-2026-3333" in findings[0].aliases


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

    def test_scan_uses_external_fixtures(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        out = tmp_path / "github_output"
        summary = tmp_path / "summary.md"
        osv.write_text(
            json.dumps(
                {
                    "results": [{"vulns": [{"id": "GHSA-abcd-1234-wxyz"}]}],
                    "details": {"GHSA-abcd-1234-wxyz": {"aliases": ["CVE-2026-1111"]}},
                }
            ),
            encoding="utf-8",
        )
        kev.write_text(
            json.dumps({"vulnerabilities": [{"cveID": "CVE-2026-1111"}]}),
            encoding="utf-8",
        )

        rc = triage.main(
            [
                "scan",
                "--repo-root",
                str(tmp_path),
                "--osv-file",
                str(osv),
                "--kev-file",
                str(kev),
                "--github-output",
                str(out),
                "--summary-file",
                str(summary),
                "--format",
                "json",
            ]
        )
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert rc == 0
        assert result["response_needed"] is True
        assert out.read_text(encoding="utf-8").splitlines() == [
            "intel_needed=true",
            "response_needed=true",
            "recommended_labels=threat:intel-needed,threat:response-needed",
            "remove_labels=",
        ]
        assert "Sources: OSV.dev, CISA KEV" in summary.read_text(encoding="utf-8")

    def test_scan_includes_ghsa_source_in_summary(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        ghsa = tmp_path / "ghsa.json"
        summary = tmp_path / "summary.md"
        osv.write_text(
            json.dumps({"results": [{"vulns": []}], "details": {}}),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        ghsa.write_text(
            json.dumps(
                {
                    "advisories": [
                        {
                            "ghsa_id": "GHSA-mmmm-nnnn-oooo",
                            "type": "malware",
                            "vulnerabilities": [
                                {"package": {"ecosystem": "pip", "name": "demo"}},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        rc = triage.main(
            [
                "scan",
                "--repo-root",
                str(tmp_path),
                "--osv-file",
                str(osv),
                "--kev-file",
                str(kev),
                "--ghsa-file",
                str(ghsa),
                "--summary-file",
                str(summary),
                "--format",
                "json",
            ]
        )
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert rc == 0
        assert result["response_needed"] is True
        summary_text = summary.read_text(encoding="utf-8")
        assert "GitHub Advisory" in summary_text
        assert "CISA KEV" in summary_text
        assert "| Source |" in summary_text
