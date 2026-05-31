#!/usr/bin/env python3
"""Fetch paginated GitHub REST API list endpoints.

Usage::

    python3 scripts/github_paginate.py fetch \\
        --path PATH --output FILE

``PATH`` is appended to ``https://api.github.com/``.  The script follows
``Link: <next>; rel="next"`` headers until all pages are consumed, writes the
combined JSON array to ``FILE``.

Environment variables:
    GH_TOKEN  GitHub token with repo read scope.

Exit codes:
    0  Success.
    1  Missing env var or API error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

_API_ROOT = "https://api.github.com"
_API_VERSION = "2022-11-28"


def _paginate_get(
    *,
    url: str,
    token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    """Fetch all pages from a GitHub REST API list endpoint.

    Follows ``Link: <...>; rel="next"`` headers until exhausted.
    """
    results: list[dict[str, Any]] = []
    next_url: str | None = url

    while next_url:
        request = urllib.request.Request(next_url, method="GET")  # noqa: S310 — fixed https://api.github.com endpoint
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", _API_VERSION)

        try:
            with opener(request) as response:
                code = int(response.status)
                body_str = response.read().decode("utf-8", errors="replace")
                link_header = str(response.headers.get("Link") or "")
        except urllib.error.HTTPError as error:
            code = int(error.code)
            body_str = error.read().decode("utf-8", errors="replace")
            link_header = ""

        if not (200 <= code < 300):
            raise RuntimeError(f"Fetch failed: HTTP {code}: {body_str[:200]}")

        try:
            page_data = json.loads(body_str)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Unexpected response: {body_str[:200]}") from exc

        if not isinstance(page_data, list):
            raise RuntimeError(f"Expected list, got: {body_str[:200]}")

        results.extend(page_data)

        next_url = None
        if link_header:
            match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
            if match:
                next_url = match.group(1)

    return results


def _cmd_fetch(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("Error: GH_TOKEN environment variable is required", file=sys.stderr)
        return 1

    url = f"{_API_ROOT}/{args.path.lstrip('/')}"
    try:
        data = _paginate_get(url=url, token=token)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    Path(args.output).write_text(json.dumps(data), encoding="utf-8")
    print(f"Wrote {len(data)} items to {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch paginated GitHub REST API endpoints.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    fetch_p = sub.add_parser("fetch", help="Fetch all pages from a list endpoint and write JSON")
    fetch_p.add_argument("--path", required=True, help="API path (appended to https://api.github.com/)")
    fetch_p.add_argument("--output", required=True, help="Output file path for JSON array")

    args = parser.parse_args(argv)

    if args.cmd == "fetch":
        return _cmd_fetch(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
