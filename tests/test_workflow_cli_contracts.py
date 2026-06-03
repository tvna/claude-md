"""CLI contract tests for scripts invoked directly by GitHub workflows.

These tests pin the argv/env/file shapes used by ``.github/workflows`` so
script-level unit tests cannot pass while an Actions invocation drifts.

Drift guard (issue #193):

* ``_iter_workflow_invocations()`` parses every workflow YAML
  structurally with ``yaml.safe_load`` and walks
  ``jobs.<job>.steps[*].run``. Each ``python3 scripts/foo.py bar`` or
  ``uv run python scripts/foo.py bar`` invocation -- including command
  substitutions like ``$(python3 scripts/uv_pin.py read)`` -- is
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
import backup_archive
import body_policy
import branch_cleanup
import ci_budget_issue
import coverage_failure_issue
import dependabot_automerge
import dependabot_labels
import devcontainer_pin_pr
import github_paginate
import issue_link
import labels_apply
import nixpkgs_cooldown
import post_issue_comment
import pr_upsert
import pytest
import ruleset_drift
import rulesets_apply
import scan_allowlist_rationale
import scan_apm_portability
import scan_compile_from_source
import scan_design_philosophy_drift
import scan_devcontainer_tool_drift
import scan_docs_inventory
import scan_flake_pin_drift
import scan_hook_coverage_drift
import scan_input_contract_drift
import scan_maintainability_metrics
import scan_markdown_links
import scan_non_ascii
import scan_preflight_drift
import scan_provisioning_hook_serial
import scan_quality_standard_drift
import scan_retro_followup_drift
import scan_secret_runbooks
import scan_secrets
import scan_test_presence_drift
import scan_workflow_action_pins
import scan_workflow_gh_calls
import scan_workflow_injection
import scan_workflow_pip
import security_drift_report
import skill_quality_gate
import threat_intel_triage
import title_policy
import update_devcontainer_image_pins
import uv_download_checksum
import uv_pin
import validate_json_syntax
import verify_apm_checksums
import verify_dependabot_author
import verify_linked_issue_titles
import verify_readme_translation
import verify_required_check_contexts
import verify_ruleset_sync
import verify_security_control_floor
import verify_shard_coverage
import verify_test_shard_markers
import workflow_diagram
import yaml

pytestmark = pytest.mark.shard_ci_ops
REPO = "owner/repo"

_WORKFLOWS_DIR = Path(".github/workflows")
# Composite actions invoke scripts from their own ``runs.steps`` -- those calls
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
# ``_iter_workflow_invocations`` observes -- the two drift tests below
# enforce that in both directions.
CONTRACT_REGISTRY: dict[tuple[str, str | None], str] = {
    ("analyze_ci_timings.py", None): "test_analyze_ci_timings_matches_workflow_args",
    ("ci_budget_issue.py", "run"): "test_ci_budget_issue_run_matches_workflow_args",
    ("attack_review_reminder.py", "assemble"): "test_attack_review_reminder_assemble_matches_workflow_args",
    ("backup_archive.py", "build"): "test_backup_archive_build_matches_workflow_args",
    ("github_paginate.py", "fetch-run-jobs"): "test_github_paginate_fetch_run_jobs_matches_workflow_args",
    ("validate_json_syntax.py", "verify"): "test_validate_json_syntax_verify_matches_workflow_args",
    ("auto_retro.py", "decision-tree-doc"): "test_auto_retro_decision_tree_doc_matches_workflow_args",
    ("auto_retro.py", "triage-report"): "test_auto_retro_triage_report_matches_workflow_env",
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
    ("dependabot_automerge.py", "audit"): "test_dependabot_automerge_audit_matches_workflow_files",
    ("dependabot_automerge.py", "list-files"): "test_dependabot_list_files_matches_workflow_args",
    ("dependabot_automerge.py", "request-automerge"): "test_dependabot_request_automerge_matches_workflow_args",
    ("dependabot_labels.py", "verify"): "test_dependabot_labels_verify_matches_workflow_paths",
    ("issue_link.py", "verify"): "test_issue_link_verify_matches_workflow_body_file_and_author",
    ("labels_apply.py", "$COMMAND"): "test_labels_apply_validate_and_plan_match_workflow_args",
    ("labels_apply.py", "plan"): "test_labels_apply_validate_and_plan_match_workflow_args",
    ("labels_apply.py", "validate"): "test_labels_apply_validate_and_plan_match_workflow_args",
    ("nixpkgs_cooldown.py", "verify"): "test_nixpkgs_cooldown_verify_matches_workflow_args",
    ("ruleset_drift.py", "detect"): "test_ruleset_drift_detect_and_file_issue_match_workflow_args",
    ("ruleset_drift.py", "file-sot-issue"): "test_ruleset_drift_detect_and_file_issue_match_workflow_args",
    ("ruleset_drift.py", "file-unknown-issue"): "test_ruleset_drift_detect_and_file_issue_match_workflow_args",
    ("rulesets_apply.py", "$MODE"): "test_rulesets_apply_plan_and_auto_delete_match_workflow_args",
    ("rulesets_apply.py", "auto-delete"): "test_rulesets_apply_plan_and_auto_delete_match_workflow_args",
    ("scan_allowlist_rationale.py", "verify"): "test_scan_allowlist_rationale_verify_matches_workflow_args",
    ("scan_apm_portability.py", "verify"): "test_scan_apm_portability_verify_matches_workflow_paths",
    ("scan_design_philosophy_drift.py", "verify"): "test_scan_design_philosophy_drift_verify_matches_workflow_paths",
    ("scan_compile_from_source.py", "verify"): "test_scan_compile_from_source_verify_matches_workflow_args",
    ("scan_devcontainer_tool_drift.py", "verify"): "test_scan_devcontainer_tool_drift_verify_matches_workflow_args",
    ("scan_docs_inventory.py", "verify"): "test_scan_docs_inventory_verify_matches_workflow_args",
    ("scan_flake_pin_drift.py", "verify"): "test_scan_flake_pin_drift_verify_matches_workflow_args",
    ("scan_markdown_links.py", "verify"): "test_scan_markdown_links_verify_matches_workflow_args",
    ("scan_maintainability_metrics.py", "verify"): "test_scan_maintainability_metrics_verify_matches_workflow_args",
    ("scan_non_ascii.py", "run"): "test_scan_non_ascii_run_matches_workflow_env",
    ("scan_hook_coverage_drift.py", "verify"): "test_scan_hook_coverage_drift_verify_matches_workflow_args",
    ("scan_input_contract_drift.py", "verify"): "test_scan_input_contract_drift_verify_matches_workflow_args",
    ("scan_preflight_drift.py", "verify"): "test_scan_preflight_drift_verify_matches_workflow_args",
    ("scan_provisioning_hook_serial.py", "verify"): "test_scan_provisioning_hook_serial_verify_matches_workflow_args",
    ("scan_quality_standard_drift.py", "verify"): "test_scan_quality_standard_drift_verify_matches_workflow_args",
    ("scan_retro_followup_drift.py", "run"): "test_scan_retro_followup_drift_run_matches_workflow_env",
    ("scan_secret_runbooks.py", "verify"): "test_scan_secret_runbooks_verify_matches_workflow_args",
    ("scan_secrets.py", "verify"): "test_scan_secrets_verify_matches_workflow_args",
    ("scan_test_presence_drift.py", "verify"): "test_scan_test_presence_drift_verify_matches_workflow_args",
    ("scan_workflow_action_pins.py", "verify"): "test_scan_workflow_action_pins_verify_matches_workflow_args",
    ("scan_workflow_gh_calls.py", "verify"): "test_scan_workflow_gh_calls_verify_matches_workflow_args",
    ("scan_workflow_injection.py", "verify"): "test_scan_workflow_injection_verify_matches_workflow_args",
    ("scan_workflow_pip.py", "verify"): "test_scan_workflow_pip_verify_matches_workflow_args",
    ("security_drift_report.py", "aggregate"): "test_security_drift_report_aggregate_and_post_comment_match_workflow_args",
    ("security_drift_report.py", "post-comment"): "test_security_drift_report_aggregate_and_post_comment_match_workflow_args",
    ("security_drift_report.py", "file-family-issues"): "test_security_drift_report_file_family_issues_matches_workflow_args",
    ("skill_quality_gate.py", "verify"): "test_skill_quality_gate_verify_matches_workflow_args",
    ("threat_intel_triage.py", "apply-labels"): "test_threat_intel_apply_labels_matches_workflow_args",
    ("threat_intel_triage.py", "scan"): "test_threat_intel_scan_matches_workflow_args",
    ("title_policy.py", "verify"): "test_title_policy_verify_matches_workflow_kind_env",
    ("update_devcontainer_image_pins.py", "$GITHUB_SHA"): "test_update_devcontainer_image_pins_matches_workflow_args",
    ("uv_download_checksum.py", "verify"): "test_uv_download_checksum_verify_matches_action_args",
    ("uv_pin.py", "drift"): "test_uv_pin_workflow_subcommands_match_ci_usage",
    ("uv_pin.py", "read"): "test_uv_pin_workflow_subcommands_match_ci_usage",
    ("uv_pin.py", "stale"): "test_uv_pin_workflow_subcommands_match_ci_usage",
    ("verify_apm_checksums.py", "verify"): "test_verify_apm_checksums_matches_workflow_args",
    ("verify_dependabot_author.py", "verify"): "test_verify_dependabot_author_verify_matches_workflow_args",
    ("verify_linked_issue_titles.py", "verify"): "test_verify_linked_issue_titles_verify_matches_workflow_args",
    ("verify_readme_translation.py", "verify"): "test_verify_readme_translation_matches_workflow_args",
    ("verify_required_check_contexts.py", "verify"): "test_verify_required_check_contexts_matches_workflow_args",
    ("verify_ruleset_sync.py", "verify"): "test_verify_ruleset_sync_matches_workflow_args",
    ("verify_security_control_floor.py", None): "test_verify_security_control_floor_matches_workflow_args",
    ("github_paginate.py", "fetch"): "test_github_paginate_fetch_matches_workflow_args",
    ("github_paginate.py", "get"): "test_github_paginate_get_matches_workflow_args",
    ("post_issue_comment.py", "create"): "test_post_issue_comment_create_matches_workflow_args",
    ("pr_upsert.py", "upsert"): "test_pr_upsert_matches_workflow_args",
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
    the inventory -- structured walk is preferred but cannot be the only path.
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


def test_auto_retro_decision_tree_doc_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the default-output shape used by the generated-doc workflow."""
    monkeypatch.chdir(tmp_path)
    output = Path("docs/generated/scripts/auto-retro-decision-tree.md")

    assert auto_retro.main(["decision-tree-doc"]) == 0

    assert output.read_text(encoding="utf-8") == (
        auto_retro.render_decision_tree_markdown()
    )


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


