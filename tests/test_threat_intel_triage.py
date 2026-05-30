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
        assert result["recommended_labels"] == []
        assert result["remove_labels"] == [triage.RESPONSE_LABEL]

    def test_existing_needed_label_is_not_recommended_again(self) -> None:
        result = triage.classify(
            "fix: evaluate CVE-2026-12345",
            "Need to determine whether this repo is affected.",
            {triage.INTEL_LABEL},
        )
        assert result["intel_needed"] is True
        assert result["response_needed"] is False
        assert result["recommended_labels"] == []
        assert result["remove_labels"] == []


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

    def test_parse_workflow_actions_sha_pinned_uses_tag_comment(
        self, tmp_path: Path
    ) -> None:
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "ci.yml"
        workflow.write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: actions/checkout@"
            "abcdef0123456789abcdef0123456789abcdef01 # v4.2.0\n"
            "      - uses: actions/setup-python@v5\n",
            encoding="utf-8",
        )

        deps = triage.parse_workflow_actions(tmp_path)

        assert deps == [
            triage.Dependency(
                "actions/checkout",
                "v4.2.0",
                triage.ECOSYSTEM_ACTIONS,
                str(workflow),
            ),
            triage.Dependency(
                "actions/setup-python",
                "v5",
                triage.ECOSYSTEM_ACTIONS,
                str(workflow),
            ),
        ]

    def test_parse_workflow_actions_sha_without_tag_falls_back_to_sha(
        self, tmp_path: Path
    ) -> None:
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "ci.yml"
        sha = "abcdef0123456789abcdef0123456789abcdef01"
        workflow.write_text(
            f"jobs:\n  build:\n    steps:\n      - uses: actions/checkout@{sha}\n",
            encoding="utf-8",
        )

        deps = triage.parse_workflow_actions(tmp_path)

        assert deps == [
            triage.Dependency(
                "actions/checkout", sha, triage.ECOSYSTEM_ACTIONS, str(workflow)
            ),
        ]

    def test_parse_workflow_actions_skips_local_and_docker(
        self, tmp_path: Path
    ) -> None:
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "ci.yml"
        workflow.write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: ./.github/workflows/reusable.yml\n"
            "      - uses: ../local/composite.yml\n"
            "      - uses: docker://example.com/image:tag\n"
            "      - uses: owner/action@v1\n",
            encoding="utf-8",
        )

        deps = triage.parse_workflow_actions(tmp_path)

        assert deps == [
            triage.Dependency(
                "owner/action", "v1", triage.ECOSYSTEM_ACTIONS, str(workflow)
            ),
        ]

    def test_parse_workflow_actions_skips_comment_lines(
        self, tmp_path: Path
    ) -> None:
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "ci.yml"
        workflow.write_text(
            "# - uses: actions/forbidden-example@v1\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: actions/real@v2\n",
            encoding="utf-8",
        )

        deps = triage.parse_workflow_actions(tmp_path)

        assert deps == [
            triage.Dependency(
                "actions/real", "v2", triage.ECOSYSTEM_ACTIONS, str(workflow)
            ),
        ]

    def test_parse_transient_uv_run_captures_exact_pin(
        self, tmp_path: Path
    ) -> None:
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "ci.yml"
        workflow.write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            '      - run: uv run --with "apm-cli==0.5.0" apm compile\n',
            encoding="utf-8",
        )

        deps = triage.parse_transient_uv_run(tmp_path)

        assert deps == [
            triage.Dependency(
                "apm-cli", "0.5.0", triage.ECOSYSTEM_PYPI, str(workflow)
            ),
        ]

    def test_parse_transient_uv_run_scans_scripts(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)
        script = scripts_dir / "bootstrap.sh"
        script.write_text(
            "#!/bin/sh\n"
            "uv run --with cowsay==6.1 cowsay hi\n",
            encoding="utf-8",
        )

        deps = triage.parse_transient_uv_run(tmp_path)

        assert deps == [
            triage.Dependency(
                "cowsay", "6.1", triage.ECOSYSTEM_PYPI, str(script)
            ),
        ]

    def test_parse_transient_uv_run_ignores_shell_vars_and_ranges(
        self, tmp_path: Path
    ) -> None:
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "ci.yml"
        workflow.write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            '      - run: uv run --with "apm-cli==${APM_CLI_VERSION}" apm compile\n'
            '      - run: uv run --with "apm-cli==<pin>" apm compile\n'
            '      - run: uv run --with "ruff>=0.5,<0.6" ruff check\n'
            '      - run: uv run --with "polars~=1.0" python -c "import polars"\n',
            encoding="utf-8",
        )

        assert triage.parse_transient_uv_run(tmp_path) == []

    def test_parse_transient_uv_run_ignores_non_executable_prose(
        self, tmp_path: Path
    ) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "note.md").write_text(
            "Run `uv run --with apm-cli==9.9.9 apm compile` to repro.\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "Quick start: `uv run --with apm-cli==9.9.9 apm compile`.\n",
            encoding="utf-8",
        )

        assert triage.parse_transient_uv_run(tmp_path) == []

    def test_discover_dependencies_includes_workflow_actions_and_transient(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "pytest"\nversion = "8.3.5"\n',
            encoding="utf-8",
        )
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "ci.yml"
        workflow.write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: actions/checkout@"
            "abcdef0123456789abcdef0123456789abcdef01 # v4.2.0\n"
            '      - run: uv run --with apm-cli==0.5.0 apm compile\n',
            encoding="utf-8",
        )

        deps = triage.discover_dependencies(tmp_path)

        assert triage.Dependency(
            "actions/checkout",
            "v4.2.0",
            triage.ECOSYSTEM_ACTIONS,
            str(workflow),
        ) in deps
        assert triage.Dependency(
            "apm-cli", "0.5.0", triage.ECOSYSTEM_PYPI, str(workflow)
        ) in deps
        assert triage.Dependency(
            "pytest", "8.3.5", triage.ECOSYSTEM_PYPI, str(tmp_path / "uv.lock")
        ) in deps


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
        assert result["recommended_labels"] == [triage.RESPONSE_LABEL]
        assert result["remove_labels"] == []

    def test_existing_finding_label_is_not_recommended_again(
        self, tmp_path: Path
    ) -> None:
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
        result = triage.classify_findings(findings, {triage.INTEL_LABEL})

        assert result["intel_needed"] is True
        assert result["response_needed"] is False
        assert result["recommended_labels"] == []
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
        assert result["intel_needed"] is True
        assert result["response_needed"] is False
        assert result["recommended_labels"] == [triage.INTEL_LABEL]
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
        assert triage.fetch_epss_scores(["CVE-2026-1111"], epss_file=epss) == {}


