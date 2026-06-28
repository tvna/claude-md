#!/usr/bin/env python3
"""Verify APM agent-rule artifacts do not contain repo-local references.

Issue #230 retrospective for PR #229: repo-local script and metadata
references leaked into the compiled ``CLAUDE.md`` / ``AGENTS.md``, which
are intended to be referenced standalone from downstream projects. This
script is the deterministic gate the PR #229 repair loop identified as
missing.

Invoked from ``.github/workflows/portable-pr-policy.yml`` as
``python3 scripts/scan_apm_portability.py verify --path <file> ...``.

The contract is:

* Each ``--path`` is a file to scan. Typical inputs are
  ``.apm/instructions/master.instructions.md``, ``CLAUDE.md``, and
  ``AGENTS.md`` (defense in depth: scan source and both compiled
  outputs).
* Each line is scanned for three violation classes:

  - **Pattern A**; forbidden literal substrings in
    :data:`FORBIDDEN_TOKENS` (case-sensitive). Concrete repo-local
    identifiers such as ``scripts/``, ``CODEOWNERS``, ``mcp__github__``.
    Introduced by #230 for PR #229.
  - **Pattern B**; assertive-existence phrasing matched by
    :data:`FORBIDDEN_PHRASE_PATTERNS` (case-insensitive). Sentences that
    assert a specific downstream artifact (runbook, doc, checklist,
    script, file, guide, spec, note) exists, without naming a concrete
    repo-local identifier the Pattern A layer would have caught.
    Introduced by #535 after the #530 -> #533 regression where
    Chapter 3 was repaired twice for the same defect at different
    abstraction levels.
  - **Pattern C**; harness-specific tool names in
    :data:`FORBIDDEN_HARNESS_TOOLS` (case-sensitive). Concrete
    Claude-only tool identifiers such as ``AskUserQuestion`` or
    ``ExitPlanMode`` that have no meaning to other harnesses (Codex /
    Devin read ``AGENTS.md`` and have no such tool), so naming one in
    the universal text breaks portability the same way a repo-local
    reference does. Introduced by #1048 after the #1044 retrospective:
    "approach A" named ``AskUserQuestion`` in the universal text, passed
    Pattern A/B, and was caught only by owner review. Claude-only hook
    scripts and settings may name these tools freely; this layer scans
    only the universal/compiled artifacts.

* Lines containing :data:`ACK_MARKER` are skipped for all layers. This
  mirrors the ``ACK_MARKER`` escape hatch in
  ``scripts/scan_non_ascii.py`` for the rare case a normative downstream
  rule must reference a repo-local artifact by name or by assertive
  phrase.
* Exit 0 when every scanned file is clean; exit 1 on any violation; the
  argparse layer returns 2 when no ``--path`` was supplied. Each hit
  emits ``::error file=<path>,line=<n>::...`` on stderr so the GitHub
  Actions UI surfaces individual violations. Each pattern class
  identifies itself in the error message so the operator knows which
  layer fired.

Tested by ``tests/test_scan_apm_portability.py``. Refs #230, #535, #1048.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path

# Lines containing this marker bypass the scan. Mirrors the precedent
# set by ``scripts/scan_non_ascii.py`` ACK_MARKER.
ACK_MARKER = "<!-- portability-ack -->"

# Literal substrings forbidden in scanned files. Each is chosen to avoid
# benign English words: ``scripts/`` requires the trailing slash so the
# word "scripted" does not match; ``.github/`` requires the trailing
# slash so ``github.com`` URLs do not match.
FORBIDDEN_TOKENS: tuple[str, ...] = (
    "scripts/",
    ".github/",
    "CODEOWNERS",
    "mcp__github__",
    "plan_language_context.py",
    "preflight_non_ascii.py",
    "owners.yaml",
)

# Phrase prefix used in error output and in :func:`scan_line` return
# values to distinguish Pattern B hits from Pattern A tokens. Callers
# split on this prefix when they need to format Pattern A vs B
# differently; otherwise the hit is treated as an opaque string just
# like a Pattern A token.
PHRASE_HIT_PREFIX = "phrase:"

# Prefix marking Pattern C (harness-specific tool name) hits, mirroring
# :data:`PHRASE_HIT_PREFIX`. The bare tool name follows the prefix so
# callers recover it by stripping the prefix.
HARNESS_HIT_PREFIX = "harness:"

# Harness-specific tool identifiers forbidden in the universal artifacts.
# Case-sensitive CamelCase identifiers, matched as literal substrings
# like :data:`FORBIDDEN_TOKENS`. ``EnterPlanMode`` is the documented
# companion to ``ExitPlanMode``; both are included so either spelling is
# caught.
FORBIDDEN_HARNESS_TOOLS: tuple[str, ...] = (
    "AskUserQuestion",
    "ExitPlanMode",
    "EnterPlanMode",
)

# Curated artifact nouns whose "existence assertion" in
# ``.apm/instructions/**`` / ``CLAUDE.md`` / ``AGENTS.md`` reads as a
# repo-local pointer once the file lands in a downstream consumer. Kept
# narrow on purpose: each entry must be a thing a downstream consumer is
# not guaranteed to ship. Generic nouns (e.g. "process", "policy",
# "rule") are intentionally excluded to keep false positives low.
_ARTIFACT_NOUN = r"runbook|doc(?:ument(?:ation)?)?|checklist|script|file|" r"guide|spec|note"

# Optional qualifier that narrows the assertion to a specific instance.
# All qualifiers are pure adjectives so the regex stays anchored to an
# artifact noun and does not match generic English (e.g. "live in CI"
# has no qualifier-noun pair).
_QUALIFIER = r"dedicated|local|repo[- ]local|specific|separate|companion|sibling"

# Regex patterns matching Pattern B (assertive-existence phrasing).
# Each pattern fires only when an article + (optional qualifier) +
# artifact noun appear together, which keeps the gate from tripping on
# benign English that happens to share a verb. Calibrated against the
# current ``main`` corpus (commit 4fb94f9): zero hits.
FORBIDDEN_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "lives in a dedicated runbook", "is documented in the companion
    # script", "are defined in a separate guide", etc.
    re.compile(
        r"\b(?:lives?|are\s+documented|is\s+documented|is\s+described|"
        r"is\s+defined|are\s+defined)\s+(?:in|at)\s+"
        r"(?:a|an|the)\s+(?:(?:" + _QUALIFIER + r")\s+)?"
        r"(?:" + _ARTIFACT_NOUN + r")s?\b",
        re.IGNORECASE,
    ),
    # "see the dedicated runbook", "refer to a companion script",
    # "consult the local checklist", etc.
    re.compile(
        r"\b(?:see|refer\s+to|consult)\s+"
        r"(?:a|an|the)\s+(?:(?:" + _QUALIFIER + r")\s+)?"
        r"(?:" + _ARTIFACT_NOUN + r")s?\b",
        re.IGNORECASE,
    ),
)


def scan_line(line: str) -> list[str]:
    """Return the forbidden tokens and phrases present in *line*.

    Pattern A hits are returned as the matching literal token from
    :data:`FORBIDDEN_TOKENS`. Pattern B hits are returned as
    ``f"{PHRASE_HIT_PREFIX}{matched-snippet}"`` and Pattern C hits as
    ``f"{HARNESS_HIT_PREFIX}{tool-name}"`` so callers can tell the
    layers apart without a second pass.

    Lines carrying :data:`ACK_MARKER` are treated as explicitly allowed
    and return an empty list.
    """
    if ACK_MARKER in line:
        return []
    hits: list[str] = [token for token in FORBIDDEN_TOKENS if token in line]
    for pattern in FORBIDDEN_PHRASE_PATTERNS:
        match = pattern.search(line)
        if match is not None:
            hits.append(f"{PHRASE_HIT_PREFIX}{match.group(0)}")
    hits.extend(f"{HARNESS_HIT_PREFIX}{tool}" for tool in FORBIDDEN_HARNESS_TOOLS if tool in line)
    return hits


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, token)`` for every violation in *text*.

    Line numbers are 1-based to match GitHub Actions ``::error file=``
    annotations.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for token in scan_line(line):
            hits.append((lineno, token))
    return hits


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Return ``(line_number, token)`` for every violation in *path*."""
    return scan_text(path.read_text(encoding="utf-8"))


