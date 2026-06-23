#!/usr/bin/env python3
"""Reproducible backup of issues/PRs/comments before non-ASCII rewriting.

Operator-run companion to ``docs/prd/non-ascii-defense.md`` Layer 1. The release
asset itself is produced by ``gh release create`` (manual step); this CLI
normalises the API responses into a deterministic ``{schema_version,
captured_at, repo, items}`` payload and emits its SHA-256 so that
``scripts/translations.json::source_sha256`` and the P5 apply tool have a
stable anchor.

Pattern mirrors ``scripts/scan_non_ascii.py`` per issue #123: pure
functions on top, a single ``runner`` boundary at the bottom so tests
monkeypatch the subprocess call.

Refs #102.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _parent_number_from_url(url: str | None) -> int | None:
    if not url:
        return None
    tail = url.rsplit("/", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return None


def _normalise_issue_or_pr(raw: dict[str, Any]) -> dict[str, Any]:
    is_pr = bool(raw.get("pull_request"))
    return {
        "type": "pr" if is_pr else "issue",
        "id": raw.get("id"),
        "number": raw.get("number"),
        "comment_id": None,
        "title": raw.get("title") or "",
        "body": raw.get("body") or "",
        "author": (raw.get("user") or {}).get("login"),
        "state": raw.get("state"),
        "author_association": raw.get("author_association"),
    }


def _normalise_issue_comment(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "issue_comment",
        "id": raw.get("id"),
        "number": _parent_number_from_url(raw.get("issue_url")),
        "comment_id": raw.get("id"),
        "title": "",
        "body": raw.get("body") or "",
        "author": (raw.get("user") or {}).get("login"),
        "state": None,
        "author_association": raw.get("author_association"),
    }


def _normalise_pr_review_comment(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "pr_review_comment",
        "id": raw.get("id"),
        "number": _parent_number_from_url(raw.get("pull_request_url")),
        "comment_id": raw.get("id"),
        "title": "",
        "body": raw.get("body") or "",
        "author": (raw.get("user") or {}).get("login"),
        "state": None,
        "author_association": raw.get("author_association"),
    }


def normalise_items(
    issues_and_prs: list[dict[str, Any]],
    issue_comments: list[dict[str, Any]],
    pr_review_comments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Concatenate and stably sort all four item kinds.

    Sort key ``(type, id)`` is total ordering across kinds; id is the
    global GitHub object id and is unique within a kind.
    """
    items: list[dict[str, Any]] = []
    items.extend(_normalise_issue_or_pr(raw) for raw in issues_and_prs)
    items.extend(_normalise_issue_comment(raw) for raw in issue_comments)
    items.extend(_normalise_pr_review_comment(raw) for raw in pr_review_comments)
    items.sort(key=lambda it: (it["type"], it["id"] or 0))
    return items


def build_payload(
    *,
    repo: str,
    items: list[dict[str, Any]],
    captured_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": captured_at,
        "repo": repo,
        "items": items,
    }


def serialise_payload(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON bytes. ``ensure_ascii=False`` preserves original
    bytes so SHA matches what GitHub stores; ``sort_keys`` + compact
    separators kill cross-platform jitter.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def gzip_bytes(raw: bytes, *, mtime: int = 0) -> bytes:
    """Gzip with ``mtime=0`` so the same JSON always yields the same gz."""
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=mtime) as gz:
        gz.write(raw)
    return buf.getvalue()


def sha256_hex(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Subprocess boundary; monkeypatched in tests
# ---------------------------------------------------------------------------


def gh_paginate(
    path: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    timeout: int = 300,
) -> list[dict[str, Any]]:
    """Return every item from a paginated ``gh api`` array endpoint.

    Uses ``--paginate`` + ``--jq '.[]'`` so the output is one JSON object
    per line regardless of page count; that is easier to parse than the
    concatenated ``[...][...]`` shape that ``--paginate`` produces by
    default for array responses.

    Auth via the ambient ``GH_TOKEN``. ``runner`` defaults to
    ``subprocess.run`` resolved at call time so tests can monkeypatch
    ``backup_non_ascii.subprocess.run``. Raises
    :class:`subprocess.CalledProcessError` on any non-zero exit so callers
    fail loudly (CLAUDE.md section 4).
    """
    if runner is None:
        runner = subprocess.run
    cmd = ["gh", "api", "--paginate", path, "--jq", ".[]"]
    result = runner(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    out: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_capture(args: argparse.Namespace) -> int:
    repo = os.environ.get("REPO")
    if not repo:
        print("::error::REPO env var is required", file=sys.stderr)
        return 2
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("::error::GH_TOKEN env var is required", file=sys.stderr)
        return 2

    issues_and_prs = gh_paginate(f"/repos/{repo}/issues?state=all&per_page=100")
    issue_comments = gh_paginate(f"/repos/{repo}/issues/comments?per_page=100")
    pr_review_comments = gh_paginate(f"/repos/{repo}/pulls/comments?per_page=100")

    items = normalise_items(issues_and_prs, issue_comments, pr_review_comments)
    captured_at = os.environ.get("BACKUP_CAPTURED_AT") or _now_iso()
    payload = build_payload(repo=repo, items=items, captured_at=captured_at)
    raw = serialise_payload(payload)
    blob = gzip_bytes(raw)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    digest = sha256_hex(blob)
    print(f"wrote {out_path} ({len(blob)} bytes)")
    print(f"items: {len(items)}")
    print(f"sha256: {digest}")
    return 0


def cmd_sha256(args: argparse.Namespace) -> int:
    in_path = Path(args.input)
    blob = in_path.read_bytes()
    print(sha256_hex(blob))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup_non_ascii",
        description="Reproducible backup snapshot for #102 Layer 1.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_capture = sub.add_parser(
        "capture",
        help="Paginate the GitHub API and write a gzipped JSON snapshot.",
    )
    p_capture.add_argument("--out", required=True, help="Output path (.json.gz).")

    p_sha = sub.add_parser(
        "sha256",
        help="Print the SHA-256 of an existing snapshot file.",
    )
    p_sha.add_argument("--in", dest="input", required=True, help="Path to snapshot file.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "capture":
        return cmd_capture(args)
    if args.command == "sha256":
        return cmd_sha256(args)
    parser.error(f"unknown command: {args.command!r}")
    return 2  # unreachable; parser.error exits


if __name__ == "__main__":
    raise SystemExit(main())
