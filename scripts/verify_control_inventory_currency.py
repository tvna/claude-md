#!/usr/bin/env python3
"""Deterministic gate: the security-control inventory stays current with the tree.

Refs #1387. ``docs/prd/security-control-inventory.md`` maps every
security-relevant repository surface to its defense, evidence, and coverage
status. Re-verification used to be manual ("re-read whenever a workflow,
script, ruleset, or runbook lands"), so the inventory drifted: privileged
surfaces landed without a row and cited evidence paths went stale. This gate
makes currency a continuous, fail-loud invariant instead of reviewer memory
(CLAUDE.md section 3).

The gate is tree-only and runs with no network, so it cannot read GitHub issue
state; reconciling a *closed* tracking issue that lingers in a Gap column stays
a one-time resync plus the weekly drift job's domain, not this gate.

Scope: the auto-detection is deliberately NARROW and high-precision. It flags
exactly the surfaces that cross a secret or privilege boundary:

- a workflow under ``.github/workflows/`` that references a non-``GITHUB_TOKEN``
  secret (a PAT or GitHub App key) OR declares an ``environment:``;
- a script under ``scripts/`` that imports the shared secret-pattern detector
  ``_secret_patterns``.

The broad ``gate_*`` / ``preflight_*`` / ``_github_api`` globs are intentionally
NOT the signal: they predominantly match CI-process gates (40+ files) rather
than ATT&CK security controls, so listing them would create a large exempt
table that is itself a drift surface (CLAUDE.md section 4).

Every detected surface MUST be listed in
``.github/security-surface-inventory.toml`` (the machine-readable manifest),
either as ``status = "inventory"`` (it has a row in the inventory document) or
``status = "exempt"`` with a non-empty ``reason``. A NEW privileged surface in
neither fails CI, forcing a human to add a row or a justified exemption.

Checks (all tree-only, fail-loud per CLAUDE.md section 4):
1. coverage: every auto-detected privileged surface is listed in the manifest;
2. manifest integrity: every manifest ``path`` exists on disk; every
   ``status = "inventory"`` surface is represented in the inventory document;
   every ``status = "exempt"`` surface carries a non-empty ``reason``;
3. dangling references: every ``scripts/<name>.py`` path-form citation in the
   inventory document resolves to a file on disk. The matching workflow
   path-form check (``.github/workflows/<name>.yml``) is intentionally left to
   ``scripts/scan_doc_workflow_refs.py``, which already enforces it across all
   tracked Markdown; duplicating it here would be a second detector for one
   invariant. Bare basenames (e.g. ``dependabot.yml``, which is
   ``.github/dependabot.yml``) are not path-form and are not checked, matching
   that gate's deliberate scope.

Contract:
- Inputs: the committed tree under ``--root`` (defaults to the repository
  root): ``docs/prd/security-control-inventory.md``,
  ``.github/security-surface-inventory.toml``, ``.github/workflows/*.yml`` and
  ``scripts/*.py``. No network, no environment variables.
- Outputs: ``::error::`` annotations on stderr naming each drift (unlisted
  privileged surface, missing inventory row, empty exemption reason, stale
  manifest path, or dangling reference); exit 0 when the inventory is current,
  exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate); a
  malformed manifest is reported as a structural error rather than skipped.

Tested by ``tests/test_verify_control_inventory_currency.py``.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = Path("docs/prd/security-control-inventory.md")
MANIFEST_PATH = Path(".github/security-surface-inventory.toml")
WORKFLOWS_DIR = Path(".github/workflows")
SCRIPTS_DIR = Path("scripts")

VALID_STATUSES = frozenset({"inventory", "exempt"})

# A non-built-in secret reference (PAT or GitHub App key) marks a privileged
# workflow; GITHUB_TOKEN is the default least-privilege token and is excluded.
SECRET_REF_RE = re.compile(r"\bsecrets\.([A-Z][A-Z0-9_]*)\b")
ENVIRONMENT_RE = re.compile(r"^\s*environment:", re.MULTILINE)
SECRET_PATTERNS_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+_secret_patterns\b", re.MULTILINE
)
IGNORED_SECRETS = frozenset({"GITHUB_TOKEN"})

# A backtick-quoted scripts/ path-form citation in the inventory. The leading
# `scripts/` is required so a bare basename (which could be a test file or a
# doc) is not misattributed; matching scan_doc_workflow_refs.py's path-form
# scope for the workflow side.
CITED_SCRIPT_RE = re.compile(r"`scripts/([a-z_][a-z0-9_]*\.py)`")


@dataclass(frozen=True)
class ManifestSurface:
    """One declared surface in the security-surface manifest."""

    path: str
    status: str
    reason: str


def detect_privileged_surfaces(root: Path) -> set[str]:
    """Return repo-relative paths of surfaces crossing a secret/privilege line."""
    detected: set[str] = set()

    workflows = root / WORKFLOWS_DIR
    if workflows.is_dir():
        for path in sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml"))):
            text = path.read_text(encoding="utf-8")
            secrets = {
                name
                for name in SECRET_REF_RE.findall(text)
                if name not in IGNORED_SECRETS
            }
            if secrets or ENVIRONMENT_RE.search(text):
                detected.add(path.relative_to(root).as_posix())

    scripts = root / SCRIPTS_DIR
    if scripts.is_dir():
        for path in sorted(scripts.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if SECRET_PATTERNS_IMPORT_RE.search(text):
                detected.add(path.relative_to(root).as_posix())

    return detected


def load_manifest(path: Path) -> tuple[list[ManifestSurface], list[str]]:
    """Parse the manifest; return (surfaces, structural errors)."""
    errors: list[str] = []
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], [f"manifest not found: {path.as_posix()}"]
    except tomllib.TOMLDecodeError as exc:
        return [], [f"manifest is not valid TOML ({path.as_posix()}): {exc}"]

    surfaces: list[ManifestSurface] = []
    for entry in raw.get("surfaces", []):
        surface_path = entry.get("path", "")
        status = entry.get("status", "")
        reason = entry.get("reason", "")
        if not surface_path:
            errors.append("manifest surface entry is missing a 'path'")
            continue
        if status not in VALID_STATUSES:
            errors.append(
                f"manifest surface {surface_path!r} has invalid status "
                f"{status!r}; expected one of {sorted(VALID_STATUSES)}"
            )
        surfaces.append(
            ManifestSurface(path=surface_path, status=status, reason=reason)
        )
    return surfaces, errors


def represented_in_inventory(inventory_text: str, surface_path: str) -> bool:
    """Return True when *surface_path*'s basename is cited in the inventory."""
    basename = Path(surface_path).name
    return f"`{basename}`" in inventory_text or f"`{surface_path}`" in inventory_text


