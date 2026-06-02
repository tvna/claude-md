#!/usr/bin/env python3
"""Fetch GitHub REST API endpoints.

Usage::

    python3 scripts/github_paginate.py fetch \\
        --path PATH --output FILE

    python3 scripts/github_paginate.py get \\
        --path PATH [--output FILE] [--field NAME]

``fetch`` follows ``Link: <next>; rel="next"`` headers until all pages are
consumed and writes the combined JSON array to ``FILE``.

``get`` makes a single request to a non-paginated endpoint.  Use ``--output``
to write the raw JSON body to a file, ``--field`` to print one top-level JSON
field to stdout; at least one of the two is required.

``PATH`` is appended to ``https://api.github.com/`` in both subcommands.

Environment variables:
    GH_TOKEN  GitHub token with repo read scope.

Exit codes:
    0  Success.
    1  Missing env var, missing argument, or API error.
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


def _get_single(
    *,
    url: str,
    token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    """Make a single GET request and return the raw response body as a string."""
    request = urllib.request.Request(url, method="GET")  # noqa: S310 — fixed https://api.github.com endpoint
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", _API_VERSION)

    try:
        with opener(request) as response:
            code = int(response.status)
            body_str = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        code = int(error.code)
        body_str = error.read().decode("utf-8", errors="replace")

    if not (200 <= code < 300):
        raise RuntimeError(f"Request failed: HTTP {code}: {body_str[:200]}")
    return body_str


def _cmd_get(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("Error: GH_TOKEN environment variable is required", file=sys.stderr)
        return 1
    if not args.output and not args.field:
        print("Error: at least one of --output or --field is required", file=sys.stderr)
        return 1

    url = f"{_API_ROOT}/{args.path.lstrip('/')}"
    try:
        body_str = _get_single(url=url, token=token)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(body_str, encoding="utf-8")

    if args.field:
        try:
            data = json.loads(body_str)
        except json.JSONDecodeError as exc:
            print(f"Error: invalid JSON response: {exc}", file=sys.stderr)
            return 1
        value = data.get(args.field)
        if value is None:
            print(f"Error: field '{args.field}' not found in response", file=sys.stderr)
            return 1
        print(value)

    return 0


def extract_run_ids(runs_json_text: str) -> list[int]:
    """Return the ``workflow_runs[].id`` values from a runs API response body.

    Returns an empty list when the ``workflow_runs`` key is absent or empty.
    Raises ValueError when the body is not valid JSON.
    """
    try:
        data = json.loads(runs_json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    runs = data.get("workflow_runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        return []
    return [int(run["id"]) for run in runs if isinstance(run, dict) and "id" in run]


def _cmd_fetch_run_jobs(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("Error: GH_TOKEN environment variable is required", file=sys.stderr)
        return 1

    try:
        run_ids = extract_run_ids(Path(args.runs).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for run_id in run_ids:
        url = f"{_API_ROOT}/repos/{args.repo}/actions/runs/{run_id}/jobs"
        try:
            body_str = _get_single(url=url, token=token)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        (outdir / f"{run_id}.json").write_text(body_str, encoding="utf-8")

    print(f"Wrote jobs for {len(run_ids)} runs to {outdir}")
    return 0


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

    get_p = sub.add_parser("get", help="Fetch a single-page endpoint; write JSON to --output and/or print --field to stdout")
    get_p.add_argument("--path", required=True, help="API path (appended to https://api.github.com/)")
    get_p.add_argument("--output", default=None, help="Output file path for raw JSON response body")
    get_p.add_argument("--field", default=None, help="Top-level JSON field name to print to stdout")

    jobs_p = sub.add_parser(
        "fetch-run-jobs",
        help="Read workflow_runs[].id from a runs JSON file and write each run's jobs to --outdir/<id>.json",
    )
    jobs_p.add_argument("--runs", required=True, help="Path to a runs API response JSON file")
    jobs_p.add_argument("--repo", required=True, help="Repository in owner/repo format")
    jobs_p.add_argument("--outdir", required=True, help="Directory to write per-run jobs JSON files")

    args = parser.parse_args(argv)

    if args.cmd == "fetch":
        return _cmd_fetch(args)
    if args.cmd == "get":
        return _cmd_get(args)
    if args.cmd == "fetch-run-jobs":
        return _cmd_fetch_run_jobs(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
