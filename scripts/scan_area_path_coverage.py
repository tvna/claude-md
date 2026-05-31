#!/usr/bin/env python3
"""Verify area-label to repository-path coverage in the label policy.

Refs #976. ``.github/label-policy.toml`` declares an ``area:*`` label family
and an ``area_paths`` table mapping each area to the files and directories it
owns. ``docs/standards/label-taxonomy.md`` promises the mapping is
conservative: "a new top-level directory, hidden configuration directory, or
generated-document lane must add an ``area:*`` mapping in the same design issue
that introduces it." Nothing enforced that promise, so a new top-level
directory could ship with no owning area, a declared area could have no paths,
or an ``area_paths`` entry could point at an undeclared area -- and no test
would catch it.

This scan is the deterministic gate. It fails loudly when the ``area:*``
family and the ``area_paths`` mapping disagree with each other or with the
repository tree.

Exit codes:
* ``0`` -- every area is mapped, every mapping targets a declared area, and
  every top-level directory is claimed by at least one area glob.
* ``1`` -- at least one of those invariants is violated.

Tested by ``tests/test_scan_area_path_coverage.py``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = Path(".github/label-policy.toml")
_GIT_TIMEOUT_SECONDS = 15

# A runner takes a git argument vector (sans the ``git`` executable) and the
# working directory, and returns stdout. The default boundary shells out;
# tests inject a stub so coverage logic stays free of subprocess concerns.
GitRunner = Callable[[list[str], Path], str]


def _run_git(args: list[str], cwd: Path) -> str:
    """Run ``git <args>`` in *cwd* and return stdout, raising on failure."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable not found on PATH")
    completed = subprocess.run(  # noqa: S603 -- argv built from hard-coded literals
        [git, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def load_policy(path: Path) -> dict[str, Any]:
    """Parse the TOML policy file into a dictionary."""
    with path.open("rb") as handle:
        return tomllib.load(handle)


def declared_area_labels(policy: dict[str, Any]) -> set[str]:
    """Return the names of every label in the ``area`` family."""
    labels = policy.get("labels", [])
    return {
        str(label["name"])
        for label in labels
        if isinstance(label, dict) and label.get("family") == "area" and "name" in label
    }


def area_path_entries(policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the ``[[area_paths]]`` table entries as a list of dictionaries."""
    return [entry for entry in policy.get("area_paths", []) if isinstance(entry, dict)]


def mapped_areas(policy: dict[str, Any]) -> set[str]:
    """Return the set of area names referenced by ``area_paths`` entries."""
    return {str(entry["area"]) for entry in area_path_entries(policy) if isinstance(entry.get("area"), str)}


def glob_top_levels(policy: dict[str, Any]) -> set[str]:
    """Return the first path segment of every ``area_paths`` glob."""
    tops: set[str] = set()
    for entry in area_path_entries(policy):
        for raw in entry.get("paths", []):
            if isinstance(raw, str) and raw:
                tops.add(PurePosixPath(raw).parts[0])
    return tops

def tracked_top_level_dirs(root: Path, runner: GitRunner = _run_git) -> set[str]:
    """Return the names of git-tracked top-level directories at *root*.

    Enumerating ``git ls-tree -d --name-only HEAD`` rather than scanning the
    working tree keeps the gate deterministic: transient, git-ignored
    directories such as ``.hypothesis/`` or ``htmlcov/`` are never counted, so
    a coverage run reflects committed structure instead of local scratch.
    """
    output = runner(["ls-tree", "-d", "--name-only", "HEAD"], root)
    return {line.strip() for line in output.splitlines() if line.strip()}


def _err(message: str) -> str:
    """Format a GitHub-annotation error scoped to the policy file."""
    return f"::error file={POLICY_PATH.as_posix()}::{message}"


def verify_policy(policy: dict[str, Any]) -> list[str]:
    """Return structural diagnostics for the area family and its mapping."""
    errors: list[str] = []
    declared = declared_area_labels(policy)
    mapped = mapped_areas(policy)

    for entry in area_path_entries(policy):
        area = entry.get("area")
        if not isinstance(area, str) or not area:
            errors.append(_err("area_paths entry is missing a string 'area' key"))
            continue
        paths = entry.get("paths")
        if not isinstance(paths, list) or not paths:
            errors.append(_err(f"area_paths entry for {area} declares no paths"))

    for area in sorted(mapped - declared):
        errors.append(_err(f"area_paths maps undeclared area {area}; add it to the area family or remove the mapping"))

    for area in sorted(declared - mapped):
        errors.append(_err(f"area label {area} has no area_paths mapping; add owned paths or retire the label"))

    return errors


def verify_directory_coverage(policy: dict[str, Any], root: Path, runner: GitRunner = _run_git) -> list[str]:
    """Return diagnostics for top-level directories with no owning area glob."""
    covered = glob_top_levels(policy)
    errors: list[str] = []
    for directory in sorted(tracked_top_level_dirs(root, runner)):
        if directory not in covered:
            errors.append(
                _err(
                    f"top-level directory {directory}/ is not claimed by any area_paths glob; "
                    "add an area:* mapping that owns it"
                )
            )
    return errors


def verify(root: Path = REPO_ROOT, runner: GitRunner = _run_git) -> list[str]:
    """Return every area-coverage diagnostic for the repository at *root*."""
    root = root.resolve()
    policy_file = root / POLICY_PATH
    if not policy_file.exists():
        return [_err(f"policy file {POLICY_PATH.as_posix()} not found")]
    policy = load_policy(policy_file)
    return verify_policy(policy) + verify_directory_coverage(policy, root, runner)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify", help="verify area-to-path coverage")
    args = parser.parse_args(argv)

    if args.command == "verify":
        errors = verify(REPO_ROOT)
        for error in errors:
            print(error, file=sys.stderr)
        return 1 if errors else 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