def test_workflow_diagram_doc_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the default-output shape used by the generate-docs workflow."""
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


def test_ruleset_drift_detect_and_file_issue_match_workflow_args(
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
            str(tmp_path / "drift-sot.md"),
            "--unknown-body-file",
            str(tmp_path / "drift-unknown.md"),
        ]
    ) == 0
    assert ruleset_drift.main(
        [
            "file-sot-issue",
            "--repo",
            REPO,
            "--run-date",
            "2026-05-24",
            "--body-file",
            str(tmp_path / "drift-sot.md"),
        ]
    ) == 0
    assert calls[-1]["repo"] == REPO
    assert calls[-1]["title"].startswith("fix(ruleset-drift): SoT vs live drift")


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

    def fake_open_or_update(
        context: coverage_failure_issue.CoverageFailureContext,
        *,
        runner=coverage_failure_issue.subprocess.run,
    ) -> str:
        calls.append(context)
        return "created"

    monkeypatch.setattr(coverage_failure_issue, "open_or_update_issue", fake_open_or_update)

    assert coverage_failure_issue.main(["run"]) == 0
    assert calls[0] == coverage_failure_issue.CoverageFailureContext(
        repo=REPO,
        run_url="https://github.com/owner/repo/actions/runs/123/attempts/2",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="123",
        run_attempt="2",
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
            {"README.md", "README.ja.md", "README.zh.md"}
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


def test_scan_workflow_injection_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert no untrusted context in workflow run blocks`` step
    in ``.github/workflows/verify-agents.yml``. Refs #1129."""
    assert scan_workflow_injection.main(["verify"]) == 0


