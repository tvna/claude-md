#!/usr/bin/env python3
"""Blocking CI gate: reconcile .gitapex/ssot.json against the partial manifests.

Phase 1 of the gitapex SSoT migration (docs/prd/gitapex-ssot-gate-registry.md):
the registry (``.gitapex/ssot.json``) claims which planes each gate fires on,
but nothing yet checks that claim against reality. This module compares the
registry's ``gates`` and ``clusters`` against the four manifests the design
names as authoritative for enforcement-plane membership:

- ``scripts/agent_hooks_source.json`` (PreToolUse plane script references,
  ``claude`` target only; the other agent-hook event planes are out of scope
  for this phase, matching #2256's scoped ask);
- ``scripts/preflight_steps.py`` ``STEPS`` (pre-push plane);
- ``.pre-commit-config.yaml`` local repo hooks (pre-commit plane);
- ``.github/rulesets/main.json`` ``rules`` (server plane, native rule types)
  and the ``pull_request:``-triggered workflow scripts under
  ``.github/workflows/`` (ci plane, via :func:`collect_workflow_refs`).

Divergence is reported as ``::error::`` lines and fails the run (exit 1).
Phase 1 first landed this gate advisory (warning-only, always exit 0); this
module completes phase 1 per the migration plan by promoting it to blocking
now that the report is clean. A ``git revert`` of the promoting commit
restores the advisory contract. A handful of manifest entries have no
scripts/*.py backing (third-party pre-commit-hooks entry points, bare
toolchain binaries such as ruff/mypy/pytest/prek/actionlint, and the
preflight_all.py runner itself) and are excluded via an inline,
rationale-carrying allowlist.

Phase 3 (child 3c, #2301) folded in the bespoke STEPS-vs-workflow reconciler
formerly at ``scripts/scan_preflight_drift.py``: :func:`collect_workflow_refs`,
:func:`extract_script_refs`, and :func:`diff_steps_vs_workflows` are that
module's logic moved here. #2340 (follow-up cleanup from that fold-in's
/code-review) then removed the second copy of the check's plane-exclusion
data: :func:`registry_ci_only_scripts` derives the CI-only exclusion set from
the registry's own ``planes`` field, and ``STEPS_VS_WORKFLOW_RESIDUAL_ALLOWLIST``
keeps only the handful of cases the registry cannot express.

Architecture: pure extraction functions per manifest, pure comparison
functions producing warning strings (or, for the STEPS-vs-workflow check,
:class:`DriftWarning`/:class:`VerifyResult` so a missing-step warning can
still carry a workflow-file GitHub annotation), a single IO boundary in
:func:`main`.

Contract:
- Inputs: the ``verify`` subcommand; ``--registry`` (default
  ``.gitapex/ssot.json``); ``--agent-hooks`` (default
  ``scripts/agent_hooks_source.json``); ``--pre-commit-config`` (default
  ``.pre-commit-config.yaml``); ``--rulesets`` (default
  ``.github/rulesets/main.json``); ``--workflows-dir`` (default
  ``.github/workflows``).
- Outputs: ``::error::`` annotations on stderr, one per divergence; an
  ``OK:`` or ``BLOCKING:`` line on stderr summarizing the count.
- Failure policy: this gate fails loud (exit 1) on any divergence found, and
  also fails loud (exit 1) on a hard configuration error, an input file
  missing or unparseable; exit 64 on an unrecognised subcommand.

Tested by ``tests/test_scan_ssot_drift.py``. Refs #2256, #2246, #2262, #2301,
#2340.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from preflight_steps import STEPS, Step

_SCRIPT = "scan_ssot_drift"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY_PATH = ".gitapex/ssot.json"
_AGENT_HOOKS_PATH = "scripts/agent_hooks_source.json"
_PRE_COMMIT_CONFIG_PATH = ".pre-commit-config.yaml"
_RULESETS_PATH = ".github/rulesets/main.json"
_WORKFLOWS_DIR = ".github/workflows"

_SCRIPT_REF = re.compile(r"\bscripts/([a-zA-Z][\w]*)\.py\b")

# STEPS entries with no scripts/*.py token in their argv: bare toolchain
# binaries the repository does not own as a gate script. Each carries its
# exclusion rationale so the allowlist stays auditable (scan_preflight_drift
# precedent).
STEPS_NO_SCRIPT_ALLOWLIST: dict[str, str] = {
    "actionlint": "toolchain binary (actionlint), not a scripts/*.py gate.",
    "ruff": "toolchain binary (ruff), not a scripts/*.py gate.",
    "mypy": "toolchain binary (mypy), not a scripts/*.py gate.",
    "pytest": "toolchain binary (pytest), not a scripts/*.py gate.",
    "prek": "toolchain binary (prek), not a scripts/*.py gate.",
}

# .pre-commit-config.yaml local hooks with no scripts/*.py token in their
# entry/args: third-party pre-commit-hooks entry points or bare toolchain
# binaries, same rationale class as STEPS_NO_SCRIPT_ALLOWLIST above.
PRE_COMMIT_NO_SCRIPT_ALLOWLIST: dict[str, str] = {
    "trailing-whitespace": "third-party pre-commit-hooks entry point, not a scripts/*.py gate.",
    "end-of-file-fixer": "third-party pre-commit-hooks entry point, not a scripts/*.py gate.",
    "check-yaml": "third-party pre-commit-hooks entry point, not a scripts/*.py gate.",
    "check-merge-conflict": "third-party pre-commit-hooks entry point, not a scripts/*.py gate.",
    "actionlint": "toolchain binary (actionlint), not a scripts/*.py gate.",
    "uv-mypy": "toolchain binary (mypy) invoked via uv, not a scripts/*.py gate.",
}

# scripts/preflight_all.py is the STEPS/collect_workflow_refs runner itself;
# mirroring it as a gate would recurse. This is the single source of truth
# for that exclusion: it covers both the ci-plane manifest (ci_manifest())
# and the STEPS-vs-workflow residual allowlist (verify_registry()), so the
# "preflight_all is a runner, not a gate" rationale is not duplicated.
CI_RUNNER_EXCLUDE = frozenset({"preflight_all"})

# The STEPS-vs-workflow check (verify_registry(), below) excludes scripts a
# `pull_request:` workflow invokes that `preflight_steps.STEPS` intentionally
# does not mirror. Most such scripts are already registered in
# .gitapex/ssot.json with planes: ["ci"] and no "pre-push", so
# registry_ci_only_scripts() derives them at runtime instead of duplicating
# that plane data by hand here (#2340). This dict keeps only the cases the
# registry's per-gate planes field cannot express:
STEPS_VS_WORKFLOW_RESIDUAL_ALLOWLIST: dict[str, str] = {
    "uv_pin": (
        "Used twice: ``uv_pin read`` is an output helper (no gate), "
        "``uv_pin drift`` IS a gate and is mirrored as a preflight step. "
        "The registry's uv-pin gate spans the pre-commit/pre-push/ci planes "
        "at the script level, so it cannot express this subcommand split."
    ),
}

# Rationale for the scripts registry_ci_only_scripts() excludes at runtime
# (each is registered in .gitapex/ssot.json with planes: ["ci"] only), kept
# here as auditable documentation since the registry's own "rule" field does
# not carry the client-side-equivalent detail below:
#   title_policy: input is the PR/issue title from the webhook payload, not
#     the working tree. Client gate: scripts/preflight_title_policy.py
#     (MCP PreToolUse).
#   body_policy: input is the PR/issue body from the webhook payload, not
#     the working tree. Client gate:
#     scripts/preflight_pr_body_required_sections.py (MCP PreToolUse).
#   issue_link: input is the PR body plus a GitHub API call rate-limited
#     without GH_TOKEN. Client gate: scripts/pr_body_close_keyword_gate.py
#     and scripts/preflight_pr_template_shape.py (MCP PreToolUse).
#   verify_linked_issue_titles: input is the PR body plus GitHub API calls
#     (one per linked issue) that require GH_TOKEN. No local equivalent: the
#     title of a remote issue cannot be checked without network access and a
#     valid token. Tracked by #941.
#   scan_review_in_progress_marker: input is a live PR's reaction state via a
#     GitHub API call that requires GH_TOKEN and a real PR number. No local
#     equivalent: there is no PR to react to before one is opened, so this
#     gate is CI-only. Refs #2312.
#   verify_shard_coverage: input is the per-leg JUnit XML artifacts produced
#     by the lint-scripts-pytest matrix legs, which only exist in CI. The
#     static counterpart `verify_test_shard_markers` IS mirrored as a
#     preflight step. Refs #545.


@dataclass(frozen=True)
class WorkflowReference:
    """One ``scripts/<name>.py`` reference discovered in a workflow."""

    workflow: str
    script: str


@dataclass(frozen=True)
class DriftWarning:
    """One blocking reconciliation warning.

    ``workflow`` is set only for the STEPS-vs-workflow missing-step case, so
    :func:`main` can attach a GitHub ``file=`` annotation anchoring the error
    to the offending workflow YAML.
    """

    message: str
    workflow: str | None = None


@dataclass(frozen=True)
class VerifyResult:
    """Blocking and advisory-only output of :func:`verify_registry`."""

    blocking: list[DriftWarning]
    advisory: list[str]


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
                if tail.startswith("[") and "pull_request" in tail:
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


def diff_steps_vs_workflows(
    workflow_refs: list[WorkflowReference],
    declared: frozenset[str],
    excluded: frozenset[str],
) -> tuple[list[WorkflowReference], frozenset[str]]:
    """Return (missing_in_steps, extra_in_steps) for the STEPS-vs-workflow check.

    ``missing_in_steps`` lists CI references whose script is not declared in
    ``preflight_steps.STEPS`` and is not in *excluded*; each is a blocking
    divergence. ``extra_in_steps`` lists scripts STEPS declares that no
    ``pull_request:`` workflow invokes; an advisory-only condition, since the
    local set may legitimately pre-empt a future CI gate.
    """
    ci_scripts = {ref.script for ref in workflow_refs}
    missing = [
        ref
        for ref in workflow_refs
        if ref.script not in declared and ref.script not in excluded
    ]
    extra = frozenset(declared) - ci_scripts
    return missing, extra


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# Manifest extraction (pure functions over already-parsed data)
# ---------------------------------------------------------------------------


def pretooluse_manifest(agent_hooks: object) -> frozenset[str]:
    """Return script basenames any agent target's PreToolUse hooks invoke.

    Unions every target with a ``config`` block (``claude``, ``codex``; the
    ``devin`` target has no own config, it mirrors ``codex``) rather than
    scoping to ``claude`` alone: registry gates carry no agent dimension, so
    a script wired for codex only (for example
    ``preflight_codex_github_footer.py``) is still a real pretooluse-plane
    gate the registry must account for.
    """
    names: set[str] = set()
    for target in _as_list(_as_dict(agent_hooks).get("targets")):
        target_d = _as_dict(target)
        hooks = _as_dict(_as_dict(target_d.get("config")).get("hooks"))
        for group in _as_list(hooks.get("PreToolUse")):
            for hook in _as_list(_as_dict(group).get("hooks")):
                command = _as_dict(hook).get("command")
                if isinstance(command, str):
                    names.update(_SCRIPT_REF.findall(command))
    return frozenset(names)


def steps_manifest(
    steps: tuple[Step, ...] = STEPS,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return (script basenames, unmapped step names) from ``preflight_steps.STEPS``.

    Every ``scripts/*.py`` token across a step's argv contributes to the
    result, not just the first match: a future step invoking two scripts in
    one argv (for example a wrapper calling two gates in sequence) must not
    silently under-report the second one.
    """
    scripts: set[str] = set()
    unmapped: set[str] = set()
    for step in steps:
        matched = {m.group(1) for token in step.argv if (m := _SCRIPT_REF.search(token))}
        if matched:
            scripts.update(matched)
        elif step.name not in STEPS_NO_SCRIPT_ALLOWLIST:
            unmapped.add(step.name)
    return frozenset(scripts), frozenset(unmapped)


