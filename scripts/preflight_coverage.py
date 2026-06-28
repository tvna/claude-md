#!/usr/bin/env python3
"""Fail before PR publication when a changed scripts/*.py has per-file coverage below the floor.

Refs #952. Supplements the aggregate post-merge coverage gate with a
per-file check so a new script with no tests cannot be hidden by the
high-coverage of existing files.

If ``coverage.json`` already exists (the developer ran pytest --cov
locally) AND it is newer than every tracked ``scripts/**`` / ``tests/**``
source file, the script reuses it.  Otherwise (absent, or stale relative
to the source tree) it runs the full test suite via
``uv run pytest --cov --cov-report=json -q`` to (re)generate it. The
freshness check (Refs #2075) prevents a cached report produced before new
tests were added from driving a false per-file verdict: in the PR #2046
session a stale ``coverage.json`` read 88.1% from a report generated
before the new tests existed and failed the gate without re-running
pytest.

Contract:
- Inputs: ``--base-ref`` (default ``origin/main``, the git ref to diff
  against for changed scripts); ``--floor`` (default 90.0, per-file
  coverage percentage); ``--coverage-json`` (default None, path to an
  existing report; skips the pytest run when supplied).
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
import contextlib
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
    # --diff-filter=d excludes deleted paths so a script-removal PR is never
    # penalised for a file that no longer exists in coverage.json.
    completed = run_git(["diff", "--name-only", "--diff-filter=d", base_ref, "--", "scripts/"], cwd=repo)
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


def newest_source_mtime(repo: Path) -> float | None:
    """Return the newest mtime among ``scripts/**`` and ``tests/**`` ``*.py`` files.

    Returns ``None`` when neither directory exists or holds a readable
    ``*.py`` file, so a caller outside the source tree (a bare temp dir)
    never triggers a regeneration. Unreadable files are skipped rather than
    aborting the scan.
    """
    newest: float | None = None
    for sub in ("scripts", "tests"):
        base = repo / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


def coverage_is_stale(coverage_path: Path, repo: Path) -> bool:
    """Return True when ``coverage_path`` does not strictly post-date every source file.

    A cached report generated before new tests or scripts were added reports
    stale per-file numbers (the PR #2046 session: an 88.1% reading from a
    report built before the new tests existed). Comparing mtimes catches that
    so the gate regenerates instead of trusting the cache. Fails safe: an
    unstattable report is treated as stale (regenerate); no source files means
    nothing to compare against, so the report is treated as fresh. Refs #2075.

    The comparison is ``<=`` (not ``<``): a report whose mtime equals the newest
    source mtime (both written in the same wall-clock second) is treated as
    stale and regenerated. ``<`` would treat that report as fresh and could
    reuse a cache produced in the same second as a later edit, reviving the
    PR #2046 false-fresh verdict inside a one-second window; erring toward
    regeneration is the fail-safe side. Refs #2093.

    Known limit (documented, not gated): git does not preserve mtimes, so a
    fresh clone/checkout or a branch switch stamps every file at checkout time.
    That can make this heuristic both skip a needed run (report and sources
    share a checkout second -> handled by the ``<=`` above, which regenerates)
    and force an unnecessary full pytest after a no-op checkout. The per-file
    floor and the absent-report fail-loud are the safety net; this mtime check
    is only a cache-reuse optimization. Refs #2093 item 1.
    """
    try:
        cov_mtime = coverage_path.stat().st_mtime
    except OSError:
        return True
    newest = newest_source_mtime(repo)
    if newest is None:
        return False
    return cov_mtime <= newest


def ensure_coverage_json(repo: Path) -> Path:
    """Return path to ``coverage.json``, running ``pytest --cov`` if absent or stale.

    Reuses an existing report only when it is newer than every tracked
    ``scripts/**`` / ``tests/**`` source file; a stale report is regenerated
    (Refs #2075) so a cache built before new tests were added cannot drive a
    false per-file verdict. The stale report is deleted BEFORE regenerating, so
    a regeneration that fails before overwriting it (uv/pytest startup crash,
    collection error, interrupted run) cannot leave the stale file in place to
    be reused; the absent-file check below then fails loud per CLAUDE.md
    section 4 instead of silently passing on the report just declared invalid.
    If the delete itself fails (read-only mount, foreign owner) the stale file
    survives, so the regeneration is also required to change the file's mtime:
    an unchanged mtime means pytest never rewrote it and the gate fails loud
    rather than reusing the report just declared invalid (Refs #2077 review).
    """
    coverage_path = repo / "coverage.json"
    stale_mtime: float | None = None
    if coverage_path.exists():
        if not coverage_is_stale(coverage_path, repo):
            return coverage_path
        print(
            "coverage.json is stale (older than a scripts/** or tests/** source "
            "file); discarding it and regenerating instead of reusing it.",
            file=sys.stderr,
        )
        with contextlib.suppress(OSError):
            stale_mtime = coverage_path.stat().st_mtime
        with contextlib.suppress(OSError):
            coverage_path.unlink()
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
    # The delete above is best-effort; if it failed, a stale file can still be
    # sitting here. Require the rerun to have rewritten it (mtime changed), else
    # the stale report could not be regenerated and must not be reused.
    if stale_mtime is not None and coverage_path.stat().st_mtime == stale_mtime:
        raise RuntimeError(
            f"stale coverage.json could not be regenerated (exit {completed.returncode}); "
            "the cached report was not rewritten. Remove it manually and rerun: "
            "rm coverage.json && uv run pytest --cov --cov-report=json -q"
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