def _verify(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        if not path.exists():
            print(
                f"::error::missing scan target: {path}",
                file=sys.stderr,
            )
            total += 1
            continue
        for lineno, hit in scan_file(path):
            if hit.startswith(PHRASE_HIT_PREFIX):
                snippet = hit[len(PHRASE_HIT_PREFIX) :]
                kind = "assertive-existence phrase"
                payload = repr(snippet)
            elif hit.startswith(HARNESS_HIT_PREFIX):
                snippet = hit[len(HARNESS_HIT_PREFIX) :]
                kind = "harness-specific tool name"
                payload = repr(snippet)
            else:
                kind = "forbidden repo-local reference"
                payload = repr(hit)
            print(
                f"::error file={path},line={lineno}::"
                f"{kind} {payload} in APM artifact "
                f"(append '{ACK_MARKER}' to this line if the "
                f"reference is intentional and downstream-safe).",
                file=sys.stderr,
            )
            total += 1
    if total:
        print(
            f"FAIL: {total} portability violation(s).",
            file=sys.stderr,
        )
        return 1
    print("OK: no repo-local references in scanned APM artifacts.")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    if not args.path:
        print(
            "error: at least one --path is required",
            file=sys.stderr,
        )
        return 2
    paths = [Path(p) for p in args.path]
    return _verify(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Scan files for forbidden repo-local references.",
    )
    p_verify.add_argument(
        "--path",
        action="append",
        default=[],
        help=(
            "Path to a file to scan. Repeatable; supply once per file. "
            "Typical inputs are .apm/instructions/master.instructions.md, "
            "CLAUDE.md, AGENTS.md."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