def pre_commit_manifest(pre_commit_config: object) -> tuple[frozenset[str], frozenset[str]]:
    """Return (script basenames, unmapped hook ids) from the local pre-commit hooks."""
    scripts: set[str] = set()
    unmapped: set[str] = set()
    repos = _as_list(_as_dict(pre_commit_config).get("repos"))
    for repo in repos:
        for hook in _as_list(_as_dict(repo).get("hooks")):
            hook_d = _as_dict(hook)
            hook_id = hook_d.get("id")
            text = str(hook_d.get("entry", "")) + " " + " ".join(
                str(a) for a in _as_list(hook_d.get("args"))
            )
            found = _SCRIPT_REF.findall(text)
            if found:
                scripts.update(found)
            elif isinstance(hook_id, str) and hook_id not in PRE_COMMIT_NO_SCRIPT_ALLOWLIST:
                unmapped.add(hook_id)
    return frozenset(scripts), frozenset(unmapped)


def _ci_scripts(workflow_refs: list[WorkflowReference]) -> frozenset[str]:
    """Return script basenames referenced by *workflow_refs*, minus the runner."""
    return frozenset({ref.script for ref in workflow_refs}) - CI_RUNNER_EXCLUDE


def ci_manifest(workflows_dir: Path) -> frozenset[str]:
    """Return script basenames referenced by ``pull_request:``-triggered workflows."""
    return _ci_scripts(collect_workflow_refs(workflows_dir))


