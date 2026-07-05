#!/usr/bin/env python3
"""CI gate: reject drift between the issue-triage runbook routing table and the registry.

Phase 3 of the gitapex SSoT migration (docs/prd/gitapex-ssot-gate-registry.md):
``.gitapex/ssot.json`` ``label_routing.rules`` is the executable single source
for agent routing decisions, and ``docs/runbooks/issue-triage.md``'s "Agent
routing" Markdown table is its human-readable projection. Nothing previously
enforced that an edit to one side is mirrored in the other, so the two could
silently diverge (the exact drift class #1041 and the SSoT migration exist to
close). This gate parses both sides into one canonical ordered representation
and rejects any mismatch, in either direction: an edit to the table without a
matching registry edit fails just as loudly as the reverse.

Canonical rule shape
---------------------
Each row/rule normalizes to a dict with:

- exactly one of ``if_any`` / ``if_all`` (+ optional ``if_none``), or
  ``default: True`` for the catch-all last row;
- ``action``: one of ``no-action``, ``no-action-umbrella``, ``investigate``,
  ``auto-fix-candidate``, ``triage-needed``;
- ``autonomous_pr``: ``True`` for ``auto-fix-candidate``, ``False`` for
  ``investigate``, absent for every other action (derived from the action
  itself, since neither side spells it out on every row);
- ``body_read``: ``"no"``, ``"yes"``, or ``"title-only"``.

Contract:
- Inputs: the ``verify`` subcommand; ``--runbook`` (default
  ``docs/runbooks/issue-triage.md``); ``--registry`` (default
  ``.gitapex/ssot.json``, read through ``scripts/_ssot.py``).
- Outputs: an ``::error::`` annotation on stderr naming the first divergent
  rule; an ``OK:`` line on success.
- Failure policy: fails loud (exit 1) per CLAUDE.md section 4; exit 64 on an
  unrecognised subcommand.

Tested by ``tests/test_scan_routing_table_drift.py``. Refs #2300, #2298, #2246.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import _ssot

_SCRIPT = "scan_routing_table_drift"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNBOOK_PATH = "docs/runbooks/issue-triage.md"

_SECTION_HEADING = "## Agent routing"
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")

# The literal condition-cell marker for the catch-all last row: "type:*" is not
# a concrete family:name label, it is the runbook's way of saying "no type:*
# label has been applied yet", so it maps to the registry's `default` rule.
_WILDCARD_TYPE_MARKER = "type:*"

_ACTION_PREFIXES: tuple[tuple[str, dict[str, object]], ...] = (
    ("no-action on umbrella", {"action": "no-action-umbrella"}),
    ("no-action", {"action": "no-action"}),
    ("investigate", {"action": "investigate", "autonomous_pr": False}),
    ("auto-fix candidate", {"action": "auto-fix-candidate", "autonomous_pr": True}),
    ("triage-needed", {"action": "triage-needed"}),
)

_BODY_READ_VALUES: dict[str, str] = {
    "no": "no",
    "yes": "yes",
    "title only": "title-only",
    "title-only": "title-only",
}


class TableParseError(Exception):
    """Raised when the runbook's Agent routing table cannot be parsed."""


# ---------------------------------------------------------------------------
# Runbook table parsing (pure over already-read text)
# ---------------------------------------------------------------------------


def extract_table_lines(runbook_text: str) -> list[str]:
    """Return the raw ``| ... |`` data-row lines of the "Agent routing" table.

    Raises :class:`TableParseError` when the section heading or its table
    header/separator cannot be found: a malformed runbook must fail loud
    rather than silently comparing against an empty rule list.
    """
    lines = runbook_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == _SECTION_HEADING)
    except StopIteration as exc:
        raise TableParseError(f"no {_SECTION_HEADING!r} heading found") from exc

    body = lines[start + 1 :]
    try:
        header_idx = next(i for i, line in enumerate(body) if _TABLE_ROW_RE.match(line) and "Condition" in line)
    except StopIteration as exc:
        raise TableParseError("no table header row found under the Agent routing heading") from exc

    data_start = header_idx + 2  # skip the header row and the |---|---| separator
    rows: list[str] = []
    for line in body[data_start:]:
        if not _TABLE_ROW_RE.match(line):
            break
        rows.append(line)
    if not rows:
        raise TableParseError("no data rows found in the Agent routing table")
    return rows


def split_row(row: str) -> tuple[str, str, str]:
    """Return the (condition, action, body_read) cell text for one table row."""
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    if len(cells) != 3:
        raise TableParseError(f"expected 3 cells, got {len(cells)}: {row!r}")
    return cells[0], cells[1], cells[2]


