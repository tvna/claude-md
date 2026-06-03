#!/usr/bin/env python3
"""Scan tracked non-Python files for high-confidence hardcoded secrets.

Refs #1129. ruff's flake8-bandit ``S`` family (S105/S106/S107) already
flags hardcoded secrets in ``*.py`` at CI. The coverage gap is every other
tracked file: JSON, YAML, shell, TOML, Markdown, and workflow YAML, where
a pasted token, key, or password is never linted. This gate closes that
gap with a small set of high-confidence, low-false-positive patterns,
mirroring the deterministic-detector layer of the upstream
security-guidance plugin without importing any LLM/agent runtime.

Design choices (CLAUDE.md S4: minimal, fail loud, never echo secrets):

* ``*.py`` is excluded -- ruff already owns it, and scanning it would
  double-flag and trip on the patterns embedded in this scanner's own
  tests.
* Only high-confidence rules are used (vendor-prefixed tokens, PEM private
  keys, and a guarded generic ``key = "value"`` rule). The generic rule
  ignores interpolations (``${{ ... }}``, ``$VAR``), template/placeholder
  values, and low-entropy values to avoid config-file noise.
* Matched secret values are NEVER printed -- only the rule id, file, and
  line are reported, so the gate output is safe to surface in CI logs,
  PR comments, and terminals.

Escape hatches:

* Inline: append ``pragma: allowlist secret`` to a line (the
  detect-secrets convention) to mark a reviewed non-secret.
* Path: add a tracked path to :data:`ALLOWLIST_PATHS` with a rationale
  when a whole file is a known non-secret fixture. The list may only
  shrink (ratchet); adding a real secret here is a review-blocking defect.

CLI::

    python3 scripts/scan_secrets.py verify  # exit 1 on findings
    python3 scripts/scan_secrets.py list     # print rule/file/line (no values)

Exit codes:
    0  verify passed (no findings) or list completed
    1  verify found a potential hardcoded secret
    2  usage error

Tested by ``tests/test_scan_secrets.py``.

Contract:
    Inputs: the set of git-tracked files under *repo_root* (discovered via
        ``git ls-files``); no stdin, no environment input.
    Outputs: ``::error file=...,line=...::`` annotations on stderr naming
        only the rule id (never the secret value), plus a one-line
        summary; exit code as documented above.
    Failure policy: loud -- a file that cannot be decoded as UTF-8 text is
        skipped, but any detected secret fails the gate with a non-zero
        exit rather than passing silently.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

from _git import run_git

REPO_ROOT = Path(__file__).resolve().parent.parent

# Inline marker (detect-secrets convention) that exempts a single line.
PRAGMA_ALLOWLIST = "pragma: allowlist secret"

# Whole-file exemptions for known non-secret fixtures. Each entry should
# carry a one-line rationale in the comment. Ratchet: shrink only.
ALLOWLIST_PATHS: frozenset[str] = frozenset()

# Files/extensions that are not text-secret carriers or are owned by
# another gate. ``*.py`` is owned by ruff's S family (see module docstring).
_SKIP_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".lock",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf",
        ".zip", ".gz", ".tar", ".whl", ".so", ".bin",
        ".woff", ".woff2", ".ttf", ".eot",
    }
)
# Lock/checksum files: high-entropy hashes, never secret-key assignments.
_SKIP_NAMES: frozenset[str] = frozenset(
    {"uv.lock", "flake.lock", "apm.lock.yaml", "CHECKSUMS"}
)


class _Rule(NamedTuple):
    rule_id: str
    pattern: re.Pattern[str]
    # When set, the capture group whose value must pass the generic guards.
    value_group: int | None = None


# Vendor-prefixed tokens and PEM headers are specific enough to flag on
# sight. The generic rule defers to :func:`_looks_like_secret_value`.
_RULES: tuple[_Rule, ...] = (
    _Rule("github-token", re.compile(r"\bgh[posru]_[A-Za-z0-9]{36,}\b")),
    _Rule("github-fine-grained-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    _Rule("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    _Rule("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    _Rule("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    _Rule(
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    _Rule(
        "generic-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|"
            r"client[_-]?secret|access[_-]?key|auth[_-]?token)\b"
            r"\s*[:=]\s*['\"]([^'\"]{12,})['\"]"
        ),
        value_group=1,
    ),
)

# Substrings that mark a value as a placeholder / interpolation, never a
# real literal secret.
_PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "${", "{{", "}}", "<", ">", "%(", "...", "***",
    "example", "dummy", "placeholder", "changeme", "change-me",
    "your_", "your-", "xxxx", "redacted", "sample", "fixture",
    "fake", "test", "todo", "none", "null",
)


def _looks_like_secret_value(value: str) -> bool:
    """Return True if *value* is a plausible literal secret (generic rule).

    Rejects interpolations and obvious placeholders, and requires a minimum
    length plus a digit+letter mix so dictionary words and config flags do
    not trip the generic rule.
    """
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return False
    if len(value) < 16:
        return False
    has_digit = any(c.isdigit() for c in value)
    has_alpha = any(c.isalpha() for c in value)
    return has_digit and has_alpha


def scan_line(line: str) -> str | None:
    """Return the rule id of the first secret match in *line*, else None.

    Lines carrying :data:`PRAGMA_ALLOWLIST` are treated as reviewed and
    return None.
    """
    if PRAGMA_ALLOWLIST in line:
        return None
    for rule in _RULES:
        match = rule.pattern.search(line)
        if match is None:
            continue
        if rule.value_group is not None:
            value = match.group(rule.value_group)
            if not _looks_like_secret_value(value):
                continue
        return rule.rule_id
    return None


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, rule_id)`` for each secret in *text* (1-based)."""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        rule_id = scan_line(line)
        if rule_id is not None:
            hits.append((lineno, rule_id))
    return hits