def server_native_rules(rulesets: object) -> frozenset[str]:
    """Return the native rule ``type`` values declared in the ruleset."""
    return frozenset(
        rule["type"]
        for rule in _as_list(_as_dict(rulesets).get("rules"))
        if isinstance(rule, dict) and isinstance(rule.get("type"), str)
    )


# ---------------------------------------------------------------------------
# Registry projections
# ---------------------------------------------------------------------------


def registry_scripts_for_plane(registry: dict[str, object], plane: str) -> dict[str, str]:
    """Return {script basename: gate id} for script-kind gates firing on *plane*."""
    result: dict[str, str] = {}
    for gate in _as_list(registry.get("gates")):
        gate_d = _as_dict(gate)
        if gate_d.get("kind") != "script":
            continue
        script = gate_d.get("script")
        gate_id = gate_d.get("id")
        planes = _as_list(gate_d.get("planes"))
        if isinstance(script, str) and isinstance(gate_id, str) and plane in planes:
            result[script.removeprefix("scripts/").removesuffix(".py")] = gate_id
    return result


def registry_native_rules_for_plane(registry: dict[str, object], plane: str) -> dict[str, str]:
    """Return {native_rule: gate id} for native-kind gates firing on *plane*."""
    result: dict[str, str] = {}
    for gate in _as_list(registry.get("gates")):
        gate_d = _as_dict(gate)
        if gate_d.get("kind") != "native":
            continue
        native_rule = gate_d.get("native_rule")
        gate_id = gate_d.get("id")
        planes = _as_list(gate_d.get("planes"))
        if isinstance(native_rule, str) and isinstance(gate_id, str) and plane in planes:
            result[native_rule] = gate_id
    return result