def parse_condition(cell: str) -> dict[str, object]:
    """Return the ``if_any``/``if_all``/``if_none``/``default`` shape for *cell*."""
    tokens = _BACKTICK_RE.findall(cell)
    if tokens == [_WILDCARD_TYPE_MARKER]:
        return {"default": True}
    if "AND NOT" in cell:
        before, _, after = cell.partition("AND NOT")
        result: dict[str, object] = {}
        before_tokens = _BACKTICK_RE.findall(before)
        after_tokens = _BACKTICK_RE.findall(after)
        if before_tokens:
            result["if_all"] = before_tokens
        if after_tokens:
            result["if_none"] = after_tokens
        return result
    if not tokens:
        raise TableParseError(f"condition cell has no label token: {cell!r}")
    return {"if_any": tokens}


def parse_action(cell: str) -> dict[str, object]:
    """Return the ``action`` (+ derived ``autonomous_pr``) shape for *cell*."""
    text = cell.strip()
    for prefix, shape in _ACTION_PREFIXES:
        if text.startswith(prefix):
            return dict(shape)
    raise TableParseError(f"unrecognised action cell: {cell!r}")


def parse_body_read(cell: str) -> str:
    """Return the canonical ``body_read`` value for *cell*."""
    normalized = cell.strip().lower()
    if normalized not in _BODY_READ_VALUES:
        raise TableParseError(f"unrecognised body-read cell: {cell!r}")
    return _BODY_READ_VALUES[normalized]


def parse_runbook_rules(runbook_text: str) -> list[dict[str, object]]:
    """Return the canonical ordered rule list parsed from the runbook table."""
    rules: list[dict[str, object]] = []
    for row in extract_table_lines(runbook_text):
        condition_cell, action_cell, body_read_cell = split_row(row)
        rule: dict[str, object] = {}
        rule.update(parse_condition(condition_cell))
        rule.update(parse_action(action_cell))
        rule["body_read"] = parse_body_read(body_read_cell)
        rules.append(rule)
    return rules


# ---------------------------------------------------------------------------
# Registry-side normalization
# ---------------------------------------------------------------------------


def normalize_registry_rules(rules: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    """Return ``label_routing.rules`` as plain dicts, for direct comparison."""
    return [dict(rule) for rule in rules]


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def diff_rules(
    runbook_rules: list[dict[str, object]], registry_rules: list[dict[str, object]]
) -> str | None:
    """Return an error message for the first divergent rule, or ``None`` if equal."""
    if len(runbook_rules) != len(registry_rules):
        return (
            f"rule count differs: runbook table has {len(runbook_rules)} row(s), "
            f"registry label_routing.rules has {len(registry_rules)}"
        )
    for i, (table_rule, registry_rule) in enumerate(zip(runbook_rules, registry_rules, strict=True)):
        if table_rule != registry_rule:
            return f"rule {i} diverges: runbook table has {table_rule!r}, registry has {registry_rule!r}"
    return None


# ---------------------------------------------------------------------------
# IO boundary
# ---------------------------------------------------------------------------


def verify(runbook_path: Path) -> list[str]:
    """Return the ``::error::`` lines for the working tree; empty means clean."""
    try:
        runbook_text = runbook_path.read_text(encoding="utf-8")
        runbook_rules = parse_runbook_rules(runbook_text)
    except (OSError, TableParseError) as exc:
        return [f"::error file={_RUNBOOK_PATH}::{_SCRIPT}: cannot parse the Agent routing table: {exc}"]

    try:
        registry_rules = normalize_registry_rules(_ssot.routing_rules())
    except TypeError as exc:
        return [f"::error file=.gitapex/ssot.json::{_SCRIPT}: cannot read label_routing.rules: {exc}"]

    mismatch = diff_rules(runbook_rules, registry_rules)
    if mismatch is not None:
        return [
            f"::error file={_RUNBOOK_PATH}::{_SCRIPT}: routing table diverges from "
            f".gitapex/ssot.json label_routing.rules: {mismatch}"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    command = argv[0] if argv else None
    if command != "verify":
        print(
            f"::error::{_SCRIPT}: unknown subcommand {command!r}; expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    parser = argparse.ArgumentParser(
        description="Reject drift between the issue-triage routing table and the registry."
    )
    parser.add_argument("command", help="Must be 'verify'.")
    parser.add_argument("--runbook", default=_RUNBOOK_PATH)
    args = parser.parse_args(argv)

    errors = verify(_REPO_ROOT / args.runbook)

    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        print(f"FAIL: {_SCRIPT}: routing table and registry disagree.", file=sys.stderr)
        return 1

    print(
        f"OK: {_SCRIPT}: {args.runbook} matches .gitapex/ssot.json label_routing.rules.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
