#!/usr/bin/env python3
"""Read-only reporter for the loop-engineering achievement audit.

Reads ``.gitapex/loop-engineering-audit.toml`` (the stored checklist and
single source of truth) and prints a status table. For items flagged
``machine_checkable`` it re-derives ``present`` / ``absent`` from the working
tree and flags ``DRIFT`` when the recorded status disagrees with the tree;
judgment items print their recorded, human-audited status and evidence.

Report, not gate: exit 0 always. A machine verdict of "achieved" on a judgment
item would be false precision, the same risk the repo declined for the skill
LLM-judge in #1099. Refs #2294, #2268.

Contract:
- Inputs: the ``run`` subcommand; ``--data`` (default the audit TOML);
  ``--root`` (default repo root; the tree the machine checks resolve against).
- Outputs: a status table on stdout; always exit 0.
- Architecture: pure functions on top; a single filesystem boundary in
  :func:`detect`, monkeypatched in tests.

Refs #2294, #2268, #2342.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO_ROOT / ".gitapex" / "loop-engineering-audit.toml"

# An audit item or its embedded check: heterogeneous TOML records read as-is.
Item = dict[str, Any]


def load_audit(data_path: Path) -> tuple[dict[str, Any], list[Item]]:
    """Return ``(meta, items)`` parsed from the audit TOML at *data_path*."""
    doc = tomllib.loads(data_path.read_text(encoding="utf-8"))
    return doc.get("meta", {}), doc.get("items", [])


def detect(check: Item, root: Path) -> bool:
    """Return whether *check* matches under *root* (the filesystem boundary)."""
    kind = check["kind"]
    if kind == "path_exists":
        return (root / check["target"]).exists()
    if kind == "glob_exists":
        return any(root.glob(check["target"]))
    if kind == "grep_in_glob":
        pattern = check["pattern"]
        for path in root.glob(check["glob"]):
            if path.is_file() and pattern in path.read_text(encoding="utf-8", errors="ignore"):
                return True
        return False
    raise ValueError(f"unknown check kind: {kind}")


def computed_status(item: Item, root: Path) -> str | None:
    """Objective ``present`` / ``absent`` for a machine item, else ``None``."""
    if not item.get("machine_checkable"):
        return None
    return "present" if detect(item["check"], root) else "absent"


def is_drift(item: Item, computed: str | None) -> bool:
    """True when a machine item's recorded status disagrees with the tree."""
    if computed is None:
        return False
    recorded = item.get("status")
    return recorded in ("present", "absent") and recorded != computed


def evaluate(items: list[Item], root: Path) -> list[tuple[Item, str | None, bool]]:
    """Evaluate every item once: ``(item, computed_status, drift)``."""
    rows: list[tuple[Item, str | None, bool]] = []
    for item in items:
        computed = computed_status(item, root)
        rows.append((item, computed, is_drift(item, computed)))
    return rows


def render(meta: dict[str, Any], items: list[Item], root: Path) -> str:
    """Render the audit table as text; IO only via *root* checks in evaluate."""
    evaluated = evaluate(items, root)
    lines = [
        f"Loop-engineering achievement audit  (source: {meta.get('source', '')})",
        f"umbrella={meta.get('audit_umbrella', '')}  "
        f"last_reviewed={meta.get('last_reviewed', '')}  items={len(items)}",
        "",
        f"{'dimension':<12} {'id':<26} {'recorded':<10} {'machine':<8} evidence",
    ]
    for item, computed, drift in evaluated:
        machine = "-" if computed is None else computed
        flag = " [DRIFT]" if drift else ""
        lines.append(
            f"{item.get('dimension', ''):<12} {item.get('id', ''):<26} "
            f"{item.get('status', ''):<10} {machine:<8}{flag} {item.get('evidence', '')}"
        )
    drifts = [item.get("id", "") for item, _computed, drift in evaluated if drift]
    lines += ["", f"DRIFT: {', '.join(drifts) if drifts else 'none'}"]
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    """CLI entry: parse args, print the table, return 0 (report, not gate)."""
    parser = argparse.ArgumentParser(prog="audit_loop_engineering")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="print the audit status table")
    run_p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    run_p.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    meta, items = load_audit(args.data)
    print(render(meta, items, args.root))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
