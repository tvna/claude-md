#!/usr/bin/env python3
"""Assemble the non-ASCII originals backup archive.

Replaces the inline ``python3 - <<'EOF'`` heredoc in
``.github/workflows/backup-non-ascii-originals.yml``: it reads the four
GitHub REST captures (issues, pull requests, issue comments, PR review
comments) from a directory, combines them into a single payload with
capture metadata, and writes an ASCII-only gzip archive.

Usage::

    python3 scripts/backup_archive.py build \\
        --indir /tmp/backup --timestamp 20260602T0000Z \\
        --repo owner/repo --archive /tmp/backup/originals-20260602T0000Z.json.gz

Exit codes:
    0  Archive written.
    1  A source capture is missing or malformed.
    2  Usage error.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

# (payload key, capture filename) pairs, in archive order.
_SOURCES: tuple[tuple[str, str], ...] = (
    ("issues", "issues.json"),
    ("pull_requests", "pull_requests.json"),
    ("issue_comments", "issue_comments.json"),
    ("pull_request_review_comments", "pull_request_review_comments.json"),
)


def build_payload(
    *,
    indir: Path,
    timestamp: str,
    repo: str,
    sources: tuple[tuple[str, str], ...] = _SOURCES,
) -> tuple[dict, list[tuple[str, int]]]:
    """Read each capture file and return the combined payload and per-source counts.

    Raises ValueError when a source file is missing or does not contain a JSON
    list (fail loud rather than archive a partial backup).
    """
    payload: dict = {"captured_at": timestamp, "repo": repo}
    counts: list[tuple[str, int]] = []
    for key, fname in sources:
        path = indir / fname
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"missing capture file: {path} ({exc})") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError(f"expected a JSON list in {path}, got {type(data).__name__}")
        payload[key] = data
        counts.append((key, len(data)))
    return payload, counts


def write_gzip(payload: dict, archive: Path) -> None:
    """Write ``payload`` as an ASCII-only, unindented JSON gzip archive."""
    with gzip.open(archive, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=True, indent=None)


def _cmd_build(args: argparse.Namespace) -> int:
    try:
        payload, counts = build_payload(
            indir=Path(args.indir),
            timestamp=args.timestamp,
            repo=args.repo,
        )
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    for key, count in counts:
        print(f"{key}: {count} items", flush=True)

    archive = Path(args.archive)
    write_gzip(payload, archive)
    print(f"Archive: {archive}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the non-ASCII originals backup archive.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build_p = sub.add_parser("build", help="Combine captures into a gzip archive")
    build_p.add_argument("--indir", default="/tmp/backup", help="Directory holding the capture JSON files")  # noqa: S108
    build_p.add_argument("--timestamp", required=True, help="Capture timestamp recorded in the archive")
    build_p.add_argument("--repo", required=True, help="Repository in owner/repo format")
    build_p.add_argument("--archive", required=True, help="Output path for the gzip archive")

    args = parser.parse_args(argv)

    if args.cmd == "build":
        return _cmd_build(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
