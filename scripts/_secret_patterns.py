#!/usr/bin/env python3
"""High-confidence hardcoded-secret detection, shared across gates.

This module owns the deterministic, low-false-positive secret patterns and
the line/text scanners that two callers reuse so they cannot drift:

* ``scripts/scan_secrets.py``; the committed-file gate (#1129) that scans
  tracked non-Python files at CI / pre-commit time.
* ``scripts/preflight_github_secrets.py``; the PreToolUse gate (#1388)
  that blocks a secret from leaving the trust boundary through a
  ``mcp__github__*`` write tool body before the API call is made.

Design choices (CLAUDE.md S4: minimal, fail loud, never echo secrets):

* Only high-confidence rules are used (vendor-prefixed tokens, PEM private
  keys, and a guarded generic ``key = "value"`` rule). The generic rule
  ignores interpolations (``${{ ... }}``, ``$VAR``), template/placeholder
  values, and low-entropy values to avoid noise.
* Matched secret values are NEVER returned to callers; the scanners hand
  back only the rule id (and, for :func:`scan_text`, the line number), so a
  caller can safely surface the result in CI logs, PR comments, and
  terminals.

Refs #1129 (origin), #1388 (extraction + PreToolUse reuse).
Tested by ``tests/test_scan_secrets.py`` and
``tests/test_preflight_github_secrets.py``.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# Inline marker (detect-secrets convention) that exempts a single line.
PRAGMA_ALLOWLIST = "pragma: allowlist secret"


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
    return None. The matched value itself is never returned.
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
