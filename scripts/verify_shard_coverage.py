#!/usr/bin/env python3
"""Completeness gate for the marker-bucketed pytest matrix.

Refs #545. The matrix legs in ``.github/workflows/verify-agents.yml`` each
run a marker-filtered subset of ``tests/`` and emit a JUnit XML artifact.
This script asserts that the union of executed test node IDs across every
JUnit artifact equals the collected universe reported by
``pytest --collect-only -q`` and that no node ID appears in more than one
shard. Either condition failing means the matrix would silently skip a test
(missing) or wastefully run it twice (duplicated); both indicate the marker
taxonomy drifted from the suite shape and must be repaired before merge.

The script is intentionally narrow: it does not call ``pytest`` itself.
The aggregate gate job in the workflow runs ``pytest --collect-only -q``
once, captures the output to a file, downloads the per-leg JUnit artifacts,
and invokes this script. Keeping pytest invocation out of this script makes
unit testing trivial (text + xml inputs only) and keeps the gate fast.

Exit codes:
* ``0``; union of executed node IDs equals the collected universe and no
  duplicates.
* ``1``; at least one collected node was not executed by any shard, or
  at least one node was executed by more than one shard.

Tested by ``tests/test_verify_shard_coverage.py``.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def parse_collected(text: str) -> set[str]:
    """Return the set of node IDs from a ``pytest --collect-only -q`` dump.

    Lines that do not look like node IDs (blank lines, summary tail such as
    ``"57 tests collected in 0.32s"``, error banners) are ignored. A node
    ID is any line containing ``"::"``; pytest's path-versus-id separator.
    """
    nodes: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or "::" not in line:
            continue
        nodes.add(line)
    return nodes


def _classname_to_path_and_class(classname: str) -> tuple[str, str]:
    """Convert ``tests.test_foo.TestBar`` to ``("tests/test_foo.py", "TestBar")``.

    The flat ``tests/`` layout means the first dotted segment is ``tests``
    and the second is the ``test_<name>`` module file. Anything after is
    class nesting (joined by ``.`` to preserve nested-class node IDs).
    Classname is taken verbatim if it does not match the expected shape;
    such cases produce a non-matching node ID and surface as missing.
    """
    parts = classname.split(".")
    if len(parts) < 2:
        return classname, ""
    file_path = f"{parts[0]}/{parts[1]}.py"
    klass = ".".join(parts[2:])
    return file_path, klass


def junit_node_id(classname: str, name: str) -> str:
    """Return the pytest node ID for a JUnit ``<testcase>`` element."""
    file_path, klass = _classname_to_path_and_class(classname)
    if klass:
        return f"{file_path}::{klass}::{name}"
    return f"{file_path}::{name}"


def parse_junit(xml_text: str) -> set[str]:
    """Return the set of executed node IDs from a JUnit XML document.

    Accepts either ``<testsuites>`` (default-family) or a bare
    ``<testsuite>`` root (legacy-family). Skipped testcases are still
    counted as executed; pytest reports them in the JUnit XML, and the
    completeness gate's job is to confirm dispatch coverage, not pass
    coverage.
    """
    root = ET.fromstring(xml_text)  # noqa: S314 -- CI artifact, not user input
    nodes: set[str] = set()
    for case in root.iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        if not classname and not name:
            continue
        nodes.add(junit_node_id(classname, name))
    return nodes


def compare(
    collected: set[str],
    per_shard: dict[str, set[str]],
) -> tuple[set[str], dict[str, list[str]]]:
    """Return (missing, duplicated) given collected nodes and shard maps.

    *missing* contains collected node IDs not executed by any shard.
    *duplicated* maps each node ID executed by more than one shard to the
    list of shards (in input order) that ran it.
    """
    seen_in: dict[str, list[str]] = defaultdict(list)
    for shard, nodes in per_shard.items():
        for node in nodes:
            seen_in[node].append(shard)
    union = set(seen_in.keys())
    missing = collected - union
    duplicated = {n: shards for n, shards in seen_in.items() if len(shards) > 1}
    return missing, duplicated


def format_errors(
    missing: set[str],
    duplicated: dict[str, list[str]],
    extra: set[str],
) -> list[str]:
    """Render the (sorted, ``::error::``-prefixed) diagnostic lines."""
    lines: list[str] = []
    for node in sorted(missing):
        lines.append(
            f"::error::test node `{node}` was collected but not executed by any shard. "
            "Add or fix the module-scope shard marker for the file."
        )
    for node in sorted(duplicated):
        shards = ", ".join(duplicated[node])
        lines.append(
            f"::error::test node `{node}` executed by multiple shards: {shards}. "
            "Each file must declare exactly one shard marker."
        )
    for node in sorted(extra):
        lines.append(
            f"::error::test node `{node}` was executed by a shard but not present "
            "in the collected universe. JUnit and collection drifted; rerun "
            "`pytest --collect-only -q` on the same commit."
        )
    return lines


def verify(collected_path: Path, junit_paths: list[Path]) -> int:
    """Read inputs, run :func:`compare`, print diagnostics, return exit code."""
    if not junit_paths:
        print("::error::no JUnit artifacts provided", file=sys.stderr)
        return 1
    try:
        collected = parse_collected(collected_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"::error::cannot read collected file {collected_path}: {exc}", file=sys.stderr)
        return 1
    per_shard: dict[str, set[str]] = {}
    for jp in junit_paths:
        try:
            xml_text = jp.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"::error::cannot read JUnit file {jp}: {exc}", file=sys.stderr)
            return 1
        try:
            per_shard[jp.stem] = parse_junit(xml_text)
        except ET.ParseError as exc:
            print(f"::error::cannot parse JUnit file {jp}: {exc}", file=sys.stderr)
            return 1
    missing, duplicated = compare(collected, per_shard)
    union = set().union(*per_shard.values()) if per_shard else set()
    extra = union - collected
    errors = format_errors(missing, duplicated, extra)
    for line in errors:
        print(line, file=sys.stderr)
    if errors:
        return 1
    total = len(collected)
    shard_summary = ", ".join(f"{name}={len(nodes)}" for name, nodes in sorted(per_shard.items()))
    print(f"OK: {total} collected node IDs covered exactly once across shards ({shard_summary}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the union of executed test node IDs across JUnit XML "
            "artifacts equals the universe collected by pytest, with no "
            "duplicates."
        ),
    )
    parser.add_argument(
        "--collected",
        required=True,
        help="Path to a file containing `pytest --collect-only -q` output.",
    )
    parser.add_argument(
        "--junit",
        required=True,
        nargs="+",
        help="One or more JUnit XML artifact paths (one per shard).",
    )
    args = parser.parse_args(argv)
    junit_paths = [Path(p) for p in args.junit]
    return verify(Path(args.collected), junit_paths)


if __name__ == "__main__":
    raise SystemExit(main())