class TestNvdEnrichment:
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
        assert result["response_needed"] is False
        summary_text = summary.read_text(encoding="utf-8")
        assert "FIRST EPSS" in summary_text
        assert "| EPSS |" in summary_text
        assert "0.421 (p95.2%)" in summary_text


# ---------------------------------------------------------------------------
# Missing line coverage
# ---------------------------------------------------------------------------


class TestParseOsvBatchResultsBranches:
    def test_non_dict_result_yields_empty(self) -> None:
        dep = triage.Dependency("demo", "1.0.0", "PyPI", "lock")
        data: dict[str, object] = {"results": ["not-a-dict"]}
        out = triage.parse_osv_batch_results([dep], data)
        assert out == [(dep, [])]

    def test_non_list_vulns_yields_empty(self) -> None:
        dep = triage.Dependency("demo", "1.0.0", "PyPI", "lock")
        data: dict[str, object] = {"results": [{"vulns": "bad"}]}
        out = triage.parse_osv_batch_results([dep], data)
        assert out == [(dep, [])]

    def test_non_list_results_raises(self) -> None:
        dep = triage.Dependency("demo", "1.0.0", "PyPI", "lock")
        import pytest as _pytest
        with _pytest.raises(ValueError, match="results array"):
            triage.parse_osv_batch_results([dep], {"results": "not-a-list"})


