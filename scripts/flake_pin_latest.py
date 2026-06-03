#!/usr/bin/env python3
"""Decide whether a flake-pinned tool should follow its latest GitHub Release.

This is the *decision* half of the flake-pin auto-follow loop (``flake_pin.py``
is the writer; the refresh workflow recomputes hashes). For a given tool it:

1. reads the currently pinned version from ``flake.nix`` (via ``flake_pin``);
2. fetches the latest GitHub Release tag for the tool's repo;
3. enforces a cooldown window -- the release's ``published_at`` must be at
   least ``[tool.uv].exclude-newer`` days old (the same freshness budget the
   repository already applies to Python packages and the locked nixpkgs, reused
   here as the single source of truth, mirroring ``nixpkgs_cooldown.py``).

It prints the adoptable target version to stdout when an update is available
*and* past cooldown, otherwise prints nothing. Exit code is 0 in both cases so
the workflow can branch on stdout; it exits non-zero only on a real error
(unreadable flake, malformed API response, unparseable version), failing loud
rather than silently skipping a bump (CLAUDE.md section 4).

The network fetch is injected, so the cooldown/comparison logic is unit-tested
without hitting GitHub.

CLI::

    python3 scripts/flake_pin_latest.py check --tool waza
        # prints e.g. "0.34.0" (adoptable) or nothing (hold)

Tested by ``tests/test_flake_pin_latest.py``. Refs #1171, #643.

Contract:
    Inputs: the ``check --tool <tool>`` subcommand; ``flake.nix`` (the pinned
        version), ``pyproject.toml`` (``[tool.uv].exclude-newer`` cooldown), and
        the GitHub ``releases/latest`` API (token read from ``GH_TOKEN`` /
        ``GITHUB_TOKEN`` env). No stdin.
    Outputs: prints the adoptable target version to stdout when a newer release
        is past the cooldown window, otherwise prints nothing; exit 0 in both
        the adopt and hold cases so the workflow branches on stdout.
    Failure policy: fails loud per CLAUDE.md section 4 -- a non-2xx API status,
        a non-JSON / non-object body, a missing ``tag_name`` / ``published_at``,
        or an unparseable version exits non-zero rather than silently holding.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
import types
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _load(module_name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name, REPO_ROOT / "scripts" / f"{module_name}.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sibling script {module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


flake_pin = _load("flake_pin")
nixpkgs_cooldown = _load("nixpkgs_cooldown")
_github_api = _load("_github_api")


class LatestPinError(RuntimeError):
    """Raised when the latest-release decision cannot be made safely."""


# A fetcher takes "owner/name" and returns the parsed /releases/latest JSON.
Fetcher = Callable[[str], dict]


def github_latest_release(repo: str) -> dict:
    """Fetch ``/repos/<repo>/releases/latest`` via the approved API wrapper.

    Uses ``scripts/_github_api.apply_call`` (CLAUDE.md section 3: read through
    the repository's approved REST wrapper, not raw HTTP) with the workflow
    token from the environment. Fails loud on a non-2xx status or non-JSON body.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    code, body = _github_api.apply_call(
        method="GET", url=url, payload=None, token=token
    )
    if not 200 <= code < 300:
        raise LatestPinError(
            f"GitHub API returned HTTP {code or '000'} for {repo} latest release"
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LatestPinError(f"GitHub API returned non-JSON for {repo}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LatestPinError(f"GitHub API returned non-object for {repo}: {body[:80]!r}")
    return payload


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse a dotted numeric version into a comparable tuple."""
    bare = version.strip().lstrip("vV")
    parts = bare.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError as exc:
        raise LatestPinError(f"unparseable version: {version!r}") from exc


def _parse_release(payload: dict, repo: str) -> tuple[str, dt.datetime]:
    """Extract ``(bare_version, published_at)`` from a release payload."""
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise LatestPinError(f"latest release for {repo} has no tag_name")
    published = payload.get("published_at")
    if not isinstance(published, str) or not published:
        raise LatestPinError(f"latest release for {repo} has no published_at")
    try:
        when = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LatestPinError(
            f"latest release for {repo} has bad published_at {published!r}"
        ) from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    return tag.lstrip("vV"), when


def decide(
    tool: str,
    *,
    flake_text: str,
    fetcher: Fetcher,
    cooldown_days: int,
    now: dt.datetime | None = None,
) -> str | None:
    """Return the adoptable target version, or ``None`` to hold.

    Holds (returns ``None``) when the latest release is not newer than the pin
    or has not yet aged past the cooldown window. Raises ``LatestPinError`` on
    any malformed input -- never silently treats an error as "hold".
    """
    if now is None:
        now = dt.datetime.now(dt.UTC)
    if cooldown_days < 0:
        raise LatestPinError(f"cooldown_days must be >= 0, got {cooldown_days}")

    spec = flake_pin.tool_spec(tool)
    pinned = flake_pin.current_version(flake_text, tool)
    latest, published = _parse_release(fetcher(spec.github_repo), spec.github_repo)

    if _version_tuple(latest) <= _version_tuple(pinned):
        return None

    age = now - published
    if age < dt.timedelta(days=cooldown_days):
        return None

    return latest


def _cmd_check(args: argparse.Namespace) -> int:
    cooldown_days = nixpkgs_cooldown.read_uv_cooldown_days(PYPROJECT_PATH)
    target = decide(
        args.tool,
        flake_text=flake_pin.read_flake_text(),
        fetcher=github_latest_release,
        cooldown_days=cooldown_days,
    )
    if target is not None:
        print(target)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="print adoptable target version or nothing")
    p_check.add_argument("--tool", required=True, choices=sorted(flake_pin.TOOLS))
    p_check.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (LatestPinError, flake_pin.FlakePinError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
