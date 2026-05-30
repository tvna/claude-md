#!/usr/bin/env python3
"""Client-side preflight: require a fresh origin/main observation.

PreToolUse hook for ``mcp__github__create_branch``. Denies the tool call
when no freshness stamp exists, or the stamp is older than the configured
TTL, meaning the operator has not confirmed origin/main state in the
current window.

The stamp file (``.git/MAIN_FRESHNESS_STAMP`` relative to the repository
root) is written by the ``record`` subcommand::

    python3 scripts/preflight_main_freshness.py record

The ``check`` subcommand prints the stamp state and exits 0 (fresh) or 1
(stale / missing)::

    python3 scripts/preflight_main_freshness.py check

When invoked with no subcommand the script acts as a PreToolUse hook,
reading the event JSON from stdin and writing a deny decision to stdout
when the guard fires. Any parse error causes the script to exit 0 (fail
open) so a hook bug cannot wedge the session.

Refs #654.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
STAMP_FILE = REPO_ROOT / ".git" / "MAIN_FRESHNESS_STAMP"
DEFAULT_TTL_SECONDS = 3600  # 1 hour

_TARGET_TOOLS: frozenset[str] = frozenset({"mcp__github__create_branch"})


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreshnessStamp:
    """A recorded observation of origin/main."""

    sha: str
    fetched_at: datetime


@dataclass(frozen=True)
class FreshnessResult:
    """Outcome of checking the freshness stamp."""

    status: str  # "fresh" | "stale" | "missing"
    detail: str
    stamp: FreshnessStamp | None = None


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(UTC)


def read_stamp(path: Path = STAMP_FILE) -> FreshnessStamp | None:
    """Return the stamp from *path*, or ``None`` if missing or malformed."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    data: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    sha = data.get("sha", "")
    fetched_at_str = data.get("fetched_at", "")
    if not sha or not fetched_at_str:
        return None
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
    except ValueError:
        return None
    return FreshnessStamp(sha=sha, fetched_at=fetched_at)


def write_stamp(sha: str, *, path: Path = STAMP_FILE) -> FreshnessStamp:
    """Write a freshness stamp for *sha* and return it."""
    now = _now_utc()
    path.write_text(f"sha={sha}\nfetched_at={now.isoformat()}\n", encoding="utf-8")
    return FreshnessStamp(sha=sha, fetched_at=now)


def check_freshness(
    *,
    path: Path = STAMP_FILE,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> FreshnessResult:
    """Return the freshness status of the stamp at *path*."""
    stamp = read_stamp(path)
    if stamp is None:
        return FreshnessResult(
            status="missing",
            detail=(
                "no origin/main freshness stamp found -- run "
                "`python3 scripts/preflight_main_freshness.py record`"
            ),
        )
    age = _now_utc() - stamp.fetched_at
    if age > timedelta(seconds=ttl_seconds):
        age_minutes = int(age.total_seconds() // 60)
        return FreshnessResult(
            status="stale",
            detail=(
                f"origin/main stamp is {age_minutes} minute(s) old "
                f"(TTL={ttl_seconds // 60} min, SHA={stamp.sha[:12]}) -- run "
                f"`python3 scripts/preflight_main_freshness.py record`"
            ),
            stamp=stamp,
        )
    age_seconds = int(age.total_seconds())
    return FreshnessResult(
        status="fresh",
        detail=f"origin/main is fresh (SHA={stamp.sha[:12]}, fetched {age_seconds}s ago)",
        stamp=stamp,
    )


def fetch_and_record(
    *,
    remote: str = "origin",
    branch: str = "main",
    repo: Path = REPO_ROOT,
    stamp_path: Path = STAMP_FILE,
) -> FreshnessStamp:
    """Fetch origin/main, resolve SHA, write stamp, and return it."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable not found on PATH")
    fetch = subprocess.run(  # noqa: S603
        [git, "fetch", "--quiet", remote, branch],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout).strip()
        raise RuntimeError(f"git fetch {remote} {branch} failed: {detail}")
    rev = subprocess.run(  # noqa: S603
        [git, "rev-parse", f"{remote}/{branch}"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if rev.returncode != 0:
        detail = (rev.stderr or rev.stdout).strip()
        raise RuntimeError(f"git rev-parse {remote}/{branch} failed: {detail}")
    sha = rev.stdout.strip()
    return write_stamp(sha, path=stamp_path)


def build_deny_reason(tool_name: str, result: FreshnessResult) -> str:
    """Return the deny reason for a stale or missing freshness stamp."""
    return (
        f"Blocked by scripts/preflight_main_freshness.py (Layer 2.5): "
        f"`{tool_name}` was called without a current observation of "
        f"origin/main. {result.detail}.\n\n"
        f"To record freshness and unblock:\n"
        f"  python3 scripts/preflight_main_freshness.py record\n\n"
        f"This guard prevents implementation from starting on a stale "
        f"view of main, so merge conflicts and integration failures are "
        f"caught at branch-creation time rather than during the PR review "
        f"loop. Refs #654."
    )


def decide(tool_name: str, _tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny dict if the freshness guard fires, or ``None`` to allow."""
    if tool_name not in _TARGET_TOOLS:
        return None
    result = check_freshness(path=STAMP_FILE)
    if result.status == "fresh":
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": build_deny_reason(tool_name, result),
        }
    }


def _build_deny_dict(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


# ---------------------------------------------------------------------------
# Side-effecting boundary
# ---------------------------------------------------------------------------


def _cmd_record(args: argparse.Namespace) -> int:
    try:
        stamp = fetch_and_record(remote=args.remote, branch=args.branch)
        print(f"OK: recorded origin/{args.branch} SHA={stamp.sha[:12]} at {stamp.fetched_at.isoformat()}")
        return 0
    except RuntimeError as exc:
        print(f"::error::preflight_main_freshness: {exc}", file=sys.stderr)
        return 1


def _cmd_check(args: argparse.Namespace) -> int:
    result = check_freshness(path=STAMP_FILE, ttl_seconds=args.ttl)
    if result.status == "fresh":
        print(f"OK: {result.detail}")
        return 0
    print(f"FAIL: {result.detail}", file=sys.stderr)
    return 1


def _hook_mode() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::preflight_main_freshness: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            "::error::preflight_main_freshness: event missing tool_name/tool_input",
            file=sys.stderr,
        )
        return 0

    decision = decide(tool_name, tool_input)
    if decision is None:
        return 0

    sys.stdout.write(json.dumps(decision))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_record = sub.add_parser("record", help="Fetch origin/main and write freshness stamp.")
    p_record.add_argument("--remote", default="origin", help="Remote name (default: origin).")
    p_record.add_argument("--branch", default="main", help="Branch to fetch (default: main).")
    p_record.set_defaults(func=_cmd_record)

    p_check = sub.add_parser("check", help="Check freshness stamp (exit 0=fresh, 1=stale/missing).")
    p_check.add_argument(
        "--ttl",
        type=int,
        default=DEFAULT_TTL_SECONDS,
        metavar="SECONDS",
        help=f"Freshness TTL in seconds (default: {DEFAULT_TTL_SECONDS}).",
    )
    p_check.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    if args.cmd is None:
        return _hook_mode()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
