#!/usr/bin/env python3
"""CLI wrapper for GitHub REST API read operations.

Agents call this script instead of `gh` CLI or raw curl to reduce token
consumption: the ``--fields`` option extracts only the JSON keys needed,
keeping context lean.

Usage:
    python3 scripts/github_api.py METHOD URL [--fields f1,f2,...] [--token TOKEN]

    METHOD  HTTP method: GET, POST, PATCH, DELETE
    URL     Full https://api.github.com/... URL

Options:
    --fields   Comma-separated top-level JSON keys to keep (array or object).
               Omit to return the full response body.
    --token    GitHub token. Default: GH_TOKEN environment variable.

Exit codes:
    0   HTTP 2xx response (body written to stdout)
    1   HTTP error or network failure (message written to stderr)
    2   Usage error

Examples:
    # List open issues, return only number/title/state
    python3 scripts/github_api.py GET \
        https://api.github.com/repos/owner/repo/issues?state=open \
        --fields number,title,state

    # Get a single issue
    python3 scripts/github_api.py GET \
        https://api.github.com/repos/owner/repo/issues/123

Refs #887.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _github_api import apply_call


def _filter_fields(data: Any, fields: list[str]) -> Any:
    """Return *data* with only *fields* kept (top-level only).

    Works for a JSON object (dict) or an array of objects (list).
    Non-dict items in arrays are returned as-is.
    """
    if not fields:
        return data
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [
            {k: v for k, v in item.items() if k in fields}
            if isinstance(item, dict)
            else item
            for item in data
        ]
    return data


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="GitHub REST API wrapper for agents.",
        add_help=True,
    )
    parser.add_argument("method", help="HTTP method (GET, POST, PATCH, DELETE)")
    parser.add_argument("url", help="Full https://api.github.com/... URL")
    parser.add_argument(
        "--fields",
        default="",
        help="Comma-separated top-level JSON keys to keep (omit for full response)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="GitHub token (default: GH_TOKEN env var)",
    )
    parser.add_argument(
        "--payload",
        default="",
        help="JSON payload string for POST/PATCH (optional)",
    )

    args = parser.parse_args(argv)

    token = args.token or os.environ.get("GH_TOKEN", "")
    if not token:
        print("error: no GitHub token; set GH_TOKEN or pass --token", file=sys.stderr)
        return 2

    if not args.url.startswith("https://api.github.com/"):
        print(
            f"error: URL must start with https://api.github.com/ (got {args.url!r})",
            file=sys.stderr,
        )
        return 2

    payload: dict[str, Any] | None = None
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            print(f"error: --payload is not valid JSON: {exc}", file=sys.stderr)
            return 2

    code, body = apply_call(
        method=args.method.upper(),
        url=args.url,
        payload=payload,
        token=token,
    )

    if not (200 <= code < 300):
        print(f"error: HTTP {code}: {body}", file=sys.stderr)
        return 1

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    if fields:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            sys.stdout.write(body)
            return 0
        sys.stdout.write(json.dumps(_filter_fields(data, fields), indent=2))
    else:
        sys.stdout.write(body)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
