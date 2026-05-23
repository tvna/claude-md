#!/usr/bin/env python3
"""Claude Code PreToolUse hook: advise when a PR body uses only `Refs`.

Bound in `.claude/settings.json` to
``mcp__github__(create_pull_request|update_pull_request)``. Reads the
tool-input JSON from stdin, classifies the PR body's issue references,
and emits a non-blocking ``ADVISORY:`` line to stderr when the body uses
only the non-closing ``Refs`` keyword.

Always exits 0 (advisory, never blocks the tool call). The repository-side
gate at ``scripts/issue_link.py`` is the enforcing layer (per #216 PR-A);
this hook surfaces the warning in the Claude Code transcript before the
API call so the operator can correct the body without round-tripping
through CI. Tested by ``tests/test_pr_body_close_keyword_advisory.py``.

Per #216 PR-C. Intentionally self-contained (no import from
``scripts/issue_link.py``) so the three child PRs of #216 stay
mergeable in any order. Slight regex duplication is the cost.
"""

from __future__ import annotations

import json
import re
import sys

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_REF_LINE = re.compile(
    r"^[ \t]*(Refs|Closes|Fixes|Resolves)[ \t]+#(\d+)",
    re.IGNORECASE | re.MULTILINE,
)
_PARTIAL_MARKER_RE = re.compile(r"<!--\s*partial\s*-->", re.IGNORECASE)
_CLOSING_KEYWORDS = frozenset({"closes", "fixes", "resolves"})


def build_advisory(body: str) -> str | None:
    """Return an advisory string for *body*, or None if no advisory is needed.

    Returns None when:
    * the body has a literal ``<!-- partial -->`` opt-out marker, or
    * the body contains no recognized references, or
    * at least one reference uses a closing keyword.
    """
    if _PARTIAL_MARKER_RE.search(body):
        return None
    cleaned = _HTML_COMMENT.sub("", body)
    matches = list(_REF_LINE.finditer(cleaned))
    if not matches:
        return None
    keywords = {m.group(1).lower() for m in matches}
    if keywords & _CLOSING_KEYWORDS:
        return None
    numbers = sorted({int(m.group(2)) for m in matches})
    joined = ", ".join(f"#{n}" for n in numbers)
    return (
        f"ADVISORY: PR body uses only 'Refs' for {joined}. "
        "If this PR fully resolves the linked issue, replace 'Refs' with "
        "'Closes', 'Fixes', or 'Resolves' so GitHub auto-closes it on merge. "
        "If this is partial work, ignore (or add '<!-- partial -->' to the "
        "body to suppress this advisory and the Verify issue link gate). "
        "See #216."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    body = tool_input.get("body")
    if not isinstance(body, str):
        return 0
    advisory = build_advisory(body)
    if advisory is not None:
        print(advisory, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
