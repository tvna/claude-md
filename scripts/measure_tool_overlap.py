#!/usr/bin/env python3
"""Measure how a newly provisioned tool overlaps its existing gate (Refs #1618).

Follow-up to #1610: the three pinned binaries (zizmor / lychee / betterleaks)
run ALONGSIDE the bespoke deterministic gates they overlap. This collector runs
each new tool and its paired gate on the SAME scope, normalizes both sides to
``(rule_id, path, line)`` findings, partitions the locations into
agree / new-tool-only / existing-gate-only diff sets, times each side, and
emits two things:

  * a JSON record array whose keys are EXACTLY the v3 ``tool_overlap_measurement``
    columns (``metrics/duckdb/schema/v3/schema.sql``), for operator-local
    ingestion into the host DuckDB store, and
  * an ASCII Markdown report (summary table + per-category diff listings) for
    ``$GITHUB_STEP_SUMMARY`` and artifact upload.

This is the report-plus-JSON shape that ``scripts/analyze_ci_timings.py`` set
the precedent for; the host DuckDB store is the metrics convention the records
match. The workflow never writes the DB (ephemeral CI is out of scope for the
host-local store by the #826 decision); it uploads the JSON instead.

Design (M1): pure functions on top; ``parse_*`` JSON parsers, ``diff_findings``,
``build_record``, ``render_markdown``; and a thin IO boundary at the bottom
(``_run`` subprocess wrapper, the ``collect_*_gate`` adapters that import the
existing scan modules, and ``main``). ``measure_pair`` takes the tool runner and
gate collector as injected callables so the orchestration is unit-tested without
the external binaries (which are NOT on the coverage runner).

Redaction (CLAUDE.md Section 4, #88): betterleaks is run with ``--redact=100``
and only its rule id / repo-relative path / line are read. The matched secret
VALUE never enters a Finding, a record, the JSON, or the Markdown; only
non-sensitive counts, paths, rule ids, and per-side durations are recorded.

Contract:
  Inputs:  ``--scope-root`` (repo root to scan, default cwd), ``--output``
           (JSON record path, optional), ``--report`` (Markdown path, optional;
           stdout when omitted), ``--commit`` (sha; default from ``git rev-parse``
           or ``"unknown"``), ``--host-id`` (opaque anonymized token; default
           ``$CLAUDE_MD_HOST_ID`` or ``"unknown"``), ``--pair`` (restrict to one
           pair; default all three), ``--smoke`` (opt-in: validate each tool's
           argv instead of measuring; Refs #1632).
  Outputs: JSON record array written to ``--output`` when given; Markdown report
           to ``--report`` or stdout; exit 0 on success. With ``--smoke``,
           prints one status line per pair and exits 1 iff any tool rejected its
           argv (empty / unparseable JSON stdout); an absent binary is skipped.
  Failure policy: fails loud per CLAUDE.md Section 4; a measurement is never
           faked with an empty result. A configured tool binary that is absent
           raises ``ToolUnavailableError``; a tool that exits unexpectedly or
           emits unparseable JSON raises ``RuntimeError``/``ValueError``; an
           unknown ``--pair`` raises ``ValueError``. It is a collector, not a
           gate: a clean scan (zero findings) is a valid measurement.

Tested by tests/test_measure_tool_overlap.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import scan_markdown_links
import scan_secrets
import scan_workflow_action_pins
import scan_workflow_injection

# Cap how many locations each diff category lists in the Markdown report, so a
# pathological run cannot emit an unbounded artifact. Counts are always exact in
# the table and the JSON record; only the human listing is truncated.
_MAX_LISTED = 50

# betterleaks emits a redacted sentinel in --redact=100 mode. We never read the
# Secret/Match fields anyway; this constant documents the expected sentinel.
_REDACTED_SENTINEL = "REDACTED"


@dataclass(frozen=True)
class Finding:
    """One normalized finding: a rule id at a repo-relative path and line.

    Only these three non-sensitive fields are ever retained from any tool. For
    the secret scanner this is the redaction boundary: the matched value is
    deliberately not a field here.
    """

    rule_id: str
    path: str  # repo-relative, POSIX separators
    line: int


# ---------------------------------------------------------------------------
# Pure: new-tool JSON parsers. Each takes the tool's raw stdout and returns
# normalized findings. They never shell out, so they are unit-tested directly
# against captured fixtures (the binaries are absent on the coverage runner).
# ---------------------------------------------------------------------------
def parse_zizmor(stdout: str) -> list[Finding]:
    """Parse ``zizmor --format json`` output into findings.

    zizmor emits a JSON array of audit findings; each has an ``ident`` (rule)
    and one or more ``locations`` carrying a local ``given_path`` and a
    tree-sitter ``start_point.row`` (0-based; converted to a 1-based line to
    line up with the 1-based lines the bespoke gates report).
    """
    data = json.loads(stdout) if stdout.strip() else []
    findings: list[Finding] = []
    for entry in data:
        rule = str(entry.get("ident", "zizmor"))
        for loc in entry.get("locations", []):
            local = loc.get("symbolic", {}).get("key", {}).get("Local")
            if not local:
                continue
            path = local.get("given_path")
            point = loc.get("concrete", {}).get("location", {}).get("start_point", {})
            row = point.get("row")
            if path is None or row is None:
                continue
            findings.append(Finding(rule_id=rule, path=str(path), line=int(row) + 1))
    return findings


def parse_lychee(stdout: str) -> list[Finding]:
    """Parse ``lychee --format json`` output into findings.

    lychee emits a summary object whose ``error_map`` maps each input file to a
    list of failed links; each carries a ``span.line``. With ``--offline`` the
    failures are local/broken links, the same surface ``scan_markdown_links``
    covers. The map key is the path exactly as it was passed to lychee.
    """
    data = json.loads(stdout) if stdout.strip() else {}
    error_map = data.get("error_map") or {}
    findings: list[Finding] = []
    for path, entries in error_map.items():
        for entry in entries:
            line = (entry.get("span") or {}).get("line")
            findings.append(
                Finding(rule_id="broken-link", path=str(path), line=int(line or 0))
            )
    return findings


def parse_betterleaks(stdout: str, repo_root: Path) -> list[Finding]:
    """Parse ``betterleaks -f json`` output into findings (rule/path/line only).

    REDACTION: betterleaks runs with ``--redact=100`` so ``Match``/``Secret``
    are the redacted sentinel, but this parser never reads them regardless --
    it keeps only ``RuleID``, the repo-relative ``File``, and ``StartLine``.
    ``betterleaks`` prints the JSON literal ``null`` (not ``[]``) for a clean
    scan; both mean "no findings".
    """
    data = json.loads(stdout) if stdout.strip() else None
    findings: list[Finding] = []
    for entry in data or []:
        rule = str(entry.get("RuleID", "betterleaks"))
        path = _relativize(str(entry.get("File", "")), repo_root)
        line = int(entry.get("StartLine", 0))
        findings.append(Finding(rule_id=rule, path=path, line=line))
    return findings


def _relativize(path_str: str, repo_root: Path) -> str:
    """Return *path_str* as a repo-relative POSIX path when it is under root."""
    candidate = Path(path_str)
    try:
        return candidate.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()


# ---------------------------------------------------------------------------
# Pure: diff partition and record assembly.
# ---------------------------------------------------------------------------
def diff_findings(
    new_tool: Sequence[Finding], gate: Sequence[Finding]
) -> tuple[set[tuple[str, int]], set[tuple[str, int]], set[tuple[str, int]]]:
    """Partition the two finding lists over ``(path, line)`` locations.

    Returns ``(agree, new_tool_only, existing_gate_only)`` as sets of
    ``(path, line)`` keys. Keying on location (not rule id) is deliberate: the
    two sides use different rule vocabularies, so location coincidence is the
    meaningful overlap signal. The finding *count* a record stores is the number
    of distinct locations, which keeps the schema's partition CHECK exact.
    """
    new_keys = {(f.path, f.line) for f in new_tool}
    gate_keys = {(f.path, f.line) for f in gate}
    return new_keys & gate_keys, new_keys - gate_keys, gate_keys - new_keys


def build_record(
    *,
    pair_name: str,
    new_tool: str,
    existing_gate: str,
    scope_label: str,
    commit_sha: str,
    host_id: str,
    new_findings: Sequence[Finding],
    gate_findings: Sequence[Finding],
    new_duration_ms: float,
    gate_duration_ms: float,
    measured_at_unix_nano: int,
    recorded_at_unix_nano: int,
    notes: str,
) -> dict[str, object]:
    """Assemble one record whose keys are EXACTLY the v3 table columns.

    ``new_tool_findings``/``existing_gate_findings`` are distinct-location
    counts so they satisfy the schema's partition CHECK
    (``findings = agree + that-side-only``).
    """
    agree, new_only, gate_only = diff_findings(new_findings, gate_findings)
    return {
        "pair_name": pair_name,
        "new_tool": new_tool,
        "existing_gate": existing_gate,
        "commit_sha": commit_sha,
        "scope_label": scope_label,
        "measured_at_unix_nano": measured_at_unix_nano,
        "recorded_at_unix_nano": recorded_at_unix_nano,
        "new_tool_findings": len(agree) + len(new_only),
        "existing_gate_findings": len(agree) + len(gate_only),
        "agree_count": len(agree),
        "new_tool_only_count": len(new_only),
        "existing_gate_only_count": len(gate_only),
        "new_tool_duration_ms": round(new_duration_ms, 3),
        "existing_gate_duration_ms": round(gate_duration_ms, 3),
        "resource_attributes": {
            "host.id": host_id,
            "service.name": "claude-md-metrics",
        },
        "notes": notes,
    }


# Exactly the v3 tool_overlap_measurement columns, in schema order. The test
# suite asserts build_record() emits this key set so the JSON stays ingestable.
RECORD_COLUMNS: tuple[str, ...] = (
    "pair_name",
    "new_tool",
    "existing_gate",
    "commit_sha",
    "scope_label",
    "measured_at_unix_nano",
    "recorded_at_unix_nano",
    "new_tool_findings",
    "existing_gate_findings",
    "agree_count",
    "new_tool_only_count",
    "existing_gate_only_count",
    "new_tool_duration_ms",
    "existing_gate_duration_ms",
    "resource_attributes",
    "notes",
)


# ---------------------------------------------------------------------------
# Pure: Markdown rendering. Human-scannable so an anomaly (a side flagging far
# more than the other) is visible without reading prose (CLAUDE.md Section 6).
# ---------------------------------------------------------------------------
def _format_locations(
    keys: Iterable[tuple[str, int]], findings: Sequence[Finding]
) -> list[str]:
    """Render ``path:line (rule)`` lines for the given location keys, sorted."""
    rule_by_key: dict[tuple[str, int], str] = {}
    for f in findings:
        rule_by_key.setdefault((f.path, f.line), f.rule_id)
    return [
        f"{path}:{line} ({rule_by_key.get((path, line), '?')})"
        for path, line in sorted(keys)
    ]


def render_markdown(records: Sequence[dict[str, object]], title: str) -> str:
    """Render the full report: a summary table plus per-pair diff listings."""
    lines = [f"## {title}", ""]
    lines.append(
        "| pair | new tool | gate | new | gate | agree | new-only | gate-only "
        "| new ms | gate ms |"
    )
    lines.append("|---|---|---|--:|--:|--:|--:|--:|--:|--:|")
    for r in records:
        lines.append(
            f"| {r['pair_name']} | {r['new_tool']} | {r['existing_gate']} "
            f"| {r['new_tool_findings']} | {r['existing_gate_findings']} "
            f"| {r['agree_count']} | {r['new_tool_only_count']} "
            f"| {r['existing_gate_only_count']} "
            f"| {r['new_tool_duration_ms']} | {r['existing_gate_duration_ms']} |"
        )
    lines.append("")
    lines.append(
        "Counts are distinct (path, line) locations. agree = both sides flag "
        "the same location; *-only = flagged by exactly one side. Scan the "
        "*-only columns: a persistent gate-only=0 points at REPLACE, "
        "new-only=0 points at DROP, both > 0 points at KEEP both. See "
        "docs/standards/tool-overlap-measurement.md for the decision rule."
    )
    return "\n".join(lines) + "\n"


def render_detail(
    pair_name: str,
    new_only: set[tuple[str, int]],
    gate_only: set[tuple[str, int]],
    new_findings: Sequence[Finding],
    gate_findings: Sequence[Finding],
) -> str:
    """Render the per-pair listing of the two *-only diff sets (capped)."""
    lines = [f"### {pair_name} diff", ""]
    for label, keys, findings in (
        ("new-tool-only", new_only, new_findings),
        ("existing-gate-only", gate_only, gate_findings),
    ):
        listed = _format_locations(keys, findings)
        lines.append(f"- {label} ({len(listed)}):")
        for item in listed[:_MAX_LISTED]:
            lines.append(f"  - {item}")
        if len(listed) > _MAX_LISTED:
            lines.append(f"  - ... and {len(listed) - _MAX_LISTED} more")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Thin IO: existing-gate adapters. These import the bespoke scanners and run
# them in-process, so they are deterministic and unit-tested against tmp dirs.
# Each returns normalized Findings; timing is applied by the caller.
# ---------------------------------------------------------------------------
def collect_workflow_static_gate(repo_root: Path) -> list[Finding]:
    """Union the injection + action-pin gates (zizmor's overlapping surface)."""
    findings: list[Finding] = []
    for v in scan_workflow_injection.find_violations(repo_root / ".github" / "workflows"):
        findings.append(
            Finding(
                rule_id="template-injection",
                path=f".github/workflows/{v.workflow}",
                line=v.line,
            )
        )
    for rel_path, line, _reason in scan_workflow_action_pins.find_violations(repo_root):
        findings.append(
            Finding(rule_id="unpinned-uses", path=rel_path.as_posix(), line=line)
        )
    return findings


def collect_markdown_links_gate(repo_root: Path) -> list[Finding]:
    """Run scan_markdown_links over its DOC_GLOBS file set (lychee's surface)."""
    findings: list[Finding] = []
    for md in scan_markdown_links.iter_markdown_files(repo_root):
        for link in scan_markdown_links.iter_links(md):
            if scan_markdown_links.verify_link(link, repo_root) is not None:
                findings.append(
                    Finding(
                        rule_id="broken-link",
                        path=scan_markdown_links.rel(link.source, repo_root),
                        line=link.line,
                    )
                )
    return findings


def collect_secrets_gate(repo_root: Path) -> list[Finding]:
    """Run scan_secrets over its tracked-file set (betterleaks's surface).

    scan_secrets already returns only ``(path, line, rule_id)``; it never
    surfaces the secret value; so this adapter inherits the redaction.
    """
    return [
        Finding(rule_id=f.rule_id, path=f.path.as_posix(), line=f.line)
        for f in scan_secrets.find_violations(repo_root)
    ]


# ---------------------------------------------------------------------------
# Thin IO: new-tool runners. Each builds an argv (pure helper) and shells out
# via _run. The argv builders are unit-tested; _run is covered by a trivial
# command; the wired runners are exercised live in a web session where the
# binaries exist (the measurement venue), not on the coverage runner.
# ---------------------------------------------------------------------------
class ToolUnavailableError(RuntimeError):
    """Raised when a measured tool binary is not on PATH (fail loud, not fake)."""


def _run(argv: Sequence[str], cwd: Path) -> tuple[str, float]:
    """Run *argv*, returning ``(stdout, duration_ms)``. Raises if it is absent.

    A non-zero exit is NOT an error here: every measured tool uses a non-zero
    exit to mean "findings present", which is normal measurement data. Only a
    missing binary (FileNotFoundError) is fatal; an absent tool must fail
    loud, never be recorded as an empty (zero-finding) result.
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 - argv is built from pinned literals
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ToolUnavailableError(
            f"required tool '{argv[0]}' is not on PATH; cannot measure"
        ) from exc
    duration_ms = (time.monotonic() - start) * 1000.0
    return proc.stdout, duration_ms


def zizmor_argv() -> list[str]:
    """argv for zizmor over the workflows dir (JSON, offline, all severities)."""
    return [
        "zizmor",
        "--format",
        "json",
        "--offline",
        "--no-exit-codes",
        "--min-severity",
        "informational",
        "--min-confidence",
        "low",
        ".github/workflows/",
    ]


def lychee_argv(md_files: Sequence[str]) -> list[str]:
    """argv for lychee over the exact DOC_GLOBS file set (JSON, offline)."""
    return [
        "lychee",
        "--offline",
        "--format",
        "json",
        "--no-progress",
        *md_files,
    ]


def betterleaks_argv() -> list[str]:
    """argv for betterleaks over the working tree (JSON, fully redacted).

    ``dir .`` respects ``.gitignore`` (verified: a 97 MB gitignored ``.venv`` is
    not scanned), so the scope is the tracked + untracked-non-ignored working
    tree; which on a fresh CI checkout is the tracked files. It includes
    Python files, which the gate (``scan_secrets``) delegates to ruff, so
    betterleaks's broader coverage surfaces as new-tool-only evidence rather
    than being hidden. A single positional path is used deliberately: passing
    the tracked files individually makes betterleaks recompile its ruleset per
    path (~0.4s each -> minutes), whereas ``dir .`` scans the tree in ~1s.

    ``--redact=100`` is non-negotiable: it guarantees the matched secret value
    never reaches stdout, the parser, or any artifact (CLAUDE.md Section 4).
    """
    return [
        "betterleaks",
        "dir",
        "--no-banner",
        "--redact=100",
        "-f",
        "json",
        "-r",
        "-",
        ".",
    ]


def run_zizmor(repo_root: Path) -> tuple[list[Finding], float]:
    stdout, ms = _run(zizmor_argv(), repo_root)
    return parse_zizmor(stdout), ms


def run_lychee(repo_root: Path) -> tuple[list[Finding], float]:
    md_files = [
        scan_markdown_links.rel(p, repo_root)
        for p in scan_markdown_links.iter_markdown_files(repo_root)
    ]
    stdout, ms = _run(lychee_argv(md_files), repo_root)
    return parse_lychee(stdout), ms


def run_betterleaks(repo_root: Path) -> tuple[list[Finding], float]:
    stdout, ms = _run(betterleaks_argv(), repo_root)
    return parse_betterleaks(stdout, repo_root), ms


# ---------------------------------------------------------------------------
# Pair registry + orchestration.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PairSpec:
    """Static description of one new-tool <-> existing-gate comparison.

    ``argv_builder`` returns the exact tool argv for a scope root; it powers the
    opt-in ``--smoke`` validation, which re-runs the argv and asserts the tool
    accepted it (non-empty, parseable JSON stdout). It defaults to ``None`` so a
    test fake can omit it; the three wired pairs all set it.
    """

    pair_name: str
    new_tool: str
    existing_gate: str
    scope_label: str
    run_tool: Callable[[Path], tuple[list[Finding], float]]
    collect_gate: Callable[[Path], list[Finding]]
    argv_builder: Callable[[Path], list[str]] | None = None


def _zizmor_smoke_argv(_repo_root: Path) -> list[str]:
    return zizmor_argv()


def _lychee_smoke_argv(repo_root: Path) -> list[str]:
    md_files = [
        scan_markdown_links.rel(p, repo_root)
        for p in scan_markdown_links.iter_markdown_files(repo_root)
    ]
    return lychee_argv(md_files)


def _betterleaks_smoke_argv(_repo_root: Path) -> list[str]:
    return betterleaks_argv()


PAIRS: tuple[PairSpec, ...] = (
    PairSpec(
        pair_name="workflow-static",
        new_tool="zizmor",
        existing_gate="scan_workflow_injection.py + scan_workflow_action_pins.py",
        scope_label=".github/workflows",
        run_tool=run_zizmor,
        collect_gate=collect_workflow_static_gate,
        argv_builder=_zizmor_smoke_argv,
    ),
    PairSpec(
        pair_name="markdown-links",
        new_tool="lychee",
        existing_gate="scan_markdown_links.py",
        scope_label="DOC_GLOBS markdown (offline)",
        run_tool=run_lychee,
        collect_gate=collect_markdown_links_gate,
        argv_builder=_lychee_smoke_argv,
    ),
    PairSpec(
        pair_name="secrets",
        new_tool="betterleaks",
        existing_gate="scan_secrets.py",
        scope_label="working tree, gitignore-respected (betterleaks dir .)",
        run_tool=run_betterleaks,
        collect_gate=collect_secrets_gate,
        argv_builder=_betterleaks_smoke_argv,
    ),
)


def measure_pair(
    spec: PairSpec,
    repo_root: Path,
    *,
    commit_sha: str,
    host_id: str,
    notes: str,
    now_ns: Callable[[], int] = time.time_ns,
) -> tuple[dict[str, object], list[Finding], list[Finding]]:
    """Run one pair and return ``(record, new_findings, gate_findings)``.

    The tool runner and gate collector come from *spec* as callables, so this
    orchestration is unit-tested with fakes (no external binary required).
    """
    new_findings, new_ms = spec.run_tool(repo_root)
    gate_start = time.monotonic()
    gate_findings = spec.collect_gate(repo_root)
    gate_ms = (time.monotonic() - gate_start) * 1000.0
    measured = now_ns()
    record = build_record(
        pair_name=spec.pair_name,
        new_tool=spec.new_tool,
        existing_gate=spec.existing_gate,
        scope_label=spec.scope_label,
        commit_sha=commit_sha,
        host_id=host_id,
        new_findings=new_findings,
        gate_findings=gate_findings,
        new_duration_ms=new_ms,
        gate_duration_ms=gate_ms,
        measured_at_unix_nano=measured,
        recorded_at_unix_nano=measured,
        notes=notes,
    )
    return record, new_findings, gate_findings


# ---------------------------------------------------------------------------
# Opt-in smoke validation (Refs #1632, Fact 1). The measurement collector
# parses leniently; an empty stdout yields zero findings; so a tool that
# REJECTS its argv (e.g. betterleaks's `--no-git` on the `dir` subcommand, which
# printed help to stderr and emitted no JSON) was recorded as a false
# zero-finding result. This smoke step re-runs each tool's argv and asserts the
# tool ACCEPTED it: stdout is non-empty AND parseable JSON. It is opt-in
# (``--smoke``) and binary-aware (an absent binary is "skipped", not "fail"), so
# it runs in the web session / the measurement workflow where the binaries
# exist, and is a no-op on the coverage runner where they are absent.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SmokeResult:
    """Outcome of smoke-checking one pair's tool argv."""

    pair_name: str
    tool: str
    status: str  # "ok" | "fail" | "skipped"
    detail: str


def smoke_pair(
    spec: PairSpec,
    repo_root: Path,
    *,
    run: Callable[[Sequence[str], Path], tuple[str, float]] | None = None,
) -> SmokeResult:
    """Run *spec*'s tool argv and assert it produced parseable JSON.

    Returns a ``SmokeResult``: ``skipped`` when the binary is absent (opt-in:
    the coverage runner has no binaries) or the pair declares no argv builder;
    ``fail``; loud; when the tool produced no stdout (argv rejected) or
    unparseable JSON; ``ok`` otherwise. ``run`` is injected so the check is
    unit-tested without the external binaries; it resolves to :func:`_run` at
    call time (not def time) so a test can monkeypatch the module attribute.
    """
    if run is None:
        run = _run
    if spec.argv_builder is None:
        return SmokeResult(spec.pair_name, spec.new_tool, "skipped", "no argv builder")
    argv = spec.argv_builder(repo_root)
    try:
        stdout, _ms = run(argv, repo_root)
    except ToolUnavailableError as exc:
        return SmokeResult(spec.pair_name, spec.new_tool, "skipped", str(exc))
    if not stdout.strip():
        return SmokeResult(
            spec.pair_name,
            spec.new_tool,
            "fail",
            f"{spec.new_tool} produced no stdout for argv {argv!r}; the tool "
            f"likely rejected a flag (help goes to stderr); a zero-finding "
            f"result here would be a false measurement",
        )
    try:
        json.loads(stdout)
    except json.JSONDecodeError as exc:
        return SmokeResult(
            spec.pair_name,
            spec.new_tool,
            "fail",
            f"{spec.new_tool} stdout for argv {argv!r} is not parseable JSON: {exc}",
        )
    return SmokeResult(
        spec.pair_name,
        spec.new_tool,
        "ok",
        f"{spec.new_tool} accepted its argv and emitted parseable JSON",
    )


def cmd_smoke(specs: Sequence[PairSpec], repo_root: Path) -> int:
    """Smoke-check each pair; print a line per pair; exit 1 iff any failed."""
    failed = False
    for spec in specs:
        result = smoke_pair(spec, repo_root)
        if result.status == "fail":
            failed = True
            print(
                f"::error::smoke {result.pair_name} ({result.tool}): {result.detail}",
                file=sys.stderr,
            )
        else:
            print(f"smoke {result.pair_name} ({result.tool}): {result.status}; {result.detail}")
    return 1 if failed else 0


def _resolve_commit(repo_root: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "unknown"
    sha = out.stdout.strip()
    return sha or "unknown"


def _select_pairs(name: str | None) -> tuple[PairSpec, ...]:
    if name is None:
        return PAIRS
    selected = tuple(p for p in PAIRS if p.pair_name == name)
    if not selected:
        valid = ", ".join(p.pair_name for p in PAIRS)
        raise ValueError(f"unknown pair '{name}'; valid pairs: {valid}")
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-root", default=".", help="Repository root to scan.")
    parser.add_argument("--output", help="Write the JSON record array to this path.")
    parser.add_argument("--report", help="Write the Markdown report here (else stdout).")
    parser.add_argument("--commit", help="Commit sha to stamp on records.")
    parser.add_argument("--host-id", help="Opaque anonymized host.id token.")
    parser.add_argument("--pair", help="Measure only this pair (default: all).")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "Opt-in: instead of measuring, assert each configured tool accepts "
            "its argv and emits parseable JSON (a bad flag fails loud rather "
            "than recording a false zero-finding result). Absent binaries are "
            "skipped, so this is a no-op when the tools are not installed."
        ),
    )
    parser.add_argument(
        "--notes", default="", help="Free-text note stamped on every record."
    )
    parser.add_argument(
        "--title",
        default="Tool overlap measurement",
        help="Markdown report title.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    import os

    args = build_parser().parse_args(argv)
    repo_root = Path(args.scope_root).resolve()
    specs = _select_pairs(args.pair)

    if args.smoke:
        return cmd_smoke(specs, repo_root)

    commit_sha = _resolve_commit(repo_root, args.commit)
    host_id = args.host_id or os.environ.get("CLAUDE_MD_HOST_ID", "unknown")

    records: list[dict[str, object]] = []
    details: list[str] = []
    for spec in specs:
        record, new_findings, gate_findings = measure_pair(
            spec,
            repo_root,
            commit_sha=commit_sha,
            host_id=host_id,
            notes=args.notes,
        )
        records.append(record)
        _agree, new_only, gate_only = diff_findings(new_findings, gate_findings)
        details.append(
            render_detail(spec.pair_name, new_only, gate_only, new_findings, gate_findings)
        )

    report = render_markdown(records, args.title) + "\n" + "\n".join(details)

    if args.output:
        # No sort_keys: keep the schema column order (RECORD_COLUMNS) so the
        # file lines up with the v3 ingest template by inspection.
        Path(args.output).write_text(
            json.dumps(records, indent=2) + "\n", encoding="utf-8"
        )
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
