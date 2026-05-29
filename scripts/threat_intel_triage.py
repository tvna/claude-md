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
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

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
EPSS_URL = "https://api.first.org/data/v1/epss"
NVD_CVE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_DETAIL_URL_PREFIX = "https://nvd.nist.gov/vuln/detail/"
SOURCE_OSV = "OSV.dev"
SOURCE_GHSA = "GitHub Advisory"
SOURCE_OSSF_MAL = "OSSF malicious-packages"
SOURCE_EPSS = "FIRST EPSS"
SOURCE_NVD = "NVD"

# OSV.dev ecosystem identifier for ``uses: owner/repo@<ref>`` workflow
# references (#176). Held in its own constant because the string is
# checked at several call sites and a typo silently produces zero
# findings against OSV.
ECOSYSTEM_ACTIONS = "GitHub Actions"
ECOSYSTEM_PYPI = "PyPI"
WORKFLOW_SUBDIR = ".github/workflows"
SCRIPTS_SUBDIR = "scripts"

# Pattern for CVE identifiers used to filter EPSS-eligible aliases. EPSS
# data is keyed on CVE only; GHSA / OSV identifiers are not accepted by
# the FIRST API and must be filtered out before batching. The same
# pattern gates NVD enrichment (#174) since NVD indexes CVE IDs only.
_CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)

# Map this module's internal ecosystem labels (taken from OSV) to the
# values accepted by GitHub's /advisories endpoint. Keep this minimal:
# only ecosystems actually discovered by ``discover_dependencies``.
_GHSA_ECOSYSTEM_MAP = {"PyPI": "pip"}

# Per CLAUDE.md s4: bound the summary surface. NVD references for some
# CVEs run into the hundreds; only the first few links carry signal for a
# triage row, and the full list remains a click away on the NVD detail
# page emitted as ``source_url``.
_NVD_MAX_REFERENCES = 5


class Indicator(NamedTuple):
    name: str
    pattern: re.Pattern[str]


class Dependency(NamedTuple):
    name: str
    version: str
    ecosystem: str
    source: str


class NvdEnrichment(NamedTuple):
    """Supplemental NVD metadata attached to a CVE-backed finding (#174).

    NVD is consulted only for CVEs already surfaced by OSV/GHSA. Missing
    or malformed enrichment is silently ignored so the underlying finding
    is never suppressed -- "no NVD data" is not evidence that the
    vulnerability is not relevant.
    """

    cve_id: str
    cvss_severity: str | None
    cvss_score: float | None
    cvss_version: str | None
    cwe_ids: tuple[str, ...]
    references: tuple[str, ...]
    source_url: str


class Finding(NamedTuple):
    dependency: Dependency
    vuln_id: str
    aliases: tuple[str, ...]
    source: str
    known_exploited: bool
    # GHSA-only attribute. ``None`` for OSV-only findings; ``"malware"``
    # escalates ``threat:response-needed`` per #172.
    advisory_type: str | None = None
    # FIRST EPSS enrichment per #173. Advisory-only: never escalates
    # ``threat:response-needed`` on its own; KEV correlation remains the
    # authoritative known-exploitation signal.
    epss_score: float | None = None
    epss_percentile: float | None = None
    # NVD CVE enrichment (#174). Supplemental only -- empty tuple means
    # "no NVD enrichment available", not "vulnerability not relevant".
    nvd_metadata: tuple[NvdEnrichment, ...] = ()


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
    """Return version-pinned dependencies discoverable in *repo_root*.

    Surfaces scanned (#176):

    * ``uv.lock`` -- PyPI transitive lock.
    * ``pyproject.toml`` -- exact PyPI pins from ``project.dependencies``
      and ``dependency-groups``.
    * ``.github/workflows/**/*.{yml,yaml}`` -- GitHub Actions ``uses:``
      references. SHA-pinned actions take the tag from the trailing
      ``# <tag>`` comment so OSV correlates against the released version
      rather than the opaque commit SHA.
    * ``.github/workflows/**/*.{yml,yaml}`` and ``scripts/**/*.{sh,py}``
      -- transient PyPI pins inside ``uv run --with pkg==version``
      invocations. Non-executable docs prose is intentionally excluded
      so README / runbook examples cannot create noisy findings.
    """
    by_key: dict[tuple[str, str, str], Dependency] = {}
    for dep in parse_uv_lock(repo_root / "uv.lock"):
        by_key[(dep.ecosystem, dep.name, dep.version)] = dep
    for dep in parse_pyproject_pinned_dependencies(repo_root / "pyproject.toml"):
        by_key.setdefault((dep.ecosystem, dep.name, dep.version), dep)
    for dep in parse_workflow_actions(repo_root):
        by_key.setdefault((dep.ecosystem, dep.name, dep.version), dep)
    for dep in parse_transient_uv_run(repo_root):
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


