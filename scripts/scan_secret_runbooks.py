#!/usr/bin/env python3
"""Verify named workflow secrets have concrete runbook issuance steps.

Refs #703. Workflow changes that introduce a named secret such as
``${{ secrets.EXAMPLE_PAT }}`` must also document the operator handoff:
where to create the token, where to store it, the minimum permissions,
rotation cadence, and a verification step that proves the handoff works
without printing the value. This gate makes that rule reproducible for
future PRs instead of relying on reviewer memory.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
RUNBOOKS_DIR = REPO_ROOT / "docs" / "runbooks"

SECRET_REF_RE = re.compile(r"\bsecrets\.([A-Z][A-Z0-9_]*)\b")
IGNORED_SECRETS = frozenset({"GITHUB_TOKEN"})


@dataclass(frozen=True)
class SecretUse:
    """One named ``secrets.NAME`` reference in a workflow."""

    name: str
    path: Path
    line: int


@dataclass(frozen=True)
class Runbook:
    """One runbook document under ``docs/runbooks``."""

    path: Path
    text: str


@dataclass(frozen=True)
class Requirement:
    """One concrete issuance detail expected in a runbook."""

    name: str
    matches: Callable[[str, str], bool]


REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement(
        name="one-time setup heading",
        matches=lambda secret, text: f"One-time setup for `{secret}`" in text,
    ),
    Requirement(
        name="secret storage location",
        matches=lambda _secret, text: any(
            phrase in text
            for phrase in (
                "Environment secret",
                "environment secret",
                "repository secret",
                "repo-level secret",
                "GitHub Environment",
            )
        ),
    ),
    Requirement(
        name="minimum permissions",
        matches=lambda _secret, text: any(
            phrase in text
            for phrase in (
                "Repository permissions",
                "minimum permissions",
                "Permissions",
                "permissions",
            )
        ),
    ),
    Requirement(
        name="rotation cadence",
        matches=lambda _secret, text: "rotation" in text.lower(),
    ),
    Requirement(
        name="verification step",
        matches=lambda _secret, text: any(
            phrase in text.lower()
            for phrase in (
                "verify",
                "verification",
                "confirm",
                "wait for",
                "guard step",
            )
        ),
    ),
)


def rel(path: Path, root: Path) -> Path:
    """Return *path* relative to *root* when possible."""
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def collect_secret_uses(workflows_dir: Path, root: Path) -> list[SecretUse]:
    """Return all named workflow secret references except built-ins."""
    uses: list[SecretUse] = []
    for path in sorted((*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml"))):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in SECRET_REF_RE.finditer(line):
                name = match.group(1)
                if name in IGNORED_SECRETS:
                    continue
                uses.append(SecretUse(name=name, path=rel(path, root), line=lineno))
    return uses


def collect_runbooks(runbooks_dir: Path, root: Path) -> list[Runbook]:
    """Return all Markdown runbooks."""
    return [
        Runbook(path=rel(path, root), text=path.read_text(encoding="utf-8"))
        for path in sorted(runbooks_dir.glob("*.md"))
    ]


def missing_requirements(secret: str, text: str) -> list[str]:
    """Return concrete issuance details missing for *secret* in *text*."""
    return [
        requirement.name
        for requirement in REQUIREMENTS
        if not requirement.matches(secret, text)
    ]


def best_documented_runbook(secret: str, runbooks: list[Runbook]) -> tuple[Runbook | None, list[str]]:
    """Return the runbook with the fewest missing requirements for *secret*."""
    candidates = [runbook for runbook in runbooks if secret in runbook.text]
    if not candidates:
        return None, [requirement.name for requirement in REQUIREMENTS]

    ranked = sorted(
        ((runbook, missing_requirements(secret, runbook.text)) for runbook in candidates),
        key=lambda item: (len(item[1]), item[0].path.as_posix()),
    )
    return ranked[0]


def format_refs(uses: list[SecretUse]) -> str:
    """Return compact workflow references for a diagnostic."""
    return ", ".join(f"{use.path.as_posix()}:{use.line}" for use in uses)


def verify(root: Path) -> list[str]:
    """Return validation errors for workflow secret runbook coverage."""
    uses = collect_secret_uses(root / ".github" / "workflows", root)
    runbooks = collect_runbooks(root / "docs" / "runbooks", root)

    errors: list[str] = []
    by_secret: dict[str, list[SecretUse]] = {}
    for use in uses:
        by_secret.setdefault(use.name, []).append(use)

    for secret, secret_uses in sorted(by_secret.items()):
        runbook, missing = best_documented_runbook(secret, runbooks)
        if not missing:
            continue
        location = "no runbook mentions the secret" if runbook is None else f"{runbook.path.as_posix()} is incomplete"
        errors.append(
            f"secret {secret} is referenced from {format_refs(secret_uses)}, "
            f"but {location}; missing: {', '.join(missing)}"
        )

    return errors


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root)
    errors = verify(root)
    for error in errors:
        print(f"::error::{error}", file=sys.stderr)
    if errors:
        return 1
    print("OK: workflow named secrets have concrete runbook issuance steps.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root to scan.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify", help="Verify workflow secret runbooks.")
    verify_parser.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