def _is_skipped(rel_posix: str) -> bool:
    if rel_posix in ALLOWLIST_PATHS:
        return True
    name = rel_posix.rsplit("/", 1)[-1]
    if name in _SKIP_NAMES:
        return True
    suffix = "" if "." not in name else "." + name.rsplit(".", 1)[-1].lower()
    return suffix in _SKIP_SUFFIXES


def iter_tracked_files(repo_root: Path) -> Iterator[Path]:
    """Yield absolute paths of git-tracked, in-scope files under *repo_root*."""
    result = run_git(["ls-files", "-z"], cwd=repo_root)
    for rel in result.stdout.split("\0"):
        if not rel or _is_skipped(rel):
            continue
        yield repo_root / rel


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


class Finding(NamedTuple):
    path: Path  # repo-relative
    line: int
    rule_id: str


def find_violations(
    repo_root: Path = REPO_ROOT,
    paths: Iterable[Path] | None = None,
) -> list[Finding]:
    """Return a Finding for every secret in the tracked, in-scope files.

    When *paths* is None the file set is discovered via ``git ls-files``;
    callers (and tests) may pass an explicit iterable of absolute paths.
    """
    if paths is None:
        paths = iter_tracked_files(repo_root)
    findings: list[Finding] = []
    for path in paths:
        text = _read_text(path)
        if text is None:
            continue
        rel = path.relative_to(repo_root)
        for lineno, rule_id in scan_text(text):
            findings.append(Finding(path=rel, line=lineno, rule_id=rule_id))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan tracked non-Python files for hardcoded secrets.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="Exit 1 if any potential secret is found")
    sub.add_parser("list", help="Print rule/file/line for every match (no values)")
    args = parser.parse_args(argv)

    findings = find_violations(REPO_ROOT)

    if args.cmd == "list":
        for f in findings:
            print(f"{f.path.as_posix()}:{f.line} ({f.rule_id})")
        return 0

    if not findings:
        print("OK: no hardcoded secrets in tracked non-Python files.")
        return 0

    for f in findings:
        print(
            f"::error file={f.path.as_posix()},line={f.line}::"
            f"potential hardcoded secret (rule: {f.rule_id}); remove it and "
            f"route the value through a secret store. If this is a non-secret "
            f"placeholder, append '{PRAGMA_ALLOWLIST}' to the line or extend "
            f"ALLOWLIST_PATHS in scripts/scan_secrets.py with a rationale.",
            file=sys.stderr,
        )
    print(
        f"FAIL: {len(findings)} potential hardcoded secret(s) in tracked files.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
