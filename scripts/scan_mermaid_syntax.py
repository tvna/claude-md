#!/usr/bin/env python3
"""Verify that every Mermaid block under ``docs/`` parses before it renders.

Refs #1597. Merged PR #1595 shipped a sequence-diagram whose message body
contained a ``;`` -- which Mermaid treats as a statement separator -- producing
a render error that flowed into both the en and ja documents and was only
caught after merge by author review. This gate replaces that author-review
reliance with a deterministic check: it extracts every ` ```mermaid ` fenced
block from ``docs/**/*.md`` and parses it with the official Mermaid parser.

Architecture mirrors the other ``scan_*.py`` gates: pure functions on top
(block extraction, exemption, diagnostic formatting) and a single thin I/O
boundary at the bottom that shells out to ``bun scripts/mermaid_parse.mjs``.
The parser is the REAL Mermaid parser on purpose -- a bracket-balance heuristic
is explicitly not a substitute for proving a block renders (measure-first).

Scope: every ` ```mermaid ` block under ``docs/`` is gated, including the
generator-owned blocks under ``docs/generated/scripts/ast/``. The ``is_exempt``
mechanism remains as an extension point but no path is exempt today.

Contract:
    Inputs: the ``verify`` subcommand, plus optional ``--root`` (repository
        root to scan, default the repo containing this script) and ``--bun``
        (path to the bun executable, default a PATH lookup). The scanned
        surface is every ` ```mermaid ` fenced block under ``<root>/docs/**/*.md``.
        The parse oracle is ``bun scripts/mermaid_parse.mjs`` (official Mermaid parser); no
        stdin, no env input, no network.
    Outputs: prints ``::error file=...,line=...::`` annotations on stderr per
        block the parser rejected plus a one-line summary, exit 0 when every
        block parses and exit 1 on any parse failure. A missing bun or a worker
        that cannot run also exits 1 with an ``::error::`` explanation.
    Failure policy: fails loud per CLAUDE.md section 4 (gate: an unparseable
        Mermaid block, an absent bun, or a worker error each exit non-zero).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MERMAID_PARSER = REPO_ROOT / "scripts" / "mermaid_parse.mjs"

# Repository-relative path prefixes excluded from the gate. Empty by design --
# every Mermaid block under docs/ is gated. This stays as an extension point so
# a future quarantine can be added declaratively without reworking is_exempt.
EXEMPT_PREFIXES: tuple[str, ...] = ()

_FENCE_INFO = "mermaid"


@dataclass(frozen=True)
class MermaidBlock:
    """One ```mermaid fenced block found in a documentation file."""

    source: Path
    line: int  # 1-based line number of the opening fence
    text: str


def rel(path: Path, root: Path) -> str:
    """Return a stable repository-relative path string."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def is_exempt(relative: str) -> bool:
    """Return True for documentation paths excluded from the gate."""
    return any(relative.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def iter_docs_markdown(root: Path) -> list[Path]:
    """Return every non-exempt Markdown document below ``docs/``."""
    docs = root / "docs"
    if not docs.exists():
        return []
    files: list[Path] = []
    for path in sorted(docs.rglob("*.md")):
        if not path.is_file():
            continue
        if is_exempt(rel(path, root)):
            continue
        files.append(path)
    return files


def _fence_marker(stripped: str) -> str | None:
    """Return the backtick/tilde fence marker if *stripped* opens a fence."""
    for marker in ("```", "~~~"):
        if stripped.startswith(marker):
            return marker
    return None


def extract_blocks(source: Path, text: str) -> list[MermaidBlock]:
    """Return the ```mermaid blocks in *text*, with opening-fence line numbers.

    Handles indented fences (a fenced block nested in a list) by stripping the
    opening fence's indentation from each body line, mirroring CommonMark. Only
    a fence whose info string is exactly ``mermaid`` opens a Mermaid block; a
    fence closes on the first line that is the same marker with no info string.
    A block left unclosed at end of file is still emitted with the text gathered
    so far so the parser reports the real error rather than silently dropping it.
    """
    lines = text.splitlines()
    blocks: list[MermaidBlock] = []
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        stripped = line.strip()
        marker = _fence_marker(stripped)
        if marker is None or stripped[len(marker) :].strip() != _FENCE_INFO:
            index += 1
            continue

        fence_line = index + 1
        indent = len(line) - len(line.lstrip())
        body: list[str] = []
        index += 1
        while index < total:
            current = lines[index]
            if current.strip() == marker:
                index += 1
                break
            if indent and current[:indent].strip() == "":
                body.append(current[indent:])
            else:
                body.append(current)
            index += 1
        blocks.append(MermaidBlock(source=source, line=fence_line, text="\n".join(body)))
    return blocks


def collect_blocks(root: Path) -> list[MermaidBlock]:
    """Return every in-scope Mermaid block under ``docs/``."""
    blocks: list[MermaidBlock] = []
    for path in iter_docs_markdown(root):
        blocks.extend(extract_blocks(path, path.read_text(encoding="utf-8")))
    return blocks


def format_error(block: MermaidBlock, message: str, root: Path) -> str:
    """Return a GitHub-annotation diagnostic for a failed block."""
    location = rel(block.source, root)
    return f"::error file={location},line={block.line}::Mermaid parse error: {message}"


def run_parser(blocks: list[MermaidBlock], bun: str) -> list[dict[str, Any]]:
    """Parse *blocks* via ``bun scripts/mermaid_parse.mjs`` and return results.

    Each block is sent as ``{id, text}`` where ``id`` is ``path:line`` so the
    worker's result maps back to the source location. Raises ``RuntimeError``
    when the worker cannot run (non-zero exit) so the gate fails loud rather
    than silently passing.
    """
    payload = [{"id": f"{block.source}:{block.line}", "text": block.text} for block in blocks]
    proc = subprocess.run(  # noqa: S603 - bun path resolved via shutil.which, static script arg
        [bun, str(MERMAID_PARSER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"mermaid_parse.mjs failed (exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"mermaid_parse.mjs produced non-JSON output: {exc}") from exc


def diagnostics(blocks: list[MermaidBlock], results: list[dict[str, Any]], root: Path) -> list[str]:
    """Return one diagnostic per block the parser rejected, in source order."""
    by_id = {f"{block.source}:{block.line}": block for block in blocks}
    errors: list[str] = []
    for result in results:
        if result.get("ok"):
            continue
        block = by_id.get(result.get("id", ""))
        if block is None:
            continue
        errors.append(format_error(block, result.get("error") or "unknown parse error", root))
    return errors


def verify(root: Path, bun: str) -> list[str]:
    """Return all Mermaid parse diagnostics under *root*."""
    blocks = collect_blocks(root)
    if not blocks:
        return []
    results = run_parser(blocks, bun)
    return diagnostics(blocks, results, root)


def resolve_bun() -> str | None:
    """Return the bun executable path, or None when bun is not installed."""
    return shutil.which("bun")


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    bun = args.bun or resolve_bun()
    if not bun:
        print(
            "::error::bun is required to validate Mermaid syntax but was not found on PATH. "
            "Run scripts/install-bun.sh (web) or use the nix dev shell, then `bun install --frozen-lockfile`.",
            file=sys.stderr,
        )
        return 1
    try:
        errors = verify(root, bun)
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"FAIL: {len(errors)} Mermaid block(s) failed to parse.", file=sys.stderr)
        return 1
    print("OK: all Mermaid blocks under docs/ parse.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root to scan.")
    parser.add_argument("--bun", default=None, help="Path to the bun executable (default: PATH lookup).")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify", help="Verify Mermaid blocks parse.")
    verify_parser.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
