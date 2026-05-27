#!/usr/bin/env python3
"""Diff the local preflight set against the scripts CI's PR gates run.

Refs #493. Closes the second half of the verification-drift gap:
:mod:`preflight_all` is the contributor-facing entrypoint, and this
module is the deterministic gate that fails CI when a new
``python3 scripts/<name>.py`` call lands in a ``pull_request:``
workflow without a matching entry in :data:`preflight_all.STEPS`.

The detector is intentionally narrow:

* Source set -- ``.github/workflows/*.yml`` files whose ``on:`` block
  includes a ``pull_request:`` trigger. ``pull_request_target:``
  workflows are excluded because their input is webhook payload
  (issue / PR body), not the working tree, so they have no local
  equivalent. ``schedule:`` / ``workflow_dispatch:`` workflows are
  excluded for the same reason.
* Reference set -- ``preflight_all.STEPS``, retrieved via the
  ``--list`` JSON manifest so this module stays decoupled from
  :data:`preflight_all.STEPS`'s in-memory shape.
* Allowlist -- scripts that gate webhook-only input (PR / issue
  bodies, titles) or that are output-only helpers (``uv_pin read``).
  Each entry carries an inline rationale so future contributors can
  audit the exclusion.

Exit codes:
* ``0`` -- preflight and CI cover the same script set (modulo the
  allowlist). Extra preflight-only scripts produce a warning.
* ``1`` -- at least one ``pull_request:`` workflow invokes a script
  that ``preflight_all`` does not.

Tested by ``tests/test_scan_preflight_drift.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Matches `scripts/<name>.py` references inside workflow ``run:`` blocks.
# Underscore and digit allowed; the leading char must be a letter to keep
# private helpers like ``_github_api.py`` out (they are never CLI gates).
_SCRIPT_REF = re.compile(r"\bscripts/([a-zA-Z][\w]*)\.py\b")

# Scripts CI invokes from ``pull_request:`` workflows but that preflight
# intentionally does NOT mirror. Each entry pairs the script name with
# the reason and the client-side equivalent (if any), so the exclusion
# is auditable.
ALLOWLIST: dict[str, str] = {
    "title_policy": (
        "Input is the PR / issue title from the webhook payload, not the "
        "working tree. Client gate: scripts/preflight_title_policy.py "
        "(MCP PreToolUse)."
    ),
    "body_policy": (
        "Input is the PR / issue body from the webhook payload, not the "
        "working tree. Client gate: "
        "scripts/preflight_pr_body_required_sections.py (MCP PreToolUse)."
    ),
    "issue_link": (
        "Input is the PR body plus a GitHub API call rate-limited without "
        "GH_TOKEN. Client gate: scripts/pr_body_close_keyword_gate.py and "
        "scripts/preflight_pr_template_shape.py (MCP PreToolUse)."
    ),
    "uv_pin": (
        "Used twice: ``uv_pin read`` is an output helper (no gate), "
        "``uv_pin drift`` IS a gate and is mirrored as a preflight step."
    ),
    "preflight_all": (
        "Runner, not a gate. Mirroring itself would recurse; the drift "
        "gate is `scan_preflight_drift` which IS mirrored as a step."
    ),
    "verify_shard_coverage": (
        "Input is the per-leg JUnit XML artifacts produced by the "
        "lint-scripts-pytest matrix legs, which only exist in CI. The "
        "static counterpart `verify_test_shard_markers` IS mirrored as a "
        "preflight step. Refs #545."
    ),
}


@dataclass(frozen=True)
class WorkflowReference:
    """One ``scripts/<name>.py`` reference discovered in a workflow."""

    workflow: str
    script: str


def workflow_targets_pull_request(yaml_text: str) -> bool:
    """Return True iff *yaml_text* declares a ``pull_request:`` trigger.

    The check is line-oriented to avoid pulling in a YAML parser for a
    cheap top-level scan. Matches either the list form
    ``on: [pull_request, ...]`` or the mapping form

        on:
          pull_request:
            ...

    ``pull_request_target:`` is explicitly excluded because its colon
    follows the ``_target`` suffix.
    """
    in_on_block = False
    on_block_indent = -1
    for raw_line in yaml_text.splitlines():
        stripped = raw_line.lstrip()
        indent = len(raw_line) - len(stripped)
        if not stripped or stripped.startswith("#"):
            continue
        if not in_on_block:
            if stripped.startswith("on:"):
                tail = stripped[3:].strip()
                if tail.startswith("[") and "pull_request" in tail and "pull_request_target" not in tail.replace("pull_request_target", ""):
                    # List form: detect ``pull_request`` as its own token.
                    tokens = re.findall(r"[\w_]+", tail)
                    if "pull_request" in tokens:
                        return True
                in_on_block = True
                on_block_indent = indent
            continue
        if indent <= on_block_indent:
            # Left the on: block without finding pull_request:.
            return False
        # Inside the on: block. Match ``pull_request:`` exactly, not
        # ``pull_request_target:``.
        head = stripped.split(":", 1)[0]
        if head == "pull_request":
            return True
    return False


def extract_script_refs(yaml_text: str) -> set[str]:
    """Return the set of ``scripts/<name>`` references in *yaml_text*."""
    return set(_SCRIPT_REF.findall(yaml_text))


def collect_workflow_refs(workflows_dir: Path) -> list[WorkflowReference]:
    """Return every (workflow, script) pair from ``pull_request:`` workflows.

    The result is sorted by (workflow, script) for deterministic output.
    """
    refs: list[WorkflowReference] = []
    for path in sorted(workflows_dir.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if not workflow_targets_pull_request(text):
            continue
        for script in sorted(extract_script_refs(text)):
            refs.append(WorkflowReference(workflow=path.name, script=script))
    return refs


def load_preflight_manifest(preflight_path: Path) -> set[str]:
    """Run ``preflight_all.py --list`` and return its declared script names.

    The names are derived from each step's argv: a token matching
    ``scripts/<name>.py`` contributes ``<name>`` to the set. Steps whose
    argv contains no such token (e.g. ``ruff``, ``mypy``, ``pytest``)
    contribute nothing -- the drift gate only cares about script-name
    coverage, not toolchain-binary coverage.
    """
    completed = subprocess.run(  # noqa: S603 -- argv is hard-coded
        [sys.executable, str(preflight_path), "--list"],
        check=True,
        capture_output=True,
        text=True,
    )
    manifest = json.loads(completed.stdout)
    declared: set[str] = set()
    for entry in manifest:
        for token in entry.get("argv", []):
            match = _SCRIPT_REF.search(token)
            if match:
                declared.add(match.group(1))
    return declared


def diff(
    workflow_refs: list[WorkflowReference],
    declared: set[str],
    allowlist: dict[str, str],
) -> tuple[list[WorkflowReference], set[str]]:
    """Return (missing_in_preflight, extra_in_preflight).

    ``missing_in_preflight`` lists CI references whose script is not
    declared locally and is not in *allowlist*. ``extra_in_preflight``
    lists scripts declared locally that no ``pull_request:`` workflow
    invokes -- a warning condition, since the local set may legitimately
    pre-empt a future CI gate.
    """
    ci_scripts = {ref.script for ref in workflow_refs}
    missing = [
        ref
        for ref in workflow_refs
        if ref.script not in declared and ref.script not in allowlist
    ]
    extra = declared - ci_scripts
    return missing, extra


def cmd_verify(args: argparse.Namespace) -> int:
    workflows_dir = Path(args.workflows_dir)
    preflight = Path(args.preflight)
    workflow_refs = collect_workflow_refs(workflows_dir)
    declared = load_preflight_manifest(preflight)
    missing, extra = diff(workflow_refs, declared, ALLOWLIST)

    for ref in missing:
        print(
            f"::error file={ref.workflow}::preflight_all.py is missing "
            f"step for script '{ref.script}' "
            f"(invoked by .github/workflows/{ref.workflow}).",
            file=sys.stderr,
        )
    for name in sorted(extra):
        print(
            f"::warning::preflight_all.py declares step '{name}' but no "
            f"pull_request: workflow invokes scripts/{name}.py.",
            file=sys.stderr,
        )

    if missing:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diff local preflight set against CI's PR-gating scripts.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser("verify", help="Run the drift check and exit non-zero on drift.")
    verify.add_argument(
        "--workflows-dir",
        default=str(WORKFLOWS_DIR),
        help="Directory containing the workflow YAML files.",
    )
    verify.add_argument(
        "--preflight",
        default=str(REPO_ROOT / "scripts" / "preflight_all.py"),
        help="Path to scripts/preflight_all.py (consulted via --list).",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
