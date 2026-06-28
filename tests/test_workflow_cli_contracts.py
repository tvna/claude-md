"""CLI contract tests for scripts invoked directly by GitHub workflows.

These tests pin the argv/env/file shapes used by ``.github/workflows`` so
script-level unit tests cannot pass while an Actions invocation drifts.

Drift guard (issue #193):

* ``_iter_workflow_invocations()`` parses every workflow YAML
  structurally with ``yaml.safe_load`` and walks
  ``jobs.<job>.steps[*].run``. Each ``python3 scripts/foo.py bar`` or
  ``uv run python scripts/foo.py bar`` invocation; including command
  substitutions like ``$(python3 scripts/uv_pin.py read)``; is
  emitted as a :class:`WorkflowInvocation`.
* ``CONTRACT_REGISTRY`` maps each ``(script, subcommand)`` pair seen in
  workflows to the contract test function name that exercises it.
* ``test_every_workflow_invocation_has_contract_test`` parametrizes
  over the inventory: a new workflow invocation without a registry
  entry fails the gate loudly, with a remediation message that names
  the file to edit and the registry key to add.
* ``test_contract_registry_has_no_stale_entries`` rejects orphan
  entries so the registry stays a true mirror of the workflow surface.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any, NamedTuple

import analyze_ci_timings
import attack_review_reminder
import auto_retro
import auto_tag_version
import backup_archive
import body_policy
import bot_pr_automerge
import branch_cleanup
import ci_budget_issue
import codebase_maturity_summary
import coverage_failure_issue
import dependabot_automerge
import dependabot_labels
import devcontainer_pin_pr
import doc_graph_viz
import flake_pin
import flake_pin_latest
import gate_agents_skills_edit
import gate_doc_graph_pr
import gate_generated_scripts_manual_edit
import github_paginate
import issue_anchors
import issue_link
import labels_apply
import measure_devcontainer_startup
import measure_tool_overlap
import nixpkgs_cooldown
import owasp_asi_mapping
import post_issue_comment
import pr_upsert
import preflight_coverage
import preflight_uv_version
import prune_codespaces
import prune_devcontainer_images
import publish_instruction_release
import pytest
import python_pin
import ruleset_drift
import rulesets_apply
import scan_allowlist_parser_parity
import scan_allowlist_rationale
import scan_apm_ascii
import scan_apm_lock_drift
import scan_apm_portability
import scan_commit_type_label_drift
import scan_compile_from_source
import scan_design_philosophy_drift
import scan_devcontainer_tool_drift
import scan_doc_workflow_refs
import scan_docs_inventory
import scan_flake_pin_drift
import scan_harness_doc_coverage
import scan_hook_coverage_drift
import scan_hook_predicate_surface_drift
import scan_input_contract_drift
import scan_issue_anchor_drift
import scan_maintainability_metrics
import scan_markdown_links
import scan_mermaid_syntax
import scan_module_size_distribution
import scan_non_ascii
import scan_nonexhaustive_invariant_drift
import scan_pr_body_quality_drift
import scan_preflight_drift
import scan_provisioning_hook_serial
import scan_quality_standard_drift
import scan_repo_double_hyphen
import scan_repo_em_dash
import scan_retro_followup_drift
import scan_ruff_format
import scan_runbook_template_drift
import scan_scripts_gh_calls
import scan_secret_runbooks
import scan_secrets
import scan_session_path_drift
import scan_test_presence_drift
import scan_workflow_action_pins
import scan_workflow_gh_calls
import scan_workflow_injection
import scan_workflow_pip
import scan_workflow_unsigned_commit
import script_ast_graph
import script_dependency_graph
import script_trigger_map
import security_drift_report
import skill_quality_gate
import threat_intel_triage
import title_policy
import update_devcontainer_image_pins
import uv_download_checksum
import uv_pin
import validate_falco_rules
import validate_json_syntax
import verify_apm_checksums
import verify_control_inventory_currency
import verify_dependabot_author
import verify_instruction_text_growth
import verify_linked_issue_titles
import verify_readme_translation
import verify_required_check_contexts
import verify_ruleset_sync
import verify_security_control_floor
import verify_shard_coverage
import verify_source_version_bump
import verify_test_shard_markers
import verify_text_delta_section
import workflow_diagram
import yaml

pytestmark = pytest.mark.shard_ci_ops_2
REPO = "owner/repo"

_WORKFLOWS_DIR = Path(".github/workflows")
# Composite actions invoke scripts from their own ``runs.steps``; those calls
# must stay under the same CLI-contract governance as workflow steps, else
# moving a call into an action (e.g. .github/actions/setup-uv) becomes a blind
# spot. The inventory below scans both surfaces.
_ACTIONS_DIR = Path(".github/actions")

# Matches ``python[3] scripts/<name>.py [<sub>]`` and
# ``uv run python scripts/<name>.py [<sub>]``. The negative lookbehind
# ``(?<!run\s)`` prevents the bare ``python3?`` alternative from
# double-matching the ``python`` inside ``uv run python``.
_PYTHON_SCRIPT_INVOCATION = re.compile(
    r"(?:(?<!run\s)python3?|uv\s+run\s+python)"
    r"\s+scripts/([A-Za-z_][\w-]*\.py)"
    r"(?:\s+(\S+))?"
)

class WorkflowInvocation(NamedTuple):
    """A single ``python ... scripts/<name>.py [<sub>]`` call in a workflow."""

    workflow: str
    job: str
    step: str
    script: str
    subcommand: str | None


# (script, subcommand) -> contract test function name. ``subcommand`` is
# the literal first non-flag token after the script, with outer shell
# punctuation stripped; shell variables like ``"$MODE"`` are stored as
# ``$MODE``. ``None`` means the workflow invokes the script with only
# flags (no subcommand). Keys must mirror what
# ``_iter_workflow_invocations`` observes; the two drift tests below
# enforce that in both directions.
CONTRACT_REGISTRY: dict[tuple[str, str | None], str] = {
    ("analyze_ci_timings.py", None): "test_analyze_ci_timings_matches_workflow_args",
    ("measure_devcontainer_startup.py", None): "test_measure_devcontainer_startup_matches_workflow_args",
    ("measure_tool_overlap.py", None): "test_measure_tool_overlap_matches_workflow_args",
    ("ci_budget_issue.py", "run"): "test_ci_budget_issue_run_matches_workflow_args",
    ("attack_review_reminder.py", "assemble"): "test_attack_review_reminder_assemble_matches_workflow_args",
    ("backup_archive.py", "build"): "test_backup_archive_build_matches_workflow_args",
    ("github_paginate.py", "fetch-run-jobs"): "test_github_paginate_fetch_run_jobs_matches_workflow_args",
    ("validate_falco_rules.py", "verify"): "test_validate_falco_rules_verify_matches_workflow_args",
    ("validate_json_syntax.py", "verify"): "test_validate_json_syntax_verify_matches_workflow_args",
    ("script_ast_graph.py", "all-doc"): "test_script_ast_graph_all_doc_matches_workflow_args",
    ("script_dependency_graph.py", "all-doc"): "test_script_dependency_graph_all_doc_matches_workflow_args",
    ("script_trigger_map.py", "all-doc"): "test_script_trigger_map_all_doc_matches_workflow_args",
    ("gate_generated_scripts_manual_edit.py", "verify"): "test_gate_generated_scripts_manual_edit_matches_workflow_args",
    ("gate_agents_skills_edit.py", "verify"): "test_gate_agents_skills_edit_verify_matches_workflow_args",
    ("gate_doc_graph_pr.py", None): "test_gate_doc_graph_pr_matches_workflow_env",
    ("doc_graph_viz.py", "all-doc"): "test_doc_graph_viz_all_doc_matches_workflow_args",
    ("auto_retro.py", "triage-report"): "test_auto_retro_triage_report_matches_workflow_env",
    ("auto_retro.py", "triage-report-pr"): "test_auto_retro_triage_report_pr_matches_workflow_env",
    ("workflow_diagram.py", "diagram-doc"): "test_workflow_diagram_doc_matches_workflow_args",
    ("auto_retro.py", "run"): "test_auto_retro_run_matches_workflow_env",
    ("auto_retro.py", "post-merge-rescan"): "test_auto_retro_post_merge_rescan_matches_workflow_env",
    ("auto_retro.py", "sentinel"): "test_auto_retro_sentinel_matches_workflow_env",
    ("auto_retro.py", "verify-retro-completeness"): "test_auto_retro_verify_retro_completeness_matches_workflow_args",
    ("auto_retro.py", "verify-no-direct-retro-pr"): "test_auto_retro_verify_no_direct_retro_pr_matches_workflow_args",
    ("body_policy.py", "verify"): "test_body_policy_verify_matches_workflow_body_file",
    ("branch_cleanup.py", "reconcile"): "test_branch_cleanup_reconcile_matches_workflow_args",
    ("branch_cleanup.py", "survey"): "test_branch_cleanup_survey_matches_workflow_args",
    ("coverage_failure_issue.py", "run"): "test_coverage_failure_issue_run_matches_workflow_env",
    ("devcontainer_pin_pr.py", "open"): "test_devcontainer_pin_pr_open_matches_workflow_args",
    ("devcontainer_pin_pr.py", "refresh"): "test_devcontainer_pin_pr_refresh_matches_workflow_args",
    ("bot_pr_automerge.py", "merge"): "test_bot_pr_automerge_merge_matches_workflow_args",
    ("flake_pin.py", "asset-url"): "test_flake_pin_workflow_subcommands_match_ci_usage",
    ("flake_pin.py", "bump"): "test_flake_pin_workflow_subcommands_match_ci_usage",
    ("flake_pin_latest.py", "check"): "test_flake_pin_latest_check_matches_workflow_args",
    ("dependabot_automerge.py", "audit"): "test_dependabot_automerge_audit_matches_workflow_files",
    ("dependabot_automerge.py", "list-files"): "test_dependabot_list_files_matches_workflow_args",
    ("dependabot_automerge.py", "request-automerge"): "test_dependabot_request_automerge_matches_workflow_args",
    ("dependabot_automerge.py", "disable-automerge"): "test_dependabot_disable_automerge_matches_workflow_args",
    ("dependabot_labels.py", "verify"): "test_dependabot_labels_verify_matches_workflow_paths",
    ("issue_anchors.py", "get"): "test_issue_anchors_get_matches_workflow_args",
    ("issue_anchors.py", "render"): "test_issue_anchors_render_matches_workflow_args",
    ("issue_link.py", "verify"): "test_issue_link_verify_matches_workflow_body_file_and_author",
    ("labels_apply.py", "$COMMAND"): "test_labels_apply_validate_and_plan_match_workflow_args",
    ("labels_apply.py", "plan"): "test_labels_apply_validate_and_plan_match_workflow_args",
    ("labels_apply.py", "validate"): "test_labels_apply_validate_and_plan_match_workflow_args",
    ("nixpkgs_cooldown.py", "verify"): "test_nixpkgs_cooldown_verify_matches_workflow_args",
    ("ruleset_drift.py", "detect"): "test_ruleset_drift_detect_and_reconcile_match_workflow_args",
    ("ruleset_drift.py", "reconcile"): "test_ruleset_drift_detect_and_reconcile_match_workflow_args",
    ("rulesets_apply.py", "$MODE"): "test_rulesets_apply_plan_and_auto_delete_match_workflow_args",
    ("rulesets_apply.py", "auto-delete"): "test_rulesets_apply_plan_and_auto_delete_match_workflow_args",
    ("rulesets_apply.py", "workflow-permissions"): "test_rulesets_apply_workflow_permissions_matches_workflow_args",
    ("scan_harness_doc_coverage.py", "verify"): "test_scan_harness_doc_coverage_verify_matches_workflow_args",
    ("scan_allowlist_parser_parity.py", "verify"): "test_scan_allowlist_parser_parity_verify_matches_workflow_args",
    ("scan_allowlist_rationale.py", "verify"): "test_scan_allowlist_rationale_verify_matches_workflow_args",
    ("scan_apm_ascii.py", "verify"): "test_scan_apm_ascii_verify_matches_workflow_paths",
    ("scan_apm_portability.py", "verify"): "test_scan_apm_portability_verify_matches_workflow_paths",
    ("scan_repo_em_dash.py", "verify"): "test_scan_repo_em_dash_verify_matches_workflow_args",
    ("scan_repo_double_hyphen.py", "verify"): "test_scan_repo_double_hyphen_verify_matches_workflow_args",
    ("scan_runbook_template_drift.py", "verify"): "test_scan_runbook_template_drift_verify_matches_workflow_args",
    ("scan_design_philosophy_drift.py", "verify"): "test_scan_design_philosophy_drift_verify_matches_workflow_paths",
    ("scan_design_philosophy_drift.py", "verify-coupling"): "test_scan_design_philosophy_drift_verify_coupling_matches_workflow_args",
    ("scan_apm_lock_drift.py", "verify"): "test_scan_apm_lock_drift_verify_matches_workflow_args",
    ("scan_compile_from_source.py", "verify"): "test_scan_compile_from_source_verify_matches_workflow_args",
    ("scan_commit_type_label_drift.py", "verify"): "test_scan_commit_type_label_drift_verify_matches_workflow_args",
    ("scan_devcontainer_tool_drift.py", "verify"): "test_scan_devcontainer_tool_drift_verify_matches_workflow_args",
    ("scan_doc_workflow_refs.py", "verify"): "test_scan_doc_workflow_refs_verify_matches_workflow_args",
    ("scan_docs_inventory.py", "verify"): "test_scan_docs_inventory_verify_matches_workflow_args",
    ("scan_flake_pin_drift.py", "verify"): "test_scan_flake_pin_drift_verify_matches_workflow_args",
    ("scan_markdown_links.py", "verify"): "test_scan_markdown_links_verify_matches_workflow_args",
    ("scan_mermaid_syntax.py", "verify"): "test_scan_mermaid_syntax_verify_matches_workflow_args",
    ("scan_maintainability_metrics.py", "verify"): "test_scan_maintainability_metrics_verify_matches_workflow_args",
    ("codebase_maturity_summary.py", "summary"): "test_codebase_maturity_summary_summary_matches_workflow_args",
    # Refs #2013. The PR-time `verify` gate was removed; the module-size
    # snapshot is now produced post-merge under the single-producer model
    # (#1540/#1543/#1546), so the only workflow contract is `write` (run by
    # the post-merge decision-tree and verify-docs-drift jobs).
    ("scan_module_size_distribution.py", "write"): "test_scan_module_size_distribution_write_matches_workflow_args",
    ("scan_non_ascii.py", "run"): "test_scan_non_ascii_run_matches_workflow_env",
    ("scan_nonexhaustive_invariant_drift.py", "verify"): "test_scan_nonexhaustive_invariant_drift_verify_matches_workflow_args",
    ("scan_hook_coverage_drift.py", "verify"): "test_scan_hook_coverage_drift_verify_matches_workflow_args",
    ("scan_hook_predicate_surface_drift.py", "verify"): "test_scan_hook_predicate_surface_drift_verify_matches_workflow_args",
    ("scan_input_contract_drift.py", "verify"): "test_scan_input_contract_drift_verify_matches_workflow_args",
    ("scan_issue_anchor_drift.py", "verify"): "test_scan_issue_anchor_drift_verify_matches_workflow_args",
    ("scan_preflight_drift.py", "verify"): "test_scan_preflight_drift_verify_matches_workflow_args",
    ("scan_provisioning_hook_serial.py", "verify"): "test_scan_provisioning_hook_serial_verify_matches_workflow_args",
    ("scan_pr_body_quality_drift.py", "verify"): "test_scan_pr_body_quality_drift_verify_matches_workflow_args",
    ("scan_quality_standard_drift.py", "verify"): "test_scan_quality_standard_drift_verify_matches_workflow_args",
    ("scan_retro_followup_drift.py", "run"): "test_scan_retro_followup_drift_run_matches_workflow_env",
    ("scan_secret_runbooks.py", "verify"): "test_scan_secret_runbooks_verify_matches_workflow_args",
    ("scan_secrets.py", "verify"): "test_scan_secrets_verify_matches_workflow_args",
    ("scan_ruff_format.py", "verify"): "test_scan_ruff_format_verify_matches_workflow_args",
    ("scan_scripts_gh_calls.py", "verify"): "test_scan_scripts_gh_calls_verify_matches_workflow_args",
    ("scan_session_path_drift.py", "verify"): "test_scan_session_path_drift_verify_matches_workflow_args",
    ("scan_test_presence_drift.py", "verify"): "test_scan_test_presence_drift_verify_matches_workflow_args",
    ("scan_workflow_action_pins.py", "verify"): "test_scan_workflow_action_pins_verify_matches_workflow_args",
    ("scan_workflow_gh_calls.py", "verify"): "test_scan_workflow_gh_calls_verify_matches_workflow_args",
    ("scan_workflow_injection.py", "verify"): "test_scan_workflow_injection_verify_matches_workflow_args",
    ("scan_workflow_unsigned_commit.py", "verify"): "test_scan_workflow_unsigned_commit_verify_matches_workflow_args",
    ("scan_workflow_pip.py", "verify"): "test_scan_workflow_pip_verify_matches_workflow_args",
    ("security_drift_report.py", "aggregate"): "test_security_drift_report_aggregate_and_post_comment_match_workflow_args",
    ("security_drift_report.py", "post-comment"): "test_security_drift_report_aggregate_and_post_comment_match_workflow_args",
    ("security_drift_report.py", "file-family-issues"): "test_security_drift_report_file_family_issues_matches_workflow_args",
    ("skill_quality_gate.py", "verify"): "test_skill_quality_gate_verify_matches_workflow_args",
    ("threat_intel_triage.py", "scan"): "test_threat_intel_scan_matches_workflow_args",
    ("threat_intel_triage.py", "comment"): "test_threat_intel_comment_matches_workflow_args",
    ("title_policy.py", "verify"): "test_title_policy_verify_matches_workflow_kind_env",
    ("update_devcontainer_image_pins.py", "$GITHUB_SHA"): "test_update_devcontainer_image_pins_matches_workflow_args",
    ("uv_download_checksum.py", "verify"): "test_uv_download_checksum_verify_matches_action_args",
    ("preflight_coverage.py", None): "test_preflight_coverage_matches_workflow_args",
    ("preflight_uv_version.py", "verify"): "test_preflight_uv_version_verify_matches_workflow_args",
    ("uv_pin.py", "drift"): "test_uv_pin_workflow_subcommands_match_ci_usage",
    ("uv_pin.py", "read"): "test_uv_pin_workflow_subcommands_match_ci_usage",
    ("uv_pin.py", "stale"): "test_uv_pin_workflow_subcommands_match_ci_usage",
    ("python_pin.py", "verify"): "test_python_pin_verify_matches_workflow_args",
    ("verify_apm_checksums.py", "verify"): "test_verify_apm_checksums_matches_workflow_args",
    ("verify_dependabot_author.py", "verify"): "test_verify_dependabot_author_verify_matches_workflow_args",
    ("verify_linked_issue_titles.py", "verify"): "test_verify_linked_issue_titles_verify_matches_workflow_args",
    ("verify_readme_translation.py", "verify"): "test_verify_readme_translation_matches_workflow_args",
    ("verify_text_delta_section.py", "verify"): "test_verify_text_delta_section_matches_workflow_args",
    ("verify_instruction_text_growth.py", "verify"): "test_verify_instruction_text_growth_matches_workflow_args",
    ("verify_source_version_bump.py", "verify"): "test_verify_source_version_bump_matches_workflow_args",
    ("auto_tag_version.py", "run"): "test_auto_tag_version_run_matches_workflow_args",
    ("verify_required_check_contexts.py", "verify"): "test_verify_required_check_contexts_matches_workflow_args",
    ("verify_ruleset_sync.py", "verify"): "test_verify_ruleset_sync_matches_workflow_args",
    ("verify_security_control_floor.py", None): "test_verify_security_control_floor_matches_workflow_args",
    ("verify_control_inventory_currency.py", "verify"): "test_verify_control_inventory_currency_matches_workflow_args",
    ("owasp_asi_mapping.py", "verify"): "test_owasp_asi_mapping_verify_matches_workflow_args",
    ("github_paginate.py", "fetch"): "test_github_paginate_fetch_matches_workflow_args",
    ("github_paginate.py", "get"): "test_github_paginate_get_matches_workflow_args",
    ("post_issue_comment.py", "create"): "test_post_issue_comment_create_matches_workflow_args",
    ("prune_codespaces.py", "prune"): "test_prune_codespaces_prune_matches_workflow_args",
    ("prune_devcontainer_images.py", "prune"): "test_prune_devcontainer_images_prune_matches_workflow_args",
    ("publish_instruction_release.py", "publish"): "test_publish_instruction_release_publish_matches_workflow_args",
    ("pr_upsert.py", "upsert-files"): "test_pr_upsert_upsert_files_matches_workflow_args",
    ("verify_shard_coverage.py", None): "test_verify_shard_coverage_matches_workflow_args",
    ("verify_test_shard_markers.py", None): "test_verify_test_shard_markers_matches_workflow_args",
}


def _flatten_shell_continuations(text: str) -> list[str]:
    """Join backslash-continued shell lines into single logical lines."""
    out: list[str] = []
    buf = ""
    for raw_line in text.split("\n"):
        stripped = raw_line.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1].rstrip() + " "
        else:
            out.append(buf + stripped)
            buf = ""
    if buf:
        out.append(buf)
    return out


def _normalize_subcommand(raw: str | None) -> str | None:
    """Strip shell punctuation around the first token after the script."""
    if raw is None:
        return None
    cleaned = raw.strip("\"'`)(};|&")
    if not cleaned or cleaned.startswith("-"):
        return None
    return cleaned


def _emit_invocations_from_run(
    workflow: str, job: str, step: str, run_text: str
) -> list[WorkflowInvocation]:
    out: list[WorkflowInvocation] = []
    for line in _flatten_shell_continuations(run_text):
        for match in _PYTHON_SCRIPT_INVOCATION.finditer(line):
            out.append(
                WorkflowInvocation(
                    workflow=workflow,
                    job=job,
                    step=step,
                    script=match.group(1),
                    subcommand=_normalize_subcommand(match.group(2)),
                )
            )
    return out


def _emit_steps(
    source: str, job: str, steps: object, found: list[WorkflowInvocation]
) -> None:
    """Emit invocations for every ``run:`` step in *steps* (a list or not)."""
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        run_text = step.get("run")
        if not isinstance(run_text, str):
            continue
        step_name = str(step.get("name", "<unnamed>"))
        found.extend(_emit_invocations_from_run(source, job, step_name, run_text))


def _iter_workflow_invocations() -> list[WorkflowInvocation]:
    """Inventory every Python script invocation under ``.github/``.

    Covers both surfaces that GitHub Actions executes: workflow jobs
    (``.github/workflows/*.yml`` -> ``jobs.*.steps``) and composite actions
    (``.github/actions/**/action.yml`` -> ``runs.steps``). A script call moved
    from a workflow step into a composite action must remain inventoried, so
    CLI-contract governance follows the call rather than the file.

    Walks each file structurally via ``yaml.safe_load`` and emits one
    :class:`WorkflowInvocation` per matched ``run:`` line. The .github YAML
    accepts GitHub Actions extensions (e.g. POSIX heredocs whose body dedents
    past the block scalar indent) that strict YAML parsers reject;
    ``.pre-commit-config.yaml`` already excludes ``.github/workflows/`` from
    ``check-yaml`` for the same reason. When structured parsing fails, fall
    back to scanning the raw text so the affected file still contributes to
    the inventory; structured walk is preferred but cannot be the only path.
    """
    found: list[WorkflowInvocation] = []

    action_files = sorted(_ACTIONS_DIR.rglob("action.yml")) + sorted(
        _ACTIONS_DIR.rglob("action.yaml")
    )
    for path in sorted(_WORKFLOWS_DIR.glob("*.yml")) + action_files:
        source = str(path)
        raw = path.read_text(encoding="utf-8")
        document: object | None
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError:
            document = None
        if isinstance(document, dict) and isinstance(document.get("jobs"), dict):
            for job_name, job in document["jobs"].items():
                if isinstance(job, dict):
                    _emit_steps(source, str(job_name), job.get("steps"), found)
        elif (
            isinstance(document, dict)
            and isinstance(document.get("runs"), dict)
        ):
            # Composite action: steps live under ``runs.steps``.
            _emit_steps(source, "<composite>", document["runs"].get("steps"), found)
        else:
            found.extend(
                _emit_invocations_from_run(
                    source, "<unparseable>", "<unparseable>", raw
                )
            )
    return found


_INVENTORY = _iter_workflow_invocations()


def test_workflow_invocation_inventory_is_nonempty() -> None:
    """Guard against the parser silently returning an empty list."""
    assert _INVENTORY, (
        "Workflow invocation inventory is empty. Either "
        ".github/workflows is missing or _iter_workflow_invocations "
        "stopped matching the python script invocation pattern."
    )


@pytest.mark.parametrize(
    "invocation",
    _INVENTORY,
    ids=lambda inv: f"{Path(inv.workflow).name}::{inv.script}::{inv.subcommand or '<none>'}",
)
def test_every_workflow_invocation_has_contract_test(
    invocation: WorkflowInvocation,
) -> None:
    key = (invocation.script, invocation.subcommand)
    if key in CONTRACT_REGISTRY:
        return
    module_name = invocation.script.removesuffix(".py")
    sub_repr = invocation.subcommand if invocation.subcommand else "<no-subcommand>"
    raise AssertionError(
        f"Workflow {invocation.workflow} job '{invocation.job}' step "
        f"'{invocation.step}' invokes scripts/{invocation.script} with "
        f"subcommand {sub_repr!r}, but no CLI contract test is "
        f"registered for this pair.\n"
        f"Remediation: in tests/test_workflow_cli_contracts.py, add a "
        f"test function that calls "
        f"{module_name}.main([{invocation.subcommand!r}, ...]) with the "
        f"same argv shape used by the workflow, then add an entry to "
        f"CONTRACT_REGISTRY: ({invocation.script!r}, "
        f"{invocation.subcommand!r}): '<test_function_name>'."
    )


def test_contract_registry_has_no_stale_entries() -> None:
    inventory_keys = {(inv.script, inv.subcommand) for inv in _INVENTORY}
    stale = sorted(set(CONTRACT_REGISTRY) - inventory_keys)
    assert not stale, (
        f"CONTRACT_REGISTRY has {len(stale)} stale entr(y/ies) that no "
        f"longer appear in .github/workflows: {stale}. Remove them so "
        f"the registry stays a true mirror of the workflow surface."
    )


def test_auto_retro_run_matches_workflow_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = {
        "pull_request": {
            "number": 12,
            "title": "fix(ci): repair gate",
            "merged": False,
        }
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("REPO", REPO)

    assert auto_retro.main(["run"]) == 0


def test_auto_retro_sentinel_matches_workflow_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the env shape used by .github/workflows/auto-retro-sentinel.yml.

    The workflow shells to ``python3 scripts/auto_retro.py sentinel`` with
    only REPO + GH_TOKEN + (optional) AUTO_RETRO_SENTINEL_DAYS in the env.
    The gh_api boundary is stubbed to an empty search result so the
    contract exercises the argv/env wiring (CLI flag parsing,
    environment lookup, sentinel_run entry) without network access.
    """
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.delenv("AUTO_RETRO_SENTINEL_DAYS", raising=False)
    monkeypatch.setattr(
        auto_retro, "gh_api", lambda *_a, **_kw: json.dumps({"items": []})
    )

    assert auto_retro.main(["sentinel"]) == 0


