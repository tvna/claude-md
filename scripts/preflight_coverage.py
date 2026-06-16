#!/usr/bin/env python3
"""Fail before PR publication when a changed scripts/*.py has per-file coverage below the floor.

Refs #952. Supplements the aggregate post-merge coverage gate with a
per-file check so a new script with no tests cannot be hidden by the
high-coverage of existing files.

If ``coverage.json`` already exists (the developer ran pytest --cov
locally), the script reuses it.  Otherwise it runs the full test suite
via ``uv run pytest --cov --cov-report=json -q`` to generate it.

Contract:
- Inputs: ``--base-ref`` (default ``origin/main``, the git ref to diff
  against for changed scripts); ``--floor`` (default 90.0, per-file
  coverage percentage); ``--coverage-json`` (default None, path to an
  existing report -- skips the pytest run when supplied).
- Outputs: ``OK: <path> <pct>%`` lines on stdout for passing files;
  ``::error file=<path>::per-file coverage: <reason>`` annotations on
  stderr for each failing file; exit 0 when all changed files meet the
  floor (or no public scripts/*.py changed), exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is both a CI
  gate and a pre-push hook; a file below the floor always exits non-zero).

Tested by ``tests/test_preflight_coverage.py``. Refs #952, #1800.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from _git import run_git

REPO_ROOT = Path(__file__).resolve().parent.parent

# Per-file line-coverage floor (percentage). Each public scripts/*.py file
# touched by the PR must meet this threshold in the coverage.json report.
# Set below the aggregate gate (95%) to allow for files that legitimately
# have uncoverable branches while still catching zero-coverage new files.
PER_FILE_FLOOR = 90.0


def changed_scripts(repo: Path, *, base_ref: str = "origin/main") -> list[str]:
    """Return ``scripts/*.py`` public-module paths changed relative to *base_ref*.

    Private helper modules (names starting with ``_``) are excluded because
    they are always exercised indirectly through their public callers and
    lack standalone CLI entry points.
    """
    completed = run_git(["diff", "--name-only", base_ref, "--", "scripts/"], cwd=repo)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git diff failed ({base_ref}): {detail}")
    return [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip().startswith("scripts/")
        and line.strip().endswith(".py")
        and not Path(line.strip()).name.startswith("_")
    ]


def ensure_coverage_json(repo: Path) -> Path:
    """Return path to ``coverage.json``, running ``pytest --cov`` if absent."""
    coverage_path = repo / "coverage.json"
    if coverage_path.exists():
        return coverage_path
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "uv not found on PATH and coverage.json is absent. "
            "Run: uv run pytest --cov --cov-report=json -q"
        )
    completed = subprocess.run(  # noqa: S603 -- argv is hard-coded
        [uv, "run", "pytest", "--cov", "--cov-report=json", "-q"],
        cwd=repo,
        check=False,
    )
    if not coverage_path.exists():
        raise RuntimeError(
            f"coverage.json not generated after pytest run (exit {completed.returncode}). "
            "Inspect the pytest output above for test failures."
        )
    return coverage_path


def parse_coverage_json(path: Path) -> dict[str, float]:
    """Return ``{script_path: percent_covered}`` from *path*.

    Keys are the file paths as recorded by coverage.py (e.g.
    ``scripts/preflight_foo.py``). Non-numeric or absent ``percent_covered``
    values are silently skipped so malformed entries do not abort the gate.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    files: object = data.get("files", {})
    if not isinstance(files, dict):
        return {}
    result: dict[str, float] = {}
    for file_path, info in files.items():
        if not isinstance(info, dict):
            continue
        summary = info.get("summary", {})
        if not isinstance(summary, dict):
            continue
        pct = summary.get("percent_covered")
        if isinstance(pct, int | float):
            result[str(file_path)] = float(pct)
    return result


def check_per_file(
    targets: list[str],
    coverage: dict[str, float],
    *,
    floor: float,
) -> list[tuple[str, str]]:
    """Return ``(path, reason)`` pairs for targets that fail the floor.

    A target absent from *coverage* is treated as zero coverage: it means
    no tests executed against that file, which is worse than low coverage
    and must be repaired before the PR can be created.
    """
    failures: list[tuple[str, str]] = []
    for target in targets:
        if target not in coverage:
            failures.append((target, "absent from coverage report (no tests executed)"))
            continue
        pct = coverage[target]
        if pct < floor:
            failures.append((target, f"{pct:.1f}% < {floor:.0f}% (per-file floor)"))
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Git ref to diff against (default: origin/main).",
    )
    parser.add_argument(
        "--floor",
        type=float,
        default=PER_FILE_FLOOR,
        help="Per-file coverage floor as a percentage (default: %(default)s).",
    )
    parser.add_argument(
        "--coverage-json",
        default=None,
        help="Path to an existing coverage.json; skips the pytest run.",
    )
    args = parser.parse_args(argv)

    try:
        targets = changed_scripts(REPO_ROOT, base_ref=args.base_ref)
    except RuntimeError as exc:
        print(f"::error::coverage preflight: {exc}", file=sys.stderr)
        return 1

    if not targets:
        print("OK: no public scripts/*.py changed relative to origin/main")
        return 0

    cov_path: Path
    if args.coverage_json is not None:
        cov_path = Path(args.coverage_json)
    else:
        try:
            cov_path = ensure_coverage_json(REPO_ROOT)
        except RuntimeError as exc:
            print(f"::error::coverage preflight: {exc}", file=sys.stderr)
            return 1

    try:
        coverage = parse_coverage_json(cov_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"::error::coverage preflight: cannot read {cov_path}: {exc}", file=sys.stderr)
        return 1

    failures = check_per_file(targets, coverage, floor=args.floor)

    failure_paths = {f[0] for f in failures}
    for target in targets:
        if target not in failure_paths:
            pct = coverage.get(target, 0.0)
            print(f"OK: {target} {pct:.1f}% >= {args.floor:.0f}%")

    for path, reason in failures:
        print(f"::error file={path}::per-file coverage: {reason}", file=sys.stderr)

    if failures:
        print(
            f"::error::per-file coverage gate failed for {len(failures)} script(s). "
            "Add or expand tests before creating the PR.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
