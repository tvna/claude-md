#!/usr/bin/env python3
"""Utilities for managing the uv version pin in pyproject.toml.

The pin lives at `[tool.uv].required-version` as an exact PEP440 specifier
(e.g. ``==X.Y.Z``). This module reads, validates, and lints that pin, and
is invoked from CI (`.github/workflows/verify-agents.yml`) and the
SessionStart hook (`scripts/install-uv.sh`).

Tested by ``tests/test_uv_pin.py``. See ``docs/standards/remote-environment.md``
for the operator-facing rationale (#112).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path

# Subdirectories the literal-value drift check inspects.
DRIFT_SUBDIRS: tuple[str, ...] = (".github", "scripts", "docs")
WORKFLOW_SUBDIR = ".github/workflows"
DOCS_SUBDIR = "docs"
# Historical snapshots of issue/PR text legitimately quote the pin in
# context (e.g. `uv-cli==X.Y.Z` recorded in past discussions). The drift
# gate protects against parallel pins drifting from pyproject.toml, not
# against the historical record naming the pin.
DRIFT_EXCLUDE_RELPATHS: frozenset[str] = frozenset({
    "scripts/translations.json",  # #102 P3 snapshot of past issue/PR bodies
})

# Matches a YAML key assignment `UV_VERSION:` followed by a literal value
# (anything that is not a GitHub `${{ ... }}` expression).
_UV_VERSION_ASSIGN = re.compile(r"^\s*UV_VERSION\s*:")
_GHA_EXPR = re.compile(r"\$\{\{")
_UV_VERSION_SYMBOL = re.compile(r"\bUV_VERSION\b")


def read_pin(pyproject_path: Path) -> str:
    """Return the stripped version from ``[tool.uv].required-version``.

    Example: ``"==X.Y.Z"`` -> ``"X.Y.Z"``. Raises :class:`ValueError` on
    missing/malformed data with a descriptive message; callers (CLI, shell)
    should let that surface so failures are loud.
    """
    try:
        with pyproject_path.open("rb") as fp:
            data = tomllib.load(fp)
    except FileNotFoundError as exc:
        raise ValueError(f"cannot read {pyproject_path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"malformed TOML in {pyproject_path}: {exc}") from exc

    try:
        spec = data["tool"]["uv"]["required-version"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"missing [tool.uv].required-version in {pyproject_path}"
        ) from exc

    if not isinstance(spec, str) or not spec.startswith("=="):
        raise ValueError(
            f"required-version must be an exact pin (==X.Y.Z), got: {spec!r}"
        )
    return spec[2:]


def find_drift(repo_root: Path, pin: str) -> list[str]:
    """Return a list of drift error messages (empty list = clean).

    Three checks:

    1. Literal pin value appearing anywhere under ``.github/``, ``scripts/``,
       ``docs/``. Fixed-string match against the resolved pin avoids false
       positives on ``APM_CLI_VERSION`` and action ``# vX.Y.Z`` comments.
    2. Any ``UV_VERSION:`` assignment to a literal value in workflow YAML.
       Assignments sourced from a ``${{ ... }}`` expression are allowed.
    3. ``UV_VERSION`` symbol appearing anywhere under ``docs/``.
    """
    errors: list[str] = []

    # (1) Literal-value check.
    for path in _iter_files(repo_root, DRIFT_SUBDIRS):
        rel = path.relative_to(repo_root)
        if rel.as_posix() in DRIFT_EXCLUDE_RELPATHS:
            continue
        for line_num, line in _read_lines(path):
            if pin in line:
                errors.append(
                    f"{rel}:{line_num}: uv pin literal {pin!r} appears "
                    f"outside pyproject.toml"
                )

    # (2) UV_VERSION assignment to literal in workflow YAML.
    workflow_dir = repo_root / WORKFLOW_SUBDIR
    if workflow_dir.exists():
        for path in workflow_dir.rglob("*"):
            if not path.is_file() or path.suffix not in (".yml", ".yaml"):
                continue
            for line_num, line in _read_lines(path):
                if _UV_VERSION_ASSIGN.match(line) and not _GHA_EXPR.search(line):
                    rel = path.relative_to(repo_root)
                    errors.append(
                        f"{rel}:{line_num}: UV_VERSION assigned to a "
                        f"literal value; source it from a step output instead"
                    )

    # (3) UV_VERSION symbol in docs/.
    docs_dir = repo_root / DOCS_SUBDIR
    if docs_dir.exists():
        for path in docs_dir.rglob("*"):
            if not path.is_file():
                continue
            for line_num, line in _read_lines(path):
                if _UV_VERSION_SYMBOL.search(line):
                    rel = path.relative_to(repo_root)
                    errors.append(
                        f"{rel}:{line_num}: UV_VERSION symbol in docs/ "
                        f"(reference [tool.uv].required-version instead)"
                    )

    return errors


def fetch_latest_uv_release() -> str | None:
    """Return the latest ``astral-sh/uv`` release tag, or None if unavailable.

    Uses ``gh release view``. Returns None on any subprocess failure (missing
    gh, network error, auth failure, empty output) -- callers should treat
    None as "skip the check" rather than as drift.
    """
    try:
        # S603/S607 justification: fixed argv (no shell, no caller-supplied input);
        # `gh` is provisioned on the GitHub Actions runner via setup-gh.
        # FileNotFoundError below covers the local-dev case where gh is absent.
        result = subprocess.run(  # noqa: S603 -- fixed argv, shell=False
            [  # noqa: S607 -- `gh` resolved via runner PATH; FileNotFoundError handled below
                "gh", "release", "view",
                "--repo", "astral-sh/uv",
                "--json", "tagName",
                "--jq", ".tagName",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    tag = result.stdout.strip()
    return tag or None


def _iter_files(root: Path, subdirs: Iterable[str]) -> Iterator[Path]:
    for sub in subdirs:
        base = root / sub
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                yield path


def _read_lines(path: Path) -> Iterator[tuple[int, str]]:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    yield from enumerate(content.splitlines(), 1)


def _cmd_read(args: argparse.Namespace) -> int:
    print(read_pin(Path(args.pyproject)))
    return 0


def _cmd_drift(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    pin = read_pin(repo_root / "pyproject.toml")
    print(f"uv pin from pyproject.toml: {pin}")
    errors = find_drift(repo_root, pin)
    for err in errors:
        print(f"::error::{err}")
    if errors:
        print(
            f"::error::uv pin drift detected ({len(errors)} issue(s)). "
            "Update pyproject.toml or remove the offending literal."
        )
        return 1
    print("OK: no uv pin drift detected.")
    return 0


def _cmd_stale(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    pin = read_pin(repo_root / "pyproject.toml")
    latest = fetch_latest_uv_release()
    if latest is None:
        print(
            "::warning::could not fetch latest astral-sh/uv release; "
            "staleness check skipped"
        )
        return 0
    if pin != latest:
        print(
            f"::warning::uv pin ({pin}) trails upstream latest ({latest}). "
            "Bump [tool.uv].required-version in pyproject.toml."
        )
    else:
        print(f"uv pin matches upstream latest ({pin}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser(
        "read", help="Print the stripped uv pin (e.g. 'X.Y.Z')."
    )
    p_read.add_argument("pyproject", nargs="?", default="pyproject.toml")
    p_read.set_defaults(func=_cmd_read)

    p_drift = sub.add_parser(
        "drift", help="Check for uv pin drift; exit 1 on drift."
    )
    p_drift.add_argument("--repo-root", default=".")
    p_drift.set_defaults(func=_cmd_drift)

    p_stale = sub.add_parser(
        "stale", help="Warn (no fail) if uv pin trails upstream."
    )
    p_stale.add_argument("--repo-root", default=".")
    p_stale.set_defaults(func=_cmd_stale)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
