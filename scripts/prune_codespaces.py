#!/usr/bin/env python3
"""List and optionally delete inactive GitHub Codespaces for an organisation.

Only ``Shutdown`` codespaces whose ``last_used_at`` (or ``created_at`` when
never used) is older than ``--min-age-days`` are candidates. Running or
transitioning codespaces are never touched.

Deletion requires a PAT with ``admin:org`` scope (``GITHUB_TOKEN`` cannot
delete codespaces; the API returns 403). Supply it as ``GH_TOKEN``.
See ``docs/runbooks/devcontainers.md`` for the ``CODESPACES_CLEANUP_TOKEN``
issuance path.

Usage::

    python3 scripts/prune_codespaces.py prune \\
        --org ORG \\
        --min-age-days DAYS \\
        --dry-run true|false \\
        [--summary-file PATH]

Environment variables:
    GH_TOKEN  PAT with ``admin:org`` scope on the target organisation.

Exit codes:
    0  Success (dry-run preview, or every candidate deleted).
    1  Missing token, bad argument, API list failure, or any failed delete.

Contract:
- Inputs: ``prune`` subcommand; ``--org``, ``--min-age-days`` (int),
  ``--dry-run`` (true/false string), optional ``--summary-file``; ``GH_TOKEN``
  env var (required).
- Outputs: per-codespace plan/result to stdout and, when ``--summary-file``
  is given, an appended Markdown report; exit 0 on success, 1 on failure.
- Failure policy: fails loud per CLAUDE.md section 4; a missing token, an
  API list error, or any failed delete exits non-zero.

Tested by ``tests/test_prune_codespaces.py``. Refs #1930.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _github_api import apply_call

API_ROOT = "https://api.github.com"
_PER_PAGE = 100
# Defensive cap so a pathological response cannot loop forever (CWE-835).
_MAX_PAGES = 100

# States that indicate a codespace is idle and safe to delete.
_DELETABLE_STATES = frozenset({"Shutdown"})

Opener = Callable[[Any], Any]


def parse_bool(value: str) -> bool:
    """Return the boolean for *value*, raising on anything ambiguous.

    Accepts ``true``/``false`` (case-insensitive). A workflow that passes an
    unexpected token (e.g. an unrendered ``${{ }}`` expression) fails loud
    rather than defaulting to a destructive real delete.
    """
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"expected 'true' or 'false' for --dry-run, got: {value!r}")


def _activity_time(codespace: dict[str, Any]) -> datetime:
    """Return the most-recent activity timestamp for *codespace*.

    Prefers ``last_used_at``; falls back to ``created_at`` for codespaces
    that were never opened. A missing or unparseable field sorts as epoch
    (oldest) so such a codespace is never accidentally excluded from cleanup.
    """
    for field in ("last_used_at", "created_at"):
        raw = codespace.get(field)
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
    return datetime.fromtimestamp(0, tz=UTC)


def select_candidates(
    codespaces: list[dict[str, Any]],
    min_age_days: int,
    now: datetime,
) -> list[dict[str, Any]]:
    """Return codespaces eligible for deletion under the idle-age policy.

    A codespace qualifies when its state is in :data:`_DELETABLE_STATES`
    **and** its most-recent activity is older than *min_age_days* before
    *now*. Running or transitioning codespaces are never returned.
    """
    if min_age_days < 0:
        raise ValueError("--min-age-days must be non-negative")
    cutoff = now - timedelta(days=min_age_days)
    return [
        cs
        for cs in codespaces
        if cs.get("state") in _DELETABLE_STATES and _activity_time(cs) < cutoff
    ]


def _list_codespaces(
    org: str,
    token: str,
    *,
    opener: Opener | None = None,
) -> list[dict[str, Any]]:
    """Return every codespace for *org*.

    Pages through ``GET /orgs/{org}/codespaces`` until a short page is
    returned. Raises ``RuntimeError`` on any non-2xx response so a list
    failure fails loud instead of silently pruning against an empty set.
    """
    results: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        url = f"{API_ROOT}/orgs/{org}/codespaces?per_page={_PER_PAGE}&page={page}"
        code, body = _call(method="GET", url=url, token=token, opener=opener)
        if not (200 <= code < 300):
            raise RuntimeError(f"listing codespaces failed: HTTP {code}: {body[:200]}")
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"unexpected response: {body[:200]}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"expected an object, got: {body[:200]}")
        chunk = data.get("codespaces", [])
        if not isinstance(chunk, list):
            raise RuntimeError(f"'codespaces' field is not a list: {body[:200]}")
        results.extend(chunk)
        if len(chunk) < _PER_PAGE:
            break
    return results


def _delete_codespace(
    org: str,
    username: str,
    name: str,
    token: str,
    *,
    opener: Opener | None = None,
) -> tuple[int, str]:
    """Delete one codespace. Returns ``(status, body)`` of the API call.

    GitHub returns 202 (Accepted) for an async delete; any 2xx is treated
    as success by the caller. The organisation member delete endpoint
    requires the owner's login as a path parameter.
    """
    url = f"{API_ROOT}/orgs/{org}/members/{username}/codespaces/{name}"
    return _call(method="DELETE", url=url, token=token, opener=opener)


def _call(
    *, method: str, url: str, token: str, opener: Opener | None
) -> tuple[int, str]:
    """Thin seam over ``_github_api.apply_call`` so tests can inject an opener."""
    if opener is None:
        return apply_call(method=method, url=url, payload=None, token=token)
    return apply_call(method=method, url=url, payload=None, token=token, opener=opener)


def _format_report(
    candidates: list[dict[str, Any]],
    mode: str,
    deleted: int,
    failures: list[str],
) -> list[str]:
    """Return Markdown report lines for the prune run."""
    lines = [f"## Codespace prune ({mode})", ""]
    if not candidates:
        lines += ["- no Shutdown codespaces older than the threshold", ""]
        return lines
    for cs in candidates:
        name = cs.get("name", "?")
        owner = cs.get("owner", {}).get("login", "?") if isinstance(cs.get("owner"), dict) else "?"
        repo = cs.get("repository", {}).get("full_name", "?") if isinstance(cs.get("repository"), dict) else "?"
        last = cs.get("last_used_at") or cs.get("created_at") or "?"
        lines.append(f"- `{name}` owner={owner} repo={repo} last_used={last}")
    lines.append("")
    if mode != "dry-run":
        lines.append(f"Deleted {deleted} codespace(s); {len(failures)} failure(s).")
        lines.append("")
    return lines


def cmd_prune(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("Error: GH_TOKEN environment variable is required", file=sys.stderr)
        return 1

    try:
        dry_run = parse_bool(args.dry_run)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        codespaces = _list_codespaces(args.org, token)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    now = datetime.now(UTC)
    candidates = select_candidates(codespaces, args.min_age_days, now)
    mode = "dry-run" if dry_run else "delete"
    print(
        f"{args.org}: {len(codespaces)} codespace(s) found, "
        f"{len(candidates)} candidate(s) to prune ({mode})"
    )
    for cs in candidates:
        name = cs.get("name", "?")
        last = cs.get("last_used_at") or cs.get("created_at") or "?"
        print(f"  candidate: {name} (last_used={last})")

    deleted = 0
    failures: list[str] = []

    if not dry_run:
        for cs in candidates:
            name = cs.get("name")
            if not name:
                failures.append("codespace missing name, skipped")
                continue
            username = cs.get("owner", {}).get("login") if isinstance(cs.get("owner"), dict) else None
            if not username:
                failures.append(f"{name}: missing owner login, skipped")
                continue
            code, body = _delete_codespace(args.org, username, name, token)
            if 200 <= code < 300:
                deleted += 1
                print(f"  deleted: {name}")
            else:
                failures.append(f"{name}: HTTP {code}: {body[:120]}")

    report = _format_report(candidates, mode, deleted, failures)
    if args.summary_file:
        with Path(args.summary_file).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(report) + "\n")

    for failure in failures:
        print(f"::error::failed to delete {failure}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune inactive GitHub Codespaces.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    prune = sub.add_parser("prune", help="Delete Shutdown codespaces older than --min-age-days.")
    prune.add_argument("--org", required=True, help="GitHub organisation login.")
    prune.add_argument(
        "--min-age-days",
        type=int,
        required=True,
        help="Delete only codespaces idle longer than this many days.",
    )
    prune.add_argument("--dry-run", required=True, help="'true' to preview, 'false' to delete.")
    prune.add_argument("--summary-file", default=None, help="Append a Markdown report to this file.")
    prune.set_defaults(func=cmd_prune)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
