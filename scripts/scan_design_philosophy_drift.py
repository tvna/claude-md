#!/usr/bin/env python3
"""Verify the design-philosophy responsibility matrix tracks the master.

Issue #308 retrospective for PR #297 and PR #304: each PR added a new
numbered section to ``.apm/instructions/master.instructions.md`` without
adding the corresponding row to the Section 3 responsibility matrix in
``docs/agent-rules-design-philosophy.md``. The existing
``verify-apm-drift`` and ``verify-apm-portability`` gates enforce
source-to-compiled-artifact equivalence and repo-local-noun absence
respectively, but neither inspects the design-philosophy doc.

Invoked from ``.github/workflows/verify-design-philosophy.yml`` as
``python3 scripts/scan_design_philosophy_drift.py verify --master <path>
--doc <path>``.

The contract is:

* ``--master`` is the APM source file. Its top-level numbered sections
  are enumerated as ``^## (\\d+)\\. ``. The maximum section number N
  determines the expected principle count.
* ``--doc`` is the design-philosophy doc. Its Section 3 responsibility
  matrix is extracted (everything between the ``## 3. `` heading and
  the next ``## ``) and the row labels ``| P(\\d+) -`` are enumerated.
* The script fails when the master section set ``{1, ..., N}`` differs
  from the doc row label set ``{P1, ..., PN}``.
* The script also fails when the doc contains a free-text count of the
  form ``<word> (principles|layers)`` whose numeric value does not
  match N. Supported words are ``one``..``twelve`` (case-insensitive)
  and any bare integer.
* Exit 0 when the doc tracks the master; exit 1 on any drift; the
  argparse layer returns 2 on missing ``--master`` or ``--doc``. Each
  hit emits ``::error file=<path>,line=<n>::...`` on stderr so the
  GitHub Actions UI surfaces individual violations.

Tested by ``tests/test_scan_design_philosophy_drift.py``. Refs #308.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MASTER_SECTION_RE = re.compile(r"^## (\d+)\. ")
DOC_SECTION_3_HEADING_RE = re.compile(r"^## 3\. ")
DOC_NEXT_SECTION_RE = re.compile(r"^## \d+\. ")
DOC_MATRIX_ROW_RE = re.compile(r"^\|\s*P(\d+)\s*-")
DOC_WORDING_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
    r"\s+(principles|layers)\b",
    re.IGNORECASE,
)

WORD_TO_INT: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def parse_master_sections(text: str) -> set[int]:
    """Return the set of top-level numbered section numbers in *text*."""
    return {
        int(match.group(1))
        for line in text.splitlines()
        if (match := MASTER_SECTION_RE.match(line)) is not None
    }


def extract_section_3(text: str) -> tuple[list[str], int]:
    """Return Section 3 lines and the 1-based start line offset.

    The slice starts at the ``## 3. ...`` heading (inclusive) and ends
    before the next ``## N. ...`` heading. When the doc has no Section
    3, an empty list is returned with offset 0.
    """
    lines = text.splitlines()
    start: int | None = None
    end: int | None = None
    for index, line in enumerate(lines):
        if DOC_SECTION_3_HEADING_RE.match(line):
            start = index
            continue
        if start is not None and DOC_NEXT_SECTION_RE.match(line):
            end = index
            break
    if start is None:
        return [], 0
    if end is None:
        end = len(lines)
    return lines[start:end], start + 1


def parse_doc_matrix_rows(section_lines: list[str]) -> set[int]:
    """Return the set of ``P<n>`` row labels in the matrix slice."""
    return {
        int(match.group(1))
        for line in section_lines
        if (match := DOC_MATRIX_ROW_RE.match(line)) is not None
    }


def parse_doc_wording_counts(text: str) -> list[tuple[int, str, int]]:
    """Return ``(line_number, raw_phrase, count)`` for each wording hit.

    Line numbers are 1-based.
    """
    hits: list[tuple[int, str, int]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in DOC_WORDING_RE.finditer(line):
            token = match.group(1).lower()
            count = WORD_TO_INT.get(token, _safe_int(token))
            if count is None:
                continue
            hits.append((lineno, match.group(0), count))
    return hits


def _safe_int(token: str) -> int | None:
    try:
        return int(token)
    except ValueError:
        return None


def _verify(master_path: Path, doc_path: Path) -> int:
    if not master_path.exists():
        print(
            f"::error::missing master file: {master_path}",
            file=sys.stderr,
        )
        return 1
    if not doc_path.exists():
        print(
            f"::error::missing doc file: {doc_path}",
            file=sys.stderr,
        )
        return 1

    master_text = master_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")

    master_sections = parse_master_sections(master_text)
    if not master_sections:
        print(
            f"::error file={master_path}::no numbered sections detected "
            f"(expected lines matching '## <n>. ...').",
            file=sys.stderr,
        )
        return 1

    expected = set(range(1, max(master_sections) + 1))
    if master_sections != expected:
        missing = sorted(expected - master_sections)
        print(
            f"::error file={master_path}::master section numbers are "
            f"non-contiguous; missing {missing}.",
            file=sys.stderr,
        )
        return 1

    section_lines, section_offset = extract_section_3(doc_text)
    if not section_lines:
        print(
            f"::error file={doc_path}::Section 3 heading "
            f"('## 3. ...') not found.",
            file=sys.stderr,
        )
        return 1

    matrix_rows = parse_doc_matrix_rows(section_lines)
    failures = 0

    missing_in_doc = sorted(expected - matrix_rows)
    if missing_in_doc:
        labels = ", ".join(f"P{n}" for n in missing_in_doc)
        print(
            f"::error file={doc_path},line={section_offset}::matrix is "
            f"missing rows for {labels}; each master '## N.' section "
            f"requires a matching '| PN -' row.",
            file=sys.stderr,
        )
        failures += 1

    extra_in_doc = sorted(matrix_rows - expected)
    if extra_in_doc:
        labels = ", ".join(f"P{n}" for n in extra_in_doc)
        print(
            f"::error file={doc_path},line={section_offset}::matrix "
            f"has rows {labels} with no corresponding '## N.' section "
            f"in master; remove the row or add the section.",
            file=sys.stderr,
        )
        failures += 1

    expected_count = max(master_sections)
    for lineno, phrase, count in parse_doc_wording_counts(doc_text):
        if count != expected_count:
            print(
                f"::error file={doc_path},line={lineno}::wording "
                f"'{phrase}' implies {count} but master has "
                f"{expected_count} principles; update the phrase to "
                f"track the current principle count.",
                file=sys.stderr,
            )
            failures += 1

    if failures:
        print(
            f"FAIL: {failures} design-philosophy drift violation(s).",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: doc matrix tracks master ({expected_count} principles, "
        f"{expected_count} matrix rows)."
    )
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    if not args.master or not args.doc:
        print(
            "error: both --master and --doc are required",
            file=sys.stderr,
        )
        return 2
    return _verify(Path(args.master), Path(args.doc))


def _cmd_report(args: argparse.Namespace) -> int:
    if not args.master or not args.doc:
        print(
            "error: both --master and --doc are required",
            file=sys.stderr,
        )
        return 2
    master_path = Path(args.master)
    doc_path = Path(args.doc)
    if not master_path.exists() or not doc_path.exists():
        print("error: one of the input files does not exist", file=sys.stderr)
        return 1
    master_sections = parse_master_sections(
        master_path.read_text(encoding="utf-8")
    )
    section_lines, _ = extract_section_3(doc_path.read_text(encoding="utf-8"))
    matrix_rows = parse_doc_matrix_rows(section_lines)
    print(f"master sections: {sorted(master_sections)}")
    print(f"doc matrix rows: {sorted(matrix_rows)}")
    print(f"missing in doc:  {sorted(set(master_sections) - matrix_rows)}")
    print(f"extra in doc:    {sorted(matrix_rows - set(master_sections))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help=(
            "Fail when the doc Section 3 matrix does not track master "
            "section numbers."
        ),
    )
    p_verify.add_argument(
        "--master",
        required=True,
        help="Path to .apm/instructions/master.instructions.md.",
    )
    p_verify.add_argument(
        "--doc",
        required=True,
        help="Path to docs/agent-rules-design-philosophy.md.",
    )
    p_verify.set_defaults(func=_cmd_verify)

    p_report = sub.add_parser(
        "report",
        help="Print master section numbers and doc matrix rows; never fail.",
    )
    p_report.add_argument("--master", required=True)
    p_report.add_argument("--doc", required=True)
    p_report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
