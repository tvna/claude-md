#!/usr/bin/env python3
"""Verify the design-philosophy responsibility matrix tracks the master.

Issue #308 retrospective for PR #297 and PR #304: each PR added a new
numbered section to ``.apm/instructions/master.instructions.md`` without
adding the corresponding row to the Section 3 responsibility matrix in
``docs/prd/agent-rules-design-philosophy.md``. The existing
``portable-pr-policy`` gate enforces
source-to-compiled-artifact equivalence and repo-local-noun absence
respectively, but does not inspect the design-philosophy doc.

Issue #329 retrospective for #322 extends this scan with two checks:
row label parity (each ``| P<n> - <label> |`` row must equal the master
``*Layer: <label> ...*`` subtitle after ``&``/``and`` normalization),
and glossary presence (section 2.5 of the doc must list every term the
section 3 invariant relies on).

Invoked from ``.github/workflows/verify-design-philosophy.yml`` as
``python3 scripts/scan_design_philosophy_drift.py verify --master <path>
--doc <path>``.

The contract is:

* ``--master`` is the APM source file. Its top-level numbered sections
  are enumerated as ``^## (\\d+)\\. ``. The maximum section number N
  determines the expected principle count. Each section's subtitle
  ``*Layer: <text> -- ...*`` (em-dash separator) yields the layer name
  for label-parity checking.
* ``--doc`` is the design-philosophy doc. Its Section 3 responsibility
  matrix is extracted (everything between the ``## 3. `` heading and
  the next ``## ``) and the row labels ``| P(\\d+) - <label>`` are
  enumerated. Its Section 2.5 glossary is extracted (everything between
  ``### 2.5 Glossary`` and the next heading) and the bolded entry
  names ``- **<term>**:`` are enumerated.
* The script fails when the master section set ``{1, ..., N}`` differs
  from the doc row label set ``{P1, ..., PN}``.
* The script also fails when a row label and its master subtitle do
  not agree after normalization (lowercase, ``&`` to ``and``,
  whitespace collapsed). When either side is missing the subtitle or
  the row, this specific check is skipped because the row-count check
  above already surfaces the structural gap.
* The script also fails when the doc contains a free-text count of the
  form ``<word> (principles|layers)`` whose numeric value does not
  match N. Supported words are ``one``..``twelve`` (case-insensitive)
  and any bare integer.
* The script also fails when section 2.5 is missing any entry named
  in :data:`REQUIRED_GLOSSARY_ENTRIES`.
* Exit 0 when the doc tracks the master; exit 1 on any drift; the
  argparse layer returns 2 on missing ``--master`` or ``--doc``. Each
  hit emits ``::error file=<path>,line=<n>::...`` on stderr so the
  GitHub Actions UI surfaces individual violations.

The ``verify-coupling`` subcommand adds a diff-aware gate (Refs #1190):
when a PR changes ``.apm/instructions/master.instructions.md`` it must,
in the same PR, also change ``docs/prd/agent-rules-design-philosophy.md``
so the Section 3 responsibility matrix is reviewed alongside the
principle edit -- or carry a plain-text ``philosophy-matrix-ack`` line in
the PR body to consciously opt out (for example a typo-only edit that
changes no responsibility). This catches the per-bullet matrix drift the
structural ``verify`` check cannot see, deterministically rather than by
reviewer memory.

Contract:
    Inputs: the ``verify`` / ``report`` subcommands (``--master`` and
        ``--doc`` paths); the ``verify-coupling`` subcommand
        (``--base-ref`` falling back to ``BASE_REF`` then ``origin/main``,
        and the PR body from ``--body-file`` or the ``PR_BODY`` env var).
    Outputs: ``::error::`` annotations on stderr; an ``OK:`` line on the
        happy path; exit 0 when clean or not required, 1 on drift, 2 on
        missing required args.
    Failure policy: fails loud per CLAUDE.md section 4 (a drift or a
        master-without-matrix change exits non-zero).

Tested by ``tests/test_scan_design_philosophy_drift.py``. Refs #308,
#322, #329, #1190.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

MASTER_SECTION_RE = re.compile(r"^## (\d+)\. ")
MASTER_SUBTITLE_RE = re.compile(r"^\*Layer:\s*(.+?);\s")
DOC_SECTION_3_HEADING_RE = re.compile(r"^## 3\. ")
DOC_NEXT_SECTION_RE = re.compile(r"^## \d+\. ")
DOC_MATRIX_ROW_RE = re.compile(r"^\|\s*P(\d+)\s*-")
DOC_ROW_LABEL_RE = re.compile(r"^\|\s*P(\d+)\s*-\s*([^|]+?)\s*\|")
DOC_GLOSSARY_HEADING_RE = re.compile(r"^### 2\.5 Glossary\s*$")
DOC_GLOSSARY_ENTRY_RE = re.compile(r"^- \*\*(.+?)\*\*:")
DOC_HEADING_RE = re.compile(r"^#{1,3} ")
DOC_WORDING_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
    r"\s+(principles|layers)\b",
    re.IGNORECASE,
)
_NORMALIZE_WS_RE = re.compile(r"\s+")

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

REQUIRED_GLOSSARY_ENTRIES: tuple[str, ...] = (
    # Master section 2 -- trust and input model
    "untrusted data",
    "trusted instruction source",
    "governance-gated provenance",
    "adversarial payload",
    "non-exhaustive instance",
    "primary source",
    # Master section 3 -- delivery harness
    "deterministic gate",
    "drift gate",
    "durable gate",
    "harness",
    "invariant",
    "freshness precondition",
    "TTL",
    "repair",
    "retrospective",
    "repair-free merge",
    "provenance marker",
    "preflight",
    "terminal state",
    # Master section 4 -- safety boundary
    "safety boundary",
    "defense-in-depth",
    "blast radius",
    "trust boundary",
    "attack surface",
    "irreversible operation",
    "dry-run",
    # Master section 5 -- quality
    "change surface",
    # Master section 6 -- handoff and communication
    "decision-ready",
    "decision brief",
    "evidence map",
    # Design-philosophy meta terms
    "PRD",
    "P1 through P6",
    "hardness contour",
    "in-line carve-out",
)

GLOSSARY_PATH = "docs/standards/ubiquitous-language.md"

_GIT_TIMEOUT_SECONDS: int = 15

# The two files the coupling gate pairs: editing the master principle
# source must be accompanied by a matrix review in the design-philosophy
# doc (or an explicit ack).
MASTER_PATH = ".apm/instructions/master.instructions.md"
DOC_PATH = "docs/prd/agent-rules-design-philosophy.md"

# Plain-text opt-out marker (MCP-safe, mirrors the `partial-pr` pattern in
# scripts/issue_link.py): a line that, after optional indentation, begins
# with `philosophy-matrix-ack` (case-insensitive). HTML-comment markers are
# stripped by the GitHub MCP write tools, so a plain-text token is used.
_MATRIX_ACK_RE = re.compile(
    r"^\s*philosophy-matrix-ack\b", re.IGNORECASE | re.MULTILINE
)


def normalize_label(text: str) -> str:
    """Return a comparable form of a layer label.

    Lowercases the text, replaces ``&`` with ``and``, and collapses any
    run of whitespace to a single space. Trailing and leading whitespace
    is stripped. The function is the basis for the label-parity check.
    """
    text = text.lower().replace("&", "and")
    return _NORMALIZE_WS_RE.sub(" ", text).strip()


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


def parse_master_subtitles(text: str) -> dict[int, str]:
    """Return ``{section_number: subtitle_text}`` for each numbered section.

    The subtitle is the first line after a ``## <n>. ...`` heading that
    matches :data:`MASTER_SUBTITLE_RE`. Sections without a matching
    subtitle are omitted. The captured ``<text>`` excludes the em-dash
    separator and the description that follows it.
    """
    result: dict[int, str] = {}
    pending: int | None = None
    for line in text.splitlines():
        section_match = MASTER_SECTION_RE.match(line)
        if section_match:
            pending = int(section_match.group(1))
            continue
        if pending is None:
            continue
        subtitle_match = MASTER_SUBTITLE_RE.match(line)
        if subtitle_match:
            result[pending] = subtitle_match.group(1)
            pending = None
    return result


def parse_doc_row_labels(section_lines: list[str]) -> dict[int, str]:
    """Return ``{n: label_text}`` for each ``P<n> - <label>`` row."""
    return {
        int(match.group(1)): match.group(2)
        for line in section_lines
        if (match := DOC_ROW_LABEL_RE.match(line)) is not None
    }


def parse_file_entries(text: str) -> set[str]:
    """Return all bolded entry names from *text* regardless of heading context.

    Scans every line of the form ``- **name**: ...`` across the entire file.
    Used for the standalone ``docs/standards/ubiquitous-language.md`` where
    entries are spread across multiple categorised sections rather than
    collected under a single ``### 2.5 Glossary`` heading.
    """
    return {
        match.group(1)
        for line in text.splitlines()
        if (match := DOC_GLOSSARY_ENTRY_RE.match(line)) is not None
    }


def parse_glossary_entries(text: str) -> set[str]:
    """Return bolded entry names under the ``### 2.5 Glossary`` heading.

    The slice begins at the heading (exclusive) and ends before the
    next ``#``, ``##``, or ``###`` heading. Each entry line of the form
    ``- **<term>**: ...`` contributes ``<term>`` to the result. Returns
    an empty set when the glossary heading is absent.
    """
    lines = text.splitlines()
    start: int | None = None
    end: int | None = None
    for i, line in enumerate(lines):
        if DOC_GLOSSARY_HEADING_RE.match(line):
            start = i + 1
            continue
        if start is not None and DOC_HEADING_RE.match(line):
            end = i
            break
    if start is None:
        return set()
    if end is None:
        end = len(lines)
    return {
        match.group(1)
        for line in lines[start:end]
        if (match := DOC_GLOSSARY_ENTRY_RE.match(line)) is not None
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


def _verify(
    master_path: Path,
    doc_path: Path,
    glossary_path: Path | None = None,
) -> int:
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
    if glossary_path is not None and not glossary_path.exists():
        print(
            f"::error::missing glossary file: {glossary_path}",
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

    master_subtitles = parse_master_subtitles(master_text)
    doc_row_labels = parse_doc_row_labels(section_lines)
    for n in sorted(master_sections & matrix_rows):
        sub_text = master_subtitles.get(n)
        label_text = doc_row_labels.get(n)
        if sub_text is None or label_text is None:
            continue
        if normalize_label(sub_text) != normalize_label(label_text):
            print(
                f"::error file={doc_path},line={section_offset}::"
                f"P{n} row label '{label_text}' does not match master "
                f"section {n} subtitle '{sub_text}' (after &/and "
                f"normalization). Rename one side to match the other "
                f"so the matrix row and the master subtitle agree.",
                file=sys.stderr,
            )
            failures += 1

    if glossary_path is not None:
        glossary_entries = parse_file_entries(
            glossary_path.read_text(encoding="utf-8")
        )
        glossary_ref = glossary_path
        glossary_hint = (
            f"Add '- **name**: ...' lines in {glossary_path} so "
            "terms used in master and in the section 3 invariant have "
            "a single source of truth."
        )
    else:
        glossary_entries = parse_glossary_entries(doc_text)
        glossary_ref = doc_path
        glossary_hint = (
            f"Add '- **name**: ...' lines under '### 2.5 Glossary' in "
            f"{doc_path} so terms used in master and in the section 3 "
            "invariant have a single source of truth."
        )
    missing_glossary = sorted(
        set(REQUIRED_GLOSSARY_ENTRIES) - glossary_entries
    )
    if missing_glossary:
        labels = ", ".join(missing_glossary)
        print(
            f"::error file={glossary_ref}::glossary is missing required "
            f"entries: {labels}. {glossary_hint}",
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
    glossary_path = Path(args.glossary) if args.glossary else None
    return _verify(Path(args.master), Path(args.doc), glossary_path)


def resolve_base() -> str:
    """Return the base ref verify-coupling diffs HEAD against.

    Resolution order: ``BASE_REF`` env, then the local fallback
    ``origin/main``. Empty environment values are treated as unset.
    """
    explicit = os.environ.get("BASE_REF")
    if explicit:
        return explicit
    return "origin/main"


def changed_files(
    base_ref: str, head: str = "HEAD", *, runner=subprocess.run
) -> frozenset[str]:
    """Return the set of files modified in ``{base}..{head}``.

    Uses ``git diff --name-only`` so renames and deletes also surface.
    """
    result = _run(
        ["git", "diff", "--name-only", f"{base_ref}..{head}"], runner=runner
    )
    return frozenset(
        line.strip() for line in result.stdout.splitlines() if line.strip()
    )


def has_matrix_ack(body: str) -> bool:
    """Return True when *body* carries the philosophy-matrix-ack opt-out."""
    return _MATRIX_ACK_RE.search(body) is not None


def evaluate_coupling(
    changed: frozenset[str], body: str
) -> tuple[int, list[str]]:
    """Return ``(exit_code, error_lines)`` for the coupling gate.

    * master.instructions.md not changed -> exit 0 (coupling not required).
    * master changed and the design-philosophy doc also changed -> exit 0.
    * master changed, doc unchanged, ack marker present -> exit 0.
    * master changed, doc unchanged, no ack -> exit 1.
    """
    if MASTER_PATH not in changed:
        return 0, []
    if DOC_PATH in changed:
        return 0, []
    if has_matrix_ack(body):
        return 0, []
    return 1, [
        f"::error::This PR changes {MASTER_PATH} but not {DOC_PATH}. A "
        "principle edit must review the Section 3 responsibility matrix in "
        "the same PR: update the matching '| PN -' cell, or add a plain-text "
        "'philosophy-matrix-ack' line to the PR body when the edit changes "
        "no responsibility (for example a typo fix). See "
        "docs/prd/agent-rules-design-philosophy.md."
    ]


def _resolve_coupling_body(args: argparse.Namespace) -> str:
    if args.body_file is not None:
        return Path(args.body_file).read_text(encoding="utf-8")
    return os.environ.get("PR_BODY", "")


def _cmd_verify_coupling(args: argparse.Namespace) -> int:
    base = args.base_ref or resolve_base()
    try:
        body = _resolve_coupling_body(args)
    except FileNotFoundError as exc:
        print(
            "::error::scan_design_philosophy_drift: body file not found: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1
    try:
        changed = changed_files(base)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        OSError,
    ) as exc:
        print(
            "::error::scan_design_philosophy_drift: git invocation failed "
            f"against base {base!r}: {exc}",
            file=sys.stderr,
        )
        return 1
    code, errors = evaluate_coupling(changed, body)
    if code == 0:
        if MASTER_PATH in changed:
            print(
                "OK: master changed and the design-philosophy matrix was "
                "updated or the change is acked."
            )
        else:
            print("OK: no master instruction text modified.")
        return 0
    for line in errors:
        print(line)
    return 1


def _run(cmd: list[str], *, runner=subprocess.run):
    """Thin subprocess boundary -- the only impure surface for diffing.

    ``check=True`` raises ``CalledProcessError`` on non-zero exit; the
    caller in :func:`_cmd_verify_coupling` translates that into the
    fail-loud ``::error::`` path. Tests monkeypatch ``runner``.
    """
    return runner(
        cmd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=True,
    )


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
        help="Path to docs/prd/agent-rules-design-philosophy.md.",
    )
    p_verify.add_argument(
        "--glossary",
        default=GLOSSARY_PATH,
        help=(
            "Path to the standalone ubiquitous-language doc. "
            f"Defaults to {GLOSSARY_PATH}. "
            "The glossary check reads entries from this file; "
            "pass an explicit path to override."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    p_report = sub.add_parser(
        "report",
        help="Print master section numbers and doc matrix rows; never fail.",
    )
    p_report.add_argument("--master", required=True)
    p_report.add_argument("--doc", required=True)
    p_report.set_defaults(func=_cmd_report)

    p_coupling = sub.add_parser(
        "verify-coupling",
        help=(
            "Fail when a PR edits master.instructions.md without also "
            "updating the design-philosophy matrix (or acking)."
        ),
    )
    p_coupling.add_argument(
        "--base-ref",
        help=(
            "Base ref to diff HEAD against. Falls back to BASE_REF, then "
            "to origin/main."
        ),
    )
    p_coupling.add_argument(
        "--body-file",
        help=(
            "Path to a file containing the PR body. Falls back to the "
            "PR_BODY env var when omitted."
        ),
    )
    p_coupling.set_defaults(func=_cmd_verify_coupling)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