# Pattern for a ``uses:`` value: captures the reference (everything up to
# whitespace, ``#``, or end-of-line) and optionally the trailing
# ``# <tag>`` comment used by SHA-pinned references. Tolerates the YAML
# list-dash prefix and arbitrary leading whitespace. Mirrors the parsing
# contract enforced by ``scripts/scan_workflow_action_pins.py`` -- the
# two scripts intentionally diverge on intent (this one ingests refs
# into the threat-intel pipeline; the other is a deterministic
# SHA-pin gate).
_USES_LINE = re.compile(
    r"^\s*-?\s*uses:\s*(?P<ref>\S+)(?:\s+#\s*(?P<tag>\S.*?)\s*$)?",
    re.MULTILINE,
)

# Comment line: any line whose first non-whitespace character is ``#``.
_COMMENT_LINE = re.compile(r"^\s*#")

# Full 40-character lowercase hex (a git commit SHA).
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# A literal exact pin inside a ``uv run --with`` argument. Strict on
# both name and version so shell-variable expansions (``${VAR}``),
# placeholders (``<pin>``), and range specifiers (``>=``, ``~=``) are
# rejected silently and never reach OSV as garbage queries. The
# optional extras group (``[foo,bar]``) matches the syntax allowed by
# pip / uv.
_UV_WITH_EXACT_PIN = re.compile(
    r"--with[=\s]+[\"']?(?P<name>[A-Za-z0-9_.\-]+)"
    r"(?:\[[A-Za-z0-9_.\-,]+\])?==(?P<version>[A-Za-z0-9_.+\-]+)[\"']?"
)


def parse_workflow_actions(repo_root: Path) -> list[Dependency]:
    """Return ``GitHub Actions`` dependencies from workflow YAML.

    Walks ``.github/workflows/**/*.{yml,yaml}`` under *repo_root* and
    converts every external ``uses:`` reference into a
    :class:`Dependency` keyed on the OSV ecosystem
    ``"GitHub Actions"``.

    * ``./...`` and ``../...`` references are local in-repo composite
      workflows; they have no upstream version surface to correlate.
    * ``docker://...`` references are OCI images; digest pinning is
      tracked separately (see ``scripts/scan_workflow_action_pins.py``)
      and is out of scope for the OSV correlation surface here.
    * Lines whose first non-whitespace character is ``#`` are skipped
      so the rule can be documented inside workflow YAML without
      self-tripping.
    * SHA-pinned references (``owner/repo@<40-hex-sha>``) take the
      version from the trailing ``# <tag>`` comment when present so
      OSV correlates against the released version rather than the
      opaque commit SHA. When the comment is missing, the SHA itself
      is used as a last-resort version string -- this keeps the
      surface complete even when ``scan_workflow_action_pins`` has not
      yet been satisfied.
    """
    workflow_dir = repo_root / WORKFLOW_SUBDIR
    if not workflow_dir.is_dir():
        return []
    deps: list[Dependency] = []
    for path in sorted(workflow_dir.rglob("*")):
        if not path.is_file() or path.suffix not in (".yml", ".yaml"):
            continue
        deps.extend(_extract_workflow_actions(path))
    return deps


def _extract_workflow_actions(path: Path) -> list[Dependency]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    source = str(path)
    deps: list[Dependency] = []
    for line in text.splitlines():
        if _COMMENT_LINE.match(line):
            continue
        match = _USES_LINE.match(line)
        if match is None:
            continue
        ref = match.group("ref")
        tag_comment = match.group("tag")
        parsed = _parse_action_reference(ref, tag_comment)
        if parsed is None:
            continue
        name, version = parsed
        deps.append(
            Dependency(
                name=name,
                version=version,
                ecosystem=ECOSYSTEM_ACTIONS,
                source=source,
            )
        )
    return deps