def registry_cluster_planes(registry: dict[str, object]) -> dict[str, set[str]]:
    """Return {cluster id: union of planes of gates carrying that cluster}."""
    result: dict[str, set[str]] = {}
    for gate in _as_list(registry.get("gates")):
        gate_d = _as_dict(gate)
        cluster = gate_d.get("cluster")
        if isinstance(cluster, str):
            result.setdefault(cluster, set()).update(
                p for p in _as_list(gate_d.get("planes")) if isinstance(p, str)
            )
    return result


def registry_ci_only_scripts(registry: dict[str, object]) -> frozenset[str]:
    """Return script basenames whose registry gate fires on 'ci' but not 'pre-push'.

    A gate the registry itself declares CI-only has no local equivalent by
    definition, so ``preflight_steps.STEPS`` correctly omits it. This is the
    STEPS-vs-workflow check's derivable exclusion set (#2340): most of
    ``STEPS_VS_WORKFLOW_RESIDUAL_ALLOWLIST``'s former entries are provably
    redundant with this projection and were removed rather than hand-kept in
    sync with it.
    """
    result: set[str] = set()
    for gate in _as_list(registry.get("gates")):
        gate_d = _as_dict(gate)
        if gate_d.get("kind") != "script":
            continue
        script = gate_d.get("script")
        planes = _as_list(gate_d.get("planes"))
        if isinstance(script, str) and "ci" in planes and "pre-push" not in planes:
            result.add(script.removeprefix("scripts/").removesuffix(".py"))
    return frozenset(result)


# ---------------------------------------------------------------------------
# Comparison (pure; returns ``::warning::``-ready message bodies)
# ---------------------------------------------------------------------------


