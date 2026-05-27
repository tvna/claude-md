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

    def test_ossf_malicious_package_match_escalates_response(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        malpkg = tmp_path / "malpkg.json"
        osv.write_text(
            json.dumps({"results": [{"vulns": []}], "details": {}}),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        malpkg.write_text(
            json.dumps(
                {
                    "malicious_packages": [
                        {
                            "id": "MAL-2026-7777",
                            "aliases": ["GHSA-mali-cious-pkg0"],
                            "affected": [
                                {
                                    "package": {"ecosystem": "PyPI", "name": "demo"},
                                    "versions": ["9.9.9"],
                                }
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
            malpkg_file=malpkg,
        )
        result = triage.classify_findings(findings, set())

        assert len(findings) == 1
        assert findings[0].source == triage.SOURCE_OSSF_MAL
        assert findings[0].vuln_id == "MAL-2026-7777"
        assert findings[0].advisory_type == triage.GHSA_MALWARE_TYPE
        assert "GHSA-mali-cious-pkg0" in findings[0].aliases
        assert result["intel_needed"] is True
        assert result["response_needed"] is True
        assert result["recommended_labels"] == [
            triage.INTEL_LABEL,
            triage.RESPONSE_LABEL,
        ]

    def test_ossf_non_matching_entry_does_not_label(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        malpkg = tmp_path / "malpkg.json"
        osv.write_text(
            json.dumps({"results": [{"vulns": []}], "details": {}}),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        malpkg.write_text(
            json.dumps(
                {
                    "malicious_packages": [
                        {
                            "id": "MAL-2026-8888",
                            "affected": [
                                {"package": {"ecosystem": "PyPI", "name": "other"}}
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
            malpkg_file=malpkg,
        )
        result = triage.classify_findings(findings, set())

        assert findings == []
        assert result["intel_needed"] is False
        assert result["response_needed"] is False
        assert result["recommended_labels"] == []
        assert result["remove_labels"] == []

    def test_ossf_drops_records_without_mal_prefix(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        malpkg = tmp_path / "malpkg.json"
        osv.write_text(
            json.dumps({"results": [{"vulns": []}], "details": {}}),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        malpkg.write_text(
            json.dumps(
                {
                    "malicious_packages": [
                        {
                            "id": "GHSA-aaaa-bbbb-cccc",
                            "affected": [
                                {"package": {"ecosystem": "PyPI", "name": "demo"}}
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
            malpkg_file=malpkg,
        )

        assert findings == []

    def test_ossf_and_osv_dedupe_preserves_source_attribution(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        malpkg = tmp_path / "malpkg.json"
        osv.write_text(
            json.dumps(
                {
                    "results": [{"vulns": [{"id": "MAL-2026-9999"}]}],
                    "details": {"MAL-2026-9999": {"aliases": []}},
                }
            ),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        malpkg.write_text(
            json.dumps(
                {
                    "malicious_packages": [
                        {
                            "id": "MAL-2026-9999",
                            "affected": [
                                {"package": {"ecosystem": "PyPI", "name": "demo"}}
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
            malpkg_file=malpkg,
        )
        result = triage.classify_findings(findings, set())

        assert len(findings) == 1
        assert findings[0].vuln_id == "MAL-2026-9999"
        assert triage.SOURCE_OSV in findings[0].source
        assert triage.SOURCE_OSSF_MAL in findings[0].source
        assert findings[0].advisory_type == triage.GHSA_MALWARE_TYPE
        assert result["response_needed"] is True

    def test_osv_mal_prefix_alone_escalates_response(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        osv.write_text(
            json.dumps(
                {
                    "results": [{"vulns": [{"id": "MAL-2026-1234"}]}],
                    "details": {"MAL-2026-1234": {"aliases": []}},
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

        assert len(findings) == 1
        assert findings[0].vuln_id == "MAL-2026-1234"
        assert findings[0].advisory_type == triage.GHSA_MALWARE_TYPE
        assert result["response_needed"] is True

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


class TestEpssEnrichment:
    """FIRST EPSS enrichment is advisory-only per #173.

    EPSS scores enrich the summary table but never escalate
    ``threat:response-needed`` on their own; KEV correlation and GHSA
    malware advisories remain the authoritative response signals.
    """

    @staticmethod
    def _write_empty_kev(path: Path) -> None:
        path.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")

    @staticmethod
    def _write_osv_with_cve(path: Path, vuln_id: str, cve: str) -> None:
        path.write_text(
            json.dumps(
                {
                    "results": [{"vulns": [{"id": vuln_id}]}],
                    "details": {vuln_id: {"aliases": [cve]}},
                }
            ),
            encoding="utf-8",
        )

    def test_epss_attaches_score_to_cve_aliased_finding(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        epss = tmp_path / "epss.json"
        self._write_osv_with_cve(osv, "GHSA-abcd-1234-wxyz", "CVE-2026-1111")
        self._write_empty_kev(kev)
        epss.write_text(
            json.dumps(
                {
                    "status": "OK",
                    "data": [
                        {"cve": "CVE-2026-1111", "epss": "0.42130", "percentile": "0.95210"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            epss_file=epss,
        )
        result = triage.classify_findings(findings, set())

        assert len(findings) == 1
        assert findings[0].epss_score == 0.4213
        assert findings[0].epss_percentile == 0.9521
        # Advisory-only: high EPSS without KEV/malware does not escalate.
        assert result["intel_needed"] is True
        assert result["response_needed"] is False
        assert result["recommended_labels"] == [triage.INTEL_LABEL]
        # finding_to_dict surfaces EPSS for downstream consumers.
        assert result["findings"][0]["epss_score"] == 0.4213
        assert result["findings"][0]["epss_percentile"] == 0.9521

    def test_high_epss_alone_does_not_escalate_response(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        epss = tmp_path / "epss.json"
        self._write_osv_with_cve(osv, "GHSA-zzzz-9999-yyyy", "CVE-2026-2222")
        self._write_empty_kev(kev)
        epss.write_text(
            json.dumps(
                {
                    "data": [
                        {"cve": "CVE-2026-2222", "epss": "0.97500", "percentile": "0.99900"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            epss_file=epss,
        )
        result = triage.classify_findings(findings, set())

        assert findings[0].epss_score == 0.975
        assert findings[0].known_exploited is False
        assert result["response_needed"] is False
        assert result["recommended_labels"] == [triage.INTEL_LABEL]

    def test_epss_supplements_kev_correlated_finding(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        epss = tmp_path / "epss.json"
        self._write_osv_with_cve(osv, "GHSA-abcd-1234-wxyz", "CVE-2026-1111")
        kev.write_text(
            json.dumps({"vulnerabilities": [{"cveID": "CVE-2026-1111"}]}),
            encoding="utf-8",
        )
        epss.write_text(
            json.dumps(
                {
                    "data": [
                        {"cve": "CVE-2026-1111", "epss": "0.88000", "percentile": "0.99000"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            epss_file=epss,
        )
        result = triage.classify_findings(findings, set())

        assert findings[0].known_exploited is True
        assert findings[0].epss_score == 0.88
        # KEV remains the authoritative response signal; EPSS rides along.
        assert result["response_needed"] is True
        assert result["recommended_labels"] == [
            triage.INTEL_LABEL,
            triage.RESPONSE_LABEL,
        ]

    def test_epss_missing_cve_leaves_finding_unchanged(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        epss = tmp_path / "epss.json"
        self._write_osv_with_cve(osv, "GHSA-abcd-1234-wxyz", "CVE-2026-1111")
        self._write_empty_kev(kev)
        # EPSS payload omits the relevant CVE -- FIRST returns no row when
        # the score is not yet published.
        epss.write_text(json.dumps({"data": []}), encoding="utf-8")

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            epss_file=epss,
        )

        assert findings[0].epss_score is None
        assert findings[0].epss_percentile is None

    def test_collect_cve_ids_filters_non_cve_identifiers(self) -> None:
        findings = [
            triage.Finding(
                dependency=triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock"),
                vuln_id="GHSA-aaaa-bbbb-cccc",
                aliases=("CVE-2026-3333", "OSV-2026-9", "not-a-cve"),
                source=triage.SOURCE_GHSA,
                known_exploited=False,
            ),
        ]
        assert triage._collect_cve_ids(findings) == ["CVE-2026-3333"]

    def test_fetch_epss_soft_fails_on_broken_fixture(self, tmp_path: Path) -> None:
        epss = tmp_path / "epss.json"
        epss.write_text("not json", encoding="utf-8")
        # Soft-fail returns an empty mapping so callers keep working.
        assert triage.fetch_epss_scores(["CVE-2026-1111"], epss_file=epss) == {}


class TestNvdEnrichment:
    """NVD CVE metadata enrichment (#174).

    NVD is a *supplemental* enrichment source -- it must never widen the
    finding set, never suppress findings on missing data, and never be
    treated as evidence-of-absence for response decisions.
    """

    def _osv_payload_with_cve_alias(self) -> dict[str, object]:
        return {
            "results": [{"vulns": [{"id": "GHSA-aaaa-bbbb-cccc"}]}],
            "details": {"GHSA-aaaa-bbbb-cccc": {"aliases": ["CVE-2026-9001"]}},
        }

    def _empty_kev(self) -> dict[str, object]:
        return {"vulnerabilities": []}

    def test_nvd_enrichment_attaches_cvss_cwe_and_references(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        nvd = tmp_path / "nvd.json"
        osv.write_text(json.dumps(self._osv_payload_with_cve_alias()), encoding="utf-8")
        kev.write_text(json.dumps(self._empty_kev()), encoding="utf-8")
        nvd.write_text(
            json.dumps(
                {
                    "cves": {
                        "CVE-2026-9001": {
                            "metrics": {
                                "cvssMetricV31": [
                                    {
                                        "cvssData": {
                                            "baseScore": 9.8,
                                            "baseSeverity": "CRITICAL",
                                        }
                                    }
                                ]
                            },
                            "weaknesses": [
                                {"description": [{"value": "CWE-79"}]},
                                {"description": [{"value": "CWE-94"}]},
                            ],
                            "references": [
                                {"url": "https://example.test/advisory-1"},
                                {"url": "https://example.test/advisory-2"},
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            nvd_file=nvd,
        )

        assert len(findings) == 1
        assert len(findings[0].nvd_metadata) == 1
        enrichment = findings[0].nvd_metadata[0]
        assert enrichment.cve_id == "CVE-2026-9001"
        assert enrichment.cvss_severity == "CRITICAL"
        assert enrichment.cvss_score == 9.8
        assert enrichment.cvss_version == "3.1"
        assert enrichment.cwe_ids == ("CWE-79", "CWE-94")
        assert enrichment.references == (
            "https://example.test/advisory-1",
            "https://example.test/advisory-2",
        )
        assert enrichment.source_url == "https://nvd.nist.gov/vuln/detail/CVE-2026-9001"

    def test_nvd_missing_metadata_preserves_finding(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        nvd = tmp_path / "nvd.json"
        osv.write_text(json.dumps(self._osv_payload_with_cve_alias()), encoding="utf-8")
        kev.write_text(json.dumps(self._empty_kev()), encoding="utf-8")
        nvd.write_text(json.dumps({"cves": {}}), encoding="utf-8")

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            nvd_file=nvd,
        )
        result = triage.classify_findings(findings, set())

        assert len(findings) == 1
        assert findings[0].nvd_metadata == ()
        assert result["intel_needed"] is True
        assert result["finding_count"] == 1

    def test_nvd_malformed_payload_preserves_finding(self, tmp_path: Path) -> None:
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        nvd = tmp_path / "nvd.json"
        osv.write_text(json.dumps(self._osv_payload_with_cve_alias()), encoding="utf-8")
        kev.write_text(json.dumps(self._empty_kev()), encoding="utf-8")
        nvd.write_text(
            json.dumps(
                {
                    "cves": {
                        "CVE-2026-9001": {
                            "metrics": "not-an-object",
                            "weaknesses": [],
                            "references": [],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            nvd_file=nvd,
        )
        result = triage.classify_findings(findings, set())

        assert len(findings) == 1
        assert findings[0].nvd_metadata == ()
        assert result["intel_needed"] is True

    def test_nvd_cvss_falls_back_v30_then_v2(self, tmp_path: Path) -> None:
        payload_v30 = {
            "metrics": {
                "cvssMetricV30": [
                    {"cvssData": {"baseScore": 7.5, "baseSeverity": "HIGH"}}
                ]
            }
        }
        result_v30 = triage.parse_nvd_cve(payload_v30, "CVE-2026-1")
        assert result_v30 is not None
        assert result_v30.cvss_version == "3.0"
        assert result_v30.cvss_severity == "HIGH"
        assert result_v30.cvss_score == 7.5

        payload_v2 = {
            "metrics": {
                "cvssMetricV2": [
                    {
                        "cvssData": {"baseScore": 5.0},
                        "baseSeverity": "MEDIUM",
                    }
                ]
            }
        }
        result_v2 = triage.parse_nvd_cve(payload_v2, "CVE-2026-2")
        assert result_v2 is not None
        assert result_v2.cvss_version == "2.0"
        assert result_v2.cvss_severity == "MEDIUM"
        assert result_v2.cvss_score == 5.0

    def test_nvd_does_not_alter_findings_without_cve_aliases(self, tmp_path: Path) -> None:
        """GHSA findings without a CVE alias must not be erased when NVD data is absent."""
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        ghsa = tmp_path / "ghsa.json"
        nvd = tmp_path / "nvd.json"
        osv.write_text(
            json.dumps({"results": [{"vulns": []}], "details": {}}),
            encoding="utf-8",
        )
        kev.write_text(json.dumps(self._empty_kev()), encoding="utf-8")
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
        nvd.write_text(json.dumps({"cves": {}}), encoding="utf-8")

        findings = triage.fetch_external_findings(
            [triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock")],
            osv_file=osv,
            kev_file=kev,
            ghsa_file=ghsa,
            nvd_file=nvd,
        )

        assert len(findings) == 1
        assert findings[0].nvd_metadata == ()
        assert findings[0].advisory_type == triage.GHSA_MALWARE_TYPE

    def test_scan_summary_includes_nvd_metadata(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        nvd = tmp_path / "nvd.json"
        summary = tmp_path / "summary.md"
        osv.write_text(json.dumps(self._osv_payload_with_cve_alias()), encoding="utf-8")
        kev.write_text(json.dumps(self._empty_kev()), encoding="utf-8")
        nvd.write_text(
            json.dumps(
                {
                    "cves": {
                        "CVE-2026-9001": {
                            "metrics": {
                                "cvssMetricV31": [
                                    {
                                        "cvssData": {
                                            "baseScore": 9.8,
                                            "baseSeverity": "CRITICAL",
                                        }
                                    }
                                ]
                            },
                            "weaknesses": [{"description": [{"value": "CWE-79"}]}],
                            "references": [{"url": "https://example.test/a"}],
                        }
                    }
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
                "--nvd-file",
                str(nvd),
                "--summary-file",
                str(summary),
                "--format",
                "json",
            ]
        )
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert rc == 0
        assert result["intel_needed"] is True
        summary_text = summary.read_text(encoding="utf-8")
        assert "NVD CVSS" in summary_text
        assert "NVD CWE" in summary_text
        assert "CRITICAL" in summary_text
        assert "CWE-79" in summary_text
        assert "https://example.test/a" in summary_text
        assert "Missing NVD enrichment does not imply" in summary_text
        assert "https://nvd.nist.gov/vuln/detail/CVE-2026-9001" in summary_text

        finding_entry = result["findings"][0]
        assert finding_entry["nvd_metadata"][0]["cve_id"] == "CVE-2026-9001"
        assert finding_entry["nvd_metadata"][0]["cvss_severity"] == "CRITICAL"
        assert finding_entry["nvd_metadata"][0]["cwe_ids"] == ["CWE-79"]


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

    def test_scan_includes_ossf_source_in_summary(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        malpkg = tmp_path / "malpkg.json"
        summary = tmp_path / "summary.md"
        out = tmp_path / "github_output"
        osv.write_text(
            json.dumps({"results": [{"vulns": []}], "details": {}}),
            encoding="utf-8",
        )
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        malpkg.write_text(
            json.dumps(
                {
                    "malicious_packages": [
                        {
                            "id": "MAL-2026-7777",
                            "affected": [
                                {"package": {"ecosystem": "PyPI", "name": "demo"}}
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
                "--malpkg-file",
                str(malpkg),
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
        assert result["recommended_labels"] == [
            triage.INTEL_LABEL,
            triage.RESPONSE_LABEL,
        ]
        summary_text = summary.read_text(encoding="utf-8")
        assert triage.SOURCE_OSSF_MAL in summary_text
        assert "CISA KEV" in summary_text
        assert out.read_text(encoding="utf-8").splitlines() == [
            "intel_needed=true",
            "response_needed=true",
            "recommended_labels=threat:intel-needed,threat:response-needed",
            "remove_labels=",
        ]

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

    def test_scan_includes_epss_in_summary(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        osv = tmp_path / "osv.json"
        kev = tmp_path / "kev.json"
        epss = tmp_path / "epss.json"
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
        kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        epss.write_text(
            json.dumps(
                {
                    "data": [
                        {"cve": "CVE-2026-1111", "epss": "0.42130", "percentile": "0.95210"},
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
                "--epss-file",
                str(epss),
                "--summary-file",
                str(summary),
                "--format",
                "json",
            ]
        )
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert rc == 0
        # EPSS is advisory-only and must not flip response_needed.
        assert result["response_needed"] is False
        summary_text = summary.read_text(encoding="utf-8")
        assert "FIRST EPSS" in summary_text
        assert "| EPSS |" in summary_text
        assert "0.421 (p95.2%)" in summary_text
