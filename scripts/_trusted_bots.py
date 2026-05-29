"""Shared allowlist of bot author logins trusted by harness gates.

Single source of truth loaded from ``.github/trusted_bots.toml`` so that
``scan_non_ascii`` (issue #137) and ``issue_link`` (issue #139) agree
byte-for-byte on which bot authors get carve-outs from harness gates.
The non-goal stated in umbrella issue #136 was duplication of the bot
login between scripts; this module prevents that drift.

Two exported sets:
- ``_TRUSTED_BOT_LOGINS``: shared across issue-link, body-policy, and
  non-ASCII scanner (advisory demotion).
- ``_NON_ASCII_SKIP_LOGINS``: non-ASCII scan only; bots whose generated
  content with non-ASCII is fully exempt (action = "none").

Exact-match only; no wildcards. Extend deliberately via the TOML file.

Fails open: if the TOML cannot be read or parsed, falls back to the
hardcoded defaults below and logs ``::warning::`` to stderr. A loader bug
must not block harness gates.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOML_PATH = Path(__file__).resolve().parent.parent / ".github" / "trusted_bots.toml"

# Hardcoded fallback values (used only when the TOML file is missing/unreadable).
_DEFAULT_GENERAL: frozenset[str] = frozenset({"dependabot[bot]"})
_DEFAULT_NON_ASCII_SKIP: frozenset[str] = frozenset({
    "codecov", "codecov[bot]", "devin-ai-integration[bot]", "devin[bot]"
})


def _load() -> tuple[frozenset[str], frozenset[str]]:
    try:
        text = _TOML_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"::warning::_trusted_bots: cannot read {_TOML_PATH}: {exc}; "
            "using hardcoded defaults",
            file=sys.stderr,
        )
        return _DEFAULT_GENERAL, _DEFAULT_NON_ASCII_SKIP

    try:
        import tomllib
        data = tomllib.loads(text)
    except Exception as exc:
        print(
            f"::warning::_trusted_bots: cannot parse {_TOML_PATH}: {exc}; "
            "using hardcoded defaults",
            file=sys.stderr,
        )
        return _DEFAULT_GENERAL, _DEFAULT_NON_ASCII_SKIP

    general = frozenset(
        login
        for login in data.get("general", {}).get("logins", [])
        if isinstance(login, str)
    )
    non_ascii_skip = frozenset(
        login
        for login in data.get("non_ascii_skip", {}).get("logins", [])
        if isinstance(login, str)
    )
    return general or _DEFAULT_GENERAL, non_ascii_skip or _DEFAULT_NON_ASCII_SKIP


_TRUSTED_BOT_LOGINS, _NON_ASCII_SKIP_LOGINS = _load()