def test_auto_retro_verify_retro_completeness_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the argv + env shape used by portable-pr-policy.yml.

    The workflow shells to ``python3 scripts/auto_retro.py
    verify-retro-completeness --repo "$REPO" --pr-title "$TITLE"
    --pr-body-file "$body_file"``. A non-retro PR title must skip
    (exit 0) without touching the gh_api boundary. Refs #1058.
    """
    body_file = tmp_path / "body.md"
    body_file.write_text("Refs #1\n", encoding="utf-8")
    monkeypatch.setattr(
        auto_retro,
        "gh_api",
        lambda *_a, **_kw: pytest.fail("gh_api must not be called for a non-retro PR"),
    )

    assert (
        auto_retro.main(
            [
                "verify-retro-completeness",
                "--repo",
                REPO,
                "--pr-title",
                "feat(x): unrelated change",
                "--pr-body-file",
                str(body_file),
            ]
        )
        == 0
    )


def test_auto_retro_verify_no_direct_retro_pr_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the argv + env shape used by portable-pr-policy.yml.

    The workflow shells to ``python3 scripts/auto_retro.py
    verify-no-direct-retro-pr --repo "$REPO" --pr-title "$TITLE"
    --pr-body-file "$body_file"``. A retro-close PR title must skip
    (exit 0) without touching the gh_api boundary. Refs #1069.
    """
    body_file = tmp_path / "body.md"
    body_file.write_text("Refs #1\n", encoding="utf-8")
    monkeypatch.setattr(
        auto_retro,
        "gh_api",
        lambda *_a, **_kw: pytest.fail(
            "gh_api must not be called for a retro-close PR"
        ),
    )

    assert (
        auto_retro.main(
            [
                "verify-no-direct-retro-pr",
                "--repo",
                REPO,
                "--pr-title",
                "docs(auto-retro): record repair-free merge",
                "--pr-body-file",
                str(body_file),
            ]
        )
        == 0
    )


def test_auto_retro_post_merge_rescan_matches_workflow_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the env shape used by auto-retro-post-merge-rescan.yml.

    The workflow shells to ``python3 scripts/auto_retro.py post-merge-rescan``
    with REPO + GH_TOKEN + (optional) AUTO_RETRO_RESCAN_HOURS in the env.
    Refs #421.
    """
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.delenv("AUTO_RETRO_RESCAN_HOURS", raising=False)
    monkeypatch.setattr(
        auto_retro, "gh_api", lambda *_a, **_kw: json.dumps({"items": []})
    )

    assert auto_retro.main(["post-merge-rescan"]) == 0


def test_script_ast_graph_all_doc_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the per-script default-output shape used by the post-merge workflow."""
    monkeypatch.chdir(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "alpha.py").write_text("def run():\n    return 0\n", encoding="utf-8")

    assert script_ast_graph.main(["all-doc"]) == 0

    output = Path("docs/generated/scripts/ast/alpha.md")
    assert output.read_text(encoding="utf-8") == (
        script_ast_graph.render_script_ast_markdown(
            scripts / "alpha.py", Path("scripts/alpha.py")
        )
    )