def cited_paths(inventory_text: str) -> set[str]:
    """Return scripts/ path-form citations in the inventory document."""
    return {
        f"{SCRIPTS_DIR.as_posix()}/{match}"
        for match in CITED_SCRIPT_RE.findall(inventory_text)
    }


def verify(root: Path) -> list[str]:
    """Return inventory-currency diagnostics (empty when current)."""
    root = root.resolve()
    errors: list[str] = []

    inventory_file = root / INVENTORY_PATH
    if not inventory_file.exists():
        return [f"inventory document not found: {INVENTORY_PATH.as_posix()}"]
    inventory_text = inventory_file.read_text(encoding="utf-8")

    surfaces, manifest_errors = load_manifest(root / MANIFEST_PATH)
    errors.extend(manifest_errors)
    listed = {surface.path for surface in surfaces}

    # Check 1: every auto-detected privileged surface is in the manifest.
    detected = detect_privileged_surfaces(root)
    for surface_path in sorted(detected - listed):
        errors.append(
            f"privileged surface {surface_path} is not listed in "
            f"{MANIFEST_PATH.as_posix()}; add it with status=\"inventory\" (and a "
            "row in the inventory) or status=\"exempt\" with a reason"
        )

    # Check 2: manifest integrity.
    for surface in surfaces:
        if not (root / surface.path).exists():
            errors.append(
                f"manifest lists {surface.path}, which does not exist on disk; "
                "remove the stale entry"
            )
            continue
        if surface.status == "inventory" and not represented_in_inventory(
            inventory_text, surface.path
        ):
            errors.append(
                f"manifest marks {surface.path} status=\"inventory\" but it is "
                f"not represented in {INVENTORY_PATH.as_posix()}; add a row or "
                "switch it to status=\"exempt\" with a reason"
            )
        if surface.status == "exempt" and not surface.reason.strip():
            errors.append(
                f"manifest marks {surface.path} status=\"exempt\" with an empty "
                "reason; an exemption must justify why it carries no inventory row"
            )

    # Check 3: dangling references in the inventory document.
    for cited in sorted(cited_paths(inventory_text)):
        if not (root / cited).exists():
            errors.append(
                f"{INVENTORY_PATH.as_posix()} cites {cited}, which does not exist "
                "on disk; fix the stale reference"
            )

    return errors


def cmd_verify(args: argparse.Namespace) -> int:
    errors = verify(Path(args.root))
    for error in errors:
        print(f"::error::{error}", file=sys.stderr)
    if errors:
        return 1
    print("OK: security-control inventory is current with the tree.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser(
        "verify", help="Verify the inventory is current with the tree."
    )
    verify_parser.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
