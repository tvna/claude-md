"""Shared regexes and helpers for issue-reference classification.

Single source of truth consumed by both the server-side gate
(``scripts/issue_link.py``, the ``verify-issue-link.yml`` workflow body)
and the client-side PreToolUse hook
(``scripts/pr_body_close_keyword_gate.py``). Centralizing them here
prevents the two layers from drifting -- which was the failure mode the
old self-contained advisory hook encoded as a known cost (PR #220,
issue #222).

Public surface (kept narrow so callers can re-export under their own
module-private names without leaking implementation details):

* :data:`HTML_COMMENT_RE`, :data:`REF_LINE_KEYWORD_RE`,
  :data:`PARTIAL_MARKER_RE` -- compiled regexes.
* :data:`CLOSING_KEYWORDS` -- frozenset of auto-closing GitHub
  keywords (lowercase).
* :data:`TRACKING_LABEL` -- the carve-out label name.
* :func:`strip_html_comments`, :func:`classify_refs`,
  :func:`body_has_partial_marker` -- pure parsers.
* :func:`format_no_closing_keyword_msg` -- shared deny/error text;
  callers pass ``prefix="::error::"`` for GitHub Actions annotations
  and ``prefix=""`` for the Claude Code transcript.
"""

from __future__ import annotations

import re


HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

REF_LINE_KEYWORD_RE = re.compile(
    r"^[ \t]*(Refs|Closes|Fixes|Resolves)[ \t]+#(\d+)",
    re.IGNORECASE | re.MULTILINE,
)

PARTIAL_MARKER_RE = re.compile(r"<!--\s*partial\s*-->", re.IGNORECASE)

CLOSING_KEYWORDS = frozenset({"closes", "fixes", "resolves"})

TRACKING_LABEL = "type:tracking"


def strip_html_comments(body: str) -> str:
    return HTML_COMMENT_RE.sub("", body)


def classify_refs(body: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for m in REF_LINE_KEYWORD_RE.finditer(body):
        key = (m.group(1).lower(), int(m.group(2)))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def body_has_partial_marker(raw_body: str) -> bool:
    return PARTIAL_MARKER_RE.search(raw_body) is not None


def format_no_closing_keyword_msg(
    numbers: list[int],
    *,
    prefix: str = "",
) -> str:
    """Render the Refs-only-without-tracking failure text.

    ``prefix`` is the GitHub Actions annotation prefix on the
    server-side path (``"::error::"``) and empty on the client-side
    PreToolUse path -- the hook output is already wrapped in a
    ``permissionDecisionReason`` field, so a stray ``::error::`` would
    confuse readers of the Claude Code transcript.
    """
    joined = ", ".join(f"#{n}" for n in numbers)
    return (
        f"{prefix}PR body uses only 'Refs' for {joined}, but none of "
        f"those issues carry the '{TRACKING_LABEL}' label and the body "
        "lacks a '<!-- partial -->' opt-out marker. If this PR fully "
        "resolves the issue, replace 'Refs' with 'Closes', 'Fixes', or "
        "'Resolves' so GitHub auto-closes it on merge. If this is "
        "partial work against a non-umbrella issue, add a literal "
        "'<!-- partial -->' line to the body. See #216."
    )
