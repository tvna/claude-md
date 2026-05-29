#!/usr/bin/env python3
"""Static check that every ``tests/test_*.py`` carries exactly one shard marker.

Refs #545. The marker-bucketed CI matrix in ``.github/workflows/verify-agents.yml``
depends on every test file declaring a single ``pytestmark = pytest.mark.shard_<bucket>``
assignment at module scope. A file with zero shard markers would be skipped by every
matrix leg; a file with multiple shard markers would run in multiple legs and inflate
runtime without adding coverage. This script fails CI before the matrix runs so the
fault surfaces with a clear diagnostic rather than a silent absence in the JUnit
aggregation (which ``verify_shard_coverage.py`` would also catch as a missing
node ID, but later in the pipeline).

The detector uses :mod:`ast` rather than regex because module-scope `pytestmark`
can be a single mark (``pytest.mark.shard_foo``) or a list of marks
(``[pytest.mark.shard_foo, pytest.mark.usefixtures("bar")]``). Both shapes are
accepted; exactly one shard marker must be present.

Exit codes:
* ``0`` -- every test file declares exactly one shard marker from the allowed set.
* ``1`` -- at least one file is missing a shard marker, has more than one, or
  references an unknown bucket.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_BUCKETS: frozenset[str] = frozenset({
    "shard_preflight",
    "shard_policy",
    "shard_ci_ops",
    "shard_ci_ops_auto_retro_append",
    "shard_ci_ops_auto_retro_create",
    "shard_ci_ops_auto_retro_create_slow",
    "shard_ci_ops_auto_retro_decision_tree",
    "shard_ci_ops_auto_retro_signals",
    "shard_ci_ops_auto_retro_skips",
    "shard_ci_ops_auto_retro_rescan",
    "shard_default",
})


def extract_shard_markers(source: str) -> list[str]:
    """Return shard marker bucket names referenced by module-scope ``pytestmark``.

    Accepts a single ``Attribute`` (``pytest.mark.shard_foo``) or a ``List`` /
    ``Tuple`` of such attributes. Any attribute whose name does NOT start with
    ``shard_`` is ignored (other markers like ``usefixtures`` may legitimately
    share the assignment).

    Returns the list of bucket names in source order. Callers decide whether
    zero, one, or many is the failure shape.
    """
    tree = ast.parse(source)
    found: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t for t in node.targets if isinstance(t, ast.Name) and t.id == "pytestmark"]
        if not targets:
            continue
        value = node.value
        candidates: list[ast.expr] = []
        if isinstance(value, ast.List | ast.Tuple):
            candidates = list(value.elts)
        else:
            candidates = [value]
        for expr in candidates:
            if not isinstance(expr, ast.Attribute):
                continue
            # Expect form ``pytest.mark.<bucket>``: outer Attribute.value is an
            # inner Attribute (.mark) whose .value is a Name (pytest).
            if not isinstance(expr.value, ast.Attribute):
                continue
            if expr.value.attr != "mark":
                continue
            inner = expr.value.value
            if not isinstance(inner, ast.Name) or inner.id != "pytest":
                continue
            if expr.attr.startswith("shard_"):
                found.append(expr.attr)
    return found


def verify_file(path: Path) -> list[str]:
    """Return ``::error::`` lines for *path*; empty list when conformant."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"::error::{path}: cannot read file: {exc}"]
    try:
        markers = extract_shard_markers(source)
    except SyntaxError as exc:
        return [f"::error::{path}: cannot parse as Python: {exc}"]
    errors: list[str] = []
    if not markers:
        errors.append(
            f"::error::{path}: missing module-scope shard marker. Add "
            "`pytestmark = pytest.mark.shard_<bucket>` where "
            "<bucket> is one of: " + ", ".join(sorted(ALLOWED_BUCKETS)) + "."
        )
        return errors
    if len(markers) > 1:
        errors.append(
            f"::error::{path}: declares multiple shard markers "
            f"({', '.join(markers)}); exactly one is allowed."
        )
    unknown = [m for m in markers if m not in ALLOWED_BUCKETS]
    if unknown:
        errors.append(
            f"::error::{path}: unknown shard bucket(s) {', '.join(unknown)}; "
            "allowed: " + ", ".join(sorted(ALLOWED_BUCKETS)) + "."
        )
    return errors


def collect_test_files(tests_dir: Path) -> list[Path]:
    """Return sorted ``tests/test_*.py`` paths under *tests_dir*."""
    return sorted(tests_dir.glob("test_*.py"))


def verify(tests_dir: Path) -> int:
    """Run :func:`verify_file` over the suite; return shell exit code."""
    files = collect_test_files(tests_dir)
    if not files:
        print(f"::error::no test files found under {tests_dir}", file=sys.stderr)
        return 1
    all_errors: list[str] = []
    for path in files:
        all_errors.extend(verify_file(path))
    for line in all_errors:
        print(line, file=sys.stderr)
    if all_errors:
        return 1
    print(f"OK: {len(files)} test files each declare exactly one shard marker.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify each tests/test_*.py declares exactly one module-scope "
            "shard marker (pytestmark = pytest.mark.shard_<bucket>)."
        ),
    )
    parser.add_argument(
        "--tests-dir",
        default=str(REPO_ROOT / "tests"),
        help="Directory containing test_*.py files (default: <repo>/tests).",
    )
    args = parser.parse_args(argv)
    return verify(Path(args.tests_dir))


if __name__ == "__main__":
    raise SystemExit(main())
