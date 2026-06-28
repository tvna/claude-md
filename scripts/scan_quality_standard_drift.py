#!/usr/bin/env python3
"""Deterministic gate: the workflow-script-quality standard stays enforcement-mapped.

The workflow `.github/workflows/verify-agents.yml` invokes this module
from the `lint-scripts-static` job. It is the root-cause fix for the
standard `docs/standards/workflow-script-quality.md` (#196) being a
doc-only snapshot: only M8 and M10 ever had backing gates, while the
other must-haves relied on reviewer memory (against CLAUDE.md section 3).

`docs/standards/workflow-script-quality.enforcement.toml` is the registry
mapping each must-have (M1-M10) to a `status`
(`enforced` / `partial` / `doc-only`) and the deterministic `backing`
that sustains it. This gate proves the registry and the standard cannot
drift apart:

- every `### M<n>.` heading in the standard has exactly one registry
  entry, and vice versa (no orphaned or missing rows);
- every `enforced` / `partial` row resolves each `backing` reference to a
  real artifact (`script:` -> scripts/<name>.py, `test:` ->
  tests/<name>.py, `tool:` -> referenced in pyproject.toml);
- every `doc-only` row has an empty `backing` list, so a claim of
  enforcement always carries a resolvable gate.

It does not prove the backing gate is *correct*; only that a row marked
enforced has a gate that exists. Tightening a row from doc-only/partial
to enforced (and adding the gate it names) is the unit of follow-up work.

Contract:
- Inputs: the `verify` subcommand; `--standard` (defaults to the standard
  doc), `--registry` (defaults to the enforcement TOML), `--repo-root`
  (defaults to the repository root, used to resolve backing references).
- Outputs: `::error::` annotations on stderr naming each drift; exit 0
  when the standard and registry agree and all enforced backings resolve,
  exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate;
  any drift or unresolved backing exits non-zero).

Tested by `tests/test_scan_quality_standard_drift.py`. Refs #1089, #196, #197.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STANDARD = REPO_ROOT / "docs" / "standards" / "workflow-script-quality.md"
REGISTRY = REPO_ROOT / "docs" / "standards" / "workflow-script-quality.enforcement.toml"

# `### M1. ...`, `### M10. ...`. Optional-enhancement (`O`) and coverage
# graduation (`G`) headings are intentionally excluded: the registry maps
# must-haves only.
_MUST_HAVE_HEADING = re.compile(r"(?m)^###\s+(M\d+)\.")

_VALID_STATUS = frozenset({"enforced", "partial", "doc-only"})
# A `tool:` backing reference resolves when its name appears anywhere in
# pyproject.toml (a dev dependency or a `[tool.<name>]` config block).
_KNOWN_TOOLS = frozenset({"ruff", "mypy", "pytest", "coverage"})


def parse_must_haves(standard_text: str) -> set[str]:
    """Return the set of must-have ids declared as headings in the standard."""
    return set(_MUST_HAVE_HEADING.findall(standard_text))


def resolve_backing(ref: str, repo_root: Path, pyproject_text: str) -> str | None:
    """Return a defect string when *ref* does not resolve, else None.

    `script:<name>` -> scripts/<name>.py exists.
    `test:<name>`   -> tests/<name>.py exists.
    `tool:<name>`   -> <name> is a known tool referenced in pyproject.toml.
    """
    kind, _, name = ref.partition(":")
    if not name:
        return f"backing '{ref}' is missing a ':<name>' target"
    if kind == "script":
        if not (repo_root / "scripts" / f"{name}.py").is_file():
            return f"backing '{ref}' resolves to no scripts/{name}.py"
        return None
    if kind == "test":
        if not (repo_root / "tests" / f"{name}.py").is_file():
            return f"backing '{ref}' resolves to no tests/{name}.py"
        return None
    if kind == "tool":
        if name not in _KNOWN_TOOLS:
            return f"backing '{ref}' names an unknown tool (known: {sorted(_KNOWN_TOOLS)})"
        if name not in pyproject_text:
            return f"backing '{ref}' is not referenced in pyproject.toml"
        return None
    return f"backing '{ref}' has an unknown kind '{kind}' (use script:/test:/tool:)"


def find_drift(
    must_haves: set[str],
    registry: dict[str, object],
    repo_root: Path,
    pyproject_text: str,
) -> list[str]:
    """Return the sorted list of drift defects between standard and registry."""
    defects: list[str] = []

    registry_keys = set(registry)
    for missing in sorted(must_haves - registry_keys):
        defects.append(f"{missing} is a must-have in the standard but has no registry entry")
    for orphan in sorted(registry_keys - must_haves):
        defects.append(f"{orphan} is in the registry but is not a must-have heading in the standard")

    for key in sorted(must_haves & registry_keys):
        entry = registry[key]
        if not isinstance(entry, dict):
            defects.append(f"{key} registry entry is not a table")
            continue
        status = entry.get("status")
        backing = entry.get("backing")
        if status not in _VALID_STATUS:
            defects.append(f"{key} has invalid status {status!r} (use {sorted(_VALID_STATUS)})")
            continue
        if not isinstance(backing, list) or not all(isinstance(item, str) for item in backing):
            defects.append(f"{key} backing must be a list of strings")
            continue
        if status == "doc-only":
            if backing:
                defects.append(f"{key} is doc-only but lists backing {backing}; doc-only rows must be empty")
            continue
        # enforced / partial
        if not backing:
            defects.append(f"{key} is {status} but lists no backing; an enforced claim needs a gate")
            continue
        for ref in backing:
            problem = resolve_backing(ref, repo_root, pyproject_text)
            if problem is not None:
                defects.append(f"{key}: {problem}")
    return defects


def cmd_verify(args: argparse.Namespace) -> int:
    standard = Path(args.standard)
    registry_path = Path(args.registry)
    repo_root = Path(args.repo_root)
    pyproject_text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")

    must_haves = parse_must_haves(standard.read_text(encoding="utf-8"))
    with registry_path.open("rb") as handle:
        registry = tomllib.load(handle)

    defects = find_drift(must_haves, registry, repo_root, pyproject_text)
    for defect in defects:
        print(
            f"::error file=docs/standards/workflow-script-quality.enforcement.toml::{defect}.",
            file=sys.stderr,
        )
    if defects:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the workflow-script-quality standard stays enforcement-mapped.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser(
        "verify",
        help="Fail (exit 1) when the standard and its enforcement registry drift.",
    )
    verify.add_argument("--standard", default=str(STANDARD), help="Path to the standard doc.")
    verify.add_argument("--registry", default=str(REGISTRY), help="Path to the enforcement TOML.")
    verify.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root used to resolve backing references.",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
