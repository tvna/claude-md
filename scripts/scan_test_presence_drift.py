#!/usr/bin/env python3
"""Deterministic gate: every script under ``scripts/`` ships its required tests.

The workflow ``.github/workflows/verify-agents.yml`` invokes this module
from the ``lint-scripts-static`` job. It closes the sustainability gap that
#189 (CLI contract tests) and #194 (GitHub API boundary tests) left behind:
both were one-time additions, and no gate fails CI when a *new* script lands
without the test kinds ``docs/standards/workflow-script-quality.md`` already
requires. Only aggregate coverage (``fail_under``) is enforced today, and a
single new file barely moves that needle (the snapshot problem flagged for
#191). This gate makes the must-have test kinds a continuous, deterministic
check instead of reviewer memory (CLAUDE.md section 3).

The gate runs three static checks:

* **M2; test-module presence.** Every ``scripts/<name>.py`` must have a
  matching ``tests/test_<name>.py`` (private ``_<name>.py`` helpers also
  satisfy the check with ``tests/test_<name>.py``, the established naming
  for ``_git`` -> ``test_git`` etc.). Private helpers that are tested only
  indirectly through their callers are listed in
  :data:`ALLOW_NO_TEST_MODULE` with a per-entry rationale. The allowlist is
  a ratchet: an entry that gains a direct test module, or whose script is
  removed, is reported as stale so the exemption set can only shrink.

* **O6; GitHub API boundary registry.** Every public script that imports
  the GitHub API boundary (``_github_api`` / ``github_api``) is enumerated
  in :data:`GITHUB_API_SCRIPTS`. The gate fails when AST detection and the
  registry disagree in either direction, so a new API-touching script
  cannot land without the author consciously registering it (and thereby
  acknowledging the boundary-test expectation that #194 promoted from
  optional O6). The matching test module is guaranteed by the M2 check.

* **M3; CLI contract registration.** Every public script invoked by a
  workflow must appear in the ``CONTRACT_REGISTRY`` of
  ``tests/test_workflow_cli_contracts.py``. That test module is the
  authority for M3 (#189, #193); this check is its static, earlier mirror
  in the cheap ``lint-scripts-static`` lane (defense-in-depth per CLAUDE.md
  section 4), so a missing contract test surfaces before the pytest matrix.

Contract:
- Inputs: the ``verify`` subcommand; ``--scripts-dir`` (defaults to
  ``scripts``), ``--tests-dir`` (defaults to ``tests``), and
  ``--workflows-dir`` (defaults to ``.github/workflows``).
- Outputs: ``::error file=...::`` annotations on stderr naming each missing
  test, registry drift, or stale allowlist entry; exit 0 when the tree is
  clean, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate, so
  any missing test or registry drift exits non-zero).

Tested by ``tests/test_scan_test_presence_drift.py``. Refs #1088, #189,
#194, #197.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
TESTS_DIR = REPO_ROOT / "tests"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# The test module that owns the M3 CLI-contract registry. CHECK C parses its
# ``CONTRACT_REGISTRY`` literal rather than importing it, so this script never
# imports a test module at runtime.
CONTRACT_TEST_MODULE = "test_workflow_cli_contracts.py"

# Matches an actual ``python[3] scripts/<name>.py`` or
# ``uv run python scripts/<name>.py`` invocation in a workflow. Requiring the
# interpreter prefix excludes bare ``scripts/<name>.py`` mentions in comments
# (e.g. the runner ``preflight_all.py``, which is referenced in comments but
# never invoked), mirroring how tests/test_workflow_cli_contracts.py inventories
# real invocations. The leading char must be a letter so private ``_`` helpers
# (never CLI entry points) are excluded.
_SCRIPT_INVOCATION = re.compile(
    r"(?:python3?|uv\s+run\s+python)\s+scripts/([a-zA-Z][\w-]*)\.py"
)

# The GitHub API boundary modules a script imports when it talks to GitHub.
# Per must-have M7, every HTTP call funnels through ``_github_api`` (and its
# CLI wrapper ``github_api``), so an import of either is the deterministic
# signal that a script touches the GitHub API.
_GITHUB_API_BOUNDARY = frozenset({"_github_api", "github_api"})

# Private ``_<name>.py`` helpers that have no direct ``tests/test_<name>.py``
# module because they are exercised indirectly through their callers' tests.
# Each entry names where the coverage actually lives. This is the tested
# allowlist required by #1088; it is a ratchet; an entry that gains a direct
# test module (or whose helper is deleted) is reported stale and must be
# removed, so the exemption set can only shrink.
ALLOW_NO_TEST_MODULE: dict[str, str] = {
    "_auto_retro_parse": (
        "Pure parser/signal layer extracted from auto_retro.py (refs #1725); "
        "every moved symbol is re-exported by auto_retro and exercised "
        "indirectly via tests/test_auto_retro.py and "
        "tests/test_auto_retro_triage_report.py."
    ),
    "_auto_retro_render": (
        "Pure renderer/body layer extracted from auto_retro.py (refs #1725); "
        "every moved symbol is re-exported by auto_retro and exercised "
        "indirectly via tests/test_auto_retro.py."
    ),
    "_github_tool_names": (
        "Tool-name constant table; exercised indirectly via its caller in "
        "tests/test_preflight_codex_connector_tools.py."
    ),
    "_ref_classifier": (
        "Issue/PR reference classifier; exercised indirectly via "
        "tests/test_verify_linked_issue_titles.py (from _ref_classifier import)."
    ),
    "_retro_labels": (
        "Retrospective label constants; exercised indirectly via "
        "tests/test_auto_retro.py and tests/test_scan_retro_followup_drift.py."
    ),
    "_secret_patterns": (
        "Shared high-confidence secret-pattern detector; exercised indirectly "
        "via tests/test_scan_secrets.py and tests/test_preflight_github_secrets.py, "
        "which drive scan_line / scan_text through their callers."
    ),
}

# Public scripts that import the GitHub API boundary (O6, #194). The gate
# asserts this set stays identical to what AST detection finds, so a new
# API-touching script forces a conscious registry update (and the boundary
# test acknowledgement that goes with it). The matching test module is
# guaranteed by the M2 check above.
GITHUB_API_SCRIPTS: frozenset[str] = frozenset(
    {
        "auto_retro",
        "check_pr_mergeability",
        "ci_budget_issue",
        "ci_early_status_probe",
        "coverage_failure_issue",
        "dependabot_automerge",
        "gate_pr_body_retro_issue_link",
        "github_api",
        "issue_closure_fast_path",
        "issue_link",
        "labels_apply",
        "np_strategy_tracking",
        "post_issue_comment",
        "post_merge_new_session_prompt",
        "pr_body_close_keyword_gate",
        "pr_upsert",
        "preflight_replacement_pr",
        "prune_codespaces",
        "prune_devcontainer_images",
        "publish_instruction_release",
        "ruleset_drift",
        "sanitize_history",
        "scan_non_ascii",
        "scan_retro_followup_drift",
        "security_drift_report",
        "uv_pin",
        "verify_ruleset_sync",
    }
)


def discover_scripts(scripts_dir: Path) -> list[str]:
    """Return the sorted stems of every ``scripts/*.py`` module."""
    return sorted(path.stem for path in scripts_dir.glob("*.py"))


def test_module_candidates(stem: str) -> tuple[str, ...]:
    """Return the accepted ``tests/test_*.py`` file names for *stem*.

    A public ``foo.py`` is tested by ``test_foo.py``. A private ``_foo.py``
    is accepted by either ``test__foo.py`` (the literal ``test_<stem>``
    form, e.g. ``_ci_watch`` -> ``test__ci_watch``) or ``test_foo.py`` (the
    leading-underscore-dropped form, e.g. ``_git`` -> ``test_git``).
    """
    candidates = [f"test_{stem}.py"]
    if stem.startswith("_"):
        candidates.append(f"test_{stem[1:]}.py")
    return tuple(candidates)


def has_test_module(stem: str, tests_dir: Path) -> bool:
    """Return True iff a matching ``tests/test_*.py`` module exists for *stem*."""
    return any((tests_dir / name).is_file() for name in test_module_candidates(stem))


def module_imports(path: Path) -> set[str]:
    """Return the top-level names imported anywhere in *path*.

    Walks the AST so both ``import x`` and ``from x import y`` (including
    imports nested inside functions) contribute ``x``. Returns an empty set
    when the file cannot be parsed; a syntax error is caught by the lint
    gate, not this presence gate.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def detect_github_api_scripts(scripts_dir: Path) -> set[str]:
    """Return the public script stems that import the GitHub API boundary."""
    detected: set[str] = set()
    for path in sorted(scripts_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        if module_imports(path) & _GITHUB_API_BOUNDARY:
            detected.add(path.stem)
    return detected


def parse_contract_registry_scripts(test_path: Path) -> set[str]:
    """Return the script stems registered in ``CONTRACT_REGISTRY``.

    Parses the ``CONTRACT_REGISTRY: dict[...] = {(script, sub): test}``
    literal in *test_path* statically (no import of the test module). Each
    key is a ``(script_filename, subcommand)`` tuple; the first element's
    ``.py`` suffix is stripped to yield the stem.
    """
    try:
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    stems: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            targets: list[ast.expr] = [node.target]
            value = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        else:
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "CONTRACT_REGISTRY" for t in targets
        ):
            continue
        if not isinstance(value, ast.Dict):
            continue
        for key in value.keys:
            if isinstance(key, ast.Tuple) and key.elts:
                first = key.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    stems.add(first.value.removesuffix(".py"))
    return stems


def find_missing_tests(
    scripts: list[str],
    tests_dir: Path,
    allowlist: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Return ``(missing, stale_allowlist)`` for the M2 presence check.

    ``missing`` lists script stems with neither a matching test module nor an
    allowlist entry. ``stale_allowlist`` lists allowlist entries that now have
    a direct test module, or whose script no longer exists; either way the
    exemption is dead and must be removed.
    """
    script_set = set(scripts)
    missing = [
        stem
        for stem in scripts
        if stem not in allowlist and not has_test_module(stem, tests_dir)
    ]
    stale: list[str] = []
    for stem in sorted(allowlist):
        if stem not in script_set or has_test_module(stem, tests_dir):
            stale.append(stem)
    return missing, stale


def find_github_api_drift(
    detected: set[str],
    declared: frozenset[str],
) -> tuple[list[str], list[str]]:
    """Return ``(undeclared, stale_declared)`` for the O6 registry check."""
    undeclared = sorted(detected - declared)
    stale_declared = sorted(declared - detected)
    return undeclared, stale_declared


def find_missing_cli_contracts(
    workflow_scripts: set[str],
    registry_scripts: set[str],
) -> list[str]:
    """Return public workflow-invoked scripts absent from the contract registry."""
    return sorted(workflow_scripts - registry_scripts)


def collect_workflow_scripts(workflows_dir: Path, scripts_dir: Path) -> set[str]:
    """Return public script stems referenced by any workflow that exist on disk."""
    existing = {
        path.stem for path in scripts_dir.glob("*.py") if not path.name.startswith("_")
    }
    referenced: set[str] = set()
    for path in sorted(workflows_dir.glob("*.yml")):
        referenced |= set(_SCRIPT_INVOCATION.findall(path.read_text(encoding="utf-8")))
    return referenced & existing


def cmd_verify(args: argparse.Namespace) -> int:
    scripts_dir = Path(args.scripts_dir)
    tests_dir = Path(args.tests_dir)
    workflows_dir = Path(args.workflows_dir)

    scripts = discover_scripts(scripts_dir)
    missing, stale = find_missing_tests(scripts, tests_dir, ALLOW_NO_TEST_MODULE)

    detected_api = detect_github_api_scripts(scripts_dir)
    undeclared_api, stale_api = find_github_api_drift(detected_api, GITHUB_API_SCRIPTS)

    workflow_scripts = collect_workflow_scripts(workflows_dir, scripts_dir)
    registry_scripts = parse_contract_registry_scripts(tests_dir / CONTRACT_TEST_MODULE)
    missing_contract = find_missing_cli_contracts(workflow_scripts, registry_scripts)

    for stem in missing:
        print(
            f"::error file=scripts/{stem}.py::scripts/{stem}.py has no matching "
            f"test module (M2). Add tests/test_{stem.lstrip('_')}.py, or; only "
            f"for a private _ helper tested through its callers; add an entry "
            f"to ALLOW_NO_TEST_MODULE in scripts/scan_test_presence_drift.py with "
            f"a rationale.",
            file=sys.stderr,
        )
    for stem in stale:
        print(
            f"::error file=scripts/scan_test_presence_drift.py::ALLOW_NO_TEST_MODULE "
            f"entry '{stem}' is stale (it now has a direct test module or its "
            f"script was removed); delete it so the allowlist only shrinks.",
            file=sys.stderr,
        )
    for stem in undeclared_api:
        print(
            f"::error file=scripts/{stem}.py::scripts/{stem}.py imports the GitHub "
            f"API boundary but is not in GITHUB_API_SCRIPTS (O6, #194). Add it to "
            f"the registry in scripts/scan_test_presence_drift.py and ensure its "
            f"boundary behaviour is covered by tests/test_{stem}.py.",
            file=sys.stderr,
        )
    for stem in stale_api:
        print(
            f"::error file=scripts/scan_test_presence_drift.py::GITHUB_API_SCRIPTS "
            f"entry '{stem}' no longer imports the GitHub API boundary; remove it "
            f"so the registry mirrors the code.",
            file=sys.stderr,
        )
    for stem in missing_contract:
        print(
            f"::error file=scripts/{stem}.py::scripts/{stem}.py is invoked by a "
            f"workflow but has no CLI contract test (M3, #189). Add a test plus a "
            f"CONTRACT_REGISTRY entry in tests/{CONTRACT_TEST_MODULE}.",
            file=sys.stderr,
        )

    if missing or stale or undeclared_api or stale_api or missing_contract:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify scripts/ ship their required test modules and kinds.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser(
        "verify",
        help="Fail (exit 1) when a script lacks its required test module or kind.",
    )
    verify.add_argument(
        "--scripts-dir",
        default=str(SCRIPTS_DIR),
        help="Directory containing the scripts under test.",
    )
    verify.add_argument(
        "--tests-dir",
        default=str(TESTS_DIR),
        help="Directory containing the test modules.",
    )
    verify.add_argument(
        "--workflows-dir",
        default=str(WORKFLOWS_DIR),
        help="Directory containing the workflow YAML files.",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