def diff_plane(
    manifest_scripts: frozenset[str],
    registry_scripts: dict[str, str],
    *,
    manifest_label: str,
    plane: str,
) -> list[str]:
    """Return warnings for scripts each side has that the other lacks."""
    warnings: list[str] = []
    for script in sorted(manifest_scripts - registry_scripts.keys()):
        warnings.append(
            f"{manifest_label} references 'scripts/{script}.py' with no registry gate "
            f"on the '{plane}' plane."
        )
    for script in sorted(registry_scripts.keys() - manifest_scripts):
        warnings.append(
            f"registry gate {registry_scripts[script]!r} claims the '{plane}' plane for "
            f"'scripts/{script}.py' but {manifest_label} does not reference it."
        )
    return warnings


def diff_native(
    manifest_rules: frozenset[str], registry_rules: dict[str, str]
) -> list[str]:
    """Return warnings for native rule types each side has that the other lacks."""
    warnings: list[str] = []
    for rule in sorted(manifest_rules - registry_rules.keys()):
        warnings.append(
            f"{_RULESETS_PATH} declares native rule {rule!r} with no registry gate "
            f"on the 'server' plane."
        )
    for rule in sorted(registry_rules.keys() - manifest_rules):
        warnings.append(
            f"registry gate {registry_rules[rule]!r} claims native rule {rule!r} but "
            f"{_RULESETS_PATH} does not declare it."
        )
    return warnings


def diff_clusters(registry: dict[str, object]) -> list[str]:
    """Return warnings for a cluster's expected_planes not covered by any of its gates."""
    warnings: list[str] = []
    achieved = registry_cluster_planes(registry)
    for cluster in _as_list(registry.get("clusters")):
        cluster_d = _as_dict(cluster)
        cluster_id = cluster_d.get("id")
        if not isinstance(cluster_id, str):
            continue
        expected = {p for p in _as_list(cluster_d.get("expected_planes")) if isinstance(p, str)}
        missing = expected - achieved.get(cluster_id, set())
        for plane in sorted(missing):
            warnings.append(
                f"cluster {cluster_id!r} expects the {plane!r} plane but no gate with "
                f"cluster={cluster_id!r} declares it."
            )
    return warnings


def diff_unmapped(unmapped: frozenset[str], *, manifest_label: str) -> list[str]:
    """Return warnings for manifest entries with no scripts/*.py mapping and no allowlist entry."""
    return [
        f"{manifest_label} entry {name!r} has no 'scripts/<name>.py' reference and is not "
        f"in the no-script allowlist."
        for name in sorted(unmapped)
    ]


def verify_registry(
    registry: dict[str, object],
    *,
    agent_hooks: object,
    pre_commit_config: object,
    rulesets: object,
    workflow_refs: list[WorkflowReference],
    push_scripts: frozenset[str],
    push_unmapped: frozenset[str],
) -> VerifyResult:
    """Return every drift warning between *registry* and the four manifests.

    ``workflow_refs``, ``push_scripts``, and ``push_unmapped`` are computed
    once by the caller (:func:`main`) via :func:`collect_workflow_refs` and
    :func:`steps_manifest`, and threaded in here rather than recomputed, so a
    single ``verify`` invocation parses the workflow YAML and the STEPS
    tuple exactly once each (#2340).
    """
    warnings: list[str] = []

    pretooluse_scripts = pretooluse_manifest(agent_hooks)
    warnings += diff_plane(
        pretooluse_scripts,
        registry_scripts_for_plane(registry, "pretooluse"),
        manifest_label=_AGENT_HOOKS_PATH,
        plane="pretooluse",
    )

    warnings += diff_plane(
        push_scripts,
        registry_scripts_for_plane(registry, "pre-push"),
        manifest_label="preflight_steps.STEPS",
        plane="pre-push",
    )
    warnings += diff_unmapped(push_unmapped, manifest_label="preflight_steps.STEPS")

    commit_scripts, commit_unmapped = pre_commit_manifest(pre_commit_config)
    warnings += diff_plane(
        commit_scripts,
        registry_scripts_for_plane(registry, "pre-commit"),
        manifest_label=_PRE_COMMIT_CONFIG_PATH,
        plane="pre-commit",
    )
    warnings += diff_unmapped(commit_unmapped, manifest_label=_PRE_COMMIT_CONFIG_PATH)

    ci_scripts = _ci_scripts(workflow_refs)
    warnings += diff_plane(
        ci_scripts,
        registry_scripts_for_plane(registry, "ci"),
        manifest_label="pull_request: workflow scripts",
        plane="ci",
    )

    warnings += diff_native(
        server_native_rules(rulesets), registry_native_rules_for_plane(registry, "server")
    )

    warnings += diff_clusters(registry)

    blocking = [DriftWarning(message=message) for message in warnings]

    excluded = (
        registry_ci_only_scripts(registry)
        | frozenset(STEPS_VS_WORKFLOW_RESIDUAL_ALLOWLIST)
        | CI_RUNNER_EXCLUDE
    )
    missing_steps, extra_declared = diff_steps_vs_workflows(
        workflow_refs, push_scripts, excluded
    )
    blocking += [
        DriftWarning(
            message=(
                f"preflight_steps.STEPS is missing a step for 'scripts/{ref.script}.py' "
                f"(invoked by pull_request: workflow {ref.workflow!r})."
            ),
            workflow=ref.workflow,
        )
        for ref in missing_steps
    ]

    advisory = [
        f"preflight_steps.STEPS declares step {name!r} but no pull_request: workflow "
        f"invokes scripts/{name}.py."
        for name in sorted(extra_declared)
    ]

    return VerifyResult(blocking=blocking, advisory=advisory)