def _parse_action_reference(
    ref: str, tag_comment: str | None
) -> tuple[str, str] | None:
    """Return ``(owner/repo, version)`` for *ref* or None when out of scope."""
    if ref.startswith("./") or ref.startswith("../"):
        return None
    if ref.startswith("docker://"):
        return None
    if "@" not in ref:
        return None
    owner_repo, _, rev = ref.rpartition("@")
    if not owner_repo or "/" not in owner_repo or not rev:
        return None
    if _FULL_SHA_RE.match(rev) and tag_comment:
        return owner_repo, tag_comment
    return owner_repo, rev


def parse_transient_uv_run(repo_root: Path) -> list[Dependency]:
    """Return PyPI dependencies pinned through ``uv run --with pkg==ver``.

    Scans executable inputs only -- ``.github/workflows/**/*.{yml,yaml}``
    and ``scripts/**/*.{sh,py}``. Markdown prose under ``docs/`` (and
    elsewhere) is intentionally excluded so a README or runbook example
    cannot create noisy findings (per #176 completion check).

    Range specifiers (``>=``, ``~=``), shell-variable expansions
    (``${VAR}``), and placeholders such as ``<pin>`` are silently
    skipped: only literal ``name==version`` pins survive the regex.
    """
    deps: list[Dependency] = []
    for path in _iter_executable_inputs(repo_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        source = str(path)
        for match in _UV_WITH_EXACT_PIN.finditer(text):
            deps.append(
                Dependency(
                    name=match.group("name"),
                    version=match.group("version"),
                    ecosystem=ECOSYSTEM_PYPI,
                    source=source,
                )
            )
    return deps


def _iter_executable_inputs(repo_root: Path) -> list[Path]:
    """Return the sorted list of executable-input files scanned for ``uv run``."""
    candidates: list[Path] = []
    workflow_dir = repo_root / WORKFLOW_SUBDIR
    if workflow_dir.is_dir():
        for path in workflow_dir.rglob("*"):
            if path.is_file() and path.suffix in (".yml", ".yaml"):
                candidates.append(path)
    scripts_dir = repo_root / SCRIPTS_SUBDIR
    if scripts_dir.is_dir():
        for path in scripts_dir.rglob("*"):
            if path.is_file() and path.suffix in (".sh", ".py"):
                candidates.append(path)
    return sorted(candidates)


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
    epss_file: Path | None = None,
    epss_live: bool = False,
    nvd_file: Path | None = None,
    nvd_live: bool = False,
) -> list[Finding]:
    """Collect OSV, CISA KEV, GHSA, OSSF malicious-package, FIRST EPSS, and NVD intelligence.

    GHSA, OSSF malicious-packages, EPSS, and NVD are opt-in to keep the
    OSV-only call sites (notably this module's own legacy tests)
    deterministic without a network call. Pass ``ghsa_file=`` /
    ``malpkg_file=`` / ``epss_file=`` / ``nvd_file=`` for fixture-driven
    runs, or ``*_live=True`` to query the upstream endpoint live
    (``api.github.com/advisories`` / ``api.osv.dev/v1/query`` for the
    OSSF malicious-packages syndication channel /
    ``api.first.org/data/v1/epss`` /
    ``services.nvd.nist.gov/rest/json/cves/2.0``).

    EPSS is advisory-only per #173: scores enrich the summary table but
    never escalate ``threat:response-needed`` on their own. NVD is
    supplemental enrichment per #174: it is consulted only for CVEs
    already surfaced by OSV/GHSA, never widens the finding set, never
    reclassifies severity, and never participates in
    ``threat:response-needed``. KEV correlation and OSSF ``MAL-``
    findings remain the authoritative known-exploitation / malware
    signals.
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
    if epss_file is not None or epss_live:
        epss_scores = fetch_epss_scores(
            _collect_cve_ids(merged),
            epss_file=epss_file,
            epss_live=epss_live,
        )
        merged = [_attach_epss(finding, epss_scores) for finding in merged]
    if nvd_file is not None or nvd_live:
        nvd_map = fetch_nvd_metadata(_collect_cve_ids(merged), nvd_file=nvd_file)
        merged = attach_nvd_to_findings(merged, nvd_map)
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


def fetch_epss_scores(
    cves: list[str],
    *,
    epss_file: Path | None = None,
    epss_live: bool = False,
) -> dict[str, tuple[float, float]]:
    """Return ``{cve: (score, percentile)}`` from FIRST EPSS for *cves*.

    Fixture mode (``epss_file``) reads a JSON object with a ``"data"``
    array shaped like ``api.first.org/data/v1/epss``. Live mode batches
    CVEs into a single ``GET /epss?cve=A,B,C`` query.

    EPSS lookups soft-fail: any transport, JSON, or parse error returns
    an empty dict so the OSV / GHSA / KEV pipeline keeps working. EPSS
    is advisory-only per #173 -- the absence of scores must not block
    routing on confirmed exploitation evidence (KEV / malware).
    """
    if not cves:
        return {}
    if epss_file is not None:
        try:
            data = load_json(epss_file)
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        return _parse_epss_payload(data)
    if not epss_live:
        return {}
    query = urllib.parse.urlencode({"cve": ",".join(sorted(set(cves)))})
    try:
        data = request_json(f"{EPSS_URL}?{query}")
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return _parse_epss_payload(data)


def _parse_epss_payload(data: dict[str, object]) -> dict[str, tuple[float, float]]:
    rows = data.get("data", [])
    if not isinstance(rows, list):
        return {}
    scores: dict[str, tuple[float, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cve = row.get("cve")
        score = _coerce_epss_float(row.get("epss"))
        percentile = _coerce_epss_float(row.get("percentile"))
        if isinstance(cve, str) and score is not None and percentile is not None:
            scores[cve.upper()] = (score, percentile)
    return scores


def _coerce_epss_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _collect_cve_ids(findings: list[Finding]) -> list[str]:
    """Return unique uppercase CVE identifiers across *findings*."""
    seen: set[str] = set()
    for finding in findings:
        for candidate in (finding.vuln_id, *finding.aliases):
            if isinstance(candidate, str) and _CVE_PATTERN.match(candidate):
                seen.add(candidate.upper())
    return sorted(seen)


def _attach_epss(finding: Finding, scores: dict[str, tuple[float, float]]) -> Finding:
    """Return *finding* with EPSS fields filled if any of its CVEs match *scores*."""
    if not scores:
        return finding
    for candidate in (finding.vuln_id, *finding.aliases):
        if not isinstance(candidate, str):
            continue
        match = scores.get(candidate.upper())
        if match is not None:
            score, percentile = match
            return finding._replace(epss_score=score, epss_percentile=percentile)
    return finding


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
            epss_score=existing.epss_score if existing.epss_score is not None else finding.epss_score,
            epss_percentile=(
                existing.epss_percentile
                if existing.epss_percentile is not None
                else finding.epss_percentile
            ),
        )
    return list(by_key.values())


def fetch_nvd_metadata(
    cve_ids: list[str],
    *,
    nvd_file: Path | None = None,
) -> dict[str, NvdEnrichment]:
    """Return NVD enrichment keyed by CVE id.

    Fixture mode (``nvd_file``) reads a JSON object with a ``"cves"``
    map whose values mirror the ``vulnerabilities[].cve`` sub-tree of
    NVD's ``/rest/json/cves/2.0`` response. Live mode issues one HTTPS
    request per CVE.

    Missing, malformed, or transport-failed entries are silently skipped
    per #174 -- absence of NVD enrichment is not evidence that the
    underlying OSV/GHSA finding is not relevant.
    """
    if not cve_ids:
        return {}

    enrichment: dict[str, NvdEnrichment] = {}

    if nvd_file is not None:
        try:
            payload = load_json(nvd_file)
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        raw_map = payload.get("cves", {})
        if not isinstance(raw_map, dict):
            return {}
        # Build an uppercase-keyed view so cve_ids (already uppercase per
        # _collect_cve_ids) match regardless of fixture casing.
        upper_raw = {key.upper(): value for key, value in raw_map.items() if isinstance(key, str)}
        for cve_id in cve_ids:
            cve_payload = upper_raw.get(cve_id)
            if not isinstance(cve_payload, dict):
                continue
            parsed = parse_nvd_cve(cve_payload, cve_id)
            if parsed is not None:
                enrichment[cve_id] = parsed
        return enrichment

    for cve_id in cve_ids:
        try:
            query = urllib.parse.urlencode({"cveId": cve_id})
            data = request_json(f"{NVD_CVE_URL}?{query}")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        vulnerabilities = data.get("vulnerabilities") if isinstance(data, dict) else None
        if not isinstance(vulnerabilities, list) or not vulnerabilities:
            continue
        first = vulnerabilities[0]
        if not isinstance(first, dict):
            continue
        cve_payload = first.get("cve")
        if not isinstance(cve_payload, dict):
            continue
        parsed = parse_nvd_cve(cve_payload, cve_id)
        if parsed is not None:
            enrichment[cve_id] = parsed
    return enrichment


def parse_nvd_cve(payload: dict[str, object], cve_id: str) -> NvdEnrichment | None:
    """Parse one NVD ``cve`` sub-object into an :class:`NvdEnrichment`.

    Returns ``None`` when the payload is too sparse to convey signal
    (no CVSS, no CWE, and no references). The caller treats ``None`` as
    "no enrichment available" and never escalates it into a missing
    finding.
    """
    cvss_severity, cvss_score, cvss_version = _extract_nvd_cvss(payload)
    cwe_ids = _extract_nvd_cwes(payload)
    references = _extract_nvd_references(payload)

    if cvss_severity is None and cvss_score is None and not cwe_ids and not references:
        return None

    return NvdEnrichment(
        cve_id=cve_id,
        cvss_severity=cvss_severity,
        cvss_score=cvss_score,
        cvss_version=cvss_version,
        cwe_ids=cwe_ids,
        references=references,
        source_url=f"{NVD_DETAIL_URL_PREFIX}{cve_id}",
    )


def _extract_nvd_cvss(
    payload: dict[str, object],
) -> tuple[str | None, float | None, str | None]:
    """Return ``(severity, score, version_label)`` from NVD CVSS metrics.

    Preference order is CVSS v3.1 -> v3.0 -> v2.0 to mirror NVD's own
    "primary first" policy. Any branch that fails its type check is
    skipped silently so a malformed metric block never displaces a
    well-formed lower-priority one.
    """
    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    if not isinstance(metrics, dict):
        return None, None, None

    for key, label in (
        ("cvssMetricV31", "3.1"),
        ("cvssMetricV30", "3.0"),
        ("cvssMetricV2", "2.0"),
    ):
        entries = metrics.get(key)
        if not isinstance(entries, list) or not entries:
            continue
        first = entries[0]
        if not isinstance(first, dict):
            continue
        cvss_data = first.get("cvssData")
        if not isinstance(cvss_data, dict):
            continue
        severity_raw = cvss_data.get("baseSeverity")
        if not isinstance(severity_raw, str):
            # CVSS v2 puts severity at the metric level, not on cvssData.
            severity_raw = first.get("baseSeverity") if isinstance(first.get("baseSeverity"), str) else None
        score_raw = cvss_data.get("baseScore")
        score: float | None = None
        if isinstance(score_raw, int | float):
            score = float(score_raw)
        if severity_raw is None and score is None:
            continue
        return severity_raw, score, label
    return None, None, None


def _extract_nvd_cwes(payload: dict[str, object]) -> tuple[str, ...]:
    weaknesses = payload.get("weaknesses") if isinstance(payload, dict) else None
    if not isinstance(weaknesses, list):
        return ()
    cwes: list[str] = []
    for weakness in weaknesses:
        if not isinstance(weakness, dict):
            continue
        descriptions = weakness.get("description")
        if not isinstance(descriptions, list):
            continue
        for desc in descriptions:
            if not isinstance(desc, dict):
                continue
            value = desc.get("value")
            if isinstance(value, str) and value.startswith("CWE-") and value not in cwes:
                cwes.append(value)
    return tuple(cwes)


def _extract_nvd_references(payload: dict[str, object]) -> tuple[str, ...]:
    references = payload.get("references") if isinstance(payload, dict) else None
    if not isinstance(references, list):
        return ()
    urls: list[str] = []
    for ref in references:
        if not isinstance(ref, dict):
            continue
        url = ref.get("url")
        if isinstance(url, str) and url not in urls:
            urls.append(url)
        if len(urls) >= _NVD_MAX_REFERENCES:
            break
    return tuple(urls)


def attach_nvd_to_findings(
    findings: list[Finding],
    nvd_map: dict[str, NvdEnrichment],
) -> list[Finding]:
    """Return *findings* with NVD enrichment attached where matching.

    Each finding is rebuilt with ``nvd_metadata`` set to every
    :class:`NvdEnrichment` whose CVE id appears in the finding's
    ``vuln_id`` or ``aliases``. Lookups use the uppercase form to align
    with :func:`_collect_cve_ids` and :func:`fetch_nvd_metadata` (both
    normalize to uppercase). Findings with no matching enrichment are
    returned unchanged.
    """
    if not nvd_map:
        return findings
    enriched: list[Finding] = []
    for finding in findings:
        matches: list[NvdEnrichment] = []
        for candidate in (finding.vuln_id, *finding.aliases):
            if not isinstance(candidate, str) or not _CVE_PATTERN.match(candidate):
                continue
            hit = nvd_map.get(candidate.upper())
            if hit is not None and hit not in matches:
                matches.append(hit)
        if matches:
            enriched.append(finding._replace(nvd_metadata=tuple(matches)))
        else:
            enriched.append(finding)
    return enriched


def classify_findings(findings: list[Finding], labels: set[str]) -> dict[str, object]:
    intel_needed = bool(findings)
    response_needed = any(
        finding.known_exploited or finding.advisory_type == GHSA_MALWARE_TYPE
        for finding in findings
    )

    recommended_labels, remove_labels = classify_label_changes(
        labels,
        intel_needed=intel_needed,
        response_needed=response_needed,
    )

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
        "epss_score": finding.epss_score,
        "epss_percentile": finding.epss_percentile,
        "nvd_metadata": [nvd_enrichment_to_dict(item) for item in finding.nvd_metadata],
    }


def nvd_enrichment_to_dict(enrichment: NvdEnrichment) -> dict[str, object]:
    return {
        "cve_id": enrichment.cve_id,
        "cvss_severity": enrichment.cvss_severity,
        "cvss_score": enrichment.cvss_score,
        "cvss_version": enrichment.cvss_version,
        "cwe_ids": list(enrichment.cwe_ids),
        "references": list(enrichment.references),
        "source_url": enrichment.source_url,
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

    recommended_labels, remove_labels = classify_label_changes(
        labels,
        intel_needed=intel_needed,
        response_needed=response_needed,
    )

    return {
        "intel_needed": intel_needed,
        "response_needed": response_needed,
        "recommended_labels": recommended_labels,
        "remove_labels": remove_labels,
        "matched_intel_indicators": intel_matches,
        "matched_response_indicators": response_matches,
        "security_labeled": security_labeled,
    }


def classify_label_changes(
    labels: set[str], *, intel_needed: bool, response_needed: bool
) -> tuple[list[str], list[str]]:
    wanted_labels: list[str] = []
    if intel_needed:
        wanted_labels.append(INTEL_LABEL)
    if response_needed:
        wanted_labels.append(RESPONSE_LABEL)
    existing_threat_labels = labels & THREAT_LABELS
    recommended_labels = [
        label for label in wanted_labels if label not in existing_threat_labels
    ]
    remove_labels = sorted(existing_threat_labels - set(wanted_labels))
    return recommended_labels, remove_labels


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
        epss_file=args.epss_file,
        epss_live=args.epss_live,
        nvd_file=args.nvd_file,
        nvd_live=args.nvd_live,
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
    has_nvd = any(finding.nvd_metadata for finding in findings)
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
        if has_nvd:
            handle.write(
                "| Dependency | Version | Vulnerability | Source | Known exploited | EPSS | NVD CVSS | NVD CWE |\n"
            )
            handle.write("|---|---:|---|---|---|---|---|---|\n")
        else:
            handle.write("| Dependency | Version | Vulnerability | Source | Known exploited | EPSS |\n")
            handle.write("|---|---:|---|---|---|---|\n")
        for finding in findings:
            row = (
                f"| `{finding.dependency.name}` | `{finding.dependency.version}` | "
                f"`{finding.vuln_id}` | {finding.source} | {_bool(finding.known_exploited)} | "
                f"{_format_epss_cell(finding)} |"
            )
            if has_nvd:
                row += f" {_nvd_cvss_cell(finding)} | {_nvd_cwe_cell(finding)} |"
            handle.write(row + "\n")
        if has_nvd:
            handle.write("\n### NVD references (supplemental)\n\n")
            handle.write(
                "NVD is consulted only for CVEs already surfaced by OSV/GitHub Advisory. "
                "Missing NVD enrichment does not imply the underlying finding is not relevant.\n\n"
            )
            for finding in findings:
                for enrichment in finding.nvd_metadata:
                    _write_nvd_detail(handle, finding, enrichment)


def _nvd_cvss_cell(finding: Finding) -> str:
    if not finding.nvd_metadata:
        return ""
    parts: list[str] = []
    for item in finding.nvd_metadata:
        severity = item.cvss_severity or "?"
        score = f"{item.cvss_score:.1f}" if item.cvss_score is not None else "?"
        version = item.cvss_version or "?"
        parts.append(f"v{version} {severity} {score}")
    return "<br>".join(parts)


def _nvd_cwe_cell(finding: Finding) -> str:
    if not finding.nvd_metadata:
        return ""
    seen: list[str] = []
    for item in finding.nvd_metadata:
        for cwe in item.cwe_ids:
            if cwe not in seen:
                seen.append(cwe)
    return ", ".join(seen)


def _write_nvd_detail(handle, finding: Finding, enrichment: NvdEnrichment) -> None:
    handle.write(
        f"- `{finding.dependency.name}@{finding.dependency.version}` "
        f"[{enrichment.cve_id}]({enrichment.source_url})\n"
    )
    if enrichment.cvss_severity or enrichment.cvss_score is not None:
        severity = enrichment.cvss_severity or "?"
        score = f"{enrichment.cvss_score:.1f}" if enrichment.cvss_score is not None else "?"
        version = enrichment.cvss_version or "?"
        handle.write(f"  - CVSS v{version}: {severity} ({score})\n")
    if enrichment.cwe_ids:
        handle.write(f"  - CWE: {', '.join(enrichment.cwe_ids)}\n")
    if enrichment.references:
        handle.write("  - References:\n")
        for url in enrichment.references:
            handle.write(f"    - {url}\n")


def _format_epss_cell(finding: Finding) -> str:
    """Render the EPSS column for *finding*. EPSS is advisory-only per #173."""
    if finding.epss_score is None or finding.epss_percentile is None:
        return "-"
    return f"{finding.epss_score:.3f} (p{finding.epss_percentile * 100:.1f}%)"


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
    if any(finding.epss_score is not None for finding in findings):
        ordered.append(SOURCE_EPSS)
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
    p_scan.add_argument(
        "--epss-file",
        type=Path,
        help="Fixture file containing a FIRST EPSS-shaped response.",
    )
    p_scan.add_argument(
        "--epss-live",
        action="store_true",
        help=(
            "Query api.first.org/data/v1/epss live for exploit prediction "
            "scores. EPSS is advisory-only and never escalates "
            "threat:response-needed (KEV remains the authoritative signal)."
        ),
    )
    p_scan.add_argument(
        "--nvd-file",
        type=Path,
        help=(
            "Fixture file containing an NVD CVE-shaped response. "
            "Supplemental enrichment per #174 -- missing data never "
            "suppresses an OSV/GHSA finding."
        ),
    )
    p_scan.add_argument(
        "--nvd-live",
        action="store_true",
        help=(
            "Query services.nvd.nist.gov/rest/json/cves/2.0 live for "
            "CVEs already surfaced by OSV/GHSA. NVD enrichment is "
            "supplemental and silently skipped on transport failure."
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
