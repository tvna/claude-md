#!/usr/bin/env python3
"""Utilities for managing the Python interpreter pin in ``.python-version``.

The pin lives in the repo-root ``.python-version`` file as a single exact
patch release (e.g. ``3.12.13``). uv reads this file when resolving ``uv run
python``, so pinning an exact patch makes the interpreter byte-deterministic
across the post-merge doc committer (#1571), the verify-docs-drift gate
(#1574), and a local checkout. Without it, ``uv run python`` binds to whatever
3.12.x the host already has, and ``ast.unparse`` renders nested f-string format
specs differently across patch releases; producing phantom drift in
``docs/generated/`` (#1680, follow-up to #1533).

This module is the deterministic counterpart to ``scripts/uv_pin.py``: where
that one guards the uv version, this one guards the Python version. It reads
the pin and verifies it cannot silently drift from the project's other Python
declarations, all of which derive their minor from a single source of truth --
``[project].requires-python`` in ``pyproject.toml``:

* ``.python-version`` must be an exact ``X.Y.Z`` patch (never a bare ``X.Y``,
  which would reintroduce the unbounded-patch problem this pin exists to fix).
* Its ``X.Y`` must equal the ``requires-python`` floor minor.
* ``[tool.ruff].target-version`` (``py3XY``), ``[tool.mypy].python_version``
  (``3.XY``), and every ``python3XY`` token in ``flake.nix`` must agree on that
  same minor, so bumping the floor without bumping the rest fails loudly.

Invoked from CI (``.github/workflows/verify-agents.yml`` and
``weekly-maintenance.yml``) and mirrored locally as a ``preflight_all`` step.
Tested by ``tests/test_python_pin.py``. See
``docs/standards/remote-environment.md`` for the operator-facing rationale.

Contract:
    Inputs: ``read`` or ``verify`` subcommand. ``read`` takes an optional
        ``.python-version`` path; ``verify`` takes an optional ``--repo-root``.
        No stdin. Reads ``.python-version``, ``pyproject.toml``, and (if
        present) ``flake.nix`` from the working tree.
    Outputs: ``read`` prints the exact pin (``X.Y.Z``) to stdout. ``verify``
        prints the pin and an ``OK`` line on stdout when consistent, or one
        ``::error::`` line per drift. Exit 0 when consistent, 1 on drift,
        a malformed/missing pin, or an unreadable ``requires-python``.
    Failure policy: fails loud per CLAUDE.md section 4; a non-exact pin or a
        minor mismatch across requires-python / ruff / mypy / flake.nix is the
        *intended* signal, never silently swallowed.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

# Exact ``X.Y.Z`` patch release. Pre-release / local suffixes are intentionally
# rejected: the pin exists to make ``ast.unparse`` output byte-stable, and a
# non-final interpreter defeats that purpose.
_EXACT_PATCH = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
# ``requires-python = ">=3.12"`` -> floor (3, 12). Only the ``>=`` floor form
# is parsed; the project has used that form since the 3.12 bump (#1491).
_REQUIRES_FLOOR = re.compile(r">=\s*(\d+)\.(\d+)")
# Every ``python3XY`` nixpkgs attribute token in flake.nix (e.g. ``python312``,
# ``python312Packages``). Two-digit minor covers 3.10+.
_FLAKE_PYTHON = re.compile(r"python3(\d\d)")


def read_pin(python_version_path: Path) -> str:
    """Return the stripped exact pin from ``.python-version``.

    Raises :class:`ValueError` on a missing file, an empty file, multiple
    lines, or a non-exact value; callers (CLI, CI) should let that surface
    so failures are loud (CLAUDE.md section 4).
    """
    try:
        raw = python_version_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"cannot read {python_version_path}: {exc}") from exc

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"{python_version_path} is empty; expected one X.Y.Z pin")
    if len(lines) > 1:
        raise ValueError(
            f"{python_version_path} must name a single interpreter, got {len(lines)} lines"
        )

    pin = lines[0]
    if not _EXACT_PATCH.match(pin):
        raise ValueError(
            f"{python_version_path} must pin an exact patch (X.Y.Z), got: {pin!r}"
        )
    return pin


def requires_python_floor(pyproject_path: Path) -> tuple[int, int]:
    """Return the ``(major, minor)`` floor from ``[project].requires-python``."""
    try:
        with pyproject_path.open("rb") as fp:
            data = tomllib.load(fp)
    except FileNotFoundError as exc:
        raise ValueError(f"cannot read {pyproject_path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"malformed TOML in {pyproject_path}: {exc}") from exc

    try:
        spec = data["project"]["requires-python"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"missing [project].requires-python in {pyproject_path}"
        ) from exc

    match = _REQUIRES_FLOOR.search(str(spec))
    if not match:
        raise ValueError(
            f"could not parse a '>=X.Y' floor from requires-python: {spec!r}"
        )
    return int(match.group(1)), int(match.group(2))


def find_inconsistencies(repo_root: Path, pin: str) -> list[str]:
    """Return a list of drift error messages (empty list = consistent).

    The Python ``X.Y`` minor declared across the project must be single-valued.
    ``requires-python`` is the source of truth; ``.python-version``, ruff,
    mypy, and flake.nix are checked against it.
    """
    errors: list[str] = []
    pyproject = repo_root / "pyproject.toml"

    floor_major, floor_minor = requires_python_floor(pyproject)
    expected = f"{floor_major}.{floor_minor}"

    pin_match = _EXACT_PATCH.match(pin)
    if pin_match and (pin_match.group(1), pin_match.group(2)) != (
        str(floor_major),
        str(floor_minor),
    ):
        errors.append(
            f".python-version pins {pin}, but requires-python floor is {expected}.x; "
            "the pin minor must match the floor"
        )

    with pyproject.open("rb") as fp:
        data = tomllib.load(fp)

    ruff_target = data.get("tool", {}).get("ruff", {}).get("target-version")
    if ruff_target is not None and ruff_target != f"py{floor_major}{floor_minor}":
        errors.append(
            f"[tool.ruff].target-version is {ruff_target!r}, "
            f"expected 'py{floor_major}{floor_minor}' to match requires-python floor"
        )

    mypy_version = data.get("tool", {}).get("mypy", {}).get("python_version")
    if mypy_version is not None and mypy_version != expected:
        errors.append(
            f"[tool.mypy].python_version is {mypy_version!r}, "
            f"expected {expected!r} to match requires-python floor"
        )

    flake = repo_root / "flake.nix"
    if flake.exists():
        for minor in set(_FLAKE_PYTHON.findall(flake.read_text(encoding="utf-8"))):
            if int(minor) != floor_minor:
                errors.append(
                    f"flake.nix references python3{minor}, "
                    f"expected python3{floor_minor} to match requires-python floor"
                )

    return errors


def _cmd_read(args: argparse.Namespace) -> int:
    print(read_pin(Path(args.python_version)))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    pin = read_pin(repo_root / ".python-version")
    print(f"python pin from .python-version: {pin}")
    errors = find_inconsistencies(repo_root, pin)
    for err in errors:
        print(f"::error::{err}")
    if errors:
        print(
            f"::error::python pin drift detected ({len(errors)} issue(s)). "
            "Align .python-version, requires-python, ruff, mypy, and flake.nix."
        )
        return 1
    print("OK: python pin is exact and consistent across the project.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="Print the exact python pin (e.g. 'X.Y.Z').")
    p_read.add_argument("python_version", nargs="?", default=".python-version")
    p_read.set_defaults(func=_cmd_read)

    p_verify = sub.add_parser(
        "verify", help="Check the python pin is exact and consistent; exit 1 on drift."
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