class TestParseKevCvesBranches:
    def test_non_list_vulnerabilities_raises(self) -> None:
        import pytest as _pytest
        with _pytest.raises(ValueError, match="vulnerabilities array"):
            triage.parse_kev_cves({"vulnerabilities": "bad"})

    def test_non_dict_vulnerability_entry_is_skipped(self) -> None:
        result = triage.parse_kev_cves({"vulnerabilities": ["not-a-dict", {"cveID": "CVE-1"}]})
        assert result == {"CVE-1"}


class TestParseEpssPayloadBranches:
    def test_non_list_data_returns_empty(self) -> None:
        assert triage._parse_epss_payload({"data": "bad"}) == {}

    def test_non_dict_row_is_skipped(self) -> None:
        assert triage._parse_epss_payload({"data": ["not-a-dict"]}) == {}


class TestCoerceEpssFloat:
    def test_int_input(self) -> None:
        assert triage._coerce_epss_float(1) == 1.0

    def test_str_input_valid(self) -> None:
        assert triage._coerce_epss_float("0.5") == 0.5

    def test_str_input_invalid(self) -> None:
        assert triage._coerce_epss_float("notfloat") is None

    def test_none_input(self) -> None:
        assert triage._coerce_epss_float(None) is None


class TestAttachEpss:
    def test_no_scores_returns_finding_unchanged(self) -> None:
        finding = triage.Finding(
            dependency=triage.Dependency("demo", "1.0.0", "PyPI", "lock"),
            vuln_id="CVE-1",
            aliases=(),
            source=triage.SOURCE_OSV,
            known_exploited=False,
        )
        assert triage._attach_epss(finding, {}) is finding

    def test_no_match_returns_finding_unchanged(self) -> None:
        finding = triage.Finding(
            dependency=triage.Dependency("demo", "1.0.0", "PyPI", "lock"),
            vuln_id="CVE-1",
            aliases=(),
            source=triage.SOURCE_OSV,
            known_exploited=False,
        )
        result = triage._attach_epss(finding, {"CVE-2": (0.5, 0.9)})
        assert result is finding


class TestFetchEpssLivePath:
    def test_live_mode_calls_request_json_and_returns_scores(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            triage,
            "request_json",
            lambda _url: {"data": [{"cve": "CVE-2026-1111", "epss": "0.5", "percentile": "0.9"}]},
        )
        result = triage.fetch_epss_scores(["CVE-2026-1111"], epss_live=True)
        assert result == {"CVE-2026-1111": (0.5, 0.9)}

    def test_live_mode_soft_fails_on_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_err(_url: str) -> dict:
            raise OSError("network error")

        monkeypatch.setattr(triage, "request_json", raise_err)
        result = triage.fetch_epss_scores(["CVE-1"], epss_live=True)
        assert result == {}


class TestQueryOsvBatch:
    def test_calls_request_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}
        monkeypatch.setattr(
            triage,
            "request_json",
            lambda url, payload=None, **kw: captured.update({"url": url, "payload": payload}) or {"results": []},
        )
        dep = triage.Dependency("demo", "1.0.0", "PyPI", "lock")
        result = triage.query_osv_batch([dep])
        assert "results" in result
        assert captured["payload"] == {
            "queries": [{"version": "1.0.0", "package": {"name": "demo", "ecosystem": "PyPI"}}]
        }


class TestFetchCisaKev:
    def test_calls_request_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            triage, "request_json", lambda url: {"vulnerabilities": []}
        )
        result = triage.fetch_cisa_kev()
        assert result == {"vulnerabilities": []}


class TestFetchOsvDetailsLivePath:
    def test_live_fetches_each_vuln(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def fake_request(url: str) -> dict:
            calls.append(url)
            return {"id": url.split("/")[-1]}

        monkeypatch.setattr(triage, "request_json", fake_request)
        dep = triage.Dependency("demo", "1.0.0", "PyPI", "lock")
        result = triage.fetch_osv_details([(dep, ["GHSA-aaaa", "GHSA-bbbb"])])
        assert set(result.keys()) == {"GHSA-aaaa", "GHSA-bbbb"}
        assert len(calls) == 2
