#!/usr/bin/env python3
"""CI gate: require new governed files to register in the doc dependency graph.

When a PR adds a file whose path matches a managed path pattern, this gate
requires that the file is either declared as a node in
``docs/graph/doc-dependencies.toml`` or carries an explicit
``doc-graph-registration-waiver: <FILE_PATH> -- <reason>`` line in the PR body.

Managed path patterns and their severity:

- ``docs/standards/**``       -- blocking (exit 1 when unregistered and not waived)
- ``docs/prd/**``             -- blocking
- ``docs/runbooks/**``        -- advisory (warning only; never exit 1)
- ``scripts/*.py``            -- advisory (direct children only; no subdirectories)
- ``.github/workflows/*.yml`` -- advisory (direct children only)

Waiver mechanism (plain text in PR body):

    doc-graph-registration-waiver: docs/runbooks/commit-signing.md -- reason

Multiple waivers are supported (one per line). The waiver value is the
repository-relative file path (not a node ID, since the file is not yet
registered). Case-insensitive marker; optional leading whitespace.

Architecture: pure functions on top (:func:`classify_path`,
:func:`parse_waivers`, :func:`get_added_files`, :func:`run_gate`), a single
subprocess call in :func:`get_added_files`, and a ``main()`` entrypoint at
the bottom.

Contract:
- Inputs: the ``verify`` subcommand; ``--graph`` (default
  ``docs/graph/doc-dependencies.toml``); ``--base-ref`` (default: ``BASE_REF``
  env var, then ``origin/main``); ``--body-file`` (PR body path) or
  ``PR_BODY`` env var.
- Outputs: ``::error file=<path>::`` annotations on stderr for unregistered
  blocking files; ``::warning::`` lines for unregistered advisory files;
  ``OK:`` line on success; exit 0 when all governed new files are registered
  or waived, exit 1 when any blocking file is unregistered and not waived,
  exit 64 on unrecognised subcommand.
- Failure policy: fails loud (exit 1) for unregistered blocking files per
  CLAUDE.md section 4; fails open (exit 0) when the git diff is unavailable
  so the gate skips rather than blocks on a missing diff.

Tested by ``tests/test_scan_doc_graph_registration.py``. Refs #1793.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_graph import DocGraph, GraphValidationError, load_graph

_GRAPH_PATH = Path("docs/graph/doc-dependencies.toml")
_SCRIPT = "scan_doc_graph_registration"

# Waiver marker: optional leading whitespace, the key, whitespace, the file
# path (non-whitespace), optional ` -- reason`.
_WAIVER_RE = re.compile(
    r"^\s*doc-graph-registration-waiver:\s*(\S+)",
    re.IGNORECASE | re.MULTILINE,
)


def classify_path(file_path: str) -> str | None:
    """Return ``'blocking'``, ``'advisory'``, or ``None`` for unmanaged paths.

    Blocking patterns: ``docs/standards/**``, ``docs/prd/**``.
    Advisory patterns: ``docs/runbooks/**``, ``scripts/*.py`` (direct
    children only), ``.github/workflows/*.yml`` (direct children only).
    """
    if file_path.startswith("docs/standards/") or file_path.startswith("docs/prd/"):
        return "blocking"
    if file_path.startswith("docs/runbooks/"):
        return "advisory"
    p = Path(file_path)
    if p.parent == Path("scripts") and p.suffix == ".py":
        return "advisory"
    if p.parent == Path(".github/workflows") and p.suffix == ".yml":
        return "advisory"
    return None


def parse_waivers(body: str) -> frozenset[str]:
    """Return the set of waived file paths extracted from *body*."""
    return frozenset(m.group(1) for m in _WAIVER_RE.finditer(body))


def get_added_files(base_ref: str) -> list[str] | None:
    """Return paths added on HEAD relative to *base_ref*.

    Uses ``git diff --name-only --diff-filter=A <base_ref>...HEAD``. Returns
    ``None`` when the git call fails (fail-open: the gate skips rather than
    blocks when the diff is unavailable).
    """
    result = subprocess.run(  # noqa: S603 -- fixed argv, shell=False
        [  # noqa: S607
            "git",
            "diff",
            "--name-only",
            "--diff-filter=A",
            f"{base_ref}...HEAD",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def registered_paths(graph: DocGraph) -> frozenset[str]:
    """Return the set of ``path`` values declared in *graph*."""
    return frozenset(node.path for node in graph.nodes.values())


def run_gate(
    known_paths: frozenset[str],
    added_files: list[str],
    waivers: frozenset[str],
) -> bool:
    """Evaluate each added file against registration and waiver status.

    Returns ``True`` when the gate passes (all blocking new files are
    registered or waived); ``False`` when at least one blocking file is
    absent from both *known_paths* and *waivers*.
    """
    if not added_files:
        print(
            f"OK: {_SCRIPT}: no new governed files detected.",
            file=sys.stderr,
        )
        return True

    passed = True
    any_governed = False

    for file_path in added_files:
        severity = classify_path(file_path)
        if severity is None:
            continue
        any_governed = True

        if file_path in known_paths:
            continue

        if file_path in waivers:
            print(
                f"  waived: {file_path!r} (waiver present in PR body)",
                file=sys.stderr,
            )
            continue

        if severity == "blocking":
            print(
                f"::error file={file_path}::{_SCRIPT}: "
                f"{file_path!r} is a new governed file but is not registered "
                f"in docs/graph/doc-dependencies.toml. "
                f"Add a [[nodes]] entry with path = {file_path!r} to "
                f"docs/graph/doc-dependencies.toml, or add "
                f"'doc-graph-registration-waiver: {file_path} -- <reason>' "
                f"to the PR body. Refs #1793.",
                file=sys.stderr,
            )
            passed = False
        else:
            print(
                f"::warning::{_SCRIPT}: "
                f"{file_path!r} is a new governed file but is not registered "
                f"in docs/graph/doc-dependencies.toml. "
                f"Consider adding a [[nodes]] entry or add "
                f"'doc-graph-registration-waiver: {file_path} -- <reason>' "
                f"to the PR body. Refs #1793.",
                file=sys.stderr,
            )

    if passed:
        if any_governed:
            print(
                f"OK: {_SCRIPT}: all new governed files are registered or waived.",
                file=sys.stderr,
            )
        else:
            print(
                f"OK: {_SCRIPT}: no new governed files detected.",
                file=sys.stderr,
            )
    return passed


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Check the subcommand before argparse so an unrecognised command returns
    # exit 64 (EX_USAGE) rather than argparse's exit 2.
    command = argv[0] if argv else None
    if command != "verify":
        print(
            f"::error::{_SCRIPT}: unknown subcommand {command!r}; "
            "expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    parser = argparse.ArgumentParser(
        description="Require new governed files to register in doc-dependencies.toml."
    )
    parser.add_argument(
        "command",
        help="Must be 'verify'.",
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
            "skipping registration check.",
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
                f"::warning::{_SCRIPT}: cannot read PR body file "
                f"{args.body_file!r}: {exc}",
                file=sys.stderr,
            )
    else:
        body = os.environ.get("PR_BODY", "")

    waivers = parse_waivers(body)
    added_files = get_added_files(args.base_ref)
    if added_files is None:
        print(
            f"::warning::{_SCRIPT}: git diff failed; skipping registration check.",
            file=sys.stderr,
        )
        return 0

    known = registered_paths(graph)
    passed = run_gate(known, added_files, waivers)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
