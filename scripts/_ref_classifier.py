"""Shared regexes and helpers for issue-reference classification.

Single source of truth consumed by both the server-side gate
(``scripts/issue_link.py``, the ``verify-issue-link.yml`` workflow body)
and the client-side PreToolUse hook
(``scripts/pr_body_close_keyword_gate.py``). Centralizing them here
prevents the two layers from drifting; which was the failure mode the
old self-contained advisory hook encoded as a known cost (PR #220,
issue #222).

The partial-work opt-out has two interchangeable spellings. The legacy
form is the HTML comment ``<!-- partial -->`` (per #216). The GitHub MCP
``create_pull_request`` / ``update_pull_request`` tools strip HTML
comments from the stored body, so an agent that writes PR bodies through
those tools cannot reach the legacy marker (#1035). For that path a
plain-text sentinel line ``partial-pr`` is accepted as well; it survives
the MCP write path because it contains no HTML comment delimiters, no
``->`` arrow sequence, and no double quote (the three constructs the MCP
layer rewrites). :func:`body_has_partial_marker` accepts either form.

Public surface (kept narrow so callers can re-export under their own
module-private names without leaking implementation details):

* :data:`HTML_COMMENT_RE`, :data:`REF_LINE_KEYWORD_RE`,
  :data:`PARTIAL_MARKER_RE`, :data:`PARTIAL_MARKER_PLAINTEXT_RE` --
  compiled regexes.
* :data:`CLOSING_KEYWORDS`; frozenset of auto-closing GitHub
  keywords (lowercase).
* :data:`TRACKING_LABEL`; the carve-out label name.
* :func:`strip_html_comments`, :func:`classify_refs`,
  :func:`body_has_partial_marker`; pure parsers.
* :func:`format_no_closing_keyword_msg`; shared deny/error text;
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

# MCP-safe plain-text spelling of the partial-work opt-out (#1035). A
# line that, after optional indentation, begins with the word
# ``partial-pr`` (case-insensitive) opts the PR out of the
# closing-keyword gate. ``\b`` after ``pr`` keeps ``partial-prefix`` and
# similar words from matching while still accepting a trailing reason
# such as ``partial-pr: first of two stacked PRs``. Line-anchored so a
# mid-sentence mention in prose does not trip the opt-out.
PARTIAL_MARKER_PLAINTEXT_RE = re.compile(
    r"^[ \t]*partial-pr\b",
    re.IGNORECASE | re.MULTILINE,
)

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
    """True if *raw_body* carries either partial-work opt-out spelling.

    Accepts the legacy ``<!-- partial -->`` HTML comment (#216) or the
    MCP-safe plain-text ``partial-pr`` line (#1035). Checked against the
    raw body BEFORE HTML comments are stripped, because the legacy form
    is itself a comment.
    """
    return (
        PARTIAL_MARKER_RE.search(raw_body) is not None
        or PARTIAL_MARKER_PLAINTEXT_RE.search(raw_body) is not None
    )


def format_no_closing_keyword_msg(
    numbers: list[int],
    *,
    prefix: str = "",
) -> str:
    """Render the Refs-only-without-tracking failure text.

    ``prefix`` is the GitHub Actions annotation prefix on the
    server-side path (``"::error::"``) and empty on the client-side
    PreToolUse path; the hook output is already wrapped in a
    ``permissionDecisionReason`` field, so a stray ``::error::`` would
    confuse readers of the Claude Code transcript.
    """
    joined = ", ".join(f"#{n}" for n in numbers)
    return (
        f"{prefix}PR body uses only 'Refs' for {joined}, but none of "
        f"those issues carry the '{TRACKING_LABEL}' label and the body "
        "lacks a partial-work opt-out marker. If this PR fully "
        "resolves the issue, replace 'Refs' with 'Closes', 'Fixes', or "
        "'Resolves' so GitHub auto-closes it on merge. If this is "
        "partial work against a non-umbrella issue, add a literal "
        "'<!-- partial -->' line to the body, or a plain-text "
        "'partial-pr' line when authoring through the GitHub MCP tools "
        "(which strip HTML comments). See #216."
    )