def test_script_dependency_graph_all_doc_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the default-output shape used by the post-merge workflow."""
    monkeypatch.chdir(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "_git.py").write_text("x = 1\n", encoding="utf-8")
    (scripts / "alpha.py").write_text("import _git\n", encoding="utf-8")

    assert script_dependency_graph.main(["all-doc"]) == 0

    output = Path("docs/generated/scripts/dependency-graph.md")
    assert output.read_text(encoding="utf-8") == script_dependency_graph.build_document(
        tmp_path
    )


def test_script_trigger_map_all_doc_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the default-output shape used by the post-merge workflow."""
    monkeypatch.chdir(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "alpha.py").write_text("x = 1\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  build:\n    steps:\n      - run: python3 scripts/alpha.py verify\n",
        encoding="utf-8",
    )

    assert script_trigger_map.main(["all-doc"]) == 0

    output = Path("docs/generated/scripts/trigger-map.md")
    assert output.read_text(encoding="utf-8") == script_trigger_map.build_document(
        tmp_path
    )


def test_gate_generated_scripts_manual_edit_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verify subcommand passes with no protected-folder changes."""
    monkeypatch.setattr(
        gate_generated_scripts_manual_edit,
        "changed_generated_docs",
        lambda *_a, **_kw: frozenset(),
    )
    monkeypatch.setattr(
        gate_generated_scripts_manual_edit,
        "resolve_branch",
        lambda *_a, **_kw: "feature/x",
    )

    assert gate_generated_scripts_manual_edit.main(["verify", "--base-ref", "origin/main"]) == 0


def test_gate_agents_skills_edit_verify_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verify subcommand passes when no managed skill tree changed."""
    monkeypatch.setattr(
        gate_agents_skills_edit,
        "_changed_files",
        lambda *_a, **_kw: frozenset({"scripts/x.py"}),
    )
    assert gate_agents_skills_edit.main(["verify", "--base-ref", "origin/main"]) == 0


def test_auto_retro_triage_report_matches_workflow_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the env + default-output shape used by the triage-report workflow."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REPO", REPO)
    # The workflow shells out to `gh api`; stub it so the contract test is
    # hermetic. An empty population still exercises the full write path.
    monkeypatch.setattr(
        auto_retro, "gh_api", lambda *_a, **_kw: json.dumps({"items": []})
    )

    assert auto_retro.main(["triage-report"]) == 0

    output = Path("docs/generated/scripts/auto-retro-triage-report.md")
    assert output.read_text(encoding="utf-8") == (
        auto_retro.render_triage_report_markdown(
            auto_retro.compute_triage_report([])
        )
    )


