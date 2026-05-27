#!/usr/bin/env python3
"""Collect threat intelligence and classify repository response needs.

The primary rule collects external intelligence from OSV.dev and CISA KEV,
correlates it with this repository's locked dependencies, and decides
whether to add:

* ``threat:intel-needed`` -- collect threat intelligence before routing.
* ``threat:response-needed`` -- security response is required; do not
  create an autonomous fix without investigation.

The older metadata classifier remains as a helper for issue/PR text, but the
workflow uses ``scan`` so triage is driven by external sources.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

import tomllib

INTEL_LABEL = "threat:intel-needed"
RESPONSE_LABEL = "threat:response-needed"
SECURITY_LABEL = "severity:security"
THREAT_LABELS = {INTEL_LABEL, RESPONSE_LABEL}
OSV_QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_QUERY_URL = "https://api.osv.dev/v1/query"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"
CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
GHSA_ADVISORIES_URL = "https://api.github.com/advisories"
GHSA_MALWARE_TYPE = "malware"
MAL_ID_PREFIX = "MAL-"
SOURCE_OSV = "OSV.dev"
SOURCE_GHSA = "GitHub Advisory"
SOURCE_OSSF_MAL = "OSSF malicious-packages"

# Map this module's internal ecosystem labels (taken from OSV) to the
# values accepted by GitHub's /advisories endpoint. Keep this minimal:
# only ecosystems actually discovered by ``discover_dependencies``.
_GHSA_ECOSYSTEM_MAP = {"PyPI": "pip"}


class Indicator(NamedTuple):
    name: str
    pattern: re.Pattern[str]


class Dependency(NamedTuple):
    name: str
    version: str
    ecosystem: str
    source: str


class Finding(NamedTuple):
    dependency: Dependency
    vuln_id: str
    aliases: tuple[str, ...]
    source: str
    known_exploited: bool
    # GHSA-only attribute. ``None`` for OSV-only findings; ``"malware"``
    # escalates ``threat:response-needed`` per #172.
    advisory_type: str | None = None


INTEL_INDICATORS = (
    Indicator("cve", re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)),
    Indicator("ghsa", re.compile(r"\bGHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}\b", re.IGNORECASE)),
    Indicator("osv", re.compile(r"\bOSV-\d{4}-\d+\b", re.IGNORECASE)),
    Indicator("advisory", re.compile(r"\b(?:security advisory|advisory)\b", re.IGNORECASE)),
    Indicator("vulnerability", re.compile(r"\b(?:vulnerability|vulnerable|vuln)\b", re.IGNORECASE)),
    Indicator("exploit", re.compile(r"\b(?:exploit|exploitable|exploitation)\b", re.IGNORECASE)),
    Indicator("zero-day", re.compile(r"\b(?:zero[- ]day|0day)\b", re.IGNORECASE)),
    Indicator("malware", re.compile(r"\b(?:malware|backdoor|trojan)\b", re.IGNORECASE)),
    Indicator("malicious-package", re.compile(r"\bmalicious (?:package|dependency|release)\b", re.IGNORECASE)),
    Indicator("supply-chain", re.compile(r"\b(?:supply[- ]chain|dependency confusion|typosquat(?:ting)?)\b", re.IGNORECASE)),
    Indicator("secret-leak", re.compile(r"\b(?:secret|token|credential)s? (?:leak|leaked|exposed|exposure)\b", re.IGNORECASE)),
    Indicator("compromise", re.compile(r"\b(?:compromise|compromised|account takeover)\b", re.IGNORECASE)),
    Indicator("ioc", re.compile(r"\b(?:indicator of compromise|ioc)s?\b", re.IGNORECASE)),
)

RESPONSE_INDICATORS = (
    Indicator("active-exploitation", re.compile(r"\b(?:active exploitation|exploited in the wild|under attack)\b", re.IGNORECASE)),
    Indicator("exploit-available", re.compile(r"\b(?:public exploit|exploit available|poc exploit)\b", re.IGNORECASE)),
    Indicator("critical", re.compile(r"\bcritical\b", re.IGNORECASE)),
    Indicator("rce", re.compile(r"\b(?:RCE|remote code execution)\b", re.IGNORECASE)),
    Indicator("malicious-package", re.compile(r"\bmalicious (?:package|dependency|release)\b", re.IGNORECASE)),
    Indicator("secret-leak", re.compile(r"\b(?:secret|token|credential)s? (?:leak|leaked|exposed|exposure)\b", re.IGNORECASE)),
    Indicator("compromise", re.compile(r"\b(?:compromise|compromised|account takeover)\b", re.IGNORECASE)),
    Indicator("credential-action", re.compile(r"\b(?:rotate|revoke) (?:secret|token|credential)s?\b", re.IGNORECASE)),
)


def parse_labels(raw: str | list[str] | tuple[str, ...]) -> set[str]:
    """Return normalized label names from comma/newline separated input."""
    if isinstance(raw, str):
        chunks = re.split(r"[,\n]", raw)
    else:
        chunks = []
        for item in raw:
            chunks.extend(re.split(r"[,\n]", item))
    return {chunk.strip() for chunk in chunks if chunk.strip()}


def discover_dependencies(repo_root: Path) -> list[Dependency]:
    """Return version-pinned dependencies from lockfiles in *repo_root*."""
    by_key: dict[tuple[str, str, str], Dependency] = {}
    for dep in parse_uv_lock(repo_root / "uv.lock"):
        by_key[(dep.ecosystem, dep.name, dep.version)] = dep
    for dep in parse_pyproject_pinned_dependencies(repo_root / "pyproject.toml"):
        by_key.setdefault((dep.ecosystem, dep.name, dep.version), dep)
    return sorted(by_key.values(), key=lambda dep: (dep.ecosystem, dep.name, dep.version))


def parse_uv_lock(path: Path) -> list[Dependency]:
    """Parse PyPI packages from a uv.lock file."""
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    packages = data.get("package", [])
    deps: list[Dependency] = []
    if not isinstance(packages, list):
        return deps
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            deps.append(Dependency(name=name, version=version, ecosystem="PyPI", source=str(path)))
    return deps


def parse_pyproject_pinned_dependencies(path: Path) -> list[Dependency]:
    """Parse exact PyPI pins from pyproject.toml.

    Versionless or range-based declarations are ignored because OSV checks
    without a resolved version are too noisy for an automated response gate.
    """
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_deps: list[str] = []
    project = data.get("project", {})
    if isinstance(project, dict):
        raw_deps.extend(_string_list(project.get("dependencies")))
    dependency_groups = data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        for value in dependency_groups.values():
            raw_deps.extend(_string_list(value))

    deps: list[Dependency] = []
    for dep in raw_deps:
        parsed = parse_exact_python_requirement(dep)
        if parsed is not None:
            name, version = parsed
            deps.append(Dependency(name=name, version=version, ecosystem="PyPI", source=str(path)))
    return deps


def parse_exact_python_requirement(requirement: str) -> tuple[str, str] | None:
    """Return ``(name, version)`` for simple exact pins such as ``pytest==8``."""
    match = re.match(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*==\s*([^,;\s]+)", requirement)
    if match is None:
        return None
    return match.group(1), match.group(2)


def fetch_external_findings(
    dependencies: list[Dependency],
    *,
    osv_file: Path | None = None,
    kev_file: Path | None = None,
    ghsa_file: Path | None = None,
    ghsa_live: bool = False,
    ghsa_token: str | None = None,
    malpkg_file: Path | None = None,
    malpkg_live: bool = False,
) -> list[Finding]:
    """Collect OSV, CISA KEV, GHSA, and OSSF malicious-package intelligence.

    GHSA and OSSF malicious-packages are opt-in to keep the OSV-only call
    sites deterministic without a network call. Pass ``ghsa_file=`` /
    ``malpkg_file=`` for fixture-driven runs, or ``*_live=True`` to query
    the upstream endpoint live.
    """
    if not dependencies:
        return []

    osv_batch = load_json(osv_file) if osv_file is not None else query_osv_batch(dependencies)
    kev_catalog = load_json(kev_file) if kev_file is not None else fetch_cisa_kev()
    kev_cves = parse_kev_cves(kev_catalog)

    vuln_ids_by_dep = parse_osv_batch_results(dependencies, osv_batch)
    vuln_details = fetch_osv_details(vuln_ids_by_dep, osv_file=osv_file)

    osv_findings: list[Finding] = []
    for dep, vuln_ids in vuln_ids_by_dep:
        for vuln_id in vuln_ids:
            details = vuln_details.get(vuln_id, {})
            aliases = tuple(str(alias) for alias in details.get("aliases", []) if isinstance(alias, str))
            cve_ids = {vuln_id, *aliases}
            known_exploited = bool(cve_ids & kev_cves)
            advisory_type = GHSA_MALWARE_TYPE if vuln_id.startswith(MAL_ID_PREFIX) else None
            osv_findings.append(
                Finding(
                    dependency=dep,
                    vuln_id=vuln_id,
                    aliases=aliases,
                    source=SOURCE_OSV,
                    known_exploited=known_exploited,
                    advisory_type=advisory_type,
                )
            )

    ghsa_findings: list[Finding] = []
    if ghsa_file is not None or ghsa_live:
        ghsa_findings = fetch_ghsa_advisories(
            dependencies,
            ghsa_file=ghsa_file,
            token=ghsa_token,
            kev_cves=kev_cves,
        )

    ossf_findings: list[Finding] = []
    if malpkg_file is not None or malpkg_live:
        ossf_findings = fetch_ossf_malicious_packages(
            dependencies,
            malpkg_file=malpkg_file,
            malpkg_live=malpkg_live,
            kev_cves=kev_cves,
        )

    merged = merge_findings(osv_findings + ghsa_findings + ossf_findings)
    return sorted(merged, key=lambda f: (f.dependency.name, f.vuln_id))


def query_osv_batch(dependencies: list[Dependency]) -> dict[str, object]:
    queries = [
        {
            "version": dep.version,
            "package": {"name": dep.name, "ecosystem": dep.ecosystem},
        }
        for dep in dependencies
    ]
    return request_json(OSV_QUERYBATCH_URL, payload={"queries": queries})


def fetch_cisa_kev() -> dict[str, object]:
    return request_json(CISA_KEV_URL)


def fetch_osv_details(
    vuln_ids_by_dep: list[tuple[Dependency, list[str]]],
    *,
    osv_file: Path | None = None,
) -> dict[str, dict[str, object]]:
    if osv_file is not None:
        data = load_json(osv_file)
        details = data.get("details", {}) if isinstance(data, dict) else {}
        if isinstance(details, dict):
            return {str(key): value for key, value in details.items() if isinstance(value, dict)}
        return {}

    vuln_ids = sorted({vuln_id for _, vuln_ids in vuln_ids_by_dep for vuln_id in vuln_ids})
    details: dict[str, dict[str, object]] = {}
    for vuln_id in vuln_ids:
        data = request_json(OSV_VULN_URL.format(id=urllib.parse.quote(vuln_id, safe="")))
        if isinstance(data, dict):
            details[vuln_id] = data
    return details


def parse_osv_batch_results(
    dependencies: list[Dependency],
    data: dict[str, object],
) -> list[tuple[Dependency, list[str]]]:
    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError("OSV querybatch response missing results array")

    parsed: list[tuple[Dependency, list[str]]] = []
    for dep, result in zip(dependencies, results, strict=False):
        if not isinstance(result, dict):
            parsed.append((dep, []))
            continue
        vulns = result.get("vulns", [])
        if not isinstance(vulns, list):
            parsed.append((dep, []))
            continue
        ids = sorted(
            {
                str(vuln["id"])
                for vuln in vulns
                if isinstance(vuln, dict) and isinstance(vuln.get("id"), str)
            }
        )
        parsed.append((dep, ids))
    return parsed


def parse_kev_cves(data: dict[str, object]) -> set[str]:
    vulnerabilities = data.get("vulnerabilities", [])
    if not isinstance(vulnerabilities, list):
        raise ValueError("CISA KEV response missing vulnerabilities array")
    cves: set[str] = set()
    for vulnerability in vulnerabilities:
        if not isinstance(vulnerability, dict):
            continue
        cve_id = vulnerability.get("cveID")
        if isinstance(cve_id, str):
            cves.add(cve_id)
    return cves


def fetch_ghsa_advisories(
    dependencies: list[Dependency],
    *,
    ghsa_file: Path | None = None,
    token: str | None = None,
    kev_cves: set[str] | None = None,
) -> list[Finding]:
    """Collect GitHub Advisory Database findings for *dependencies*.

    Fixture mode (``ghsa_file``) reads a JSON object with an
    ``"advisories"`` array shaped like GitHub's ``/advisories`` response.
    Live mode queries ``/advisories?affects=<name>@<ver>&ecosystem=<eco>``
    per dependency. Ecosystems without a GHSA mapping (see
    ``_GHSA_ECOSYSTEM_MAP``) are skipped silently; broader coverage is
    tracked under #176.
    """
    if not dependencies:
        return []
    kev = kev_cves if kev_cves is not None else set()

    advisories: list[dict[str, object]] = []
    if ghsa_file is not None:
        advisories = load_ghsa_advisories(ghsa_file)
    else:
        for dep in dependencies:
            ghsa_eco = _GHSA_ECOSYSTEM_MAP.get(dep.ecosystem)
            if ghsa_eco is None:
                continue
            query = urllib.parse.urlencode(
                {
                    "affects": f"{dep.name}@{dep.version}",
                    "ecosystem": ghsa_eco,
                    "per_page": "100",
                }
            )
            data = request_json_any(f"{GHSA_ADVISORIES_URL}?{query}", token=token)
            if isinstance(data, list):
                advisories.extend(item for item in data if isinstance(item, dict))

    findings: list[Finding] = []
    for advisory in advisories:
        vuln_id = _ghsa_primary_id(advisory)
        if not vuln_id:
            continue
        aliases = _ghsa_aliases(advisory, vuln_id)
        advisory_type = _ghsa_type(advisory)
        identifiers = {vuln_id, *aliases}
        known_exploited = bool(identifiers & kev)
        for dep in dependencies:
            if not _ghsa_affects_dependency(advisory, dep):
                continue
            findings.append(
                Finding(
                    dependency=dep,
                    vuln_id=vuln_id,
                    aliases=aliases,
                    source=SOURCE_GHSA,
                    known_exploited=known_exploited,
                    advisory_type=advisory_type,
                )
            )
    return findings


def load_ghsa_advisories(path: Path) -> list[dict[str, object]]:
    """Return the list of advisory dicts from a GHSA fixture file."""
    data = load_json(path)
    advisories = data.get("advisories", [])
    if not isinstance(advisories, list):
        raise ValueError(f"{path} must contain an 'advisories' array")
    return [item for item in advisories if isinstance(item, dict)]


def _ghsa_primary_id(advisory: dict[str, object]) -> str:
    raw = advisory.get("ghsa_id")
    return str(raw) if isinstance(raw, str) else ""


def _ghsa_aliases(advisory: dict[str, object], primary: str) -> tuple[str, ...]:
    aliases: list[str] = []
    cve = advisory.get("cve_id")
    if isinstance(cve, str) and cve:
        aliases.append(cve)
    identifiers = advisory.get("identifiers", [])
    if isinstance(identifiers, list):
        for item in identifiers:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if isinstance(value, str) and value and value != primary and value not in aliases:
                aliases.append(value)
    return tuple(aliases)


def _ghsa_type(advisory: dict[str, object]) -> str | None:
    raw = advisory.get("type")
    return str(raw) if isinstance(raw, str) else None


def _ghsa_affects_dependency(advisory: dict[str, object], dep: Dependency) -> bool:
    ghsa_eco = _GHSA_ECOSYSTEM_MAP.get(dep.ecosystem)
    if ghsa_eco is None:
        return False
    vulnerabilities = advisory.get("vulnerabilities", [])
    if not isinstance(vulnerabilities, list):
        return False
    for vuln in vulnerabilities:
        if not isinstance(vuln, dict):
            continue
        package = vuln.get("package")
        if not isinstance(package, dict):
            continue
        if package.get("ecosystem") != ghsa_eco:
            continue
        name = package.get("name")
        if isinstance(name, str) and name.lower() == dep.name.lower():
            return True
    return False


def fetch_ossf_malicious_packages(
    dependencies: list[Dependency],
    *,
    malpkg_file: Path | None = None,
    malpkg_live: bool = False,
    kev_cves: set[str] | None = None,
) -> list[Finding]:
    """Collect OSSF malicious-package findings for *dependencies*.

    Fixture mode (``malpkg_file``) reads a JSON object with a
    ``"malicious_packages"`` array of OSV-shaped records (each carrying
    ``id``, optional ``aliases``, and ``affected[].package.{ecosystem,name}``).
    Live mode queries ``api.osv.dev/v1/query`` per dependency with the
    version field omitted and keeps only IDs prefixed ``MAL-`` -- this
    is the OSSF malicious-packages syndication channel on OSV.dev and
    is the documented stable access path for the corpus.

    Matching is **name-only** (case-insensitive within ecosystem) so a
    newly introduced typosquat or maintainer-takeover release registers
    even when the locked version is not itself flagged.
    """
    if not dependencies:
        return []
    if malpkg_file is None and not malpkg_live:
        return []
    kev = kev_cves if kev_cves is not None else set()

    records: list[dict[str, object]]
    if malpkg_file is not None:
        records = load_ossf_malicious_records(malpkg_file)
    else:
        records = []
        for dep in dependencies:
            records.extend(query_osv_malicious_for_dependency(dep))

    findings: list[Finding] = []
    for record in records:
        vuln_id = record.get("id")
        if not isinstance(vuln_id, str) or not vuln_id.startswith(MAL_ID_PREFIX):
            continue
        raw_aliases = record.get("aliases", [])
        aliases = tuple(
            str(alias)
            for alias in (raw_aliases if isinstance(raw_aliases, list) else [])
            if isinstance(alias, str)
        )
        identifiers = {vuln_id, *aliases}
        known_exploited = bool(identifiers & kev)
        for dep in _ossf_affected_dependencies(record, dependencies):
            findings.append(
                Finding(
                    dependency=dep,
                    vuln_id=vuln_id,
                    aliases=aliases,
                    source=SOURCE_OSSF_MAL,
                    known_exploited=known_exploited,
                    advisory_type=GHSA_MALWARE_TYPE,
                )
            )
    return findings


def load_ossf_malicious_records(path: Path) -> list[dict[str, object]]:
    """Return the list of malicious-package dicts from an OSSF fixture file."""
    data = load_json(path)
    records = data.get("malicious_packages", [])
    if not isinstance(records, list):
        raise ValueError(f"{path} must contain a 'malicious_packages' array")
    return [item for item in records if isinstance(item, dict)]


def query_osv_malicious_for_dependency(dep: Dependency) -> list[dict[str, object]]:
    """Query OSV.dev for *dep* by name only and return MAL-prefixed records."""
    payload: dict[str, object] = {
        "package": {"name": dep.name, "ecosystem": dep.ecosystem},
    }
    response = request_json(OSV_QUERY_URL, payload=payload)
    vulns = response.get("vulns", [])
    if not isinstance(vulns, list):
        return []
    return [
        vuln
        for vuln in vulns
        if isinstance(vuln, dict)
        and isinstance(vuln.get("id"), str)
        and vuln["id"].startswith(MAL_ID_PREFIX)
    ]


def _ossf_affected_dependencies(
    record: dict[str, object], dependencies: list[Dependency]
) -> list[Dependency]:
    affected = record.get("affected", [])
    if not isinstance(affected, list):
        return []
    matched: list[Dependency] = []
    for entry in affected:
        if not isinstance(entry, dict):
            continue
        package = entry.get("package")
        if not isinstance(package, dict):
            continue
        eco = package.get("ecosystem")
        name = package.get("name")
        if not isinstance(eco, str) or not isinstance(name, str):
            continue
        for dep in dependencies:
            if (
                dep.ecosystem == eco
                and dep.name.lower() == name.lower()
                and dep not in matched
            ):
                matched.append(dep)
    return matched


def merge_findings(findings: list[Finding]) -> list[Finding]:
    """Dedupe findings sharing (dependency identity, vuln_id) while keeping source attribution.

    Source strings are joined with ", " so a vulnerability surfaced by
    both OSV.dev and GitHub Advisory keeps both attributions visible in
    the threat triage summary (#172 scope).
    """
    by_key: dict[tuple[str, str, str, str], Finding] = {}
    for finding in findings:
        dep = finding.dependency
        key = (dep.ecosystem, dep.name, dep.version, finding.vuln_id)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = finding
            continue
        sources = [s.strip() for s in existing.source.split(",") if s.strip()]
        for chunk in finding.source.split(","):
            src = chunk.strip()
            if src and src not in sources:
                sources.append(src)
        merged_aliases = list(existing.aliases)
        for alias in finding.aliases:
            if alias not in merged_aliases:
                merged_aliases.append(alias)
        by_key[key] = Finding(
            dependency=existing.dependency,
            vuln_id=existing.vuln_id,
            aliases=tuple(merged_aliases),
            source=", ".join(sources),
            known_exploited=existing.known_exploited or finding.known_exploited,
            advisory_type=existing.advisory_type or finding.advisory_type,
        )
    return list(by_key.values())


def classify_findings(findings: list[Finding], labels: set[str]) -> dict[str, object]:
    intel_needed = bool(findings)
    response_needed = any(
        finding.known_exploited or finding.advisory_type == GHSA_MALWARE_TYPE
        for finding in findings
    )

    recommended_labels: list[str] = []
    if intel_needed:
        recommended_labels.append(INTEL_LABEL)
    if response_needed:
        recommended_labels.append(RESPONSE_LABEL)
    remove_labels = sorted((labels & THREAT_LABELS) - set(recommended_labels))

    return {
        "intel_needed": intel_needed,
        "response_needed": response_needed,
        "recommended_labels": recommended_labels,
        "remove_labels": remove_labels,
        "finding_count": len(findings),
        "known_exploited_count": sum(1 for finding in findings if finding.known_exploited),
        "findings": [finding_to_dict(finding) for finding in findings],
    }


def finding_to_dict(finding: Finding) -> dict[str, object]:
    return {
        "dependency": {
            "name": finding.dependency.name,
            "version": finding.dependency.version,
            "ecosystem": finding.dependency.ecosystem,
            "source": finding.dependency.source,
        },
        "vuln_id": finding.vuln_id,
        "aliases": list(finding.aliases),
        "source": finding.source,
        "known_exploited": finding.known_exploited,
        "advisory_type": finding.advisory_type,
    }


def find_indicators(text: str, indicators: tuple[Indicator, ...]) -> list[str]:
    """Return sorted-unique indicator names present in *text*."""
    return sorted({indicator.name for indicator in indicators if indicator.pattern.search(text)})


def classify(title: str, body: str, labels: set[str]) -> dict[str, object]:
    """Classify threat-intelligence and response requirements."""
    text = f"{title}\n{body}"
    intel_matches = find_indicators(text, INTEL_INDICATORS)
    response_matches = find_indicators(text, RESPONSE_INDICATORS)
    security_labeled = SECURITY_LABEL in labels

    intel_needed = security_labeled or bool(intel_matches) or bool(response_matches)
    response_needed = security_labeled or bool(response_matches)

    recommended_labels: list[str] = []
    if intel_needed:
        recommended_labels.append(INTEL_LABEL)
    if response_needed:
        recommended_labels.append(RESPONSE_LABEL)
    remove_labels = sorted((labels & THREAT_LABELS) - set(recommended_labels))

    return {
        "intel_needed": intel_needed,
        "response_needed": response_needed,
        "recommended_labels": recommended_labels,
        "remove_labels": remove_labels,
        "matched_intel_indicators": intel_matches,
        "matched_response_indicators": response_matches,
        "security_labeled": security_labeled,
    }


def _cmd_classify(args: argparse.Namespace) -> int:
    body = args.body or ""
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    labels = parse_labels(args.labels or os.environ.get("LABELS", ""))
    result = classify(args.title or os.environ.get("TITLE", ""), body, labels)

    if args.github_output:
        _write_github_output(Path(args.github_output), result)

    if args.format == "json":
        print(json.dumps(result, sort_keys=True))
        return 0

    print(f"intel_needed={_bool(result['intel_needed'])}")
    print(f"response_needed={_bool(result['response_needed'])}")
    print(f"recommended_labels={','.join(result['recommended_labels'])}")
    print(f"remove_labels={','.join(result['remove_labels'])}")
    print(f"matched_intel_indicators={','.join(result['matched_intel_indicators'])}")
    print(f"matched_response_indicators={','.join(result['matched_response_indicators'])}")
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root)
    labels = parse_labels(args.labels or os.environ.get("LABELS", ""))
    dependencies = discover_dependencies(repo_root)
    findings = fetch_external_findings(
        dependencies,
        osv_file=args.osv_file,
        kev_file=args.kev_file,
        ghsa_file=args.ghsa_file,
        ghsa_live=args.ghsa_live,
        ghsa_token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"),
        malpkg_file=args.malpkg_file,
        malpkg_live=args.malpkg_live,
    )
    result = classify_findings(findings, labels)

    if args.summary_file:
        write_summary(Path(args.summary_file), dependencies, findings, result)
    if args.github_output:
        _write_github_output(Path(args.github_output), result)

    if args.format == "json":
        print(json.dumps(result, sort_keys=True))
        return 0

    print(f"dependencies={len(dependencies)}")
    print(f"findings={result['finding_count']}")
    print(f"known_exploited={result['known_exploited_count']}")
    print(f"intel_needed={_bool(result['intel_needed'])}")
    print(f"response_needed={_bool(result['response_needed'])}")
    print(f"recommended_labels={','.join(result['recommended_labels'])}")
    print(f"remove_labels={','.join(result['remove_labels'])}")
    return 0


def write_summary(
    path: Path,
    dependencies: list[Dependency],
    findings: list[Finding],
    result: dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sources_line = _summary_sources_line(findings)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("## Threat intelligence triage\n\n")
        handle.write(f"- Sources: {sources_line}\n")
        handle.write(f"- Dependencies checked: {len(dependencies)}\n")
        handle.write(f"- Findings: {result['finding_count']}\n")
        handle.write(f"- Known exploited findings: {result['known_exploited_count']}\n")
        handle.write(f"- Recommended labels: `{','.join(result['recommended_labels'])}`\n\n")
        if not findings:
            handle.write("No external threat-intelligence findings matched locked dependencies.\n")
            return
        handle.write("| Dependency | Version | Vulnerability | Source | Known exploited |\n")
        handle.write("|---|---:|---|---|---|\n")
        for finding in findings:
            handle.write(
                f"| `{finding.dependency.name}` | `{finding.dependency.version}` | "
                f"`{finding.vuln_id}` | {finding.source} | {_bool(finding.known_exploited)} |\n"
            )


def _summary_sources_line(findings: list[Finding]) -> str:
    """Return a human-readable list of sources observed across *findings*.

    CISA KEV is always part of the pipeline (used as correlation, not as
    a primary finding source), so it stays present in the summary even
    when no findings were KEV-correlated.
    """
    seen: list[str] = []
    for finding in findings:
        for chunk in finding.source.split(","):
            src = chunk.strip()
            if src and src not in seen:
                seen.append(src)
    # Stable preferred order so the summary reads the same regardless of
    # iteration order of the underlying findings.
    preferred = [SOURCE_OSV, SOURCE_GHSA, SOURCE_OSSF_MAL]
    ordered = [src for src in preferred if src in seen]
    ordered.extend(src for src in seen if src not in preferred)
    if not ordered:
        ordered = [SOURCE_OSV, SOURCE_GHSA, SOURCE_OSSF_MAL]
    ordered.append("CISA KEV")
    return ", ".join(ordered)


def _write_github_output(path: Path, result: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"intel_needed={_bool(result['intel_needed'])}\n")
        handle.write(f"response_needed={_bool(result['response_needed'])}\n")
        handle.write(f"recommended_labels={','.join(result['recommended_labels'])}\n")
        handle.write(f"remove_labels={','.join(result['remove_labels'])}\n")


def _bool(value: object) -> str:
    return "true" if bool(value) else "false"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def request_json(
    url: str,
    payload: dict[str, object] | None = None,
    *,
    token: str | None = None,
) -> dict[str, object]:
    parsed = request_json_any(url, payload=payload, token=token)
    if not isinstance(parsed, dict):
        raise ValueError(f"{url} returned a non-object JSON response")
    return parsed


def request_json_any(
    url: str,
    *,
    payload: dict[str, object] | None = None,
    token: str | None = None,
) -> object:
    """Issue an HTTP request and return the parsed JSON body unchecked.

    ``token`` adds an ``Authorization`` header (used for the GitHub
    Advisory endpoint to lift the unauthenticated rate limit). The
    value is never echoed back into log lines per CLAUDE.md s4.
    """
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # All callers pass one of the module-level https endpoints
    # (OSV_QUERYBATCH_URL, OSV_VULN_URL, CISA_KEV_URL, GHSA_ADVISORIES_URL).
    # vuln_id segments are urllib.parse.quote'd at the call site.
    request = urllib.request.Request(  # noqa: S310 -- fixed https OSV/CISA/GHSA endpoints
        url,
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- paired with the Request above
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_classify = sub.add_parser(
        "classify",
        help="Classify threat intelligence and response requirements.",
    )
    p_classify.add_argument("--title", help="Issue or PR title. Defaults to $TITLE.")
    p_classify.add_argument("--body", help="Issue or PR body text.")
    p_classify.add_argument("--body-file", help="Path to issue or PR body text.")
    p_classify.add_argument(
        "--labels",
        action="append",
        help="Comma or newline separated label names. Defaults to $LABELS.",
    )
    p_classify.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    p_classify.add_argument(
        "--github-output",
        help="Append GitHub Actions outputs to this file.",
    )
    p_classify.set_defaults(func=_cmd_classify)

    p_scan = sub.add_parser(
        "scan",
        help="Collect OSV.dev and CISA KEV intelligence for repository dependencies.",
    )
    p_scan.add_argument("--repo-root", type=Path, default=Path())
    p_scan.add_argument(
        "--labels",
        action="append",
        help="Comma or newline separated label names. Defaults to $LABELS.",
    )
    p_scan.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    p_scan.add_argument(
        "--github-output",
        help="Append GitHub Actions outputs to this file.",
    )
    p_scan.add_argument(
        "--summary-file",
        help="Append a markdown summary to this file.",
    )
    p_scan.add_argument(
        "--osv-file",
        type=Path,
        help="Fixture file containing an OSV querybatch-shaped response.",
    )
    p_scan.add_argument(
        "--kev-file",
        type=Path,
        help="Fixture file containing a CISA KEV-shaped response.",
    )
    p_scan.add_argument(
        "--ghsa-file",
        type=Path,
        help="Fixture file containing a GitHub Advisory-shaped response.",
    )
    p_scan.add_argument(
        "--ghsa-live",
        action="store_true",
        help=(
            "Query api.github.com/advisories live. Uses GH_TOKEN or "
            "GITHUB_TOKEN if set to lift the unauthenticated rate limit."
        ),
    )
    p_scan.add_argument(
        "--malpkg-file",
        type=Path,
        help=(
            "Fixture file containing an OSSF malicious-packages JSON "
            "envelope ({'malicious_packages': [OSV-shaped records]})."
        ),
    )
    p_scan.add_argument(
        "--malpkg-live",
        action="store_true",
        help=(
            "Query api.osv.dev/v1/query live for each dependency by name "
            "only and keep MAL- prefixed records (the OSSF "
            "malicious-packages syndication channel on OSV.dev)."
        ),
    )
    p_scan.set_defaults(func=_cmd_scan)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"::error::{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
