#!/usr/bin/env python3
"""CI gate: validate document dependency co-changes using the typed graph.

When a PR changes a file that is declared as a node in
``docs/graph/doc-dependencies.toml``, this gate requires that all
blocking-severity dependent nodes are also changed in the same PR. If any
are missing, the gate fails with ``::error::`` annotations that name the
absent documents and show the waiver syntax.

Waiver mechanism (MCP-safe plain text, mirrors the ``philosophy-matrix-ack``
pattern): add a line to the PR body:

    doc-graph-waiver: NODE_ID -- reason for skipping co-change

Multiple waivers are supported (one per line). The gate checks all required
co-changes and then checks the waiver set; a waived node is reported as
"waived" and does not cause a failure.

This gate is complementary to ``scan_design_philosophy_drift.py
verify-coupling``: the existing gate provides semantic depth for the
master->philosophy relationship; this gate provides breadth across all
declared relationships.

Architecture: pure functions on top (:func:`parse_waivers`,
:func:`get_changed_files`, :func:`run_gate`), a single subprocess call in
:func:`get_changed_files`, and a ``main()`` entrypoint at the bottom.

Contract:
- Inputs: ``--graph`` (default ``docs/graph/doc-dependencies.toml``),
  ``--base-ref`` (default: ``BASE_REF`` env var, then ``origin/main``),
  ``--body-file`` (PR body path) or ``PR_BODY`` env var.
- Outputs: ``::error file=<path>::`` annotations on stderr for missing
  co-changes; ``OK:`` line on success; exit 0 when all required co-changes
  are present or waived, exit 1 otherwise.
- Failure policy: fails loud (exit 1) on graph validation errors per
  CLAUDE.md section 4; fails open (exit 0) when the git diff is unavailable
  so the gate skips rather than blocks on a missing diff.

Tested by ``tests/test_gate_doc_graph_pr.py``. Refs #1754.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_graph import DocGraph, GraphValidationError, impact_report, load_graph

_GRAPH_PATH = Path("docs/graph/doc-dependencies.toml")
_SCRIPT = "gate_doc_graph_pr"

# Plain-text waiver marker (MCP-safe; HTML comments are stripped by GitHub MCP
# write tools). Pattern: optional leading whitespace, `doc-graph-waiver:`,
# whitespace, the node id (non-whitespace), optional ` -- reason`.
_WAIVER_RE = re.compile(
    r"^\s*doc-graph-waiver:\s*(\S+)",
    re.IGNORECASE | re.MULTILINE,
)


def parse_waivers(body: str) -> frozenset[str]:
    """Return the set of waived node IDs extracted from *body*."""
    return frozenset(m.group(1) for m in _WAIVER_RE.finditer(body))


def get_changed_files(base_ref: str) -> list[str]:
    """Return paths changed on HEAD relative to *base_ref*.

    Uses ``git diff --name-only <base_ref>...HEAD``. Returns an empty list
    when the git call fails (fail-open: the gate skips rather than blocks
    when the diff is unavailable).
    """
    result = subprocess.run(  # noqa: S603 — fixed argv, shell=False
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(
            f"::warning::{_SCRIPT}: git diff failed: {result.stderr.strip()!r}; "
            "skipping graph validation.",
            file=sys.stderr,
        )
        return []
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def run_gate(
    graph: DocGraph,
    changed_files: list[str],
    waivers: frozenset[str],
) -> bool:
    """Evaluate the impact report and emit annotations.

    Returns ``True`` when the gate passes (all blocking dependents present or
    waived); ``False`` when at least one required co-change is absent.
    """
    if not changed_files:
        print(f"OK: {_SCRIPT}: no changed files detected.", file=sys.stderr)
        return True

    report = impact_report(graph, changed_files)
    passed = True

    for changed_node, required_node in report.required_co_changes:
        if required_node.id in waivers:
            print(
                f"  waived: {required_node.path!r} "
                f"(node {required_node.id!r}; waiver present in PR body)",
                file=sys.stderr,
            )
            continue
        print(
            f"::error file={changed_node.path}::{_SCRIPT}: "
            f"changing {changed_node.path!r} requires a co-change of "
            f"{required_node.path!r} (node {required_node.id!r}). "
            f"Either add the file to this PR or add "
            f"'doc-graph-waiver: {required_node.id} -- <reason>' "
            f"to the PR body. Refs #1754.",
            file=sys.stderr,
        )
        passed = False

    for changed_node, noted_node, edge_type in report.advisory_notes:
        print(
            f"  note ({edge_type}): {changed_node.path!r} -> "
            f"{noted_node.path!r} (advisory; no action required)",
            file=sys.stderr,
        )

    if passed:
        print(f"OK: {_SCRIPT}: all required co-changes present or waived.", file=sys.stderr)
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate document dependency co-changes for a PR."
    )
    parser.add_argument(
        "--graph",
        default=str(_GRAPH_PATH),
        help="Path to doc-dependencies.toml (default: %(default)s).",
    )
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("BASE_REF", "origin/main"),
        help="Git ref to diff HEAD against (default: BASE_REF env or origin/main).",
    )
    parser.add_argument(
        "--body-file",
        default=None,
        help="Path to a file containing the PR body (alternative to PR_BODY env var).",
    )
    args = parser.parse_args(argv)

    graph_path = Path(args.graph)
    if not graph_path.exists():
        print(
            f"::warning::{_SCRIPT}: graph file not found at {graph_path}; "
            "skipping graph validation.",
            file=sys.stderr,
        )
        return 0

    try:
        graph = load_graph(graph_path)
    except GraphValidationError as exc:
        print(
            f"::error file={graph_path}::{_SCRIPT}: graph validation error: {exc}",
            file=sys.stderr,
        )
        return 1

    body = ""
    if args.body_file:
        try:
            body = Path(args.body_file).read_text()
        except OSError as exc:
            print(
                f"::warning::{_SCRIPT}: cannot read PR body file {args.body_file!r}: {exc}",
                file=sys.stderr,
            )
    else:
        body = os.environ.get("PR_BODY", "")

    waivers = parse_waivers(body)
    changed_files = get_changed_files(args.base_ref)
    passed = run_gate(graph, changed_files, waivers)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