def test_scan_secrets_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert no hardcoded secrets in tracked non-Python files``
    step in ``.github/workflows/verify-agents.yml``. Refs #1129."""
    assert scan_secrets.main(["verify"]) == 0


def test_scan_secret_runbooks_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert workflow secrets have concrete runbooks`` step."""
    assert scan_secret_runbooks.main(["verify"]) == 0


def test_scan_input_contract_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify workflow-script input contracts`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1087."""
    assert scan_input_contract_drift.main(["verify"]) == 0


def test_scan_quality_standard_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify quality-standard enforcement map`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1089."""
    assert scan_quality_standard_drift.main(["verify"]) == 0


def test_scan_test_presence_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify scripts ship required tests`` step in
    ``.github/workflows/verify-agents.yml``. Refs #1088."""
    assert scan_test_presence_drift.main(["verify"]) == 0


def test_scan_markdown_links_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert local Markdown links resolve`` step."""
    assert scan_markdown_links.main(["verify"]) == 0


def test_scan_compile_from_source_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify no tool is compiled from source on the CI
    surface`` step in ``.github/workflows/verify-agents.yml``."""
    assert scan_compile_from_source.main(["verify"]) == 0


def test_scan_devcontainer_tool_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify devcontainer provisions gate-required tools``
    step in ``.github/workflows/verify-agents.yml``."""
    assert scan_devcontainer_tool_drift.main(["verify"]) == 0


def test_scan_allowlist_rationale_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify devcontainer egress hosts carry a triage
    rationale`` step in ``.github/workflows/verify-agents.yml``. Refs #1170."""
    assert scan_allowlist_rationale.main(["verify"]) == 0


def test_scan_flake_pin_drift_verify_matches_workflow_args() -> None:
    """Mirrors the ``Verify flake.nix is the single source of truth for pinned
    hashes`` step in ``.github/workflows/verify-agents.yml``."""
    assert scan_flake_pin_drift.main(["verify"]) == 0


def test_scan_docs_inventory_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert docs index and lane placement`` step."""
    assert scan_docs_inventory.main(["verify"]) == 0


def test_scan_maintainability_metrics_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert script maintainability metrics`` step in
    ``.github/workflows/verify-agents.yml``."""
    assert scan_maintainability_metrics.main(["verify", "--repo-root", "."]) == 0


def test_scan_workflow_pip_verify_matches_workflow_args() -> None:
    """Mirrors the ``Assert workflows install Python deps via uv only``
    step in ``.github/workflows/verify-agents.yml``."""
    assert scan_workflow_pip.main(["verify", "--repo-root", "."]) == 0


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
            "--uv-stale-rc",
            "0",
            "--uv-stale-output",
            str(uv_stale),
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
    --run-date D --families <csv> --dry-run <bool>`` where ``<csv>`` is the
    ``drift_families`` output of the aggregate step. Exercise the dry-run path
    (no token, no network) across every target family so the contract pins the
    accepted flag set and the family allowlist.
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
            "labels,apm-instructions,uv-pin-literal",
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
            "type:fix",
            "--ghsa-live",
            "--github-output",
            str(tmp_path / "output"),
            "--summary-file",
            str(tmp_path / "summary.md"),
        ]
    ) == 0


def test_threat_intel_apply_labels_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply-labels subcommand accepts the --add-labels/--remove-labels args used by the workflow."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("NUMBER", "42")
    monkeypatch.setattr(threat_intel_triage, "_apply_labels", lambda **kw: 0)

    assert threat_intel_triage.main(["apply-labels", "--add-labels", "threat:intel-needed"]) == 0
    assert threat_intel_triage.main(["apply-labels", "--remove-labels", "threat:response-needed"]) == 0
    assert threat_intel_triage.main(["apply-labels"]) == 0


def test_pr_upsert_find_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """find subcommand accepts --head used by publish-devcontainer-images.yml. Refs #911."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setattr(pr_upsert, "_list_open_prs", lambda **kw: [{"number": 55}])
    assert pr_upsert.main(["find", "--head", "codex/devcontainer-image-pins-abc123"]) == 0


def test_pr_upsert_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """upsert subcommand accepts the --head/--base/--title/--body-file args used by generate-agents.yml and post-merge.yml."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")
    body_file = tmp_path / "pr-body.md"
    body_file.write_text("body content", encoding="utf-8")
    monkeypatch.setattr(pr_upsert, "_upsert_pr", lambda **kw: ("created", 99))

    assert pr_upsert.main([
        "upsert",
        "--head", "chore/regenerate-agent-instructions",
        "--base", "main",
        "--title", "chore: regenerate agent instructions (#18)",
        "--body-file", str(body_file),
    ]) == 0


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


def test_validate_json_syntax_verify_matches_workflow_args() -> None:
    """verify subcommand accepts the repeated --file args used by the
    ``Validate ruleset JSON syntax`` steps in apply-rulesets.yml and
    weekly-maintenance.yml."""
    assert validate_json_syntax.main([
        "verify",
        "--file", ".github/rulesets/main.json",
        "--file", ".github/rulesets/all-branches.json",
    ]) == 0


def test_pr_label_mutation_jobs_have_pull_request_write() -> None:
    offenders: list[str] = []
    for workflow in sorted(_WORKFLOWS_DIR.glob("*.yml")):
        raw = workflow.read_text(encoding="utf-8")
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError:
            continue
        if not isinstance(document, dict) or "pull_request_target" not in raw:
            continue
        jobs = document.get("jobs")
        if not isinstance(jobs, dict):
            continue
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps")
            if not isinstance(steps, list):
                continue
            mutates_pr_labels = False
            for step in steps:
                if not isinstance(step, dict):
                    continue
                run_text = step.get("run")
                if not isinstance(run_text, str):
                    continue
                if "threat_intel_triage.py" in run_text and "apply-labels" in run_text:
                    mutates_pr_labels = True
            if not mutates_pr_labels:
                continue
            permissions = job.get("permissions")
            if not isinstance(permissions, dict):
                offenders.append(f"{workflow}:{job_name} missing permissions block")
                continue
            if permissions.get("pull-requests") != "write":
                offenders.append(
                    f"{workflow}:{job_name} must declare pull-requests: write"
                )

    assert offenders == []


def test_title_policy_verify_matches_workflow_kind_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    assert "DEVCONTAINER_PIN_PR_TOKEN" in raw

    open_pr = next(
        step for step in update_pins["steps"] if step.get("name") == "Open pin update PR"
    )
    # Thin orchestration: GH_TOKEN comes from the environment secret, REPO from
    # the workflow context (both consumed by scripts/devcontainer_pin_pr.py).
    assert open_pr["env"] == {
        "GH_TOKEN": "${{ secrets.DEVCONTAINER_PIN_PR_TOKEN }}",
        "REPO": "${{ github.repository }}",
    }
    assert "scripts/devcontainer_pin_pr.py open" in open_pr["run"]
    assert "Refs #696" in open_pr["run"]


def test_devcontainer_pin_pr_open_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """open subcommand accepts the args used by the Open pin update PR step.

    The branch/PR decision flow and auto-merge request are exercised by
    tests/test_devcontainer_pin_pr.py; here we pin the workflow argv shape.
    Refs #696, #911.
    """
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", REPO)
    template = tmp_path / "tmpl.md"
    template.write_text("Pinned to __GITHUB_SHA__.\n", encoding="utf-8")
    # Branch absent -> create branch + upsert; mock git and the GitHub API helpers.
    monkeypatch.setattr(
        devcontainer_pin_pr,
        "run_git",
        lambda args, **kw: __import__("subprocess").CompletedProcess(
            ["git", *args], 1 if args[0] == "diff" else 2 if args[0] == "ls-remote" else 0
        ),
    )
    monkeypatch.setattr(devcontainer_pin_pr, "_upsert_pr", lambda **kw: ("created", 42))
    monkeypatch.setattr(devcontainer_pin_pr, "_enable_auto_merge", lambda **kw: None)
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
    with no subcommand and no flags -- it relies on the script defaulting
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
