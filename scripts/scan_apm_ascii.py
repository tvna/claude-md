#!/usr/bin/env python3
"""Verify APM agent-rule artifacts stay ASCII except a reviewed allowlist.

Issue #1688 (follow-up to #1682): PR #1682 replaced the 34 em-dash
(U+2014) occurrences in the universal text source
``.apm/instructions/master.instructions.md`` with the ASCII `; `
separator, but its own issue body and commit message note that "no
repo-tree ASCII gate exists"; nothing stops an em-dash (or any other
smart-punctuation glyph) from regressing back in on the next edit. The
universal text is distributed downstream via submodule import, so a
downstream agent that lifts a rule phrase into a GitHub post would carry
the non-ASCII glyph into the ASCII-gated post boundary
(``scan_non_ascii`` / ``title_policy`` / ``preflight_non_ascii``). This
script is the deterministic gate that #1682 identified as missing.

Invoked from ``.github/workflows/verify-pr.yml`` and registered in
``preflight_all.STEPS`` as
``python3 scripts/scan_apm_ascii.py verify --path <file> ...``, mirroring
the sibling gate ``scripts/scan_apm_portability.py`` so the two scans run
side by side over the same artifacts.

The contract is:

* Each ``--path`` is a file to scan. Typical inputs are
  ``.apm/instructions/master.instructions.md``, ``CLAUDE.md``, and
  ``AGENTS.md`` (defense in depth: scan source and both compiled
  outputs; the compiled mirrors are also drift-gated against the source
  by ``verify-pr.yml``).
* Every character whose codepoint is > U+007F is a violation unless it is
  in :data:`_ALLOWED_NON_ASCII`. The allowlist is a code-reviewed
  constant rather than an inline ACK marker on purpose: a per-line ACK in
  the markdown would let arbitrary non-ASCII in behind a comment, which
  is the opposite of the discipline this gate enforces. Admitting a new
  legitimate glyph requires editing this script, which is a
  code-owner-reviewed change (governance-gated per CLAUDE.md section 2),
  not a self-service bypass.
* The whole file text is scanned directly (not via ``str.splitlines``)
  so a non-ASCII line/paragraph separator such as U+2028 / U+2029; one
  of the sneakier injections; is itself flagged instead of being
  silently consumed as a line boundary. Only ``"\n"`` advances the line
  counter, so reported line numbers match an editor's view.
* Exit 0 when every scanned file is clean; exit 1 on any violation; the
  argparse layer returns 2 when no ``--path`` was supplied. Each hit
  emits ``::error file=<path>,line=<n>,col=<c>::...`` on stderr so the
  GitHub Actions UI surfaces individual violations with the offending
  codepoint and its Unicode name.

Contract:
    Inputs: the ``verify`` subcommand and one or more ``--path`` file
        arguments. No stdin, no environment, no network.
    Outputs: an ``::error file=<path>,line=<n>,col=<c>::`` annotation on
        stderr for each disallowed character (naming the codepoint and
        its Unicode name), plus an ``OK:`` / ``FAIL:`` summary line; exit
        0 when every scanned file is clean, 1 on any violation or a
        missing target, 2 when no ``--path`` was supplied.
    Failure policy: fails loud per CLAUDE.md section 4 (gate: a disallowed
        non-ASCII character, or a missing scan target, exits non-zero
        rather than passing silently).

Tested by ``tests/test_scan_apm_ascii.py``. Refs #1688, #1682.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path

# Non-ASCII codepoints permitted in the scanned artifacts. Kept as narrow
# as possible: each entry is a glyph the universal text deliberately uses
# and that has no plain-ASCII substitute carrying the same meaning.
#
# * U+00A7 SECTION SIGN; the section cross-reference glyph (e.g. the
#   "section 2 applies" shorthand). One occurrence per artifact today;
#   #1682 explicitly scoped it out of the em-dash normalization.
_ALLOWED_NON_ASCII: frozenset[str] = frozenset(
    {
        "§",  # SECTION SIGN
    }
)


def _codepoint_label(char: str) -> str:
    """Return a human-readable ``U+XXXX NAME`` label for *char*."""
    name = unicodedata.name(char, "")
    code = f"U+{ord(char):04X}"
    return f"{code} {name}".rstrip()


def scan_text(text: str) -> list[tuple[int, int, str]]:
    """Return ``(line, column, char)`` for every disallowed non-ASCII char.

    Line and column numbers are 1-based to match GitHub Actions
    ``::error file=`` annotations and an editor's cursor. The scan walks
    the raw text so a non-ASCII line separator is reported rather than
    consumed; only ``"\\n"`` advances the line counter.

    The function is pure; it never touches the filesystem; so the
    classification is unit-tested directly on string fixtures.
    """
    hits: list[tuple[int, int, str]] = []
    lineno = 1
    column = 0
    for char in text:
        if char == "\n":
            lineno += 1
            column = 0
            continue
        column += 1
        if ord(char) > 0x7F and char not in _ALLOWED_NON_ASCII:
            hits.append((lineno, column, char))
    return hits


def scan_file(path: Path) -> list[tuple[int, int, str]]:
    """Return ``(line, column, char)`` for every violation in *path*."""
    return scan_text(path.read_text(encoding="utf-8"))


def _verify(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        if not path.exists():
            print(
                f"::error::missing scan target: {path}",
                file=sys.stderr,
            )
            total += 1
            continue
        for lineno, column, char in scan_file(path):
            print(
                f"::error file={path},line={lineno},col={column}::"
                f"non-ASCII character {_codepoint_label(char)} in APM "
                "artifact. Replace it with its ASCII equivalent (em-dash "
                "U+2014 -> '; '), or, if it is an intentional and "
                "downstream-safe glyph, add it to "
                "scan_apm_ascii._ALLOWED_NON_ASCII in a code-owner-reviewed "
                "change.",
                file=sys.stderr,
            )
            total += 1
    if total:
        print(
            f"FAIL: {total} non-ASCII violation(s).",
            file=sys.stderr,
        )
        return 1
    print("OK: scanned APM artifacts are ASCII (allowlist applied).")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    if not args.path:
        print(
            "error: at least one --path is required",
            file=sys.stderr,
        )
        return 2
    paths = [Path(p) for p in args.path]
    return _verify(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Scan files for disallowed non-ASCII characters.",
    )
    p_verify.add_argument(
        "--path",
        action="append",
        default=[],
        help=(
            "Path to a file to scan. Repeatable; supply once per file. "
            "Typical inputs are .apm/instructions/master.instructions.md, "
            "CLAUDE.md, AGENTS.md."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
