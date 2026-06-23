#!/usr/bin/env python3
"""Deterministic gate: every workflow-called script declares its input Contract.

The workflow ``.github/workflows/verify-agents.yml`` invokes this module
from the ``lint-scripts-static`` job. It is the missing deterministic
enforcement for two must-have items in
``docs/standards/workflow-script-quality.md`` that were previously left to
reviewer memory (against CLAUDE.md section 3): M4 (input validation at the
workflow boundary) and M9 (fail-loud vs fail-open policy declared in the
module docstring).

The check is static and narrow. For every public ``scripts/<name>.py``
referenced by any workflow under ``.github/workflows/`` (private helpers
prefixed with ``_`` are out of scope; they are never CLI entry points),
the module docstring must carry the canonical ``Contract:`` block shown in
the standard's skeleton:

    Contract:
    - Inputs: <flag list and env-var fallbacks>.
    - Outputs: <stdout shape>, <summary file shape>, <exit codes>.
    - Failure policy: fails <loud|open> per CLAUDE.md section 4.

Requiring the block forces the author to enumerate every boundary (the
precondition for validating it) and to declare the failure posture. It
does not, and cannot, statically prove the validation is correct; that
remains the job of review and the M2/M3 tests.

Gradual adoption: scripts that predate this gate and have not yet been
backfilled are listed in :data:`BASELINE_MISSING_CONTRACT` with a
rationale, mirroring ``scan_maintainability_metrics.DEFERRED_OVERSIZE_MODULES``.
New scripts must comply on day one. The baseline is a ratchet: an entry
that becomes compliant (or leaves the workflow-referenced set) is reported
as stale and must be deleted, so the debt can only shrink.

Contract:
- Inputs: the ``verify`` subcommand; ``--workflows-dir`` (defaults to
  ``.github/workflows``) and ``--scripts-dir`` (defaults to ``scripts``).
- Outputs: ``::error file=scripts/<name>.py::`` annotations on stderr for
  each non-baseline violation and for each stale baseline entry; exit 0
  when the tree is clean, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate, so
  any unexpected input or missing Contract block exits non-zero).

Tested by ``tests/test_scan_input_contract_drift.py``. Refs #1087, #191.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

from scan_preflight_drift import extract_script_refs

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# A module docstring satisfies the contract when it carries a ``Contract:``
# marker line plus an ``Inputs:`` line, an ``Outputs:`` line, and a
# ``Failure policy:`` line whose value names ``loud`` or ``open``. The
# label matchers tolerate a leading bullet and a parenthetical qualifier
# (e.g. ``- Inputs (aggregate):``) so an existing well-formed variant is
# not forced into a churned rewrite.
_CONTRACT_MARKER = re.compile(r"(?m)^\s*Contract:\s*$")
_INPUTS = re.compile(r"(?im)^\s*[-*]?\s*Inputs\b[^:\n]*:")
_OUTPUTS = re.compile(r"(?im)^\s*[-*]?\s*Outputs\b[^:\n]*:")
_FAILURE_POLICY = re.compile(r"(?im)^\s*[-*]?\s*Failure policy\b[^:\n]*:\s*(.+)$")
_POLICY_VALUE = re.compile(r"\b(loud|open)\b", re.IGNORECASE)

# Scripts referenced by a workflow before this gate landed that have not
# yet been backfilled with a Contract block. Each entry is deferred debt
# tracked by #1087; the set may only shrink. Adding a brand-new script
# here instead of writing its Contract block is a review-blocking defect.
_BASELINE_REASON = "pre-#1087 script; Contract: docstring backfill tracked by #1087."
BASELINE_MISSING_CONTRACT: dict[str, str] = {
    name: _BASELINE_REASON
    for name in (
        "analyze_ci_timings",
        "attack_review_reminder",
        "auto_retro",
        "backup_archive",
        "branch_cleanup",
        "coverage_failure_issue",
        "dependabot_labels",
        "devcontainer_pin_pr",
        "github_paginate",
        "issue_link",
        "labels_apply",
        "nixpkgs_cooldown",
        "post_issue_comment",
        "pr_upsert",
        "preflight_all",
        "ruleset_drift",
        "rulesets_apply",
        "scan_apm_portability",
        "scan_docs_inventory",
        "scan_hook_coverage_drift",
        "scan_maintainability_metrics",
        "scan_markdown_links",
        "scan_preflight_drift",
        "scan_retro_followup_drift",
        "scan_secret_runbooks",
        "scan_workflow_action_pins",
        "scan_workflow_gh_calls",
        "scan_workflow_pip",
        "update_devcontainer_image_pins",
        "uv_pin",
        "validate_json_syntax",
        "verify_apm_checksums",
        "verify_linked_issue_titles",
        "verify_readme_translation",
        "verify_required_check_contexts",
        "verify_ruleset_sync",
        "verify_shard_coverage",
        "verify_test_shard_markers",
        "workflow_diagram",
    )
}


def check_contract(docstring: str | None) -> list[str]:
    """Return the list of missing/invalid Contract elements for *docstring*.

    An empty list means the docstring satisfies the convention. A
    non-empty list names each defect so the annotation is actionable.
    """
    if not docstring:
        return ["missing module docstring"]
    defects: list[str] = []
    if not _CONTRACT_MARKER.search(docstring):
        defects.append("missing 'Contract:' marker line")
    if not _INPUTS.search(docstring):
        defects.append("missing 'Inputs:' line")
    if not _OUTPUTS.search(docstring):
        defects.append("missing 'Outputs:' line")
    match = _FAILURE_POLICY.search(docstring)
    if match is None:
        defects.append("missing 'Failure policy:' line")
    elif not _POLICY_VALUE.search(match.group(1)):
        defects.append("'Failure policy:' must declare 'loud' or 'open'")
    return defects


def read_module_docstring(path: Path) -> str | None:
    """Return the module-level docstring of *path*, or None if unavailable.

    Uses :func:`ast.get_docstring` rather than a text grep so a string
    literal in the body cannot masquerade as the module docstring.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    return ast.get_docstring(tree)


