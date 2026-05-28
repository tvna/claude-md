#!/usr/bin/env python3
"""Verify that the pinned nixpkgs input respects uv's cooldown window.

The repository already delays Python package adoption through
``[tool.uv].exclude-newer``. Devcontainer packages are pinned through
``flake.lock``, so this gate reuses the uv cooldown as the single source
of truth and fails when the locked nixpkgs revision is newer than that
window.

Tested by ``tests/test_nixpkgs_cooldown.py``. Refs #643.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import tomllib

_EXCLUDE_NEWER_RE = re.compile(r"^(?P<days>[1-9][0-9]*) days?$")


def read_uv_cooldown_days(pyproject_path: Path) -> int:
    """Return the cooldown days from ``[tool.uv].exclude-newer``."""
    try:
        with pyproject_path.open("rb") as fp:
            data = tomllib.load(fp)
    except FileNotFoundError as exc:
        raise ValueError(f"cannot read {pyproject_path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"malformed TOML in {pyproject_path}: {exc}") from exc

    try:
        raw = data["tool"]["uv"]["exclude-newer"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"missing [tool.uv].exclude-newer in {pyproject_path}") from exc

    if not isinstance(raw, str):
        raise ValueError(f"exclude-newer must be a string, got: {raw!r}")

    match = _EXCLUDE_NEWER_RE.fullmatch(raw.strip())
    if match is None:
        raise ValueError(f"exclude-newer must be '<N> days', got: {raw!r}")
    return int(match.group("days"))


def read_nixpkgs_last_modified(flake_lock_path: Path) -> int:
    """Return the ``lastModified`` epoch for the locked nixpkgs input."""
    try:
        data = json.loads(flake_lock_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"cannot read {flake_lock_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {flake_lock_path}: {exc}") from exc

    try:
        last_modified = data["nodes"]["nixpkgs"]["locked"]["lastModified"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"missing nodes.nixpkgs.locked.lastModified in {flake_lock_path}") from exc

    if not isinstance(last_modified, int) or last_modified <= 0:
        raise ValueError(f"nixpkgs lastModified must be a positive integer, got: {last_modified!r}")
    return last_modified


def verify_cooldown(repo_root: Path, now_epoch: int | None = None) -> list[str]:
    """Return cooldown errors for *repo_root*; empty means clean."""
    cooldown_days = read_uv_cooldown_days(repo_root / "pyproject.toml")
    last_modified = read_nixpkgs_last_modified(repo_root / "flake.lock")
    now = int(time.time()) if now_epoch is None else now_epoch
    minimum_age_seconds = cooldown_days * 24 * 60 * 60
    actual_age_seconds = now - last_modified

    if actual_age_seconds < minimum_age_seconds:
        actual_days = max(0, actual_age_seconds) / (24 * 60 * 60)
        return [
            "flake.lock nixpkgs input is newer than "
            f"[tool.uv].exclude-newer ({cooldown_days} days): "
            f"age={actual_days:.2f} days"
        ]
    return []


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    errors = verify_cooldown(repo_root, args.now_epoch)
    for err in errors:
        print(f"::error::{err}")
    if errors:
        print("::error::nixpkgs cooldown check failed")
        return 1
    print("OK: nixpkgs lock respects [tool.uv].exclude-newer cooldown.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser("verify", help="Check nixpkgs lock cooldown.")
    p_verify.add_argument("--repo-root", default=".")
    p_verify.add_argument("--now-epoch", type=int, default=None)
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
