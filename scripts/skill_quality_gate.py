#!/usr/bin/env python3
"""Deterministic skill quality gate built on ``waza check``.

``waza`` (https://github.com/microsoft/waza) validates agent skills, but
``waza check`` returns exit code 0 even for non-compliant skills, so it
cannot gate a commit or CI run on its own. This wrapper runs
``waza check --format json`` against each skill, parses the result, and
decides the exit code per the policy fixed in issue #1099:

* spec-compliance failure  -> FAIL (exit 1). These are mechanical,
  spec-defined violations (bad name, dir mismatch, disallowed frontmatter
  field, ...). They are cheap to fix and must never land.
* token budget exceedance  -> WARNING only (exit 0). Every existing skill
  already exceeds waza's default 500-token hard limit; failing on it would
  red-line the entire baseline. Surfaced so drift stays visible.
* ``ready: false``         -> informational. ``ready`` folds in the token
  limit and eval-suite presence, neither of which we gate on here.

The LLM-as-Judge path (``waza quality``) is intentionally NOT invoked: it
routes full SKILL.md content through the embedded GitHub Copilot CLI to a
judge model (external send, non-deterministic, requires auth). It stays a
manual, opt-in tool; never part of this automated gate. See #1099.

Usage:

    python scripts/skill_quality_gate.py verify [SKILL ...]

With no arguments, ``verify`` discovers every ``SKILL.md`` under
``.agents/skills/``. Paths (a SKILL.md file or its directory) may be passed
to check a subset; this is what the pre-commit hook does, passing only the
changed skills.

Spec failures are emitted as ``::error file=<path>::`` and token warnings as
``::warning file=<path>::`` so the GitHub Actions UI surfaces each one.

Contract:
- Inputs: the ``verify`` subcommand; optional skill paths (SKILL.md files
  or their directories) as positional args, defaulting to every skill
  under ``.agents/skills/``; ``--repo-root`` (default ``.``); the
  ``waza`` binary resolved from PATH or the Go bin hints.
- Outputs: ``::error file=<path>::`` for each spec-compliance failure and
  ``::warning file=<path>::`` for each token-budget exceedance on stderr,
  plus ``OK``/``FAIL`` per skill on stdout; exit 0 when every skill passes
  spec-compliance (token warnings do not affect the code), exit 1 on any
  spec failure or when waza is missing/unparseable.
- Failure policy: fails loud per CLAUDE.md section 4 (gate: a spec
  violation, a missing waza binary, or unparseable waza output all exit
  non-zero rather than silently passing).

Refs #1099.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILLS_SUBDIR = ".agents/skills"

# Locations to probe for the waza binary beyond a bare PATH lookup, so the
# gate works whether waza was installed via scripts/install_waza.sh or is
# already on PATH. Kept in sync with install_waza.sh: the prebuilt-download
# path installs to ~/.local/bin, and the go-install backstop drops it in the
# Go bin dir.
_GO_BIN_HINTS = (
    Path.home() / ".local" / "bin",
    Path.home() / "go" / "bin",
    Path("/root/go/bin"),
)


def find_waza() -> str | None:
    """Return a path to the waza binary, or None if it cannot be found."""
    found = shutil.which("waza")
    if found:
        return found
    for hint in _GO_BIN_HINTS:
        candidate = hint / "waza"
        if candidate.is_file():
            return str(candidate)
    return None


def discover_skills(repo_root: Path) -> list[Path]:
    """Return the directory of every skill under ``.agents/skills/``."""
    skills_dir = repo_root / SKILLS_SUBDIR
    return sorted(
        p.parent for p in skills_dir.glob("*/SKILL.md") if p.is_file()
    )


def _normalize_target(repo_root: Path, raw: str) -> Path | None:
    """Resolve a CLI argument to a skill directory containing SKILL.md.

    Accepts either the SKILL.md file or its directory. Returns None when the
    target has no SKILL.md (e.g. an unrelated path matched by a glob).
    """
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    if path.name == "SKILL.md":
        path = path.parent
    if (path / "SKILL.md").is_file():
        return path
    return None


def run_waza_check(waza: str, skill_dir: Path) -> dict[str, Any]:
    """Run ``waza check --format json`` for one skill and parse the result.

    Raises RuntimeError (loudly) if waza cannot run or emits unparseable
    output; a broken gate must never be mistaken for a passing one.
    """
    proc = subprocess.run(  # noqa: S603 -- argv built from the resolved waza path and skill dir, shell=False
        [waza, "check", "--format", "json", "--no-update-check", str(skill_dir)],
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        raise RuntimeError(
            f"waza produced no JSON for {skill_dir} "
            f"(exit {proc.returncode}): {proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"could not parse waza JSON for {skill_dir}: {exc}\n"
            f"stderr: {proc.stderr.strip()}"
        ) from exc


def evaluate_skill(entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (spec_failures, token_warnings) message lists for one skill."""
    spec_failures: list[str] = []
    token_warnings: list[str] = []

    for check in entry.get("specCompliance", []):
        # ``passed`` is the gate; ``status: warning`` entries keep
        # ``passed: true`` (e.g. missing optional license/version), so they
        # never trip a failure here.
        if not check.get("passed", True):
            spec_failures.append(
                f"{check.get('name', '?')}: {check.get('summary', '')}"
            )

    budget = entry.get("tokenBudget", {})
    if budget.get("exceeded"):
        token_warnings.append(
            f"{budget.get('count', '?')} tokens "
            f"(hard limit {budget.get('limit', '?')})"
        )

    return spec_failures, token_warnings


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()

    waza = find_waza()
    if waza is None:
        print(
            "::error::waza binary not found. Run scripts/install_waza.sh first.",
            file=sys.stderr,
        )
        return 1

    if args.skills:
        targets: list[Path] = []
        for raw in args.skills:
            target = _normalize_target(repo_root, raw)
            if target is None:
                print(
                    f"skill-quality-gate: skipping '{raw}' (no SKILL.md)",
                    file=sys.stderr,
                )
                continue
            targets.append(target)
    else:
        targets = discover_skills(repo_root)

    if not targets:
        print("skill-quality-gate: no skills to check.", file=sys.stderr)
        return 0

    total_failures = 0
    for skill_dir in targets:
        result = run_waza_check(waza, skill_dir)
        for entry in result.get("skills", []):
            rel = Path(entry.get("path", str(skill_dir)))
            with contextlib.suppress(ValueError):
                rel = rel.relative_to(repo_root)
            spec_failures, token_warnings = evaluate_skill(entry)

            for msg in token_warnings:
                print(
                    f"::warning file={rel}::token budget {msg}; "
                    f"warning only (not a gate failure).",
                    file=sys.stderr,
                )
            for msg in spec_failures:
                print(f"::error file={rel}::spec-compliance failed: {msg}", file=sys.stderr)

            if spec_failures:
                total_failures += len(spec_failures)
                print(f"FAIL {rel}: {len(spec_failures)} spec violation(s).", file=sys.stderr)
            else:
                print(f"OK   {rel}")

    if total_failures:
        print(
            f"skill-quality-gate: {total_failures} spec-compliance "
            f"violation(s); commit blocked.",
            file=sys.stderr,
        )
        return 1
    print("skill-quality-gate: all skills pass spec-compliance.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Check skills with waza; exit 1 on any spec-compliance failure.",
    )
    p_verify.add_argument(
        "skills",
        nargs="*",
        help="Skill dirs or SKILL.md paths. Default: all under .agents/skills.",
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