def collect_target_scripts(workflows_dir: Path, scripts_dir: Path) -> set[str]:
    """Return public script names referenced by any workflow YAML.

    The reference regex (reused from :mod:`scan_preflight_drift`) only
    matches names whose first character is a letter, so private helpers
    (``_github_api`` etc.) are excluded. The result is intersected with
    the files that actually exist so a reference in a comment to a removed
    script does not produce a phantom target.
    """
    existing = {
        path.stem for path in scripts_dir.glob("*.py") if not path.name.startswith("_")
    }
    referenced: set[str] = set()
    for path in sorted(workflows_dir.glob("*.yml")):
        referenced |= extract_script_refs(path.read_text(encoding="utf-8"))
    return referenced & existing


def find_violations(
    target_scripts: set[str],
    scripts_dir: Path,
    baseline: dict[str, str],
) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """Return ``(violations, stale_baseline)``.

    ``violations`` is the sorted list of ``(name, defects)`` for every
    target script that is not in *baseline* and fails the contract check.
    ``stale_baseline`` is the sorted list of baseline entries that are now
    compliant, or that no workflow references any more; either way the
    entry is dead and must be removed so the ratchet stays honest.
    """
    violations: list[tuple[str, list[str]]] = []
    for name in sorted(target_scripts):
        if name in baseline:
            continue
        defects = check_contract(read_module_docstring(scripts_dir / f"{name}.py"))
        if defects:
            violations.append((name, defects))

    stale: list[str] = []
    for name in sorted(baseline):
        if name not in target_scripts:
            stale.append(name)
            continue
        if not check_contract(read_module_docstring(scripts_dir / f"{name}.py")):
            stale.append(name)
    return violations, stale


def cmd_verify(args: argparse.Namespace) -> int:
    workflows_dir = Path(args.workflows_dir)
    scripts_dir = Path(args.scripts_dir)
    target = collect_target_scripts(workflows_dir, scripts_dir)
    violations, stale = find_violations(target, scripts_dir, BASELINE_MISSING_CONTRACT)

    for name, defects in violations:
        print(
            f"::error file=scripts/{name}.py::scripts/{name}.py is invoked by a "
            f"workflow but its module docstring is missing the Contract: block "
            f"(M4/M9): {'; '.join(defects)}. Add it per the skeleton in "
            f"docs/standards/workflow-script-quality.md.",
            file=sys.stderr,
        )
    for name in stale:
        print(
            f"::error file=scripts/scan_input_contract_drift.py::baseline entry "
            f"'{name}' in BASELINE_MISSING_CONTRACT is stale (now compliant or no "
            f"longer workflow-referenced); remove it so the baseline only shrinks.",
            file=sys.stderr,
        )

    if violations or stale:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify workflow-called scripts declare their input Contract.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser(
        "verify",
        help="Fail (exit 1) when a workflow script lacks the Contract: block.",
    )
    verify.add_argument(
        "--workflows-dir",
        default=str(WORKFLOWS_DIR),
        help="Directory containing the workflow YAML files.",
    )
    verify.add_argument(
        "--scripts-dir",
        default=str(SCRIPTS_DIR),
        help="Directory containing the workflow-called scripts.",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