def test_auto_retro_triage_report_pr_matches_workflow_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the env shape used by the post-merge triage-report-pr step.

    The workflow shells to ``python3 scripts/auto_retro.py triage-report-pr``
    with REPO + GH_TOKEN + GITHUB_REF_NAME in the env, reading the snapshot the
    preceding triage-report step wrote. The PR-upsert boundary is stubbed so the
    contract exercises the argv/env wiring (report read, base resolution) without
    network access. Also pins ``recreate=True`` so the refresh branch is rebuilt
    from main each run and cannot retain an unsigned ancestor. Refs #1466, #1560.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")

    report_path = Path("docs/generated/scripts/auto-retro-triage-report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# snapshot\n", encoding="utf-8")

    captured: dict[str, Any] = {}

    def fake_upsert(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "created:99"

    monkeypatch.setattr(auto_retro, "upsert_single_file_pr", fake_upsert)

    assert auto_retro.main(["triage-report-pr"]) == 0

    assert captured["repo"] == REPO
    assert captured["base"] == "main"
    assert captured["branch"] == "chore/refresh-auto-retro-triage-report"
    assert captured["path"] == "docs/generated/scripts/auto-retro-triage-report.md"
    assert captured["content"] == b"# snapshot\n"
    # #1560: the refresh branch is recreated from main each run (delete+create),
    # so it never accumulates an unsigned ancestor that required_signatures rejects.
    assert captured["recreate"] is True


def _step_env_pr_title(workflow: str, step_name: str) -> str:
    """Return the ``PR_TITLE`` env literal of a named step in *workflow*."""
    document = yaml.safe_load((_WORKFLOWS_DIR / workflow).read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == step_name:
                return str(step["env"]["PR_TITLE"])
    raise AssertionError(f"step {step_name!r} with PR_TITLE not found in {workflow}")


def test_generated_bot_pr_titles_pass_title_policy() -> None:
    """Every generated bot PR title must clear the Portable PR policy gate.

    Regression guard for #1549: three bot workflows hard-coded a PR title that
    embedded a `(#NNN)` issue ref, which ``title_policy`` (the required
    ``Portable PR policy / gate``) rejects (#167), so every PR they reopened was
    unmergeable; PR #1485 being the visible instance. The titles are sourced
    from their authoritative locations (workflow ``PR_TITLE`` env and the
    ``auto_retro`` constant) so a reintroduced `(#NNN)` fails this gate loudly.
    """
    titles = {
        "auto_retro._TRIAGE_REPORT_PR_TITLE": auto_retro._TRIAGE_REPORT_PR_TITLE,
        "post-merge.yml decision-tree": _step_env_pr_title(
            "post-merge.yml", "Open pull request if any generated doc changed"
        ),
        "generate-agents.yml": _step_env_pr_title(
            "generate-agents.yml", "Open pull request if generated instructions changed"
        ),
    }
    for source, title in titles.items():
        assert not title_policy.pr_title_has_issue_ref(title), (
            f"{source}: PR title must not embed a (#NNN) issue ref; "
            "put Refs #NNN in the body instead (#167)."
        )
        assert (
            title_policy.verify_title(
                title, kind="pull_request", author="tvna-bot[bot]"
            )
            == 0
        ), f"{source}: title does not pass title_policy.verify_title"


def test_workflow_diagram_doc_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the default-output shape used by the post-merge generate-docs job."""
    import shutil

    # Resolve source path before chdir so it stays absolute.
    src_wf_abs = Path(".github/workflows/post-merge.yml").resolve()

    monkeypatch.chdir(tmp_path)
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    shutil.copy(src_wf_abs, wf_dir / src_wf_abs.name)

    out_dir = tmp_path / "docs" / "generated" / "workflows"
    assert workflow_diagram.main(["diagram-doc", "--output-dir", str(out_dir)]) == 0

    expected = out_dir / "post-merge-if-branches.md"
    assert expected.exists()
    # diagram-doc uses a relative path glob; compare against the same relative path
    # so the preamble source field matches.
    assert expected.read_text(encoding="utf-8") == workflow_diagram.render_markdown(
        workflow_diagram.parse_workflow(Path(".github/workflows") / src_wf_abs.name)
    )


def test_body_policy_verify_matches_workflow_body_file(tmp_path: Path) -> None:
    body_file = tmp_path / "body.md"
    body_file.write_text(
        "\n".join(
            [
                "## Scope",
                "prose",
                "## Facts",
                "- Fact: one",
                "## Proposed work",
                "- step",
                "## Verification",
                "- pytest",
                "## Acceptance criteria",
                "- [ ] done",
            ]
        ),
        encoding="utf-8",
    )

    assert body_policy.main(["verify", "--kind", "issue", "--body-file", str(body_file)]) == 0


def test_branch_cleanup_survey_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        branch_cleanup,
        "list_branches",
        lambda repo, **kwargs: [("main", "abc")],
    )

    assert branch_cleanup.main(
        [
            "survey",
            "--repo",
            REPO,
            "--dry-run",
            "true",
            "--min-age-days",
            "60",
            "--default-branch",
            "main",
            "--event-name",
            "workflow_dispatch",
            "--run-url",
            "https://example.test/run",
            "--out",
            str(tmp_path / "cleanup-comment.md"),
            "--github-output",
            str(tmp_path / "output"),
        ]
    ) == 0


def test_branch_cleanup_reconcile_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(branch_cleanup, "find_rolling_issue", lambda repo, title: None)

    assert branch_cleanup.main(
        [
            "reconcile",
            "--repo",
            REPO,
            "--title",
            "Branch cleanup rolling summary",
            "--candidate-count",
            "0",
            "--comment-file",
            str(tmp_path / "cleanup-comment.md"),
            "--idle-close-days",
            "28",
            "--run-url",
            "https://example.test/run",
        ]
    ) == 0


def test_dependabot_automerge_audit_matches_workflow_files(tmp_path: Path) -> None:
    event = {
        "pull_request": {
            "user": {"login": "dependabot[bot]"},
            "head": {"ref": "dependabot/github-actions/actions-checkout-6"},
            "title": "Bump actions/checkout from v5 to v6",
            "labels": [],
            "draft": False,
        }
    }
    policy = {
        "enabled": False,
        "allow": [
            {
                "ecosystem": "github-actions",
                "update_types": ["major"],
                "paths": [".github/workflows/*"],
            }
        ],
    }
    event_file = tmp_path / "event.json"
    policy_file = tmp_path / "policy.json"
    changed_files = tmp_path / "changed-files.txt"
    event_file.write_text(json.dumps(event), encoding="utf-8")
    policy_file.write_text(json.dumps(policy), encoding="utf-8")
    changed_files.write_text(".github/workflows/verify.yml\n", encoding="utf-8")

    assert dependabot_automerge.main(
        [
            "audit",
            "--event",
            str(event_file),
            "--policy",
            str(policy_file),
            "--changed-files",
            str(changed_files),
            "--summary-file",
            str(tmp_path / "summary.md"),
            "--output",
            str(tmp_path / "output"),
        ]
    ) == 0


def test_dependabot_list_files_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setattr(dependabot_automerge, "_list_pr_files", lambda **kw: ["uv.lock"])
    out = tmp_path / "changed-files.txt"
    assert dependabot_automerge.main(["list-files", "--pr-number", "42", "--output", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == "uv.lock\n"


def test_dependabot_request_automerge_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setattr(dependabot_automerge, "_enable_auto_merge", lambda **kw: None)
    assert dependabot_automerge.main(["request-automerge", "--pr-number", "42"]) == 0


def test_dependabot_disable_automerge_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setattr(dependabot_automerge, "_disable_auto_merge", lambda **kw: False)
    assert dependabot_automerge.main(["disable-automerge", "--pr-number", "42"]) == 0


def test_dependabot_labels_verify_matches_workflow_paths(tmp_path: Path) -> None:
    dependabot = tmp_path / "dependabot.yml"
    labels = tmp_path / "labels.json"
    dependabot.write_text("updates:\n  - labels:\n      - dependencies\n", encoding="utf-8")
    labels.write_text(
        json.dumps(
            [{"name": "dependencies", "color": "0366d6", "description": ""}]
        ),
        encoding="utf-8",
    )

    assert dependabot_labels.main(
        ["verify", "--dependabot", str(dependabot), "--labels", str(labels)]
    ) == 0


def test_issue_link_verify_matches_workflow_body_file_and_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body_file = tmp_path / "body.md"
    body_file.write_text("Closes #189\n", encoding="utf-8")
    monkeypatch.setattr(issue_link, "issue_exists", lambda repo, number: True)

    assert issue_link.main(
        [
            "verify",
            "--repo",
            REPO,
            "--body-file",
            str(body_file),
            "--author",
            "octocat",
        ]
    ) == 0


def test_labels_apply_validate_and_plan_match_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sot = tmp_path / "labels.json"
    sot.write_text(
        json.dumps([{"name": "type:fix", "color": "d73a4a", "description": "Bug fix"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(labels_apply, "fetch_live_labels", lambda repo, token: [])

    assert labels_apply.main(["validate", "--sot", str(sot)]) == 0
    assert labels_apply.main(
        [
            "plan",
            "--repo",
            REPO,
            "--sot",
            str(sot),
            "--prune",
            "false",
            "--dry-run",
            "true",
            "--summary-file",
            str(tmp_path / "labels-summary.md"),
        ]
    ) == 0


def test_ruleset_drift_detect_and_reconcile_match_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sot_dir = _write_ruleset_sot(tmp_path)
    monkeypatch.setenv("GH_TOKEN_API", "token")
    monkeypatch.setattr(
        ruleset_drift,
        "fetch_live_rulesets_list",
        lambda repo, token: [
            {"id": 1, "name": "main-protection", "target": "branch", "enforcement": "active"},
            {"id": 2, "name": "all-branches-no-force-push", "target": "branch", "enforcement": "active"},
        ],
    )
    monkeypatch.setattr(
        ruleset_drift,
        "fetch_live_ruleset",
        lambda repo, ruleset_id, token: _ruleset_for_id(ruleset_id),
    )
    calls: list[dict[str, Any]] = []

    def fake_file_issue(
        repo: str,
        title: str,
        body_file: Path,
        labels: tuple[str, ...] = ruleset_drift.ISSUE_LABELS,
    ) -> None:
        calls.append(
            {"repo": repo, "title": title, "body_file": body_file, "labels": labels}
        )

    # No open rolling issue + capture create; reconcile must never shell out.
    monkeypatch.setattr(ruleset_drift, "find_rolling_issue", lambda repo, title: None)
    monkeypatch.setattr(ruleset_drift, "file_issue", fake_file_issue)

    assert ruleset_drift.main(
        [
            "detect",
            "--repo",
            REPO,
            "--sot-dir",
            str(sot_dir),
            "--run-url",
            "https://example.test/run",
            "--summary-file",
            str(tmp_path / "summary.md"),
            "--sot-body-file",
            str(tmp_path / "drift-sot-issue.md"),
            "--unknown-body-file",
            str(tmp_path / "drift-unknown-issue.md"),
        ]
    ) == 0
    assert ruleset_drift.main(
        [
            "reconcile",
            "--repo",
            REPO,
            "--kind",
            "sot",
            "--detected",
            "true",
            "--body-file",
            str(tmp_path / "drift-sot-issue.md"),
        ]
    ) == 0
    assert ruleset_drift.main(
        [
            "reconcile",
            "--repo",
            REPO,
            "--kind",
            "unknown",
            "--detected",
            "false",
            "--body-file",
            str(tmp_path / "drift-unknown-issue.md"),
        ]
    ) == 0
    assert calls[-1]["repo"] == REPO
    assert calls[-1]["title"] == ruleset_drift.SOT_ISSUE_TITLE


def test_rulesets_apply_plan_and_auto_delete_match_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sot_dir = _write_ruleset_sot(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(
        rulesets_apply,
        "fetch_live_rulesets",
        lambda repo, token, **kwargs: [],
    )
    monkeypatch.setattr(
        rulesets_apply,
        "get_repo_setting",
        lambda repo, key, token, **kwargs: False,
    )

    assert rulesets_apply.main(
        [
            "plan",
            "--repo",
            REPO,
            "--sot-dir",
            str(sot_dir),
            "--choice",
            "main",
            "--enable-auto-delete",
            "true",
            "--summary-file",
            str(tmp_path / "rulesets-summary.md"),
        ]
    ) == 0
    assert rulesets_apply.main(
        [
            "auto-delete",
            "--repo",
            REPO,
            "--dry-run",
            "true",
            "--summary-file",
            str(tmp_path / "rulesets-summary.md"),
        ]
    ) == 0


def test_rulesets_apply_workflow_permissions_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the argv shape used by apply-rulesets.yml and
    weekly-maintenance.yml.

    apply-rulesets.yml runs ``workflow-permissions --mode plan|apply`` and the
    weekly security-control-drift job runs it ``--mode drift`` (read-only). The
    live GET is stubbed so the contract exercises argv/env wiring (SoT read,
    diff, exit-code mapping) without network access.
    """
    sot = tmp_path / "workflow.json"
    sot.write_text(
        json.dumps(
            {
                "default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(
        rulesets_apply,
        "get_workflow_permissions",
        lambda *_a, **_k: {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": True,
        },
    )

    # drift mode, in sync -> exit 0
    assert rulesets_apply.main(
        [
            "workflow-permissions",
            "--repo",
            REPO,
            "--sot-file",
            str(sot),
            "--mode",
            "drift",
            "--summary-file",
            str(tmp_path / "wfperm-summary.md"),
        ]
    ) == 0
    # plan mode -> exit 0
    assert rulesets_apply.main(
        [
            "workflow-permissions",
            "--repo",
            REPO,
            "--sot-file",
            str(sot),
            "--mode",
            "plan",
            "--summary-file",
            str(tmp_path / "wfperm-summary.md"),
        ]
    ) == 0


def test_coverage_failure_issue_run_matches_workflow_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[coverage_failure_issue.CoverageFailureContext] = []
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.setenv("RUN_ID", "123")
    monkeypatch.setenv("RUN_ATTEMPT", "2")
    monkeypatch.setenv("SERVER_URL", "https://github.com")
    monkeypatch.setenv("WORKFLOW", "Post-merge automation")
    monkeypatch.setenv("COVERAGE_RESULT", "failure")

    def fake_post_failure_comment(
        context: coverage_failure_issue.CoverageFailureContext,
        *,
        token: str | None = None,
    ) -> str:
        calls.append(context)
        return "commented"

    monkeypatch.setattr(coverage_failure_issue, "post_failure_comment", fake_post_failure_comment)

    assert coverage_failure_issue.main(["run"]) == 0
    assert calls[0] == coverage_failure_issue.CoverageFailureContext(
        repo=REPO,
        run_url="https://github.com/owner/repo/actions/runs/123/attempts/2",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="123",
        run_attempt="2",
    )


def test_scan_apm_ascii_verify_matches_workflow_paths(tmp_path: Path) -> None:
    path = tmp_path / "ascii.md"
    path.write_text("ascii prose; clean\n", encoding="utf-8")

    assert scan_apm_ascii.main(
        ["verify", "--path", str(path), "--path", str(path), "--path", str(path)]
    ) == 0


def test_scan_repo_em_dash_verify_matches_workflow_args(tmp_path: Path) -> None:
    """Mirrors the ``Scan all tracked files for em-dash (U+2014)`` step in
    ``.github/workflows/verify-pr.yml`` (issue #1889).

    The workflow passes ``--git-tracked``; the contract exercises the same
    subcommand shape against a real (empty) git-ls-files mock so the
    ``verify`` path is exercised end-to-end.
    """
    from unittest.mock import MagicMock, patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        assert scan_repo_em_dash.main(["verify", "--git-tracked"]) == 0


def test_scan_repo_double_hyphen_verify_matches_workflow_args(tmp_path: Path) -> None:
    """Mirrors the ``Scan all tracked files for prose double-hyphen separator`` step in
    ``.github/workflows/verify-pr.yml`` (issue #1903).

    The workflow passes ``--git-tracked``; the contract exercises the same
    subcommand shape against a real (empty) git-ls-files mock so the
    ``verify`` path is exercised end-to-end.
    """
    from unittest.mock import MagicMock, patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        assert scan_repo_double_hyphen.main(["verify", "--git-tracked"]) == 0


def test_scan_runbook_template_drift_verify_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mirrors the ``Verify runbook template conformance`` step in
    ``.github/workflows/verify-pr.yml`` (issue #2065).

    The workflow shells to ``python3 scripts/scan_runbook_template_drift.py
    verify --base-ref "$BASE_REF" --body-file "$body_file"``. Stub the
    changed-runbook lookup so the test stays hermetic across CI checkout
    depths (a real ``git diff origin/main...HEAD`` would fail on a shallow
    checkout).
    """
    monkeypatch.setattr(
        scan_runbook_template_drift,
        "get_changed_runbooks",
        lambda base_ref: [],
    )
    body_file = tmp_path / "body.md"
    body_file.write_text("no waiver needed\n", encoding="utf-8")
    assert (
        scan_runbook_template_drift.main(
            [
                "verify",
                "--base-ref",
                "origin/main",
                "--body-file",
                str(body_file),
            ]
        )
        == 0
    )


def test_scan_apm_portability_verify_matches_workflow_paths(tmp_path: Path) -> None:
    path = tmp_path / "portable.md"
    path.write_text("portable prose\n", encoding="utf-8")

    assert scan_apm_portability.main(
        ["verify", "--path", str(path), "--path", str(path), "--path", str(path)]
    ) == 0


def test_verify_apm_checksums_matches_workflow_args(tmp_path: Path) -> None:
    apm_source = tmp_path / ".apm/instructions/master.instructions.md"
    apm_source.parent.mkdir(parents=True)
    apm_source.write_text("source\n", encoding="utf-8")

    assert verify_apm_checksums.main(["--root", str(tmp_path), "update"]) == 0
    assert verify_apm_checksums.main(["--root", str(tmp_path), "verify"]) == 0


def test_verify_dependabot_author_verify_matches_workflow_args() -> None:
    """Mirror the env+argv shape used by issue-pr-triage.yml.

    The workflow shells to
    ``python3 scripts/verify_dependabot_author.py verify
    --head-ref "$HEAD_REF" --author "$AUTHOR"``. A trusted bot on a
    dependabot/* branch passes; a non-bot author fails.
    """
    assert verify_dependabot_author.main(
        [
            "verify",
            "--head-ref",
            "dependabot/github_actions/actions/checkout-6",
            "--author",
            "dependabot[bot]",
        ]
    ) == 0
    assert verify_dependabot_author.main(
        [
            "verify",
            "--head-ref",
            "dependabot/github_actions/actions/checkout-6",
            "--author",
            "mallory",
        ]
    ) == 1


def test_verify_linked_issue_titles_verify_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the env+argv shape used by portable-pr-policy.yml.

    The workflow shells to
    ``python3 scripts/verify_linked_issue_titles.py verify
    --repo "$REPO" --body-file "$body_file"``.
    Exercise the same shape with get_issue_title stubbed so the test
    stays hermetic (no GH_TOKEN or network required). Tracked by #941.
    """
    body_file = tmp_path / "body.md"
    body_file.write_text("Closes #941\n", encoding="utf-8")
    monkeypatch.setattr(
        verify_linked_issue_titles,
        "get_issue_title",
        lambda repo, number, **_k: "ci: valid linked issue title",
    )
    assert verify_linked_issue_titles.main(
        [
            "verify",
            "--repo",
            REPO,
            "--body-file",
            str(body_file),
        ]
    ) == 0


def test_verify_readme_translation_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mirror the env+argv shape used by portable-pr-policy.yml.

    The workflow shells to
    ``python3 scripts/verify_readme_translation.py verify
    --base-ref "$BASE_REF" --body-file "$body_file"``.
    Exercise the same shape with the changed-files lookup stubbed so
    the test stays hermetic across CI checkout depths (the
    lint-scripts-pytest job checks out shallow, so a real
    ``git diff origin/main..HEAD`` would fail with exit 128).
    """
    monkeypatch.setattr(
        verify_readme_translation,
        "changed_readmes",
        lambda base, head="HEAD", **kwargs: frozenset(
            {"README.md", "README.ja.md", "README.zh.md", "README.ko.md"}
        ),
    )

    body_file = tmp_path / "body.md"
    body_file.write_text("no marker", encoding="utf-8")
    assert verify_readme_translation.main(
        [
            "verify",
            "--base-ref",
            "origin/main",
            "--body-file",
            str(body_file),
        ]
    ) == 0


def test_verify_text_delta_section_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mirror the env+argv shape used by portable-pr-policy.yml.

    The workflow shells to
    ``python3 scripts/verify_text_delta_section.py verify
    --base-ref "$BASE_REF" --body-file "$body_file"
    --created-at "$PR_CREATED_AT" --cutoff "$BODY_POLICY_CUTOFF"``.
    Stub the changed-files lookup so the test stays hermetic across CI
    checkout depths (the lint-scripts-pytest job checks out shallow, so a
    real ``git diff origin/main..HEAD`` would fail with exit 128).
    """
    monkeypatch.setattr(
        verify_text_delta_section,
        "changed_instruction_files",
        lambda base, head="HEAD", **kwargs: frozenset({"CLAUDE.md"}),
    )

    body_file = tmp_path / "body.md"
    body_file.write_text(
        "## Text delta\n\n"
        "- chars: +20\n"
        "- Added context: x\n"
        "- Removed context: y\n",
        encoding="utf-8",
    )
    assert verify_text_delta_section.main(
        [
            "verify",
            "--base-ref",
            "origin/main",
            "--body-file",
            str(body_file),
            "--created-at",
            "2026-06-03T00:00:00Z",
            "--cutoff",
            "2026-05-26T00:00:00Z",
        ]
    ) == 0


def test_verify_instruction_text_growth_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mirror the env+argv shape used by verify-pr.yml.

    The workflow shells to
    ``python3 scripts/verify_instruction_text_growth.py verify
    --base-ref "$BASE_REF" --body-file "$body_file"
    --created-at "$PR_CREATED_AT" --cutoff "$BODY_POLICY_CUTOFF"``.
    Stub the diff lookup so the test stays hermetic across CI checkout
    depths (the lint-scripts-pytest job checks out shallow, so a real
    ``git diff origin/main..HEAD`` would fail with exit 128). A growth
    diff plus a ``text-growth-ack:`` body must pass.
    """
    growth_diff = (
        "--- a/.apm/instructions/master.instructions.md\n"
        "+++ b/.apm/instructions/master.instructions.md\n"
        "@@ -10 +10 @@\n"
        "-old text\n"
        "+old text expanded more\n"
    )
    monkeypatch.setattr(
        verify_instruction_text_growth,
        "instruction_diff",
        lambda base, head="HEAD", **kwargs: growth_diff,
    )

    body_file = tmp_path / "body.md"
    body_file.write_text(
        "## Summary\n\ntext-growth-ack: warranted clarification\n",
        encoding="utf-8",
    )
    assert verify_instruction_text_growth.main(
        [
            "verify",
            "--base-ref",
            "origin/main",
            "--body-file",
            str(body_file),
            "--created-at",
            "2026-06-03T00:00:00Z",
            "--cutoff",
            "2026-05-26T00:00:00Z",
        ]
    ) == 0


def test_verify_source_version_bump_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the env+argv shape used by verify-pr.yml.

    The workflow shells to
    ``python3 scripts/verify_source_version_bump.py verify
    --base-ref "$BASE_REF"`` with ``PR_LABELS`` in the step env. Stub the
    changed-files lookup and the apm.yml version reads so the test stays
    hermetic across CI checkout depths (a real ``git diff origin/main..HEAD``
    would fail with exit 128 on a shallow checkout). A universal-text change,
    a minor bump, and a matching ``semver:minor`` label must pass.
    """
    monkeypatch.setattr(
        verify_source_version_bump,
        "changed_files",
        lambda base, head="HEAD", **kwargs: frozenset({"CLAUDE.md"}),
    )
    versions = iter([(1, 0, 0), (1, 1, 0)])
    monkeypatch.setattr(
        verify_source_version_bump,
        "read_version_at",
        lambda ref, **kwargs: next(versions),
    )
    monkeypatch.setenv("PR_LABELS", "semver:minor")
    assert verify_source_version_bump.main(
        ["verify", "--base-ref", "origin/main"]
    ) == 0


def test_auto_tag_version_run_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the env+argv shape used by post-merge.yml.

    The workflow shells to ``python3 scripts/auto_tag_version.py run`` with
    ``MERGE_SHA`` in the step env. Stub the apm.yml version reads and the tag
    git boundary so the test is hermetic. A version bump across the merge
    commit and its first parent must create and push the v{version} tag.
    """
    monkeypatch.setenv("MERGE_SHA", "deadbeef")
    versions = {"deadbeef": (1, 1, 0), "deadbeef^": (1, 0, 0)}
    monkeypatch.setattr(
        auto_tag_version,
        "read_version_at",
        lambda ref, **kwargs: versions[ref],
    )
    monkeypatch.setattr(auto_tag_version, "tag_exists", lambda *a, **k: False)
    pushed: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        auto_tag_version,
        "create_and_push_tag",
        lambda *a, **k: pushed.append(a),
    )
    assert auto_tag_version.main(["run"]) == 0
    assert pushed == [("v1.1.0", "deadbeef", "origin")]


def test_scan_design_philosophy_drift_verify_matches_workflow_paths(
    tmp_path: Path,
) -> None:
    master = tmp_path / "master.md"
    doc = tmp_path / "doc.md"
    master.write_text(
        "## 1. A\n## 2. B\n",
        encoding="utf-8",
    )
    glossary_lines = "".join(
        f"- **{term}**: definition.\n"
        for term in scan_design_philosophy_drift.REQUIRED_GLOSSARY_ENTRIES
    )
    doc.write_text(
        "### 2.5 Glossary\n"
        f"{glossary_lines}"
        "## 3. Matrix\n"
        "two principles by four lanes.\n"
        "| P1 - a | x |\n"
        "| P2 - b | y |\n"
        "## 4. Next\n",
        encoding="utf-8",
    )
    assert scan_design_philosophy_drift.main(
        ["verify", "--master", str(master), "--doc", str(doc)]
    ) == 0


def test_scan_design_philosophy_drift_verify_coupling_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mirror the env+argv shape used by portable-pr-policy.yml.

    The workflow shells to
    ``python3 scripts/scan_design_philosophy_drift.py verify-coupling
    --base-ref "$BASE_REF" --body-file "$body_file"``. Stub the
    changed-files lookup so the test stays hermetic across CI checkout
    depths (the lint-scripts-pytest job checks out shallow, so a real
    ``git diff origin/main..HEAD`` would fail with exit 128).
    """
    monkeypatch.setattr(
        scan_design_philosophy_drift,
        "changed_files",
        lambda base, **kwargs: frozenset(
            {
                scan_design_philosophy_drift.MASTER_PATH,
                scan_design_philosophy_drift.DOC_PATH,
            }
        ),
    )
    body_file = tmp_path / "body.md"
    body_file.write_text("no ack needed; doc is in the diff\n", encoding="utf-8")
    assert scan_design_philosophy_drift.main(
        [
            "verify-coupling",
            "--base-ref",
            "origin/main",
            "--body-file",
            str(body_file),
        ]
    ) == 0


def test_scan_non_ascii_run_matches_workflow_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = {
        "pull_request": {
            "number": 7,
            "title": "fix(ci): ascii title",
            "body": "ASCII body",
            "author_association": "CONTRIBUTOR",
            "user": {"login": "octocat"},
        }
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))

    assert scan_non_ascii.main(["run"]) == 0


def test_scan_retro_followup_drift_run_matches_workflow_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scan_retro_followup_drift, "search_retro_issues", lambda repo: []
    )
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))

    assert scan_retro_followup_drift.main(["run"]) == 0


def test_scan_workflow_action_pins_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert workflows pin actions to SHA + tag comment``
    step in ``.github/workflows/verify-agents.yml``."""
    assert scan_workflow_action_pins.main(["verify", "--repo-root", "."]) == 0


def test_scan_workflow_gh_calls_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert no unallowlisted gh CLI calls in workflows`` step
    in ``.github/workflows/verify-agents.yml`` and ``weekly-maintenance.yml``.

    Refs #911.
    """
    assert scan_workflow_gh_calls.main(["verify"]) == 0


def test_scan_scripts_gh_calls_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert no direct gh CLI calls in scripts`` step in
    ``.github/workflows/verify-agents.yml``. Refs #909.
    """
    assert scan_scripts_gh_calls.main(["verify"]) == 0


def test_scan_workflow_injection_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert no untrusted context in workflow run blocks`` step
    in ``.github/workflows/verify-agents.yml``. Refs #1129."""
    assert scan_workflow_injection.main(["verify"]) == 0


def test_scan_workflow_unsigned_commit_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert no git push (unsigned authoring) in workflow run
    blocks`` step in ``.github/workflows/verify-agents.yml``. Refs #1437, #1466."""
    assert scan_workflow_unsigned_commit.main(["verify"]) == 0


def test_scan_secrets_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert no hardcoded secrets in tracked non-Python files``
    step in ``.github/workflows/verify-agents.yml``. Refs #1129."""
    assert scan_secrets.main(["verify"]) == 0


def test_scan_secret_runbooks_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert workflow secrets have concrete runbooks`` step."""
    assert scan_secret_runbooks.main(["verify"]) == 0


def test_scan_hook_predicate_surface_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify git hook predicate covers its command surface`` step
    in ``.github/workflows/verify-agents.yml``. Refs #2133."""
    assert scan_hook_predicate_surface_drift.main(["verify"]) == 0


def test_scan_input_contract_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify workflow-script input contracts`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1087."""
    assert scan_input_contract_drift.main(["verify"]) == 0


def test_scan_pr_body_quality_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify PR body content-quality enforcement map`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1828."""
    assert scan_pr_body_quality_drift.main(["verify"]) == 0


def test_scan_quality_standard_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify quality-standard enforcement map`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1089."""
    assert scan_quality_standard_drift.main(["verify"]) == 0


def test_scan_nonexhaustive_invariant_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify section 2/4 safety enumerations stay
    non-exhaustive`` step in ``.github/workflows/verify-agents.yml``. Refs
    #1241, #1242, #1243."""
    assert scan_nonexhaustive_invariant_drift.main(["verify"]) == 0


def test_scan_test_presence_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify scripts ship required tests`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1088."""
    assert scan_test_presence_drift.main(["verify"]) == 0


def test_scan_markdown_links_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert local Markdown links resolve`` step."""
    assert scan_markdown_links.main(["verify"]) == 0


def test_scan_mermaid_syntax_verify_matches_workflow_args() -> None:
    """Mirrors verify-mermaid.yml's ``python3 scripts/scan_mermaid_syntax.py verify``.

    The ``verify`` argv shape is exercised in both environments: with bun and
    the pinned node_modules the gate parses the current docs (exit 0, since
    docs/generated/scripts/ast/ is exempt); without them it reaches the
    bun-missing branch (exit 1). Either way ``verify`` is a real, parseable
    subcommand; the contract this test guards.
    """
    has_deps = bool(scan_mermaid_syntax.resolve_bun()) and (
        scan_mermaid_syntax.REPO_ROOT / "node_modules" / "mermaid"
    ).is_dir()
    assert scan_mermaid_syntax.main(["verify"]) == (0 if has_deps else 1)


def test_scan_compile_from_source_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify no tool is compiled from source on the CI
    surface`` step in ``.github/workflows/verify-agents.yml``."""
    assert scan_compile_from_source.main(["verify"]) == 0


def test_scan_commit_type_label_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify type:* labels match title-policy commit types``
    step in ``.github/workflows/verify-agents.yml`` (issue #2081)."""
    assert scan_commit_type_label_drift.main(["verify"]) == 0


def test_scan_devcontainer_tool_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify devcontainer provisions gate-required tools``
    step in ``.github/workflows/verify-agents.yml``."""
    assert scan_devcontainer_tool_drift.main(["verify"]) == 0


def test_scan_harness_doc_coverage_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify harness file documentation coverage`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1761."""
    assert scan_harness_doc_coverage.main(["verify"]) == 0


def test_scan_allowlist_parser_parity_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify devcontainer allowlist parser parity`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1257."""
    assert scan_allowlist_parser_parity.main(["verify"]) == 0


def test_scan_allowlist_rationale_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify devcontainer egress hosts carry a triage
    rationale`` step in ``.github/workflows/verify-agents.yml``. Refs #1170."""
    assert scan_allowlist_rationale.main(["verify"]) == 0


def test_scan_apm_lock_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify apm.lock.yaml MCP drift`` step in
    ``.github/workflows/portable-pr-policy.yml``."""
    assert scan_apm_lock_drift.main(["verify"]) == 0


def test_scan_flake_pin_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify flake.nix is the single source of truth for pinned
    hashes`` step in ``.github/workflows/verify-agents.yml``."""
    assert scan_flake_pin_drift.main(["verify"]) == 0


def test_scan_docs_inventory_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert docs index and lane placement`` step."""
    assert scan_docs_inventory.main(["verify"]) == 0


def test_scan_doc_workflow_refs_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert docs cite existing workflow files`` step in
    ``.github/workflows/verify-agents.yml`` (issue #1325)."""
    assert scan_doc_workflow_refs.main(["verify"]) == 0


def test_scan_maintainability_metrics_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert script maintainability metrics`` step in
    ``.github/workflows/verify-agents.yml``."""
    assert scan_maintainability_metrics.main(["verify", "--repo-root", "."]) == 0


def test_scan_module_size_distribution_write_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors the ``write`` invocation used by the post-merge ``decision-tree``
    and ``verify-docs-drift`` jobs in ``.github/workflows/post-merge.yml``.

    Refs #2013: the PR-time ``verify`` gate was removed so feature branches no
    longer touch the snapshot; the post-merge job is the single producer
    (#1540/#1543/#1546), so the surviving workflow contract is ``write`` with no
    ``--repo-root`` (it defaults to the checkout root)."""
    monkeypatch.chdir(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "alpha.py").write_text("x = 1\n", encoding="utf-8")

    assert scan_module_size_distribution.main(["write"]) == 0
    assert scan_module_size_distribution.main(["verify"]) == 0


def test_scan_workflow_pip_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert workflows install Python deps via uv only``
    step in ``.github/workflows/verify-agents.yml``."""
    assert scan_workflow_pip.main(["verify", "--repo-root", "."]) == 0


def test_scan_ruff_format_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert ruff is enforced as check-only`` step in
    ``.github/workflows/verify-agents.yml`` (issue #2143 repair (a))."""
    assert scan_ruff_format.main(["verify", "--repo-root", "."]) == 0


def test_skill_quality_gate_verify_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors the ``Run skill quality gate`` step in
    ``.github/workflows/skill-quality.yml``. waza is an external Go binary
    installed by the workflow but absent from the pytest matrix, so its
    discovery and execution are stubbed; this asserts the ``verify`` argv
    shape is accepted and exits 0, not waza itself."""
    monkeypatch.setattr(skill_quality_gate, "find_waza", lambda: "waza")
    monkeypatch.setattr(
        skill_quality_gate, "run_waza_check", lambda _w, _sd: {"skills": []}
    )
    assert skill_quality_gate.main(["verify"]) == 0


def test_nixpkgs_cooldown_verify_matches_workflow_args(tmp_path: Path) -> None:
    """Mirrors the ``Assert nixpkgs lock respects uv cooldown`` step."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv]\nexclude-newer = "14 days"\n',
        encoding="utf-8",
    )
    (tmp_path / "flake.lock").write_text(
        json.dumps({"nodes": {"nixpkgs": {"locked": {"lastModified": 1_700_000_000}}}}),
        encoding="utf-8",
    )

    assert nixpkgs_cooldown.main(
        [
            "verify",
            "--repo-root",
            str(tmp_path),
            "--now-epoch",
            str(1_700_000_000 + (14 * 24 * 60 * 60)),
        ]
    ) == 0


def test_devcontainer_uv_pin_comes_from_pyproject() -> None:
    """Devcontainer shells must not drift behind the repository uv pin."""
    flake = Path("flake.nix").read_text(encoding="utf-8")
    runtime = Path(".devcontainer/scripts/configure-agent-runtime.sh").read_text(encoding="utf-8")

    assert "builtins.readFile ./pyproject.toml" in flake
    assert "required-version" in flake
    assert "pkgs.uv" not in flake
    assert "agentPackages.pinned-uv" in flake
    assert "install_nix_binary pinned-uv uv" in runtime
    assert "/usr/local/bin" in runtime


def test_security_drift_report_aggregate_and_post_comment_match_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ruleset_out = tmp_path / "ruleset-detect.out"
    labels_summary = tmp_path / "labels-summary.md"
    uv_stale = tmp_path / "uv-stale.out"
    report = tmp_path / "security-drift-report.md"
    ruleset_out.write_text("run_date=2026-05-24\ndrift_count=0\nunknown_count=0\n", encoding="utf-8")
    labels_summary.write_text("| `type:fix` | no-op | no | no | unchanged |\n", encoding="utf-8")
    uv_stale.write_text("", encoding="utf-8")

    assert security_drift_report.main(
        [
            "aggregate",
            "--ruleset-detect-output",
            str(ruleset_out),
            "--ruleset-detect-rc",
            "0",
            "--labels-plan-rc",
            "0",
            "--labels-summary-file",
            str(labels_summary),
            "--apm-diff-rc",
            "0",
            "--uv-drift-rc",
            "0",
            "--workflow-permissions-drift-rc",
            "0",
            "--uv-stale-rc",
            "0",
            "--uv-stale-output",
            str(uv_stale),
            "--owasp-asi-verify-rc",
            "0",
            "--run-url",
            "https://example.test/run",
            "--summary-file",
            str(tmp_path / "summary.md"),
            "--report-file",
            str(report),
            "--github-output",
            str(tmp_path / "output"),
        ]
    ) == 0
    assert security_drift_report.main(
        [
            "post-comment",
            "--repo",
            REPO,
            "--issue",
            "178",
            "--report-file",
            str(report),
            "--dry-run",
            "true",
        ]
    ) == 0


def test_security_drift_report_file_family_issues_matches_workflow_args() -> None:
    """Mirror the argv shape of the File-per-family-drift-issues step.

    weekly-maintenance.yml shells to ``file-family-issues --repo R --run-url U
    --run-date D --families <csv> --resolved-families <csv> --dry-run <bool>``
    where the two CSVs are the ``drift_families`` / ``covered_families`` outputs
    of the aggregate step. Exercise the dry-run path (no token, no network) across
    every target family so the contract pins the accepted flag set and allowlist.
    """
    assert security_drift_report.main(
        [
            "file-family-issues",
            "--repo",
            REPO,
            "--run-url",
            "https://example.test/run",
            "--run-date",
            "2026-06-03",
            "--families",
            "labels,apm-instructions",
            "--resolved-families",
            "uv-pin-literal,workflow-permissions",
            "--dry-run",
            "true",
        ]
    ) == 0


def test_verify_security_control_floor_matches_workflow_args() -> None:
    """Mirror the argv shape used by verify-agents.yml lint-scripts-static.

    The workflow shells to ``uv run python
    scripts/verify_security_control_floor.py`` with no further arguments, so
    the gate reads the committed ``.github/security-control-floor.toml`` and
    must exit 0 on it. Refs #178.
    """
    assert verify_security_control_floor.main([]) == 0


def test_verify_control_inventory_currency_matches_workflow_args() -> None:
    """Mirror the argv shape used by verify-agents.yml lint-scripts-static.

    The workflow shells to ``uv run python
    scripts/verify_control_inventory_currency.py verify`` with no further
    arguments, so the gate reads the committed inventory plus
    ``.github/security-surface-inventory.toml`` and must exit 0 on them.
    Refs #1387.
    """
    assert verify_control_inventory_currency.main(["verify"]) == 0


def test_owasp_asi_mapping_verify_matches_workflow_args() -> None:
    """Mirror the argv shape used by both workflow callers.

    verify-agents.yml (lint-scripts-static, PR gate) and weekly-maintenance.yml
    (security-control-drift job) both shell to ``scripts/owasp_asi_mapping.py
    verify`` with no further arguments, so the gate reads the committed
    ``docs/prd/security-control-inventory.md`` and must exit 0 on it. Refs #1378.
    """
    assert owasp_asi_mapping.main(["verify"]) == 0


def test_threat_intel_scan_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dep = threat_intel_triage.Dependency(
        name="pytest",
        version="8.0.0",
        ecosystem="PyPI",
        source="uv.lock",
    )
    monkeypatch.setattr(threat_intel_triage, "discover_dependencies", lambda repo_root: [dep])
    monkeypatch.setattr(
        threat_intel_triage,
        "fetch_external_findings",
        lambda dependencies, **kwargs: [],
    )

    assert threat_intel_triage.main(
        [
            "scan",
            "--repo-root",
            ".",
            "--labels",
            "",
            "--ghsa-live",
            "--malpkg-live",
            "--epss-live",
            "--summary-file",
            str(tmp_path / "summary.md"),
            "--github-output",
            str(tmp_path / "output"),
            "--comment-file",
            str(tmp_path / "threat-aggregate.md"),
            "--fail-on-intel",
        ]
    ) == 0
    # scan must render the same markdown to the comment file that the
    # comment subcommand later posts (the two surfaces share render_summary_markdown).
    assert (tmp_path / "threat-aggregate.md").exists()


def test_threat_intel_comment_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """comment subcommand accepts the argv shapes used by weekly-maintenance.yml.

    The ``Aggregate findings onto the security tracking issue`` step invokes
    both branches against the #178 umbrella, with the issue number resolved at
    runtime via ``issue_anchors.py`` and passed as ``--issue`` (never
    hardcoded): ``comment --body-file <f> --issue <n> --marker <m>`` when
    findings fired (create allowed) and the same plus ``--update-only`` when
    none did. The _upsert_comment boundary is stubbed so the contract
    exercises argv/env wiring without network access.
    """
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    # No NUMBER env: the workflow passes the tracking issue via --issue.
    body_file = tmp_path / "threat-aggregate.md"
    body_file.write_text("## Threat intelligence triage\n", encoding="utf-8")
    marker = "<!-- threat-intel-aggregate v1 -->"

    seen: list[dict[str, object]] = []

    def fake_upsert(**kw: object) -> int:
        seen.append(kw)
        return 0

    monkeypatch.setattr(threat_intel_triage, "_upsert_comment", fake_upsert)

    assert threat_intel_triage.main(
        ["comment", "--body-file", str(body_file), "--issue", "178", "--marker", marker]
    ) == 0
    assert threat_intel_triage.main(
        ["comment", "--body-file", str(body_file), "--issue", "178", "--marker", marker, "--update-only"]
    ) == 0
    assert [kw["create"] for kw in seen] == [True, False]
    assert all(kw["number"] == 178 for kw in seen)
    assert all(kw["marker"] == marker for kw in seen)


def test_pr_upsert_find_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """find subcommand accepts --head used by publish-devcontainer-images.yml. Refs #911."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setattr(pr_upsert, "_list_open_prs", lambda **kw: [{"number": 55}])
    assert pr_upsert.main(["find", "--head", "codex/devcontainer-image-pins-abc123"]) == 0


def test_pr_upsert_upsert_files_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """upsert-files accepts the --add (generate-agents.yml) and --from-diff
    (post-merge.yml) arg shapes used to publish signed App-bot commits."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    body_file = tmp_path / "pr-body.md"
    body_file.write_text("body content", encoding="utf-8")
    monkeypatch.setattr(pr_upsert, "_collect_worktree_changes", lambda **kw: ([("CLAUDE.md", b"x\n")], []))
    monkeypatch.setattr(pr_upsert, "upsert_files_pr", lambda **kw: "created:99")

    # generate-agents.yml shape: explicit --add files.
    assert pr_upsert.main([
        "upsert-files",
        "--head", "chore/regenerate-agent-instructions",
        "--base", "main",
        "--title", "chore: regenerate agent instructions",
        "--commit-body", "Refs #18",
        "--body-file", str(body_file),
        "--add", "CLAUDE.md",
        "--add", "AGENTS.md",
    ]) == 0

    # post-merge.yml decision-tree shape: --from-diff over a directory prefix,
    # with --recreate so the fixed branch is rebuilt off base rather than
    # appended onto its stale tip (#1574).
    assert pr_upsert.main([
        "upsert-files",
        "--head", "chore/update-generated-docs",
        "--base", "main",
        "--title", "docs(generated): regenerate decision tree and workflow diagrams",
        "--commit-body", "Refs #960",
        "--body-file", str(body_file),
        "--from-diff", "docs/generated/",
        "--recreate",
    ]) == 0


def test_issue_anchors_get_matches_workflow_args(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """get <key> prints the bare issue number consumed via command
    substitution in weekly-maintenance.yml, monthly-maintenance.yml,
    post-merge.yml, generate-agents.yml, devcontainer-pin-refresh.yml, and
    publish-devcontainer-images.yml. Refs #1640."""
    for key, expected in (
        ("security-tracking", "178"),
        ("flake-pin", "1171"),
        ("generated-docs", "960"),
        ("agents-regen", "18"),
        ("devcontainer-pins", "696"),
    ):
        assert issue_anchors.main(["get", key]) == 0
        assert capsys.readouterr().out.strip() == expected


def test_issue_anchors_render_matches_workflow_args(tmp_path: Path) -> None:
    """render --file rewrites the heredoc-built PR bodies in place
    (post-merge.yml, generate-agents.yml). Refs #1640."""
    body = tmp_path / "pr-body.md"
    body.write_text("Closes #__ISSUE_ANCHOR:generated-docs__\n", encoding="utf-8")
    assert issue_anchors.main(["render", "--file", str(body)]) == 0
    assert body.read_text(encoding="utf-8") == "Closes #960\n"


def test_scan_issue_anchor_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify tracking-issue anchors stay declarative`` step in
    verify-agents.yml. Refs #1640."""
    assert scan_issue_anchor_drift.main(["verify"]) == 0


def test_github_paginate_fetch_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch subcommand accepts --path/--output args used by backup-non-ascii-originals.yml."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    out = tmp_path / "issues.json"
    monkeypatch.setattr(github_paginate, "_paginate_get", lambda **kw: [{"id": 1}])
    rc = github_paginate.main([
        "fetch",
        "--path", "repos/owner/repo/issues?state=all&per_page=100",
        "--output", str(out),
    ])
    assert rc == 0


def test_github_paginate_get_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """get subcommand accepts --path/--output/--field args used by weekly-maintenance.yml. Refs #911."""
    import json as _json
    monkeypatch.setenv("GH_TOKEN", "tok")

    # --field form: used by "Resolve default branch" step
    monkeypatch.setattr(github_paginate, "_get_single", lambda **kw: _json.dumps({"default_branch": "main"}))
    rc = github_paginate.main(["get", "--path", "repos/owner/repo", "--field", "default_branch"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "main"

    # --output form: used by "Fetch verify-agents.yml runs" and "Fetch per-run jobs" steps
    out = tmp_path / "runs.json"
    payload = {"total_count": 1, "workflow_runs": [{"id": 42}]}
    monkeypatch.setattr(github_paginate, "_get_single", lambda **kw: _json.dumps(payload))
    rc = github_paginate.main([
        "get",
        "--path", "repos/owner/repo/actions/workflows/verify-agents.yml/runs?per_page=100",
        "--output", str(out),
    ])
    assert rc == 0
    assert _json.loads(out.read_text(encoding="utf-8")) == payload


def test_post_issue_comment_create_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create subcommand accepts --issue-number/--body args used by backup-non-ascii-originals.yml.

    The ``Post review reminder comment`` step in
    ``attack-coverage-review-reminder.yml`` also invokes the ``--body-file``
    form. Refs #184, #911.
    """
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setattr(post_issue_comment, "_post_comment", lambda **kw: None)
    rc = post_issue_comment.main(["create", "--issue-number", "42", "--body", "test body"])
    assert rc == 0
    body_file = tmp_path / "comment.md"
    body_file.write_text("assembled comment", encoding="utf-8")
    rc = post_issue_comment.main(["create", "--issue-number", "178", "--body-file", str(body_file)])
    assert rc == 0


def test_publish_instruction_release_publish_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """publish accepts the --tag/--asset argv used by publish-instructions-release.yml.

    The release job calls ``publish_instruction_release.py publish --tag "$TAG"
    --asset CLAUDE.md --asset AGENTS.md --asset SHA256SUMS``. Monkeypatch the
    publish boundary so the contract test pins the argv shape without an API
    call or on-disk asset files. Refs #1678.
    """
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setattr(publish_instruction_release, "publish", lambda **kw: "https://x/rel")
    rc = publish_instruction_release.main(
        [
            "publish",
            "--tag",
            "v1.0.0",
            "--asset",
            "CLAUDE.md",
            "--asset",
            "AGENTS.md",
            "--asset",
            "SHA256SUMS",
        ]
    )
    assert rc == 0


def test_attack_review_reminder_assemble_matches_workflow_args(tmp_path: Path) -> None:
    """assemble subcommand accepts the args used by the ``Assemble review
    reminder comment`` step in ``attack-coverage-review-reminder.yml``. Refs #184."""
    runbook = tmp_path / "rb.md"
    runbook.write_text(
        f"{attack_review_reminder.BEGIN_MARKER}\n### A\n### B\n{attack_review_reminder.END_MARKER}\n",
        encoding="utf-8",
    )
    out = tmp_path / "review-comment.md"
    summary = tmp_path / "summary.md"
    rc = attack_review_reminder.main([
        "assemble",
        "--runbook", str(runbook),
        "--out", str(out),
        "--summary-file", str(summary),
        "--repo", "owner/repo",
        "--run-url", "https://example/run/1",
        "--expected-h3", "2",
    ])
    assert rc == 0
    assert out.exists()


def test_backup_archive_build_matches_workflow_args(tmp_path: Path) -> None:
    """build subcommand accepts the --indir/--timestamp/--repo/--archive args
    used by the ``Capture issues, PRs, and comments`` step in
    ``backup-non-ascii-originals.yml``."""
    for fname in ("issues.json", "pull_requests.json", "issue_comments.json", "pull_request_review_comments.json"):
        (tmp_path / fname).write_text("[]", encoding="utf-8")
    archive = tmp_path / "originals.json.gz"
    rc = backup_archive.main([
        "build",
        "--indir", str(tmp_path),
        "--timestamp", "20260602T0000Z",
        "--repo", "owner/repo",
        "--archive", str(archive),
    ])
    assert rc == 0
    assert archive.exists()


def test_github_paginate_fetch_run_jobs_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch-run-jobs subcommand accepts the --runs/--repo/--outdir args used by
    the ``Fetch per-run jobs`` step in ``weekly-maintenance.yml``. Refs #911."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps({"workflow_runs": [{"id": 42}]}), encoding="utf-8")
    monkeypatch.setattr(github_paginate, "_get_single", lambda **kw: json.dumps({"jobs": []}))
    rc = github_paginate.main([
        "fetch-run-jobs",
        "--runs", str(runs),
        "--repo", "owner/repo",
        "--outdir", str(tmp_path / "jobs"),
    ])
    assert rc == 0
    assert (tmp_path / "jobs" / "42.json").exists()


def test_prune_codespaces_prune_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prune subcommand accepts the --org/--min-age-days/--dry-run/--summary-file args
    used by the ``Prune inactive codespaces`` step in weekly-maintenance.yml. Refs #1930."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(prune_codespaces, "_list_codespaces", lambda *a, **k: [])
    monkeypatch.setattr(prune_codespaces, "_delete_codespace", lambda *a, **k: (202, ""))
    summary = tmp_path / "summary.md"
    rc = prune_codespaces.main([
        "prune",
        "--org", "myorg",
        "--min-age-days", "30",
        "--dry-run", "true",
        "--summary-file", str(summary),
    ])
    assert rc == 0


def test_prune_devcontainer_images_prune_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prune subcommand accepts the --owner/--package/--pinned-sha-from/--keep-recent/
    --min-age-days/--dry-run/--summary-file args used by the ``Prune old devcontainer
    image versions`` step in monthly-maintenance.yml. Refs #1400."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(prune_devcontainer_images, "_list_versions", lambda *a, **k: [])
    monkeypatch.setattr(prune_devcontainer_images, "_delete_version", lambda *a, **k: (204, ""))
    cfg = tmp_path / "devcontainer.json"
    cfg.write_text(json.dumps({"image": "ghcr.io/tvna/x:" + "a" * 40}), encoding="utf-8")
    summary = tmp_path / "summary.md"
    rc = prune_devcontainer_images.main([
        "prune",
        "--owner", "owner",
        "--package", "claude-md-devcontainer-claude",
        "--package", "claude-md-devcontainer-codex",
        "--pinned-sha-from", str(cfg),
        "--pinned-sha-from", str(cfg),
        "--keep-recent", "10",
        "--min-age-days", "90",
        "--dry-run", "true",
        "--summary-file", str(summary),
    ])
    assert rc == 0


def test_validate_falco_rules_verify_matches_workflow_args() -> None:
    """verify subcommand accepts the --file arg used in verify-falco-rules.yml."""
    assert validate_falco_rules.main([
        "verify",
        "--file", ".devcontainer/falco/custom-rules.yaml",
    ]) == 0


def test_validate_json_syntax_verify_matches_workflow_args() -> None:
    """verify subcommand accepts the repeated --file args used by the
    ``Validate ruleset JSON syntax`` steps in apply-rulesets.yml and
    weekly-maintenance.yml."""
    assert validate_json_syntax.main([
        "verify",
        "--file", ".github/rulesets/main.json",
        "--file", ".github/rulesets/all-branches.json",
    ]) == 0


def test_title_policy_verify_matches_workflow_kind_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # title_policy.verify_title falls back to PR_BODY / ISSUE_BODY when called
    # with an empty body; the single-process pre-push preflight exports PR_BODY
    # for its body gates, so clear both to keep this type-fit check deterministic
    # regardless of the ambient environment. Refs #1451.
    monkeypatch.delenv("PR_BODY", raising=False)
    monkeypatch.delenv("ISSUE_BODY", raising=False)
    monkeypatch.setenv("TITLE", "fix(ci): ascii title")

    assert title_policy.main(["verify", "--kind", "pull_request"]) == 0


def test_update_devcontainer_image_pins_matches_workflow_args(tmp_path: Path) -> None:
    old_sha = "0" * 40
    new_sha = "1" * 40
    for agent in update_devcontainer_image_pins.AGENTS:
        config_dir = tmp_path / ".devcontainer" / agent
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "devcontainer.json").write_text(
            json.dumps(
                {
                    "name": f"claude-md {agent}",
                    "image": f"{update_devcontainer_image_pins.IMAGE_PREFIX}-{agent}:{old_sha}",
                    "remoteUser": agent,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    runbook_dir = tmp_path / "docs" / "runbooks"
    runbook_dir.mkdir(parents=True, exist_ok=True)
    (runbook_dir / "devcontainers.md").write_text(
        "\n".join(
            [
                f"pinned images were published from `{old_sha}`",
                f"`{update_devcontainer_image_pins.IMAGE_PREFIX}-claude:{old_sha}`",
                f"`{update_devcontainer_image_pins.IMAGE_PREFIX}-codex:{old_sha}`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert update_devcontainer_image_pins.main([new_sha, "--repo-root", str(tmp_path)]) == 0

    for agent in update_devcontainer_image_pins.AGENTS:
        config_path = tmp_path / ".devcontainer" / agent / "devcontainer.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert config["image"] == f"{update_devcontainer_image_pins.IMAGE_PREFIX}-{agent}:{new_sha}"


def test_devcontainer_pin_pr_uses_environment_secret_token() -> None:
    workflow_path = Path(".github/workflows/publish-devcontainer-images.yml")
    raw = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)

    update_pins = workflow["jobs"]["update-pins"]
    assert update_pins["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    # The PR is authored by a GitHub App bot: the token is minted at runtime from
    # the App ID + private key, fully replacing the old PAT. Refs #1401.
    assert "DEVCONTAINER_PIN_APP_ID" in raw
    assert "DEVCONTAINER_PIN_APP_PRIVATE_KEY" in raw
    assert "DEVCONTAINER_PIN_PR_TOKEN" not in raw

    app_token = next(step for step in update_pins["steps"] if step.get("id") == "app-token")
    assert app_token["uses"].startswith("actions/create-github-app-token@")
    assert app_token["with"] == {
        "app-id": "${{ secrets.DEVCONTAINER_PIN_APP_ID }}",
        "private-key": "${{ secrets.DEVCONTAINER_PIN_APP_PRIVATE_KEY }}",
    }

    open_pr = next(
        step for step in update_pins["steps"] if step.get("name") == "Open pin update PR"
    )
    # Thin orchestration: GH_TOKEN is the App installation token (so the PR
    # author is the App bot and the API-created pin commit is signed under that
    # same bot), REPO from the workflow context. Both consumed by
    # scripts/devcontainer_pin_pr.py. Refs #1437.
    assert open_pr["env"] == {
        "GH_TOKEN": "${{ steps.app-token.outputs.token }}",
        "REPO": "${{ github.repository }}",
    }
    assert "scripts/devcontainer_pin_pr.py open" in open_pr["run"]
    # Refs #1640: the trailer's issue number is resolved from the anchor
    # table at runtime, never hardcoded in the workflow.
    assert "scripts/issue_anchors.py get devcontainer-pins" in open_pr["run"]
    assert 'Refs #${TRACKING_ISSUE}' in open_pr["run"]


def test_devcontainer_pin_pr_open_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """open subcommand accepts the args used by the Open pin update PR step.

    The branch/PR decision flow is exercised by
    tests/test_devcontainer_pin_pr.py; here we pin the workflow argv shape.
    Refs #696, #911.
    """
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", REPO)
    template = tmp_path / "tmpl.md"
    template.write_text("Pinned to __GITHUB_SHA__.\n", encoding="utf-8")
    # Branch absent -> create branch + upsert; mock the git probes, the signed
    # commit API path, and the PR upsert. Refs #1437.
    monkeypatch.setattr(
        devcontainer_pin_pr,
        "run_git",
        lambda args, **kw: __import__("subprocess").CompletedProcess(
            ["git", *args], 1 if args[0] == "diff" else 2 if args[0] == "ls-remote" else 0
        ),
    )
    monkeypatch.setattr(devcontainer_pin_pr, "_create_pin_branch", lambda **kw: None)
    monkeypatch.setattr(devcontainer_pin_pr, "_upsert_pr", lambda **kw: ("created", 42))
    rc = devcontainer_pin_pr.main([
        "open",
        "--github-sha", "abc123",
        "--base", "main",
        "--title", "fix(devcontainer): pin published agent images",
        "--commit-subject", "fix(devcontainer): pin published agent images",
        "--commit-trailer", "Refs #696",
        "--template", str(template),
        "--file", ".devcontainer/claude/devcontainer.json",
        "--file", ".devcontainer/codex/devcontainer.json",
        "--file", "docs/runbooks/devcontainers.md",
    ])
    assert rc == 0


def test_devcontainer_pin_pr_refresh_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """refresh subcommand accepts the args used by devcontainer-pin-refresh.yml.

    The supersede flow is exercised by tests/test_devcontainer_pin_pr.py; here we
    pin the workflow argv shape. Refs #1137.
    """
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", REPO)
    template = tmp_path / "tmpl.md"
    template.write_text("Pinned to __GITHUB_SHA__.\n", encoding="utf-8")
    # No open pin PR -> the command is a no-op; we only assert the argv parses.
    monkeypatch.setattr(devcontainer_pin_pr, "_list_open_prs_by_prefix", lambda **kw: [])
    rc = devcontainer_pin_pr.main([
        "refresh",
        "--base", "main",
        "--target-sha", "b417e5833394f6f04a6e9b1eefe48026c09b4089",
        "--title", "fix(devcontainer): pin published agent images",
        "--commit-subject", "fix(devcontainer): pin published agent images",
        "--commit-trailer", "Refs #696",
        "--template", str(template),
        "--file", ".devcontainer/claude/devcontainer.json",
        "--file", ".devcontainer/codex/devcontainer.json",
        "--file", "docs/runbooks/devcontainers.md",
    ])
    assert rc == 0


def test_tvna_bot_automerge_workflow_contract() -> None:
    """The unified tvna-bot keeper triggers on workflow_run + schedule, uses an App token.

    The repository-level "Allow auto-merge" toggle is intentionally OFF, so every
    PR authored by the App bot (``tvna-bot[bot]``) is completed by this single
    keeper instead of native auto-merge. The earlier per-flow pin keeper is
    consolidated here. ``check_suite: completed`` never fires for Actions-created
    suites (recursion suppression), so the keeper is driven by ``workflow_run``
    on the workflows that own the required status checks, plus a ``schedule``
    safety net. The merge subcommand filters by author and clean state, so unlike
    the old pin keeper the job is not branch-prefix-gated; it runs on any
    successful run and no-ops when nothing is eligible. Refs #1539, #1352, #1363,
    #1401.
    """
    workflow = yaml.safe_load((_WORKFLOWS_DIR / "tvna-bot-automerge.yml").read_text(encoding="utf-8"))
    # ``on`` may parse to the truthy bool key True under YAML 1.1; tolerate both.
    triggers = workflow.get("on", workflow.get(True))
    # check_suite is suppressed for Actions-created suites, so it must be gone.
    assert "check_suite" not in triggers
    # workflow_run fires off the workflows that own the required status checks.
    assert triggers["workflow_run"]["types"] == ["completed"]
    assert triggers["workflow_run"]["workflows"] == ["Verify PR", "Verify repository scripts"]
    # schedule is the safety net that converges a missed workflow_run event.
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers

    job = workflow["jobs"]["merge"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    # The job is no longer branch-prefix-gated; it gates on a successful run and
    # the merge subcommand filters to tvna-bot[bot] authors.
    assert "github.event.workflow_run.conclusion == 'success'" in job["if"]
    assert "workflow_dispatch" in job["if"]
    assert "schedule" in job["if"]

    app_token = next(s for s in job["steps"] if s.get("id") == "app-token")
    assert app_token["uses"].startswith("actions/create-github-app-token@")
    assert app_token["with"] == {
        "app-id": "${{ secrets.DEVCONTAINER_PIN_APP_ID }}",
        "private-key": "${{ secrets.DEVCONTAINER_PIN_APP_PRIVATE_KEY }}",
    }

    # The merge step needs only the App token (it merges; it does not author a commit).
    merge_step = next(s for s in job["steps"] if "bot_pr_automerge.py merge" in str(s.get("run", "")))
    assert merge_step["env"] == {
        "GH_TOKEN": "${{ steps.app-token.outputs.token }}",
        "REPO": "${{ github.repository }}",
    }


def test_bot_pr_automerge_merge_matches_workflow_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """merge subcommand accepts the args used by tvna-bot-automerge.yml.

    The merge decision flow is exercised by tests/test_bot_pr_automerge.py; here
    we pin the workflow argv shape. Refs #1539.
    """
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", REPO)
    # No open bot PR -> the command is a no-op; we only assert the argv parses.
    monkeypatch.setattr(bot_pr_automerge, "_list_open_prs_by_author", lambda **kw: [])
    rc = bot_pr_automerge.main(["merge"])
    assert rc == 0


def test_devcontainer_pin_refresh_persists_checkout_credentials() -> None:
    """The refresh job's checkout must persist credentials for the remote probe.

    Regression guard for #1301: ``scripts/devcontainer_pin_pr.py`` still runs
    ``git ls-remote origin <fresh-branch>`` (the branch-existence check) which
    authenticates with the GITHUB_TOKEN that ``actions/checkout`` persists by
    default. The pin commit itself is now created via the GitHub API
    (createCommitOnBranch), not ``git push``, so it is signed; but a
    ``persist-credentials: false`` on this checkout would still strip the
    ls-remote credential. Assert the checkout step does not disable credential
    persistence. Refs #1229, #1301, #1303, #1437.
    """
    workflow = yaml.safe_load(
        (_WORKFLOWS_DIR / "devcontainer-pin-refresh.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["refresh"]["steps"]
    checkout_steps = [s for s in steps if "actions/checkout" in str(s.get("uses", ""))]
    assert checkout_steps, "refresh job must check out the repository before probing the remote"
    for step in checkout_steps:
        persist = step.get("with", {}).get("persist-credentials", True)
        assert persist is not False, (
            "devcontainer-pin-refresh checkout must persist credentials so the refresh "
            "ls-remote probe authenticates (regression #1301); remove `persist-credentials: false`."
        )


def test_force_with_lease_push_fetches_branch_first() -> None:
    """Bot-branch ``--force-with-lease`` pushes must fetch the branch first.

    Regression guard for #1412: the auto-retro/regenerate jobs check out
    ``main`` shallowly, recreate the bot branch from ``main``, then run
    ``git push --force-with-lease origin "$PR_BRANCH"``. With no
    ``refs/remotes/origin/$PR_BRANCH`` tracking ref (the shallow checkout
    never fetched it), the lease cannot be verified and git rejects the
    overwrite with ``stale info`` whenever the branch already exists. The
    fix fetches the branch into its tracking ref before the push. Assert
    every ``--force-with-lease`` push step fetches ``$PR_BRANCH`` earlier in
    the same step so the repair stays a deterministic gate.
    """
    offenders: list[str] = []
    for path in sorted(_WORKFLOWS_DIR.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in (workflow.get("jobs") or {}).items():
            for step in job.get("steps", []):
                run = str(step.get("run", ""))
                if 'git push --force-with-lease origin "$PR_BRANCH"' not in run:
                    continue
                lines = run.splitlines()
                push_idx = next(
                    i
                    for i, line in enumerate(lines)
                    if 'git push --force-with-lease origin "$PR_BRANCH"' in line
                )
                fetched_before = any(
                    "git fetch origin" in line and "$PR_BRANCH" in line
                    for line in lines[:push_idx]
                )
                if not fetched_before:
                    offenders.append(f"{path.name}::{job_name}")
    assert not offenders, (
        "force-with-lease push must fetch $PR_BRANCH into its tracking ref first "
        "or git rejects the overwrite with 'stale info' (#1412); missing fetch in: "
        + ", ".join(offenders)
    )


def test_analyze_ci_timings_matches_workflow_args(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mirror the argv shape used by weekly-maintenance.yml.

    The workflow shells to
    ``uv run python scripts/analyze_ci_timings.py --jobs jobs/
    --workflow "Verify repository scripts" --title "..."``. Exercise the
    same shape against a minimal jobs/ fixture so the contract pins the
    flag-only invocation (no subcommand). Refs #552.
    """
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "1.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "name": "lint-scripts-static",
                        "workflow_name": "Verify repository scripts",
                        "started_at": "2026-05-27T12:00:00Z",
                        "completed_at": "2026-05-27T12:01:00Z",
                        "steps": [
                            {
                                "name": "Checkout repository",
                                "started_at": "2026-05-27T12:00:00Z",
                                "completed_at": "2026-05-27T12:00:10Z",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rc = analyze_ci_timings.main(
        [
            "--jobs",
            str(jobs_dir),
            "--workflow",
            "Verify repository scripts",
            "--title",
            "verify-agents.yml timings (weekly)",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "verify-agents.yml timings (weekly)" in out


def test_measure_tool_overlap_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the argv shape used by measure-tool-overlap.yml.

    The workflow shells to ``uv run python scripts/measure_tool_overlap.py
    --scope-root . --commit <sha> --host-id <token> --notes "..." --output
    records.json --report report.md``. Exercise that flag-only shape (no
    subcommand) with the three pairs stubbed by a fake PairSpec, so the
    contract is pinned without the web-session-only binaries. Refs #1618.
    """
    fake = measure_tool_overlap.PairSpec(
        pair_name="fake",
        new_tool="nt",
        existing_gate="eg",
        scope_label="s",
        run_tool=lambda root: ([measure_tool_overlap.Finding("r", "f", 1)], 1.0),
        collect_gate=lambda root: [],
    )
    monkeypatch.setattr(measure_tool_overlap, "PAIRS", (fake,))
    out_path = tmp_path / "records.json"
    report_path = tmp_path / "report.md"
    rc = measure_tool_overlap.main(
        [
            "--scope-root",
            str(tmp_path),
            "--commit",
            "deadbeef",
            "--host-id",
            "ci-ephemeral",
            "--notes",
            "scheduled measurement (123)",
            "--output",
            str(out_path),
            "--report",
            str(report_path),
        ]
    )
    assert rc == 0
    records = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert tuple(records[0].keys()) == measure_tool_overlap.RECORD_COLUMNS
    assert records[0]["commit_sha"] == "deadbeef"
    assert records[0]["resource_attributes"]["host.id"] == "ci-ephemeral"
    assert "Tool overlap measurement" in report_path.read_text(encoding="utf-8")


def test_measure_devcontainer_startup_matches_workflow_args(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mirror the argv shape used by measure-devcontainer-startup.yml.

    The workflow shells to ``python3 scripts/measure_devcontainer_startup.py
    --config .devcontainer/<agent>/devcontainer.json --runtime docker
    --user <agent> --cap NET_ADMIN --probe-composition --output
    startup-<agent>.json``. Exercise that flag-only shape (no subcommand)
    against the real claude config, with the container runtime stubbed so no
    daemon is needed. Refs #1322, #1332.
    """

    class _StubSession:
        image = "stub"

        def pull(self) -> measure_devcontainer_startup.RunResult:
            return measure_devcontainer_startup.RunResult(0, "", 1.0)

        def image_size(self) -> int:
            return 1024

        def start(self) -> None:
            pass

        def exec(self, segment: str) -> measure_devcontainer_startup.RunResult:
            return measure_devcontainer_startup.RunResult(0, "", 0.5)

        def close(self) -> None:
            pass

    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> _StubSession:
        captured.update(kwargs)
        return _StubSession()

    out_path = tmp_path / "startup-claude.json"
    rc = measure_devcontainer_startup.run(
        [
            "--config",
            ".devcontainer/claude/devcontainer.json",
            "--runtime",
            "docker",
            "--user",
            "claude",
            "--cap",
            "NET_ADMIN",
            "--probe-composition",
            "--output",
            str(out_path),
        ],
        session_factory=factory,
        which=lambda _name: "/usr/bin/docker",
    )
    assert rc == 0
    assert captured["runtime"] == "/usr/bin/docker"
    assert captured["user"] == "claude"
    assert captured["caps"] == ["NET_ADMIN"]
    assert json.loads(out_path.read_text(encoding="utf-8"))["image"] == "stub"
    assert json.loads(capsys.readouterr().out)["image"] == "stub"


def test_ci_budget_issue_run_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the argv shape used by weekly-maintenance.yml.

    The workflow shells to ``python3 scripts/ci_budget_issue.py run --repo
    "${REPO}" --breach-file budget.json --run-url "${RUN_URL}" --dry-run
    "${DRY_RUN}"``. Exercise that exact shape against a real breach file with
    ``open_or_update_issue`` stubbed so the contract pins the flags without a
    network call. Refs #1156.
    """
    breach_file = tmp_path / "budget.json"
    breach_file.write_text(
        json.dumps(
            {"budget_seconds": 300.0, "breaches": [{"job": "slow", "p50": 410.0}]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GH_TOKEN", "token")
    captured: dict[str, object] = {}

    def fake_open(**kwargs: object) -> str:
        captured.update(kwargs)
        return "created"

    monkeypatch.setattr(ci_budget_issue, "open_or_update_issue", fake_open)

    rc = ci_budget_issue.main(
        [
            "run",
            "--repo",
            REPO,
            "--breach-file",
            str(breach_file),
            "--run-url",
            "https://github.com/owner/repo/actions/runs/123",
            "--dry-run",
            "false",
        ]
    )
    assert rc == 0
    assert captured["repo"] == REPO
    assert captured["budget_seconds"] == 300.0


def test_verify_test_shard_markers_matches_workflow_args(tmp_path: Path) -> None:
    """Mirror the argv shape used by verify-agents.yml lint-scripts-static.

    The workflow shells to ``uv run python scripts/verify_test_shard_markers.py``
    with no subcommand and no flags; it relies on the script defaulting
    ``--tests-dir`` to ``<repo>/tests``. Exercise the same shape against a
    tiny conformant fixture so the contract pins the no-argv invocation.
    Refs #545.
    """
    (tmp_path / "test_a.py").write_text(
        "import pytest\npytestmark = pytest.mark.shard_default\n",
        encoding="utf-8",
    )

    assert verify_test_shard_markers.main(["--tests-dir", str(tmp_path)]) == 0


def test_verify_shard_coverage_matches_workflow_args(tmp_path: Path) -> None:
    """Mirror the argv shape used by verify-agents.yml lint-scripts-pytest-gate.

    The workflow shells to
    ``uv run python scripts/verify_shard_coverage.py --collected <file>
    --junit <one or more junit-*.xml>``. Exercise the same shape with a
    minimal collected-universe + single JUnit artifact so the contract
    pins the multi-value --junit flag. Refs #545.
    """
    collected = tmp_path / "collected.txt"
    collected.write_text("tests/test_a.py::test_one\n", encoding="utf-8")
    junit = tmp_path / "junit-default.xml"
    junit.write_text(
        '<?xml version="1.0"?><testsuite>'
        '<testcase classname="tests.test_a" name="test_one"/>'
        "</testsuite>\n",
        encoding="utf-8",
    )

    assert verify_shard_coverage.main(
        ["--collected", str(collected), "--junit", str(junit)]
    ) == 0


def test_uv_pin_workflow_subcommands_match_ci_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv]\nrequired-version = "==0.11.11"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(uv_pin, "fetch_latest_uv_release", lambda: "0.11.11")

    assert uv_pin.main(["read", str(tmp_path / "pyproject.toml")]) == 0
    assert uv_pin.main(["drift", "--repo-root", str(tmp_path)]) == 0
    assert uv_pin.main(["stale", "--repo-root", str(tmp_path)]) == 0


def test_python_pin_verify_matches_workflow_args(tmp_path: Path) -> None:
    """Mirror the workflow step in ``.github/workflows/verify-agents.yml`` and
    ``weekly-maintenance.yml`` that runs
    ``uv run python scripts/python_pin.py verify``; no extra flags, cwd is the
    repo root. Refs #1680.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.12"\n'
        '\n[tool.ruff]\ntarget-version = "py312"\n'
        '\n[tool.mypy]\npython_version = "3.12"\n',
        encoding="utf-8",
    )
    (tmp_path / ".python-version").write_text("3.12.13\n", encoding="utf-8")
    (tmp_path / "flake.nix").write_text("python312\n", encoding="utf-8")

    assert python_pin.main(["verify", "--repo-root", str(tmp_path)]) == 0


def test_preflight_uv_version_verify_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the workflow step in ``.github/workflows/verify-agents.yml``
    that runs ``uv run python scripts/preflight_uv_version.py verify`` --
    no extra flags, no env input. The CI step relies on the cwd being the
    repo root and ``uv`` matching the pin (the workflow's setup-uv action
    just installed the matching uv). Refs #1207.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv]\nrequired-version = "==0.11.11"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        preflight_uv_version, "probe_uv_version", lambda: "0.11.11"
    )

    assert (
        preflight_uv_version.main(["verify", "--repo-root", str(tmp_path)]) == 0
    )


_FLAKE_PIN_FIXTURE = """
{
  outputs = { ... }:
    let
      apmVersion = "0.12.1";
      wazaVersion = "0.33.0";
      wazaNative = {
        aarch64-linux = {
          asset = "waza-linux-arm64";
          hash = "sha256-VSuk9F5fc+PpwMk0KeLFniHxpN6LmJX5j1Te6n8D36g=";
        };
        x86_64-linux = {
          asset = "waza-linux-amd64";
          hash = "sha256-waMaFdlZ0s1Tb+tBz3sg+UsENKjoaUnT3j0hweP7b/M=";
        };
      }.${system};
    in { };
}
"""


def test_flake_pin_workflow_subcommands_match_ci_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the ``asset-url`` and ``bump`` argv shapes used by the
    ``Recompute per-system hashes and bump flake.nix`` step in
    ``.github/workflows/flake-pin-refresh.yml``. Refs #1171."""
    flake = tmp_path / "flake.nix"
    flake.write_text(_FLAKE_PIN_FIXTURE, encoding="utf-8")
    monkeypatch.setattr(flake_pin, "FLAKE_PATH", flake)

    assert (
        flake_pin.main(
            [
                "asset-url",
                "--tool",
                "waza",
                "--system",
                "x86_64-linux",
                "--version",
                "0.34.0",
            ]
        )
        == 0
    )
    new_sri = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    assert (
        flake_pin.main(
            [
                "bump",
                "--tool",
                "waza",
                "--version",
                "0.34.0",
                "--hash",
                f"x86_64-linux={new_sri}",
                "--hash",
                f"aarch64-linux={new_sri}",
            ]
        )
        == 0
    )
    assert flake_pin.current_version(flake.read_text(encoding="utf-8"), "waza") == "0.34.0"


def test_flake_pin_latest_check_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the ``check --tool <tool>`` argv used by the
    ``Decide target version`` step in ``.github/workflows/flake-pin-refresh.yml``.

    The GitHub fetch is stubbed with a release older than the pin so the
    decision is a deterministic "hold" (exit 0, no stdout) without touching the
    network. Refs #1171."""
    monkeypatch.setattr(
        flake_pin_latest,
        "github_latest_release",
        lambda repo: {"tag_name": "v0.0.1", "published_at": "2000-01-01T00:00:00Z"},
    )
    assert flake_pin_latest.main(["check", "--tool", "waza"]) == 0
    assert flake_pin_latest.main(["check", "--tool", "apm"]) == 0
    assert flake_pin_latest.main(["check", "--tool", "rtk"]) == 0


def test_uv_download_checksum_verify_matches_action_args(tmp_path: Path) -> None:
    """Mirror the verify call in .github/actions/setup-uv/action.yml.

    The composite action runs
    ``python3 scripts/uv_download_checksum.py verify --file <tarball>
    --target x86_64-unknown-linux-gnu``. Exercise that argv shape against a
    tarball whose digest matches a synthetic flake pin so the contract is
    pinned the same way every other workflow/action script invocation is.
    """
    payload = b"uv-tarball-bytes"
    tarball = tmp_path / "uv.tar.gz"
    tarball.write_bytes(payload)
    sri = "sha256-" + base64.b64encode(
        hashlib.sha256(payload).digest()
    ).decode()
    flake = tmp_path / "flake.nix"
    flake.write_text(
        f'target = "x86_64-unknown-linux-gnu"; hash = "{sri}";',
        encoding="utf-8",
    )

    assert (
        uv_download_checksum.main(
            [
                "verify",
                "--file",
                str(tarball),
                "--target",
                "x86_64-unknown-linux-gnu",
                "--flake",
                str(flake),
            ]
        )
        == 0
    )


def test_verify_ruleset_sync_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live = _ruleset_for_id(1)
    sot_text = json.dumps(live)
    monkeypatch.setenv("GH_TOKEN_API", "token")
    monkeypatch.setattr(
        verify_ruleset_sync,
        "fetch_live_ruleset_by_name",
        lambda repo, name, token: live,
    )
    monkeypatch.setattr(
        verify_ruleset_sync,
        "fetch_base_ref_sot",
        lambda repo, base_ref, sot_path, token: sot_text,
    )

    assert verify_ruleset_sync.main(
        [
            "verify",
            "--repo",
            REPO,
            "--base-ref",
            "main",
            "--sot-path",
            ".github/rulesets/main.json",
            "--ruleset-name",
            "main-protection",
        ]
    ) == 0


def test_verify_required_check_contexts_matches_workflow_args() -> None:
    """Mirrors the `Verify required-check contexts match workflow job names`
    step in `.github/workflows/verify-ruleset-sync.yml`."""
    assert verify_required_check_contexts.main(
        [
            "verify",
            "--sot-path",
            ".github/rulesets/main.json",
            "--workflows-dir",
            ".github/workflows",
        ]
    ) == 0


def test_scan_hook_coverage_drift_verify_matches_workflow_args() -> None:
    """Mirrors the `Verify Claude/Codex hook coverage parity` step in
    `.github/workflows/verify-agents.yml` (issue #615)."""
    assert scan_hook_coverage_drift.main(["verify"]) == 0


def test_scan_preflight_drift_verify_matches_workflow_args() -> None:
    """Mirrors the `Verify preflight set matches CI script invocations`
    step in `.github/workflows/verify-agents.yml` (issue #493)."""
    assert scan_preflight_drift.main(["verify"]) == 0


def test_scan_provisioning_hook_serial_verify_matches_workflow_args() -> None:
    """Mirrors the `Verify shared-binary provisioning hooks are serial`
    step in `.github/workflows/verify-agents.yml` (issue #1155)."""
    assert scan_provisioning_hook_serial.main(["verify"]) == 0


def test_scan_session_path_drift_verify_matches_workflow_args() -> None:
    """Mirrors the `$CLAUDE_ENV_FILE` persistence centralization step in
    `.github/workflows/verify-agents.yml` (issue #1232)."""
    assert scan_session_path_drift.main(["verify"]) == 0


@pytest.mark.parametrize(
    ("label", "call"),
    [
        (
            "branch-cleanup invalid min age",
            lambda tmp: branch_cleanup.main(
                [
                    "survey",
                    "--repo",
                    REPO,
                    "--dry-run",
                    "true",
                    "--min-age-days",
                    "sixty",
                    "--default-branch",
                    "main",
                    "--out",
                    str(tmp / "out.md"),
                ]
            ),
        ),
        (
            "labels invalid boolean",
            lambda tmp: labels_apply.main(
                [
                    "plan",
                    "--repo",
                    REPO,
                    "--sot",
                    str(tmp / "missing.json"),
                    "--prune",
                    "maybe",
                    "--dry-run",
                    "true",
                    "--summary-file",
                    str(tmp / "summary.md"),
                ]
            ),
        ),
        (
            "security report invalid dry-run",
            lambda tmp: security_drift_report.main(
                [
                    "post-comment",
                    "--repo",
                    REPO,
                    "--issue",
                    "178",
                    "--report-file",
                    str(tmp / "missing.md"),
                    "--dry-run",
                    "maybe",
                ]
            ),
        ),
    ],
)
def test_workflow_cli_operator_errors_fail_loudly(
    label: str, call: Any, tmp_path: Path
) -> None:
    _ = label
    assert call(tmp_path) == 1


def test_verify_ruleset_sync_decodes_base_ref_fixture_like_github_api() -> None:
    raw = b'{"rules":[]}'
    payload = {
        "encoding": "base64",
        "content": base64.b64encode(raw).decode("ascii"),
    }

    assert verify_ruleset_sync.decode_base64_content(payload) == raw.decode("utf-8")


def _write_ruleset_sot(tmp_path: Path) -> Path:
    sot_dir = tmp_path / "rulesets"
    sot_dir.mkdir()
    for filename, ruleset in {
        "main.json": _ruleset_for_id(1),
        "all-branches.json": _ruleset_for_id(2),
    }.items():
        (sot_dir / filename).write_text(json.dumps(ruleset), encoding="utf-8")
    return sot_dir


def _ruleset_for_id(ruleset_id: int) -> dict[str, Any]:
    names = {
        1: "main-protection",
        2: "all-branches-no-force-push",
    }
    return {
        "id": ruleset_id,
        "name": names[ruleset_id],
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": "script tests"}]
                },
            }
        ],
    }


def test_no_unallowlisted_gh_calls_in_workflows() -> None:
    """Deterministic gate: any new direct gh CLI call in a workflow run: block must have an
    allowlist entry in scan_workflow_gh_calls.ALLOWLIST_ENTRIES before it lands.

    Refs #911.
    """
    violations = scan_workflow_gh_calls.find_violations()
    assert violations == [], (
        "Unallowlisted gh CLI calls found in .github/workflows/:\n"
        + "\n".join(
            f"  {v.workflow} / {v.job} / {v.step!r}: {v.fragment!r}"
            for v in violations
        )
        + "\n\nMigrate the gh call to a tested Python script, or add an allowlist entry "
        "with rationale in scripts/scan_workflow_gh_calls.py ALLOWLIST_ENTRIES."
    )


def test_gate_doc_graph_pr_matches_workflow_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the env shape used by validate-doc-graph.yml.

    The workflow invokes `uv run python scripts/gate_doc_graph_pr.py` with
    BASE_REF and PR_BODY as environment variables (no subcommand). The graph
    file is expected at the repository default path; the contract test
    exercises the missing-graph fail-open path so no real git subprocess runs.
    Refs #1754.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BASE_REF", "origin/main")
    monkeypatch.setenv("PR_BODY", "")
    # No graph file in tmp_path -> gate returns 0 (fail-open, missing graph).
    result = gate_doc_graph_pr.main([])
    assert result == 0


def test_doc_graph_viz_all_doc_matches_workflow_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the ``all-doc`` subcommand invocation from post-merge.yml.

    The workflow calls `uv run python scripts/doc_graph_viz.py all-doc` with
    no additional arguments; the default graph path and output path are used.
    The contract test uses tmp_path so no real graph file is required and no
    output is written to docs/generated/. Refs #1754.
    """
    monkeypatch.chdir(tmp_path)
    # No graph file present -> viz returns 1 (missing graph).
    result = doc_graph_viz.main(["all-doc"])
    assert result == 1


def test_codebase_maturity_summary_summary_matches_workflow_args(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Mirror the ``summary`` invocation from post-merge.yml.

    The maturity-summary job calls
    ``uv run python scripts/codebase_maturity_summary.py summary`` and
    redirects stdout to ``$GITHUB_STEP_SUMMARY``; the script takes no extra
    arguments (``--repo-root`` defaults to ``.``). Exercise the flag-free
    subcommand against an empty tmp tree so no real repo scan is needed; the
    contract is the argv shape and the Markdown-on-stdout behaviour. Refs #1955.
    """
    rc = codebase_maturity_summary.main(["summary", "--repo-root", str(tmp_path)])
    assert rc == 0
    assert "# Codebase maturity and scale" in capsys.readouterr().out


def test_preflight_coverage_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the argv shape used by verify-agents.yml coverage job.

    The workflow invokes:
        uv run python scripts/preflight_coverage.py --base-ref "$BASE_REF"
    where BASE_REF=origin/<github.base_ref>. The contract test exercises the
    no-changed-scripts exit-0 path so no real pytest --cov run is triggered.
    Refs #1800.
    """
    monkeypatch.setattr(preflight_coverage, "changed_scripts", lambda *a, **kw: [])
    assert preflight_coverage.main(["--base-ref", "origin/main"]) == 0