# ---------------------------------------------------------------------------
# IO boundary
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    command = argv[0] if argv else None
    if command != "verify":
        print(
            f"::error::{_SCRIPT}: unknown subcommand {command!r}; expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    parser = argparse.ArgumentParser(
        description="Report drift between .gitapex/ssot.json and the four partial gate manifests (blocking)."
    )
    parser.add_argument("command", help="Must be 'verify'.")
    parser.add_argument("--registry", default=_REGISTRY_PATH)
    parser.add_argument("--agent-hooks", default=_AGENT_HOOKS_PATH)
    parser.add_argument("--pre-commit-config", default=_PRE_COMMIT_CONFIG_PATH)
    parser.add_argument("--rulesets", default=_RULESETS_PATH)
    parser.add_argument("--workflows-dir", default=_WORKFLOWS_DIR)
    args = parser.parse_args(argv)

    registry_path = _REPO_ROOT / args.registry
    agent_hooks_path = _REPO_ROOT / args.agent_hooks
    pre_commit_path = _REPO_ROOT / args.pre_commit_config
    rulesets_path = _REPO_ROOT / args.rulesets
    workflows_dir = _REPO_ROOT / args.workflows_dir

    for label, path in (
        ("registry", registry_path),
        ("agent-hooks", agent_hooks_path),
        ("pre-commit-config", pre_commit_path),
        ("rulesets", rulesets_path),
    ):
        if not path.exists():
            print(f"::error::{_SCRIPT}: {label} file not found at {path}.", file=sys.stderr)
            return 1
    if not workflows_dir.is_dir():
        print(f"::error::{_SCRIPT}: workflows directory not found at {workflows_dir}.", file=sys.stderr)
        return 1

    try:
        registry = _load_json(registry_path)
        agent_hooks = _load_json(agent_hooks_path)
        pre_commit_config = _load_yaml(pre_commit_path)
        rulesets = _load_json(rulesets_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"::error::{_SCRIPT}: cannot parse an input file: {exc}", file=sys.stderr)
        return 1

    if not isinstance(registry, dict):
        print(f"::error::{_SCRIPT}: {args.registry} root is not a JSON object.", file=sys.stderr)
        return 1

    workflow_refs = collect_workflow_refs(workflows_dir)
    push_scripts, push_unmapped = steps_manifest()

    result = verify_registry(
        registry,
        agent_hooks=agent_hooks,
        pre_commit_config=pre_commit_config,
        rulesets=rulesets,
        workflow_refs=workflow_refs,
        push_scripts=push_scripts,
        push_unmapped=push_unmapped,
    )

    for message in result.advisory:
        print(f"::warning::{_SCRIPT}: {message}", file=sys.stderr)

    if result.blocking:
        for warning in result.blocking:
            if warning.workflow:
                print(
                    f"::error file={warning.workflow}::{_SCRIPT}: {warning.message}",
                    file=sys.stderr,
                )
            else:
                print(f"::error::{_SCRIPT}: {warning.message}", file=sys.stderr)
        print(
            f"BLOCKING: {_SCRIPT}: {len(result.blocking)} divergence(s) reported above.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {_SCRIPT}: registry and manifests agree.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
