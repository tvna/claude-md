"""Shared allowlist of bot author logins trusted by harness gates.

Single source of truth for ``_TRUSTED_BOT_LOGINS`` so that ``scan_non_ascii``
(issue #137) and ``issue_link`` (issue #139) agree byte-for-byte on which
bot authors get carve-outs from harness gates. The non-goal stated in
umbrella issue #136 was duplication of the bot login between scripts; this
module exists to prevent that drift.

Exact-match only; no wildcards. Extend deliberately, one entry at a time.
"""

from __future__ import annotations

_TRUSTED_BOT_LOGINS: frozenset[str] = frozenset({"dependabot[bot]"})
