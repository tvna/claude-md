"""Tests for ``scripts/threat_intel_triage.py``."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import threat_intel_triage as triage

pytestmark = pytest.mark.shard_ci_ops_2


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

    def test_parse_workflow_pinned_images_reads_threat_intel_pin(
        self, tmp_path: Path
    ) -> None:
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "scan.yml"
        workflow.write_text(
            "jobs:\n"
            "  scan:\n"
            "    steps:\n"
            "      - run: |\n"
            "          # threat-intel-pin: Go github.com/aquasecurity/trivy 0.70.0\n"
            "          docker run --rm ghcr.io/aquasecurity/trivy@sha256:abc image\n",
            encoding="utf-8",
        )

        deps = triage.parse_workflow_pinned_images(tmp_path)

        assert deps == [
            triage.Dependency(
                "github.com/aquasecurity/trivy",
                "0.70.0",
                "Go",
                str(workflow),
            ),
        ]

    def test_parse_workflow_pinned_images_ignores_unmarked_comments(
        self, tmp_path: Path
    ) -> None:
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "scan.yml"
        workflow.write_text(
            "jobs:\n"
            "  scan:\n"
            "    steps:\n"
            "      - run: |\n"
            "          # just a normal comment, not a pin\n"
            "          docker run ghcr.io/aquasecurity/trivy@sha256:abc image\n",
            encoding="utf-8",
        )

        assert triage.parse_workflow_pinned_images(tmp_path) == []

    def test_parse_workflow_pinned_images_empty_without_workflow_dir(
        self, tmp_path: Path
    ) -> None:
        assert triage.parse_workflow_pinned_images(tmp_path) == []

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
        # Per #176: README / runbook prose is not an executable input.
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
            '      - run: uv run --with apm-cli==0.5.0 apm compile\n'
            "      - run: |\n"
            "          # threat-intel-pin: Go github.com/aquasecurity/trivy 0.70.0\n"
            "          docker run ghcr.io/aquasecurity/trivy@sha256:abc image\n",
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
            "github.com/aquasecurity/trivy", "0.70.0", "Go", str(workflow)
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


# ---------------------------------------------------------------------------
# parse_uv_lock() -- non-list packages and non-dict package entries
# ---------------------------------------------------------------------------


class TestParseUvLockEdgeCases:
    def test_non_list_packages_returns_empty(self, tmp_path: Path) -> None:
        lock = tmp_path / "uv.lock"
        lock.write_text('[metadata]\n[package]\nname = "x"\n', encoding="utf-8")
        # TOML with package as a dict (not array) hits the non-list guard.
        # We patch the return value directly to avoid TOML format constraints.
        import tomllib

        content = lock.read_text(encoding="utf-8")
        data = tomllib.loads(content)
        data["package"] = "not-a-list"
        # Test the function with the guard by creating a TOML that produces a dict for "package".
        # Easier: write valid TOML with a non-array package value and call via Path.
        lock.write_text('[package]\nname = "x"\n', encoding="utf-8")
        result = triage.parse_uv_lock(lock)
        # "package" is a TOML table (dict), not an array -> isinstance check triggers
        assert result == []

    def test_non_dict_package_entry_is_skipped(self, tmp_path: Path) -> None:
        lock = tmp_path / "uv.lock"
        # Write valid TOML array with one valid and one non-dict entry.
        # TOML arrays of tables require [[package]] syntax.
        lock.write_text(
            '[[package]]\nname = "pytest"\nversion = "8.3.5"\n',
            encoding="utf-8",
        )
        # patch the loaded data to include a non-dict entry
        import tomllib as _tomllib

        orig_loads = _tomllib.loads

        def fake_loads(text: str) -> dict:
            data = orig_loads(text)
            data["package"] = [{"name": "pytest", "version": "8.3.5"}, "not-a-dict"]
            return data

        import sys
        sys.modules["tomllib"].loads = fake_loads  # type: ignore[attr-defined]
        try:
            result = triage.parse_uv_lock(lock)
        finally:
            sys.modules["tomllib"].loads = orig_loads  # type: ignore[attr-defined]
        # The non-dict entry should be skipped; only the valid one kept.
        assert len(result) == 1
        assert result[0].name == "pytest"


# ---------------------------------------------------------------------------
# parse_workflow_actions() -- missing .github/workflows directory (line 307)
# ---------------------------------------------------------------------------


class TestParseWorkflowActionsNoDir:
    def test_returns_empty_when_workflow_dir_missing(self, tmp_path: Path) -> None:
        result = triage.parse_workflow_actions(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# scan_dependencies() -- empty list returns [] immediately (line 438)
# ---------------------------------------------------------------------------


class TestFetchExternalFindingsEmpty:
    def test_empty_dependencies_returns_empty_list(self, tmp_path: Path) -> None:
        result = triage.fetch_external_findings([])
        assert result == []


# ---------------------------------------------------------------------------
# parse_osv_batch_results() -- defensive isinstance checks (lines 540, 545-546, 549-550)
# ---------------------------------------------------------------------------


class TestParseOsvBatchResultsDefensiveChecks:
    def test_non_list_results_raises(self) -> None:
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        with pytest.raises(ValueError, match="results array"):
            triage.parse_osv_batch_results([dep], {"results": "not-a-list"})

    def test_non_dict_result_entry_yields_empty_ids(self) -> None:
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        result = triage.parse_osv_batch_results([dep], {"results": ["not-a-dict"]})
        assert result == [(dep, [])]

    def test_non_list_vulns_yields_empty_ids(self) -> None:
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        result = triage.parse_osv_batch_results([dep], {"results": [{"vulns": "not-a-list"}]})
        assert result == [(dep, [])]


# ---------------------------------------------------------------------------
# parse_kev_cves() -- non-list vulnerabilities raises; non-dict entry skipped
# ---------------------------------------------------------------------------


class TestParseKevCvesEdgeCases:
    def test_non_list_vulnerabilities_raises(self) -> None:
        with pytest.raises(ValueError, match="vulnerabilities array"):
            triage.parse_kev_cves({"vulnerabilities": "not-a-list"})

    def test_non_dict_vulnerability_is_skipped(self) -> None:
        result = triage.parse_kev_cves({"vulnerabilities": ["not-a-dict", {"cveID": "CVE-2026-1"}]})
        assert result == {"CVE-2026-1"}


# ---------------------------------------------------------------------------
# request_json_any() -- mock urlopen (lines 1471-1488)
# ---------------------------------------------------------------------------


class TestRequestJsonAny:
    def test_get_request_returns_parsed_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import urllib.request as _urllib_request

        response_body = json.dumps({"ok": True}).encode("utf-8")

        class _FakeResponse:
            def read(self) -> bytes:
                return response_body

            def __enter__(self) -> _FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        monkeypatch.setattr(_urllib_request, "urlopen", lambda req, timeout=None: _FakeResponse())
        result = triage.request_json_any("https://example.com/api")
        assert result == {"ok": True}

    def test_post_request_sends_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import urllib.request as _urllib_request

        captured_requests: list[_urllib_request.Request] = []

        class _FakeResponse:
            def read(self) -> bytes:
                return b'{"result": "ok"}'

            def __enter__(self) -> _FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        def fake_urlopen(req: object, timeout: object = None) -> _FakeResponse:
            captured_requests.append(req)  # type: ignore[arg-type]
            return _FakeResponse()

        monkeypatch.setattr(_urllib_request, "urlopen", fake_urlopen)
        result = triage.request_json_any("https://example.com/api", payload={"key": "val"})
        assert result == {"result": "ok"}
        assert captured_requests[0].method == "POST"

    def test_token_adds_authorization_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import urllib.request as _urllib_request

        captured_requests: list[_urllib_request.Request] = []

        class _FakeResponse:
            def read(self) -> bytes:
                return b'{"ok": true}'

            def __enter__(self) -> _FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        def fake_urlopen(req: object, timeout: object = None) -> _FakeResponse:
            captured_requests.append(req)  # type: ignore[arg-type]
            return _FakeResponse()

        monkeypatch.setattr(_urllib_request, "urlopen", fake_urlopen)
        triage.request_json_any("https://example.com/api", token="secret-token")
        auth = captured_requests[0].get_header("Authorization")
        assert auth == "Bearer secret-token"


# ---------------------------------------------------------------------------
# query_osv_batch() and fetch_cisa_kev() -- mock request_json (lines 499-510)
# ---------------------------------------------------------------------------


class TestNetworkBoundaryFunctions:
    def test_query_osv_batch_returns_request_json_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = {"results": []}
        monkeypatch.setattr(triage, "request_json", lambda *a, **kw: payload)
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        result = triage.query_osv_batch([dep])
        assert result == payload

    def test_fetch_cisa_kev_returns_request_json_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = {"vulnerabilities": []}
        monkeypatch.setattr(triage, "request_json", lambda *a, **kw: payload)
        result = triage.fetch_cisa_kev()
        assert result == payload

    def test_fetch_osv_details_no_file_calls_request_json(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        details = {"GHSA-xxxx-xxxx-xxxx": {"aliases": []}}
        monkeypatch.setattr(triage, "request_json", lambda *a, **kw: details)
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        result = triage.fetch_osv_details([(dep, ["GHSA-xxxx-xxxx-xxxx"])])
        assert "GHSA-xxxx-xxxx-xxxx" in result


# ---------------------------------------------------------------------------
# parse_uv_lock() -- file not found (line 195)
# ---------------------------------------------------------------------------


class TestParseUvLockFileMissing:
    def test_returns_empty_when_file_does_not_exist(self, tmp_path: Path) -> None:
        result = triage.parse_uv_lock(tmp_path / "nonexistent.lock")
        assert result == []


# ---------------------------------------------------------------------------
# parse_workflow_actions() -- non-yml file triggers continue (line 307)
# ---------------------------------------------------------------------------


class TestParseWorkflowActionsNonYml:
    def test_skips_non_yml_files_in_workflow_dir(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "README.md").write_text("not a workflow\n")
        result = triage.parse_workflow_actions(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# _parse_action_ref() -- missing @ (line 348) and malformed ref (line 351)
# ---------------------------------------------------------------------------


class TestParseActionRefEdgeCases:
    def test_returns_none_when_no_at_sign(self) -> None:
        assert triage._parse_action_reference("actions/checkout", None) is None

    def test_returns_none_when_no_slash_in_owner_repo(self) -> None:
        assert triage._parse_action_reference("@abc123", None) is None


# ---------------------------------------------------------------------------
# fetch_osv_details() -- file mode with non-dict details (line 523)
# ---------------------------------------------------------------------------


class TestFetchOsvDetailsNonDictDetails:
    def test_returns_empty_when_details_not_a_dict(self, tmp_path: Path) -> None:
        osv_file = tmp_path / "osv.json"
        osv_file.write_text('{"details": ["not", "a", "dict"]}', encoding="utf-8")
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        result = triage.fetch_osv_details([(dep, ["GHSA-x-y-z"])], osv_file=osv_file)
        assert result == {}


# ---------------------------------------------------------------------------
# fetch_epss_scores() -- empty CVEs (594), no live (601-602), live mode (603-608)
# ---------------------------------------------------------------------------


class TestFetchEpssScoresEdgeCases:
    def test_empty_cves_returns_empty(self) -> None:
        assert triage.fetch_epss_scores([]) == {}

    def test_no_live_mode_returns_empty(self) -> None:
        assert triage.fetch_epss_scores(["CVE-2024-0001"]) == {}

    def test_live_mode_calls_request_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(triage, "request_json", lambda *a, **kw: {"data": []})
        result = triage.fetch_epss_scores(["CVE-2024-0001"], epss_live=True)
        assert result == {}

    def test_live_mode_propagates_network_error_as_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*a: object, **kw: object) -> object:
            raise OSError("network down")

        monkeypatch.setattr(triage, "request_json", _raise)
        result = triage.fetch_epss_scores(["CVE-2024-0001"], epss_live=True)
        assert result == {}


# ---------------------------------------------------------------------------
# _parse_epss_payload() -- non-list rows (614), non-dict row (618)
# ---------------------------------------------------------------------------


class TestParseEpssPayloadEdgeCases:
    def test_returns_empty_when_data_not_a_list(self) -> None:
        assert triage._parse_epss_payload({"data": "not-a-list"}) == {}

    def test_skips_non_dict_rows(self) -> None:
        payload = {"data": ["not-a-dict", {"cve": "CVE-2024-0001", "epss": "0.5", "percentile": "0.9"}]}
        result = triage._parse_epss_payload(payload)
        assert "CVE-2024-0001" in result


# ---------------------------------------------------------------------------
# _coerce_epss_float() -- string branch (629-635)
# ---------------------------------------------------------------------------


class TestCoerceEpssFloat:
    def test_float_value_returned_directly(self) -> None:
        assert triage._coerce_epss_float(0.5) == pytest.approx(0.5)

    def test_int_value_coerced_to_float(self) -> None:
        assert triage._coerce_epss_float(42) == pytest.approx(42.0)

    def test_string_numeric_coerced(self) -> None:
        assert triage._coerce_epss_float("0.123") == pytest.approx(0.123)

    def test_string_non_numeric_returns_none(self) -> None:
        assert triage._coerce_epss_float("not-a-number") is None

    def test_non_str_non_numeric_returns_none(self) -> None:
        assert triage._coerce_epss_float(None) is None


# ---------------------------------------------------------------------------
# _attach_epss() -- non-str candidate (654), no match found (659)
# ---------------------------------------------------------------------------


_DEP = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")


class TestAttachEpssEdgeCases:
    def test_non_str_candidate_skipped(self) -> None:
        finding = triage.Finding(
            dependency=_DEP,
            vuln_id="GHSA-x-y-z",
            aliases=(None,),  # type: ignore[arg-type]
            source="OSV.dev",
            known_exploited=False,
        )
        scores = {"CVE-2024-0001": (0.5, 0.9)}
        result = triage._attach_epss(finding, scores)
        assert result.epss_score is None

    def test_no_matching_score_returns_unchanged(self) -> None:
        finding = triage.Finding(
            dependency=_DEP,
            vuln_id="GHSA-x-y-z",
            aliases=("CVE-2099-9999",),
            source="OSV.dev",
            known_exploited=False,
        )
        scores = {"CVE-2024-0001": (0.5, 0.9)}
        result = triage._attach_epss(finding, scores)
        assert result.epss_score is None


# ---------------------------------------------------------------------------
# fetch_ghsa_advisories() -- empty deps (679), live mode (686-699),
# no vuln_id (705), dep not affected (712), load ValueError (731)
# ---------------------------------------------------------------------------


class TestFetchGhsaAdvisories:
    def test_empty_deps_returns_empty(self) -> None:
        assert triage.fetch_ghsa_advisories([]) == []

    def test_live_mode_queries_per_dep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dep = triage.Dependency("requests", "2.28.0", "PyPI", "uv.lock")
        advisory = {
            "ghsa_id": "GHSA-a-b-c",
            "vulnerabilities": [{"package": {"ecosystem": "pip", "name": "requests"}}],
        }
        monkeypatch.setattr(triage, "request_json_any", lambda *a, **kw: [advisory])
        result = triage.fetch_ghsa_advisories([dep])
        assert len(result) == 1
        assert result[0].vuln_id == "GHSA-a-b-c"

    def test_live_mode_skips_unknown_ecosystem(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dep = triage.Dependency("some-pkg", "1.0.0", "Cargo", "Cargo.lock")
        called = []
        monkeypatch.setattr(
            triage, "request_json_any", lambda *a, **kw: called.append(1) or []
        )
        result = triage.fetch_ghsa_advisories([dep])
        assert result == []
        assert called == []

    def test_advisory_without_ghsa_id_skipped(self, tmp_path: Path) -> None:
        ghsa_file = tmp_path / "ghsa.json"
        advisory = {
            "vulnerabilities": [{"package": {"ecosystem": "pip", "name": "requests"}}]
        }
        ghsa_file.write_text(
            '{"advisories": [' + __import__("json").dumps(advisory) + "]}",
            encoding="utf-8",
        )
        dep = triage.Dependency("requests", "2.28.0", "PyPI", "uv.lock")
        result = triage.fetch_ghsa_advisories([dep], ghsa_file=ghsa_file)
        assert result == []

    def test_advisory_not_affecting_dep_skipped(self, tmp_path: Path) -> None:
        ghsa_file = tmp_path / "ghsa.json"
        advisory = {
            "ghsa_id": "GHSA-a-b-c",
            "vulnerabilities": [{"package": {"ecosystem": "pip", "name": "other-pkg"}}],
        }
        ghsa_file.write_text(
            '{"advisories": [' + __import__("json").dumps(advisory) + "]}",
            encoding="utf-8",
        )
        dep = triage.Dependency("requests", "2.28.0", "PyPI", "uv.lock")
        result = triage.fetch_ghsa_advisories([dep], ghsa_file=ghsa_file)
        assert result == []

    def test_load_ghsa_advisories_raises_on_non_list(
        self, tmp_path: Path
    ) -> None:
        ghsa_file = tmp_path / "ghsa.json"
        ghsa_file.write_text('{"advisories": "not-a-list"}', encoding="utf-8")
        with pytest.raises(ValueError, match="advisories"):
            triage.load_ghsa_advisories(ghsa_file)


# ---------------------------------------------------------------------------
# _ghsa_aliases() -- identifier items (749, 752)
# ---------------------------------------------------------------------------


class TestGhsaAliases:
    def test_non_dict_identifier_item_skipped(self) -> None:
        advisory = {
            "ghsa_id": "GHSA-a-b-c",
            "identifiers": ["not-a-dict", {"value": "CVE-2024-0001", "type": "CVE"}],
        }
        aliases = triage._ghsa_aliases(advisory, "GHSA-a-b-c")
        assert "CVE-2024-0001" in aliases

    def test_identifier_value_added_as_alias(self) -> None:
        advisory = {
            "ghsa_id": "GHSA-a-b-c",
            "identifiers": [{"value": "CVE-2024-9999", "type": "CVE"}],
        }
        aliases = triage._ghsa_aliases(advisory, "GHSA-a-b-c")
        assert "CVE-2024-9999" in aliases


# ---------------------------------------------------------------------------
# _ghsa_affects_dependency() -- all branch paths (764, 767, 770, 773, 775, 779)
# ---------------------------------------------------------------------------


class TestGhsaAffectsDependency:
    def test_unknown_ecosystem_returns_false(self) -> None:
        advisory: dict[str, object] = {}
        dep = triage.Dependency("pkg", "1.0", "Cargo", "Cargo.lock")
        assert triage._ghsa_affects_dependency(advisory, dep) is False

    def test_non_list_vulnerabilities_returns_false(self) -> None:
        advisory = {"vulnerabilities": "not-a-list"}
        dep = triage.Dependency("requests", "2.28.0", "PyPI", "uv.lock")
        assert triage._ghsa_affects_dependency(advisory, dep) is False

    def test_non_dict_vuln_entry_skipped(self) -> None:
        advisory = {"vulnerabilities": ["not-a-dict"]}
        dep = triage.Dependency("requests", "2.28.0", "PyPI", "uv.lock")
        assert triage._ghsa_affects_dependency(advisory, dep) is False

    def test_non_dict_package_skipped(self) -> None:
        advisory = {"vulnerabilities": [{"package": "not-a-dict"}]}
        dep = triage.Dependency("requests", "2.28.0", "PyPI", "uv.lock")
        assert triage._ghsa_affects_dependency(advisory, dep) is False

    def test_wrong_ecosystem_skipped(self) -> None:
        advisory = {
            "vulnerabilities": [{"package": {"ecosystem": "npm", "name": "requests"}}]
        }
        dep = triage.Dependency("requests", "2.28.0", "PyPI", "uv.lock")
        assert triage._ghsa_affects_dependency(advisory, dep) is False

    def test_matching_name_wrong_dep_returns_false(self) -> None:
        advisory = {
            "vulnerabilities": [{"package": {"ecosystem": "pip", "name": "other"}}]
        }
        dep = triage.Dependency("requests", "2.28.0", "PyPI", "uv.lock")
        assert triage._ghsa_affects_dependency(advisory, dep) is False


# ---------------------------------------------------------------------------
# fetch_ossf_malicious_packages() -- early returns (804, 806), live mode (813-815)
# ---------------------------------------------------------------------------


class TestFetchOssfMaliciousPackages:
    def test_empty_deps_returns_empty(self) -> None:
        assert triage.fetch_ossf_malicious_packages([]) == []

    def test_no_file_no_live_returns_empty(self) -> None:
        dep = triage.Dependency("pkg", "1.0", "PyPI", "uv.lock")
        assert triage.fetch_ossf_malicious_packages([dep]) == []

    def test_live_mode_queries_per_dep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dep = triage.Dependency("evil-pkg", "1.0.0", "PyPI", "uv.lock")
        monkeypatch.setattr(
            triage,
            "query_osv_malicious_for_dependency",
            lambda d: [],
        )
        result = triage.fetch_ossf_malicious_packages([dep], malpkg_live=True)
        assert result == []

    def test_load_ossf_records_raises_on_non_list(
        self, tmp_path: Path
    ) -> None:
        malpkg_file = tmp_path / "malpkg.json"
        malpkg_file.write_text(
            '{"malicious_packages": "not-a-list"}', encoding="utf-8"
        )
        with pytest.raises(ValueError, match="malicious_packages"):
            triage.load_ossf_malicious_records(malpkg_file)


# ---------------------------------------------------------------------------
# query_osv_malicious_for_dependency() -- network call (855-862)
# ---------------------------------------------------------------------------


class TestQueryOsvMaliciousForDependency:
    def test_returns_mal_prefixed_records(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dep = triage.Dependency("evil-pkg", "1.0.0", "PyPI", "uv.lock")
        vulns = [
            {"id": "MAL-2024-0001", "aliases": []},
            {"id": "GHSA-x-y-z"},
        ]
        monkeypatch.setattr(triage, "request_json", lambda *a, **kw: {"vulns": vulns})
        result = triage.query_osv_malicious_for_dependency(dep)
        assert len(result) == 1
        assert result[0]["id"] == "MAL-2024-0001"

    def test_non_list_vulns_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dep = triage.Dependency("pkg", "1.0.0", "PyPI", "uv.lock")
        monkeypatch.setattr(triage, "request_json", lambda *a, **kw: {"vulns": "bad"})
        assert triage.query_osv_malicious_for_dependency(dep) == []


# ---------------------------------------------------------------------------
# _ossf_affected_dependencies() -- all defensive branches (876, 880, 883, 887)
# ---------------------------------------------------------------------------


class TestOssfAffectedDependencies:
    def test_non_list_affected_returns_empty(self) -> None:
        record: dict[str, object] = {"affected": "not-a-list"}
        dep = triage.Dependency("pkg", "1.0", "PyPI", "uv.lock")
        assert triage._ossf_affected_dependencies(record, [dep]) == []

    def test_non_dict_entry_skipped(self) -> None:
        record = {"affected": ["not-a-dict"]}
        dep = triage.Dependency("pkg", "1.0", "PyPI", "uv.lock")
        assert triage._ossf_affected_dependencies(record, [dep]) == []

    def test_non_dict_package_skipped(self) -> None:
        record = {"affected": [{"package": "not-a-dict"}]}
        dep = triage.Dependency("pkg", "1.0", "PyPI", "uv.lock")
        assert triage._ossf_affected_dependencies(record, [dep]) == []

    def test_non_str_ecosystem_skipped(self) -> None:
        record = {"affected": [{"package": {"ecosystem": 42, "name": "pkg"}}]}
        dep = triage.Dependency("pkg", "1.0", "PyPI", "uv.lock")
        assert triage._ossf_affected_dependencies(record, [dep]) == []


# ---------------------------------------------------------------------------
# merge_findings() -- new alias added (line 921)
# ---------------------------------------------------------------------------


class TestMergeFindingsNewAlias:
    def test_new_alias_from_duplicate_finding_merged(self) -> None:
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        f1 = triage.Finding(
            dependency=dep,
            vuln_id="GHSA-x-y-z",
            aliases=("CVE-2024-0001",),
            source="OSV.dev",
            known_exploited=False,
        )
        f2 = triage.Finding(
            dependency=dep,
            vuln_id="GHSA-x-y-z",
            aliases=("CVE-2024-0001", "CVE-2024-0002"),
            source="GitHub Advisory",
            known_exploited=False,
        )
        merged = triage.merge_findings([f1, f2])
        assert len(merged) == 1
        assert "CVE-2024-0002" in merged[0].aliases


# ---------------------------------------------------------------------------
# fetch_nvd_metadata() -- file mode error branches (963-964, 967), live mode (980-998)
# ---------------------------------------------------------------------------


class TestFetchNvdMetadata:
    def test_file_mode_ioerror_returns_empty(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent.json"
        result = triage.fetch_nvd_metadata(["CVE-2024-0001"], nvd_file=nonexistent)
        assert result == {}

    def test_file_mode_non_dict_raw_map_returns_empty(
        self, tmp_path: Path
    ) -> None:
        nvd_file = tmp_path / "nvd.json"
        nvd_file.write_text('{"cves": ["not-a-dict"]}', encoding="utf-8")
        result = triage.fetch_nvd_metadata(["CVE-2024-0001"], nvd_file=nvd_file)
        assert result == {}

    def test_live_mode_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cve_payload = {"references": [{"url": "https://nvd.nist.gov/vuln/detail/CVE-2024-0001"}]}
        nvd_response = {"vulnerabilities": [{"cve": cve_payload}]}
        monkeypatch.setattr(triage, "request_json", lambda *a, **kw: nvd_response)
        result = triage.fetch_nvd_metadata(["CVE-2024-0001"])
        assert "CVE-2024-0001" in result

    def test_live_mode_network_error_continues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*a: object, **kw: object) -> object:
            raise OSError("network down")

        monkeypatch.setattr(triage, "request_json", _raise)
        result = triage.fetch_nvd_metadata(["CVE-2024-0001"])
        assert result == {}

    def test_live_mode_empty_vulnerabilities_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(triage, "request_json", lambda *a, **kw: {"vulnerabilities": []})
        result = triage.fetch_nvd_metadata(["CVE-2024-0001"])
        assert result == {}

    def test_live_mode_non_dict_first_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            triage, "request_json", lambda *a, **kw: {"vulnerabilities": ["not-a-dict"]}
        )
        result = triage.fetch_nvd_metadata(["CVE-2024-0001"])
        assert result == {}

    def test_live_mode_non_dict_cve_payload_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            triage,
            "request_json",
            lambda *a, **kw: {"vulnerabilities": [{"cve": "not-a-dict"}]},
        )
        result = triage.fetch_nvd_metadata(["CVE-2024-0001"])
        assert result == {}


# ---------------------------------------------------------------------------
# _extract_nvd_cvss() -- branch paths (1051, 1054, 1064, 1066)
# ---------------------------------------------------------------------------


class TestExtractNvdCvss:
    def test_non_dict_first_entry_skipped(self) -> None:
        payload = {
            "metrics": {"cvssMetricV31": ["not-a-dict"]}
        }
        result = triage._extract_nvd_cvss(payload)
        assert result == (None, None, None)

    def test_non_dict_cvss_data_skipped(self) -> None:
        payload = {
            "metrics": {"cvssMetricV31": [{"cvssData": "not-a-dict"}]}
        }
        result = triage._extract_nvd_cvss(payload)
        assert result == (None, None, None)

    def test_none_severity_and_score_falls_through(self) -> None:
        payload = {
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseSeverity": None, "baseScore": None}}]
            }
        }
        result = triage._extract_nvd_cvss(payload)
        assert result == (None, None, None)


# ---------------------------------------------------------------------------
# _extract_nvd_cwes() -- branch paths (1076, 1079, 1082)
# ---------------------------------------------------------------------------


class TestExtractNvdCwes:
    def test_non_dict_weakness_skipped(self) -> None:
        payload = {"weaknesses": ["not-a-dict"]}
        assert triage._extract_nvd_cwes(payload) == ()

    def test_non_list_descriptions_skipped(self) -> None:
        payload = {"weaknesses": [{"description": "not-a-list"}]}
        assert triage._extract_nvd_cwes(payload) == ()

    def test_non_dict_desc_entry_skipped(self) -> None:
        payload = {"weaknesses": [{"description": ["not-a-dict"]}]}
        assert triage._extract_nvd_cwes(payload) == ()


# ---------------------------------------------------------------------------
# _extract_nvd_references() -- branch paths (1096, 1101)
# ---------------------------------------------------------------------------


class TestExtractNvdReferences:
    def test_non_dict_ref_entry_skipped(self) -> None:
        payload = {"references": ["not-a-dict", {"url": "https://example.com"}]}
        result = triage._extract_nvd_references(payload)
        assert result == ("https://example.com",)

    def test_max_references_limit_enforced(self) -> None:
        refs = [{"url": f"https://example.com/{i}"} for i in range(10)]
        payload = {"references": refs}
        result = triage._extract_nvd_references(payload)
        assert len(result) == triage._NVD_MAX_REFERENCES


# ---------------------------------------------------------------------------
# attach_nvd_to_findings() -- no matching NVD enrichment (line 1132)
# ---------------------------------------------------------------------------


class TestAttachNvdToFindingsNoMatch:
    def test_finding_without_cve_alias_returned_unchanged(self) -> None:
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        finding = triage.Finding(
            dependency=dep,
            vuln_id="GHSA-x-y-z",
            aliases=(),
            source="OSV.dev",
            known_exploited=False,
        )
        enrichment = triage.NvdEnrichment(
            cve_id="CVE-2024-0001",
            cvss_severity="HIGH",
            cvss_score=8.5,
            cvss_version="3.1",
            cwe_ids=("CWE-79",),
            references=("https://example.com",),
            source_url="https://nvd.nist.gov/vuln/detail/CVE-2024-0001",
        )
        nvd_map = {"CVE-2024-0001": enrichment}
        result = triage.attach_nvd_to_findings([finding], nvd_map)
        assert len(result) == 1
        assert result[0].nvd_metadata == ()


# ---------------------------------------------------------------------------
# _nvd_cvss_cell() / _nvd_cwe_cell() -- empty metadata (1350, 1362)
# ---------------------------------------------------------------------------


class TestNvdCellHelpers:
    def test_nvd_cvss_cell_empty_metadata(self) -> None:
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        finding = triage.Finding(
            dependency=dep, vuln_id="GHSA-x-y-z", aliases=(), source="OSV.dev",
            known_exploited=False,
        )
        assert triage._nvd_cvss_cell(finding) == ""

    def test_nvd_cwe_cell_empty_metadata(self) -> None:
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        finding = triage.Finding(
            dependency=dep, vuln_id="GHSA-x-y-z", aliases=(), source="OSV.dev",
            known_exploited=False,
        )
        assert triage._nvd_cwe_cell(finding) == ""


# ---------------------------------------------------------------------------
# _string_list() -- non-list input (line 1436)
# ---------------------------------------------------------------------------


class TestStringList:
    def test_non_list_returns_empty(self) -> None:
        assert triage._string_list("not-a-list") == []

    def test_list_with_strings_returned(self) -> None:
        assert triage._string_list(["a", "b", 3]) == ["a", "b"]


# ---------------------------------------------------------------------------
# load_json() -- non-dict raises (line 1443)
# ---------------------------------------------------------------------------


class TestLoadJsonNonDict:
    def test_raises_when_json_is_not_object(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON object"):
            triage.load_json(f)


# ---------------------------------------------------------------------------
# request_json() -- non-dict response raises (lines 1453-1456)
# ---------------------------------------------------------------------------


class TestRequestJsonNonDict:
    def test_raises_when_response_is_not_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(triage, "request_json_any", lambda *a, **kw: [1, 2, 3])
        with pytest.raises(ValueError, match="non-object"):
            triage.request_json("https://example.com/api")

    def test_returns_dict_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        expected = {"key": "value"}
        monkeypatch.setattr(triage, "request_json_any", lambda *a, **kw: expected)
        result = triage.request_json("https://example.com/api")
        assert result == expected


# ---------------------------------------------------------------------------
# main() -- OSError/ValueError exception handler (lines 1620-1622)
# ---------------------------------------------------------------------------


class TestThreatIntelMainExceptionHandler:
    def test_main_catches_oserror_from_cmd_scan(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _raise_os(args: object) -> object:
            raise OSError("disk I/O failed")

        monkeypatch.setattr(triage, "_cmd_scan", _raise_os)
        rc = triage.main(["scan"])
        assert rc == 1
        assert "disk I/O failed" in capsys.readouterr().out

    def test_main_block_exits_via_runpy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import runpy
        import sys

        monkeypatch.setattr(sys, "argv", ["threat_intel_triage", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("threat_intel_triage", run_name="__main__")
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# _apply_labels() and _cmd_apply_labels() -- apply-labels subcommand
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b"[]") -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


class TestApplyLabels:
    def _make_opener(self, responses: list[int]) -> object:
        """Return an opener that returns successive HTTP status codes."""
        import urllib.error
        import urllib.request

        codes = iter(responses)

        def opener(req: urllib.request.Request) -> _FakeResponse:
            code = next(codes)
            if 200 <= code < 300:
                return _FakeResponse(status=code)
            raise urllib.error.HTTPError(req.full_url, code, "error", {}, None)  # type: ignore[arg-type]

        return opener

    def test_add_labels_posts_to_github_api(self) -> None:
        import urllib.request

        captured: list[urllib.request.Request] = []

        def opener(req: urllib.request.Request) -> _FakeResponse:
            captured.append(req)
            return _FakeResponse(status=200, body=b'[{"name":"threat:intel-needed"}]')

        assert triage._apply_labels(
            add_labels=["threat:intel-needed"],
            remove_labels=[],
            repo="owner/repo",
            number=42,
            token="tok",
            opener=opener,
        ) == 0

        assert len(captured) == 1
        req = captured[0]
        assert "issues/42/labels" in req.full_url
        assert req.method == "POST"

    def test_remove_label_deletes_from_github_api(self) -> None:
        import urllib.request

        captured: list[urllib.request.Request] = []

        def opener(req: urllib.request.Request) -> _FakeResponse:
            captured.append(req)
            return _FakeResponse(status=200, body=b'[]')

        assert triage._apply_labels(
            add_labels=[],
            remove_labels=["threat:response-needed"],
            repo="owner/repo",
            number=7,
            token="tok",
            opener=opener,
        ) == 0

        assert len(captured) == 1
        req = captured[0]
        assert "issues/7/labels/threat%3Aresponse-needed" in req.full_url
        assert req.method == "DELETE"

    def test_remove_label_404_is_not_an_error(self) -> None:
        import urllib.error
        import urllib.request

        def opener(req: urllib.request.Request) -> _FakeResponse:
            raise urllib.error.HTTPError(req.full_url, 404, "not found", {}, None)  # type: ignore[arg-type]

        assert triage._apply_labels(
            add_labels=[],
            remove_labels=["not-there"],
            repo="owner/repo",
            number=1,
            token="tok",
            opener=opener,
        ) == 0

    def test_add_labels_api_error_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        opener = self._make_opener([422])
        assert triage._apply_labels(
            add_labels=["bad-label"],
            remove_labels=[],
            repo="owner/repo",
            number=1,
            token="tok",
            opener=opener,
        ) == 1
        assert "422" in capsys.readouterr().err

    def test_remove_label_api_error_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        opener = self._make_opener([500])
        assert triage._apply_labels(
            add_labels=[],
            remove_labels=["bad"],
            repo="owner/repo",
            number=1,
            token="tok",
            opener=opener,
        ) == 1
        assert "500" in capsys.readouterr().err

    def test_empty_lists_do_nothing(self) -> None:
        called = []

        def opener(req: object) -> _FakeResponse:
            called.append(req)
            return _FakeResponse()

        assert triage._apply_labels(
            add_labels=[], remove_labels=[], repo="owner/repo", number=1, token="tok", opener=opener
        ) == 0
        assert called == []

    def test_bearer_token_in_header(self) -> None:
        import urllib.request

        captured: list[urllib.request.Request] = []

        def opener(req: urllib.request.Request) -> _FakeResponse:
            captured.append(req)
            return _FakeResponse()

        triage._apply_labels(
            add_labels=["x"], remove_labels=[], repo="r/r", number=1, token="secret", opener=opener
        )
        assert "Bearer secret" in captured[0].get_header("Authorization")


class TestCmdApplyLabels:
    def test_missing_gh_token_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setenv("NUMBER", "1")
        assert triage.main(["apply-labels", "--add-labels", "threat:intel-needed"]) == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_missing_repo_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.setenv("NUMBER", "1")
        assert triage.main(["apply-labels", "--add-labels", "threat:intel-needed"]) == 1
        assert "REPO" in capsys.readouterr().err

    def test_missing_number_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.delenv("NUMBER", raising=False)
        assert triage.main(["apply-labels", "--add-labels", "threat:intel-needed"]) == 1
        assert "NUMBER" in capsys.readouterr().err

    def test_non_integer_number_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setenv("NUMBER", "not-a-number")
        assert triage.main(["apply-labels", "--add-labels", "threat:intel-needed"]) == 1
        assert "NUMBER" in capsys.readouterr().err

    def test_comma_separated_add_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setenv("NUMBER", "5")

        captured_labels: list[list[str]] = []

        def fake_apply(**kw: object) -> int:
            captured_labels.append(kw["add_labels"])  # type: ignore[arg-type]
            return 0

        monkeypatch.setattr(triage, "_apply_labels", fake_apply)
        assert triage.main(["apply-labels", "--add-labels", "threat:intel-needed,threat:response-needed"]) == 0
        assert captured_labels == [["threat:intel-needed", "threat:response-needed"]]

    def test_no_labels_args_is_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setenv("NUMBER", "5")
        monkeypatch.setattr(triage, "_apply_labels", lambda **kw: 0)
        assert triage.main(["apply-labels"]) == 0


# ---------------------------------------------------------------------------
# render_summary_markdown() -- the pure renderer shared by the step summary
# and the idempotent issue/PR evidence comment (#1285).
# ---------------------------------------------------------------------------


def _demo_finding(**overrides: object) -> triage.Finding:
    base: dict[str, object] = {
        "dependency": triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock"),
        "vuln_id": "CVE-2024-0001",
        "aliases": ("GHSA-aaaa-bbbb-cccc",),
        "source": triage.SOURCE_OSV,
        "known_exploited": True,
    }
    base.update(overrides)
    return triage.Finding(**base)  # type: ignore[arg-type]


class TestRenderSummaryMarkdown:
    def test_findings_render_a_table_row(self) -> None:
        finding = _demo_finding()
        result = triage.classify_findings([finding], set())
        md = triage.render_summary_markdown([finding.dependency], [finding], result)
        assert "## Threat intelligence triage" in md
        assert "| `requests` | `2.31.0` | `CVE-2024-0001` |" in md
        assert "threat:intel-needed" in md
        assert "threat:response-needed" in md  # known_exploited escalates

    def test_no_findings_states_the_clear_result(self) -> None:
        dep = triage.Dependency("requests", "2.31.0", "PyPI", "uv.lock")
        result = triage.classify_findings([], set())
        md = triage.render_summary_markdown([dep], [], result)
        assert "No external threat-intelligence findings matched locked dependencies." in md
        assert "|---" not in md  # no table when there are no findings

    def test_outages_emit_reduced_confidence_note(self) -> None:
        finding = _demo_finding()
        result = triage.classify_findings([finding], set())
        md = triage.render_summary_markdown(
            [finding.dependency], [finding], result, outages=[triage.SOURCE_EPSS, triage.SOURCE_NVD]
        )
        assert "Live-source outages (reduced confidence): FIRST EPSS, NVD" in md
        assert "not evidence of safety" in md

    def test_no_outages_omits_the_note(self) -> None:
        finding = _demo_finding()
        result = triage.classify_findings([finding], set())
        md = triage.render_summary_markdown([finding.dependency], [finding], result, outages=[])
        assert "reduced confidence" not in md

    def test_nvd_enrichment_adds_columns_and_detail(self) -> None:
        enrichment = triage.NvdEnrichment(
            cve_id="CVE-2024-0001",
            cvss_severity="Critical",
            cvss_score=9.8,
            cvss_version="3.1",
            cwe_ids=("CWE-79",),
            references=("https://example.com/a",),
            source_url=f"{triage.NVD_DETAIL_URL_PREFIX}CVE-2024-0001",
        )
        finding = _demo_finding(nvd_metadata=(enrichment,))
        result = triage.classify_findings([finding], set())
        md = triage.render_summary_markdown([finding.dependency], [finding], result)
        assert "NVD CVSS" in md
        assert "### NVD references (supplemental)" in md
        assert "CWE-79" in md

    def test_rendered_summary_is_ascii(self) -> None:
        finding = _demo_finding()
        result = triage.classify_findings([finding], set())
        md = triage.render_summary_markdown(
            [finding.dependency], [finding], result, outages=[triage.SOURCE_NVD]
        )
        assert md.isascii()

    def test_write_summary_appends_rendered_text(self, tmp_path: Path) -> None:
        finding = _demo_finding()
        result = triage.classify_findings([finding], set())
        path = tmp_path / "summary.md"
        triage.write_summary(path, [finding.dependency], [finding], result, outages=[triage.SOURCE_EPSS])
        text = path.read_text(encoding="utf-8")
        assert text == triage.render_summary_markdown(
            [finding.dependency], [finding], result, outages=[triage.SOURCE_EPSS]
        )


# ---------------------------------------------------------------------------
# Live-source outage accumulation -- silent soft-fail sources surface their
# outage so confidence loss is visible (#1285).
# ---------------------------------------------------------------------------


class TestLiveSourceOutages:
    def test_epss_live_failure_records_outage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*a: object, **kw: object) -> object:
            raise OSError("network down")

        monkeypatch.setattr(triage, "request_json", _raise)
        outages: list[str] = []
        triage.fetch_epss_scores(["CVE-2024-0001"], epss_live=True, outages=outages)
        assert outages == [triage.SOURCE_EPSS]

    def test_nvd_live_failure_records_outage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*a: object, **kw: object) -> object:
            raise OSError("network down")

        monkeypatch.setattr(triage, "request_json", _raise)
        outages: list[str] = []
        triage.fetch_nvd_metadata(["CVE-2024-0001"], outages=outages)
        assert outages == [triage.SOURCE_NVD]

    def test_outage_recorded_once_despite_multiple_cves(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*a: object, **kw: object) -> object:
            raise OSError("network down")

        monkeypatch.setattr(triage, "request_json", _raise)
        outages: list[str] = []
        triage.fetch_nvd_metadata(["CVE-2024-0001", "CVE-2024-0002"], outages=outages)
        assert outages == [triage.SOURCE_NVD]

    def test_no_outage_when_caller_opts_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*a: object, **kw: object) -> object:
            raise OSError("network down")

        monkeypatch.setattr(triage, "request_json", _raise)
        # outages=None (default) must not raise and must still soft-fail empty.
        assert triage.fetch_epss_scores(["CVE-2024-0001"], epss_live=True) == {}


# ---------------------------------------------------------------------------
# _upsert_comment() -- marker-anchored idempotent comment (#1285).
# ---------------------------------------------------------------------------


class TestUpsertComment:
    MARKER = triage._TRIAGE_COMMENT_MARKER

    def test_creates_when_no_marked_comment_exists(self) -> None:
        import urllib.request

        captured: list[urllib.request.Request] = []

        def opener(req: urllib.request.Request) -> _FakeResponse:
            captured.append(req)
            if req.method == "GET":
                return _FakeResponse(status=200, body=b"[]")
            return _FakeResponse(status=201, body=b"{}")

        rc = triage._upsert_comment(
            body=f"{self.MARKER}\n\nx", repo="o/r", number=5, token="tok",
            marker=self.MARKER, create=True, opener=opener,
        )
        assert rc == 0
        assert [r.method for r in captured] == ["GET", "POST"]
        assert "issues/5/comments" in captured[1].full_url

    def test_updates_when_marked_comment_exists(self) -> None:
        import urllib.request

        existing = json.dumps([{"id": 77, "body": f"{self.MARKER}\n\nold"}]).encode()
        captured: list[urllib.request.Request] = []

        def opener(req: urllib.request.Request) -> _FakeResponse:
            captured.append(req)
            if req.method == "GET":
                return _FakeResponse(status=200, body=existing)
            return _FakeResponse(status=200, body=b"{}")

        rc = triage._upsert_comment(
            body="new", repo="o/r", number=5, token="tok",
            marker=self.MARKER, create=True, opener=opener,
        )
        assert rc == 0
        assert captured[1].method == "PATCH"
        assert "issues/comments/77" in captured[1].full_url

    def test_update_only_with_no_existing_comment_is_a_noop(self) -> None:
        import urllib.request

        captured: list[urllib.request.Request] = []

        def opener(req: urllib.request.Request) -> _FakeResponse:
            captured.append(req)
            if req.method == "GET":
                return _FakeResponse(status=200, body=b"[]")
            raise AssertionError("update-only must not write when absent")

        rc = triage._upsert_comment(
            body="x", repo="o/r", number=5, token="tok",
            marker=self.MARKER, create=False, opener=opener,
        )
        assert rc == 0
        assert [r.method for r in captured] == ["GET"]

    def test_api_error_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        import urllib.error
        import urllib.request

        def opener(req: urllib.request.Request) -> _FakeResponse:
            if req.method == "GET":
                return _FakeResponse(status=200, body=b"[]")
            raise urllib.error.HTTPError(req.full_url, 422, "error", {}, None)  # type: ignore[arg-type]

        rc = triage._upsert_comment(
            body="x", repo="o/r", number=5, token="tok",
            marker=self.MARKER, create=True, opener=opener,
        )
        assert rc == 1
        assert "422" in capsys.readouterr().err

    def test_marker_in_mid_body_is_not_matched(self) -> None:
        import urllib.request

        # A user comment that merely mentions the marker text must not be
        # treated as the bot's anchored comment (startswith, not contains).
        existing = json.dumps([{"id": 9, "body": f"see {self.MARKER} here"}]).encode()
        captured: list[urllib.request.Request] = []

        def opener(req: urllib.request.Request) -> _FakeResponse:
            captured.append(req)
            if req.method == "GET":
                return _FakeResponse(status=200, body=existing)
            return _FakeResponse(status=201, body=b"{}")

        triage._upsert_comment(
            body=f"{self.MARKER}\n\nx", repo="o/r", number=5, token="tok",
            marker=self.MARKER, create=True, opener=opener,
        )
        assert captured[1].method == "POST"  # created, not matched the mid-body marker


class TestCmdComment:
    def test_missing_env_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setenv("NUMBER", "5")
        body_file = tmp_path / "c.md"
        body_file.write_text("body", encoding="utf-8")
        assert triage.main(["comment", "--body-file", str(body_file)]) == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_prepends_marker_and_passes_create_flag(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setenv("NUMBER", "5")
        body_file = tmp_path / "c.md"
        body_file.write_text("RENDERED", encoding="utf-8")

        captured: dict[str, object] = {}

        def fake_upsert(**kw: object) -> int:
            captured.update(kw)
            return 0

        monkeypatch.setattr(triage, "_upsert_comment", fake_upsert)
        assert triage.main(["comment", "--body-file", str(body_file)]) == 0
        assert captured["create"] is True
        assert str(captured["body"]).startswith(triage._TRIAGE_COMMENT_MARKER)
        assert "RENDERED" in str(captured["body"])

    def test_update_only_flag_disables_create(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "owner/repo")
        monkeypatch.setenv("NUMBER", "5")
        body_file = tmp_path / "c.md"
        body_file.write_text("RENDERED", encoding="utf-8")

        captured: dict[str, object] = {}
        monkeypatch.setattr(triage, "_upsert_comment", lambda **kw: captured.update(kw) or 0)
        assert triage.main(["comment", "--body-file", str(body_file), "--update-only"]) == 0
        assert captured["create"] is False


def _intel_finding(**overrides: object) -> triage.Finding:
    """A non-response advisory finding (the suppressible class)."""
    base: dict[str, object] = {
        "dependency": triage.Dependency("demo", "1.0.0", "PyPI", "uv.lock"),
        "vuln_id": "CVE-2026-2222",
        "aliases": ("GHSA-aaaa-bbbb-cccc",),
        "source": triage.SOURCE_OSV,
        "known_exploited": False,
    }
    base.update(overrides)
    return triage.Finding(**base)  # type: ignore[arg-type]


def _supp(**overrides: object) -> triage.Suppression:
    base: dict[str, object] = {
        "ecosystem": "PyPI",
        "name": "demo",
        "vuln_id": "CVE-2026-2222",
        "reason": "reviewed intel gap; advisory unconfirmable",
        "review_by": date(2099, 1, 1),
    }
    base.update(overrides)
    return triage.Suppression(**base)  # type: ignore[arg-type]


class TestLoadSuppressions:
    def test_valid_file_parses_entries(self, tmp_path: Path) -> None:
        path = tmp_path / "supp.json"
        path.write_text(
            json.dumps(
                {
                    "suppressions": [
                        {
                            "ecosystem": "PyPI",
                            "name": "demo",
                            "vuln_id": "CVE-2026-2222",
                            "reason": "reviewed gap",
                            "review_by": "2026-09-01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        result = triage.load_suppressions(path)
        assert result == [
            triage.Suppression("PyPI", "demo", "CVE-2026-2222", "reviewed gap", date(2026, 9, 1))
        ]

    def test_missing_array_is_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "supp.json"
        path.write_text(json.dumps({"documentation": "note"}), encoding="utf-8")
        assert triage.load_suppressions(path) == []

    def test_suppressions_not_array_fails_loud(self, tmp_path: Path) -> None:
        path = tmp_path / "supp.json"
        path.write_text(json.dumps({"suppressions": {}}), encoding="utf-8")
        with pytest.raises(ValueError, match="must be an array"):
            triage.load_suppressions(path)

    def test_missing_required_field_fails_loud(self, tmp_path: Path) -> None:
        path = tmp_path / "supp.json"
        path.write_text(
            json.dumps(
                {
                    "suppressions": [
                        {"ecosystem": "PyPI", "name": "demo", "vuln_id": "CVE-2026-2222"}
                    ]
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="field 'reason'"):
            triage.load_suppressions(path)

    def test_blank_field_fails_loud(self, tmp_path: Path) -> None:
        path = tmp_path / "supp.json"
        path.write_text(
            json.dumps(
                {
                    "suppressions": [
                        {
                            "ecosystem": "PyPI",
                            "name": "demo",
                            "vuln_id": "CVE-2026-2222",
                            "reason": "   ",
                            "review_by": "2026-09-01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="field 'reason'"):
            triage.load_suppressions(path)

    def test_bad_date_fails_loud(self, tmp_path: Path) -> None:
        path = tmp_path / "supp.json"
        path.write_text(
            json.dumps(
                {
                    "suppressions": [
                        {
                            "ecosystem": "PyPI",
                            "name": "demo",
                            "vuln_id": "CVE-2026-2222",
                            "reason": "reviewed gap",
                            "review_by": "2026/09/01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
            triage.load_suppressions(path)

    def test_entry_not_object_fails_loud(self, tmp_path: Path) -> None:
        path = tmp_path / "supp.json"
        path.write_text(json.dumps({"suppressions": ["nope"]}), encoding="utf-8")
        with pytest.raises(ValueError, match="must be an object"):
            triage.load_suppressions(path)

    def test_committed_repo_allowlist_is_valid(self) -> None:
        # The checked-in file must always parse so a malformed commit fails the
        # unit suite, not only a networked scan.
        path = Path(".github/threat-intel-suppressions.json")
        assert triage.load_suppressions(path) == []


class TestClassifyFindingsSuppression:
    def test_unexpired_suppression_clears_intel(self) -> None:
        finding = _intel_finding()
        result = triage.classify_findings(
            [finding], set(), suppressions=[_supp()], today=date(2026, 6, 6)
        )
        assert result["intel_needed"] is False
        assert result["suppressed_count"] == 1
        assert result["active_finding_count"] == 0
        assert result["recommended_labels"] == []
        # The finding still appears in the evidence table.
        assert result["finding_count"] == 1

    def test_suppression_matches_via_alias(self) -> None:
        finding = _intel_finding(vuln_id="OSV-2026-9", aliases=("CVE-2026-2222",))
        result = triage.classify_findings(
            [finding], set(), suppressions=[_supp()], today=date(2026, 6, 6)
        )
        assert result["intel_needed"] is False

    def test_expired_suppression_resurfaces_label(self) -> None:
        finding = _intel_finding()
        today = date(2026, 6, 6)
        # review_by == today counts as expired (fail-safe).
        result = triage.classify_findings(
            [finding], set(), suppressions=[_supp(review_by=today)], today=today
        )
        assert result["intel_needed"] is True
        assert result["suppressed_count"] == 0
        assert result["expired_suppressions"]
        assert "CVE-2026-2222" in result["expired_suppressions"][0]
        assert triage.INTEL_LABEL in result["recommended_labels"]

    def test_response_class_finding_is_never_suppressed(self) -> None:
        finding = _intel_finding(known_exploited=True)
        result = triage.classify_findings(
            [finding], set(), suppressions=[_supp()], today=date(2026, 6, 6)
        )
        assert result["intel_needed"] is True
        assert result["response_needed"] is True
        assert result["suppressed_count"] == 0

    def test_malware_finding_is_never_suppressed(self) -> None:
        finding = _intel_finding(advisory_type=triage.GHSA_MALWARE_TYPE)
        result = triage.classify_findings(
            [finding], set(), suppressions=[_supp()], today=date(2026, 6, 6)
        )
        assert result["intel_needed"] is True
        assert result["response_needed"] is True

    def test_non_matching_suppression_leaves_label(self) -> None:
        finding = _intel_finding()
        other = _supp(name="unrelated")
        result = triage.classify_findings(
            [finding], set(), suppressions=[other], today=date(2026, 6, 6)
        )
        assert result["intel_needed"] is True

    def test_expired_note_renders_in_summary(self) -> None:
        finding = _intel_finding()
        today = date(2026, 6, 6)
        result = triage.classify_findings(
            [finding], set(), suppressions=[_supp(review_by=today)], today=today
        )
        md = triage.render_summary_markdown([finding.dependency], [finding], result)
        assert "Expired accepted-intel suppressions re-surfaced" in md


def _write_intel_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    osv = tmp_path / "osv.json"
    kev = tmp_path / "kev.json"
    osv.write_text(
        json.dumps({"results": [{"vulns": [{"id": "CVE-2026-2222"}]}], "details": {}}),
        encoding="utf-8",
    )
    kev.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
    return osv, kev


class TestScanSuppressionCli:
    def _run(self, tmp_path: Path, capsys, *extra: str) -> dict[str, object]:
        osv, kev = _write_intel_fixtures(tmp_path)
        rc = triage.main(
            [
                "scan",
                "--repo-root",
                str(tmp_path),
                "--osv-file",
                str(osv),
                "--kev-file",
                str(kev),
                "--format",
                "json",
                *extra,
            ]
        )
        captured = capsys.readouterr()
        return {"rc": rc, "result": json.loads(captured.out)}

    def test_explicit_suppressions_file_clears_intel(self, tmp_path: Path, capsys) -> None:
        supp = tmp_path / "supp.json"
        supp.write_text(
            json.dumps(
                {
                    "suppressions": [
                        {
                            "ecosystem": "PyPI",
                            "name": "demo",
                            "vuln_id": "CVE-2026-2222",
                            "reason": "reviewed gap",
                            "review_by": "2099-01-01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        out = self._run(tmp_path, capsys, "--suppressions-file", str(supp))
        assert out["rc"] == 0
        assert out["result"]["intel_needed"] is False

    def test_default_allowlist_auto_loaded(self, tmp_path: Path, capsys) -> None:
        gh_dir = tmp_path / ".github"
        gh_dir.mkdir()
        (gh_dir / "threat-intel-suppressions.json").write_text(
            json.dumps(
                {
                    "suppressions": [
                        {
                            "ecosystem": "PyPI",
                            "name": "demo",
                            "vuln_id": "CVE-2026-2222",
                            "reason": "reviewed gap",
                            "review_by": "2099-01-01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        out = self._run(tmp_path, capsys)
        assert out["result"]["intel_needed"] is False

    def test_missing_explicit_file_fails_loud(self, tmp_path: Path) -> None:
        osv, kev = _write_intel_fixtures(tmp_path)
        rc = triage.main(
            [
                "scan",
                "--repo-root",
                str(tmp_path),
                "--osv-file",
                str(osv),
                "--kev-file",
                str(kev),
                "--suppressions-file",
                str(tmp_path / "absent.json"),
            ]
        )
        assert rc == 1

    def test_fail_on_intel_returns_nonzero_when_flagged(self, tmp_path: Path, capsys) -> None:
        out = self._run(tmp_path, capsys, "--fail-on-intel")
        assert out["rc"] == 1
        assert out["result"]["intel_needed"] is True

    def test_fail_on_intel_zero_when_suppressed(self, tmp_path: Path, capsys) -> None:
        supp = tmp_path / "supp.json"
        supp.write_text(
            json.dumps(
                {
                    "suppressions": [
                        {
                            "ecosystem": "PyPI",
                            "name": "demo",
                            "vuln_id": "CVE-2026-2222",
                            "reason": "reviewed gap",
                            "review_by": "2099-01-01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        out = self._run(tmp_path, capsys, "--suppressions-file", str(supp), "--fail-on-intel")
        assert out["rc"] == 0
        assert out["result"]["intel_needed"] is False

    def test_expired_default_allowlist_fails_scheduled_run(self, tmp_path: Path, capsys) -> None:
        gh_dir = tmp_path / ".github"
        gh_dir.mkdir()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        (gh_dir / "threat-intel-suppressions.json").write_text(
            json.dumps(
                {
                    "suppressions": [
                        {
                            "ecosystem": "PyPI",
                            "name": "demo",
                            "vuln_id": "CVE-2026-2222",
                            "reason": "reviewed gap",
                            "review_by": yesterday,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        out = self._run(tmp_path, capsys, "--fail-on-intel")
        assert out["rc"] == 1
        assert out["result"]["intel_needed"] is True
        assert out["result"]["expired_suppressions"]
