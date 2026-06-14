#!/usr/bin/env python3
"""Deterministic gate: the OWASP Agentic Top 10 (ASI01-ASI10) mapping stays complete.

Refs #1378 (re-homed from the retired umbrella #1023 under the Zero Trust
central umbrella #178). ``docs/prd/security-control-inventory.md`` maps every
security surface to MITRE ATT&CK; it also carries a peer-axis mapping onto the
OWASP Top 10 for Agentic Applications 2026 (ASI01-ASI10, OWASP GenAI Security
Project). ATT&CK answers "which attacker tactic is covered"; OWASP Agentic
answers "which agent-class risk is covered".

Why a gate (CLAUDE.md section 3): a documentation-only mapping drifts the moment
an ASI row is dropped or its status is blanked, and only reviewer memory would
catch it. This gate makes the mapping a continuous, fail-loud invariant: every
one of ASI01..ASI10 must appear exactly once in the inventory's OWASP section
with a status drawn from the inventory's own vocabulary and a non-empty
rationale. It is the PR-time enforcement; the weekly ``security-control-drift``
job re-runs the same check on cron as a redundant visibility signal.

The gate is tree-only and runs with no network: it reads the committed
inventory document and nothing else. It does not, and cannot, judge whether a
status is *correct* -- that stays the job of review and the quarterly cadence in
``docs/runbooks/attack-coverage-review-cadence.md``.

Contract:
- Inputs: the ``verify`` subcommand; ``--inventory`` (defaults to
  ``docs/prd/security-control-inventory.md``). No network, no environment
  variables.
- Outputs: ``::error::`` annotations on stderr naming each missing or duplicate
  ASI item, invalid status, or empty rationale; exit 0 when all ten items map
  cleanly, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate); a
  missing OWASP section is reported as a structural error rather than skipped.

Tested by ``tests/test_owasp_asi_mapping.py``. Refs #1378, parent #178.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_INVENTORY = Path("docs/prd/security-control-inventory.md")

# The heading text that opens the OWASP section in the inventory document. The
# gate locates the section by substring match so a renumbered "## N." prefix
# does not break it.
SECTION_ANCHOR = "OWASP Top 10 for Agentic Applications 2026"

# Every item that MUST be mapped. The 2026 edition is exactly ASI01..ASI10.
EXPECTED_IDS: tuple[str, ...] = tuple(f"ASI{n:02d}" for n in range(1, 11))

# Status vocabulary, mirroring the per-surface tables in the same document.
# `not applicable` here means structurally out of scope (no persistent memory
# store for ASI06, no inter-agent bus for ASI07), not "skipped".
VALID_STATUSES: frozenset[str] = frozenset(
    {"covered", "partially covered", "not covered", "not applicable"}
)


def extract_section(text: str) -> str | None:
    """Return the OWASP section body, or None when the section is absent.

    The body runs from the line whose ``##``-level heading contains
    :data:`SECTION_ANCHOR` up to (but excluding) the next ``## `` heading or
    end of file.
    """
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("## ") and SECTION_ANCHOR in line:
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _split_row(line: str) -> list[str]:
    """Split a Markdown table row into trimmed cells, dropping the edge pipes."""
    cells = [cell.strip() for cell in line.strip().split("|")]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def _strip_code(value: str) -> str:
    return value.strip().strip("`").strip()


def evaluate(text: str) -> list[str]:
    """Return a list of human-readable violation messages (empty == clean).

    Pure: takes the inventory document text, performs no I/O. Each of
    ASI01..ASI10 must appear exactly once as a table row in the OWASP section
    with a valid status cell and a non-empty rationale cell.
    """
    section = extract_section(text)
    if section is None:
        return [
            f"OWASP section not found: no '## ...{SECTION_ANCHOR}...' heading in "
            "the inventory document"
        ]

    seen: dict[str, int] = {}
    errors: list[str] = []
    for line in section.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _split_row(line)
        if len(cells) < 4:
            continue
        asi_id = _strip_code(cells[0]).upper()
        if asi_id not in EXPECTED_IDS:
            continue
        seen[asi_id] = seen.get(asi_id, 0) + 1
        status = cells[2].strip().lower()
        rationale = cells[3].strip()
        if status not in VALID_STATUSES:
            errors.append(
                f"{asi_id}: status {cells[2].strip()!r} is not one of "
                f"{sorted(VALID_STATUSES)}"
            )
        if not rationale:
            errors.append(f"{asi_id}: rationale cell is empty")

    for asi_id in EXPECTED_IDS:
        count = seen.get(asi_id, 0)
        if count == 0:
            errors.append(f"{asi_id}: no mapping row found in the OWASP section")
        elif count > 1:
            errors.append(f"{asi_id}: mapped {count} times (must be exactly once)")

    return errors


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        text = args.inventory.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::cannot read {args.inventory}: {exc}", file=sys.stderr)
        return 1

    errors = evaluate(text)
    for message in errors:
        print(f"::error::{message}", file=sys.stderr)
    if errors:
        print(
            f"::error::OWASP ASI mapping gate failed ({len(errors)} violation(s)).",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: all {len(EXPECTED_IDS)} OWASP ASI items carry a valid status row "
        f"in {args.inventory}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_verify = sub.add_parser(
        "verify", help="Fail when the ASI01-ASI10 mapping is incomplete."
    )
    p_verify.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
