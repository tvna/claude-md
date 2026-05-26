#!/usr/bin/env python3
"""Maintain the committed checksum lock for APM source files.

The lockfile is ``.apm/CHECKSUMS``. Each non-empty row is:

    sha256  .apm/path/to/file

Only regular files under ``.apm/`` are covered. The lockfile itself is
excluded so an update does not recursively change its own digest.
Refs #311.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

LOCKFILE_REL = Path(".apm/CHECKSUMS")
APM_DIR_REL = Path(".apm")
HASH_LEN = 64


@dataclass(frozen=True)
class ChecksumRow:
    digest: str
    path: Path


def _display(path: Path) -> str:
    return path.as_posix()


def _repo_path(root: Path, rel: Path) -> Path:
    return root / rel


def _iter_apm_files(root: Path) -> list[Path]:
    apm_dir = _repo_path(root, APM_DIR_REL)
    if not apm_dir.is_dir():
        raise FileNotFoundError(f"missing APM directory: {_display(APM_DIR_REL)}")

    files: list[Path] = []
    for path in apm_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel == LOCKFILE_REL:
            continue
        files.append(rel)
    return sorted(files, key=_display)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_checksums(root: Path) -> dict[Path, str]:
    return {rel: _sha256(_repo_path(root, rel)) for rel in _iter_apm_files(root)}


def format_checksums(checksums: dict[Path, str]) -> str:
    lines = [f"{digest}  {_display(path)}" for path, digest in sorted(checksums.items(), key=lambda item: _display(item[0]))]
    return "\n".join(lines) + "\n"


def parse_lockfile(text: str) -> tuple[dict[Path, str], list[str]]:
    rows: dict[Path, str] = {}
    errors: list[str] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        parts = raw_line.split()
        if len(parts) != 2:
            errors.append(f"line {lineno}: expected '<sha256>  <path>'")
            continue
        digest, path_text = parts
        rel = Path(path_text)
        if len(digest) != HASH_LEN or any(ch not in "0123456789abcdef" for ch in digest):
            errors.append(f"line {lineno}: invalid sha256 digest")
        if rel.is_absolute() or ".." in rel.parts or rel.parts[:1] != (".apm",):
            errors.append(f"line {lineno}: path must be a relative .apm/ path")
        if rel == LOCKFILE_REL:
            errors.append(f"line {lineno}: lockfile must not checksum itself")
        if rel in rows:
            errors.append(f"line {lineno}: duplicate path {_display(rel)}")
        rows[rel] = digest
    return rows, errors


def _read_lockfile(root: Path) -> tuple[dict[Path, str], list[str]]:
    lockfile = _repo_path(root, LOCKFILE_REL)
    if not lockfile.exists():
        return {}, [f"missing lockfile: {_display(LOCKFILE_REL)}"]
    return parse_lockfile(lockfile.read_text(encoding="utf-8"))


def verify(root: Path) -> list[str]:
    expected, errors = _read_lockfile(root)
    if errors:
        return errors

    actual = build_checksums(root)
    actual_paths = set(actual)
    expected_paths = set(expected)
    problems: list[str] = []

    for rel in sorted(expected_paths - actual_paths, key=_display):
        problems.append(f"missing file listed in lockfile: {_display(rel)}")
    for rel in sorted(actual_paths - expected_paths, key=_display):
        problems.append(f"new file missing from lockfile: {_display(rel)}")
    for rel in sorted(actual_paths & expected_paths, key=_display):
        if actual[rel] != expected[rel]:
            problems.append(f"checksum mismatch: {_display(rel)}")
    return problems


def update(root: Path) -> None:
    lockfile = _repo_path(root, LOCKFILE_REL)
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    lockfile.write_text(format_checksums(build_checksums(root)), encoding="utf-8")


def _cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        problems = verify(root)
    except FileNotFoundError as exc:
        problems = [str(exc)]
    if problems:
        for problem in problems:
            print(f"::error::{problem}", file=sys.stderr)
        print(f"FAIL: {len(problems)} APM checksum problem(s).", file=sys.stderr)
        return 1
    print("OK: .apm/CHECKSUMS matches APM source files.")
    return 0


def _cmd_update(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        update(root)
    except FileNotFoundError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"Updated {_display(LOCKFILE_REL)}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root. Defaults to the current working directory.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser("verify", help="Verify .apm/CHECKSUMS.")
    p_verify.set_defaults(func=_cmd_verify)

    p_update = sub.add_parser("update", help="Regenerate .apm/CHECKSUMS.")
    p_update.set_defaults(func=_cmd_update)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
