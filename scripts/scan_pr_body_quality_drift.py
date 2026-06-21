#!/usr/bin/env python3
"""Deterministic gate: the PR body content-quality enforcement registry stays current.

The workflow `.github/workflows/verify-agents.yml` invokes this module from
the `lint-scripts-static` job. It is the root-cause fix for PR body quality
defects (placeholder-residue, empty-section, missing-good-bad-examples,
retro-feedback-loop) being doc-only: only reviewer memory prevented regression,
which violates CLAUDE.md section 3.

`docs/standards/pr-body-quality.enforcement.toml` is the registry mapping each
known defect class to a `status` (`enforced` / `partial` / `doc-only`) and the
deterministic `backing` that sustains it. This gate proves the registry is
internally consistent:

- every `enforced` / `partial` row resolves each `backing` reference to a real
  artifact (`script:` -> scripts/<name>.py, `test:` -> tests/<name>.py);
- every `doc-only` row has an empty `backing` list, so a claim of enforcement
  always carries a resolvable gate;
- every key in the registry is a known defect class (no orphaned rows);
- every known defect class has a row in the registry (no missing rows).

It does not prove the backing gate is *correct* -- only that a row marked
enforced has a gate that exists. Tightening a row from doc-only/partial to
enforced (and adding the gate it names) is the unit of follow-up work.

Contract:
- Inputs: the `verify` subcommand; `--registry` (defaults to the enforcement
  TOML), `--repo-root` (defaults to the repository root).
- Outputs: `::error::` annotations on stderr naming each drift; exit 0 when
  all enforced backings resolve; exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4; exit 1 on any drift or
  unresolved backing.

Tested by `tests/test_scan_pr_body_quality_drift.py`. Refs #1828.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "docs" / "standards" / "pr-body-quality.enforcement.toml"

_VALID_STATUS = frozenset({"enforced", "partial", "doc-only"})

# Defect classes tracked in the registry. Each maps to a row in the TOML.
# Adding a new companion issue adds a row here and in the TOML simultaneously.
KNOWN_DEFECTS: frozenset[str] = frozenset(
    {
        "placeholder-residue",
        "empty-section",
        "missing-good-bad-examples",
        "retro-feedback-loop",
    }
)


def resolve_backing(ref: str, repo_root: Path) -> str | None:
    """Return a defect string when *ref* does not resolve, else None.

    `script:<name>` -> scripts/<name>.py exists.
    `test:<name>`   -> tests/<name>.py exists.
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
    return f"backing '{ref}' has an unknown kind '{kind}' (use script:/test:)"


def find_drift(
    registry: dict[str, object],
    repo_root: Path,
) -> list[str]:
    """Return the sorted list of drift defects in *registry*."""
    defects: list[str] = []

    registry_keys = set(registry)
    for orphan in sorted(registry_keys - KNOWN_DEFECTS):
        defects.append(
            f"'{orphan}' is in the registry but is not a known defect class"
        )
    for missing in sorted(KNOWN_DEFECTS - registry_keys):
        defects.append(
            f"'{missing}' is a known defect class but has no row in the registry"
        )

    for key in sorted(registry_keys & KNOWN_DEFECTS):
        entry = registry[key]
        if not isinstance(entry, dict):
            defects.append(f"'{key}' registry entry is not a table")
            continue
        status = entry.get("status")
        backing = entry.get("backing")
        if status not in _VALID_STATUS:
            defects.append(
                f"'{key}' has invalid status {status!r} (use {sorted(_VALID_STATUS)})"
            )
            continue
        if not isinstance(backing, list) or not all(
            isinstance(item, str) for item in backing
        ):
            defects.append(f"'{key}' backing must be a list of strings")
            continue
        if status == "doc-only":
            if backing:
                defects.append(
                    f"'{key}' is doc-only but lists backing {backing}; "
                    "doc-only rows must have an empty backing list"
                )
            continue
        # enforced / partial
        if not backing:
            defects.append(
                f"'{key}' is {status} but lists no backing; "
                "an enforced claim needs a gate"
            )
            continue
        for ref in backing:
            problem = resolve_backing(ref, repo_root)
            if problem is not None:
                defects.append(f"'{key}': {problem}")
    return defects


def cmd_verify(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    repo_root = Path(args.repo_root)

    with registry_path.open("rb") as handle:
        registry = tomllib.load(handle)

    defects = find_drift(registry, repo_root)
    for defect in defects:
        print(
            f"::error file=docs/standards/pr-body-quality.enforcement.toml::{defect}.",
            file=sys.stderr,
        )
    if defects:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the PR body content-quality enforcement registry.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser(
        "verify",
        help=(
            "Fail (exit 1) when the registry has orphaned rows or an "
            "enforced/partial row names a backing that does not exist."
        ),
    )
    verify.add_argument(
        "--registry", default=str(REGISTRY), help="Path to the enforcement TOML."
    )
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
