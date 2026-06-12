# Script trigger reverse-map

This file is generated from the repository launch surfaces by `python3 scripts/script_trigger_map.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540, #1543) -- update the source instead.

Detection is string-match based:

- Fact: only literal `scripts/<name>.py` references in `.github/workflows/*.yml` `run:` steps, `.pre-commit-config.yaml` hook entries, `scripts/preflight_all.py` `Step` argv, and `scripts/agent_hooks_source.json` commands are matched.
- Speculation: a script launched through a dynamically computed command is not matched and may appear as a dead-script candidate even though it is reachable.
- Speculation: a helper module imported by another script (e.g. `_git.py`) is reachable via import, not via these launch sources, so it is expected in the unreferenced list; cross-reference the dependency graph (#1543).

## Trigger map

| Script | Trigger kind | Location |
| --- | --- | --- |
| `analyze_ci_timings.py` | workflow | `weekly-maintenance.yml (measure-timings)` |
| `attack_review_reminder.py` | workflow | `monthly-maintenance.yml (remind)` |
| `auto_retro.py` | preflight | `auto_retro_decision_tree_compat` |
| `auto_retro.py` | workflow | `daily-maintenance.yml (rescan)` |
| `auto_retro.py` | workflow | `daily-maintenance.yml (scan-and-close)` |
| `auto_retro.py` | workflow | `post-merge.yml (open-retro)` |
| `auto_retro.py` | workflow | `post-merge.yml (triage-report)` |
| `auto_retro.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `backup_archive.py` | workflow | `backup-non-ascii-originals.yml (backup)` |
| `block_sensitive_reads.py` | agent-hook | `claude:PreToolUse` |
| `block_sensitive_reads.py` | agent-hook | `codex:PreToolUse` |
| `body_policy.py` | workflow | `verify-github-content.yml (gate)` |
| `body_policy.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `bot_pr_automerge.py` | workflow | `tvna-bot-automerge.yml (merge)` |
| `branch_cleanup.py` | workflow | `weekly-maintenance.yml (branch-cleanup)` |
| `check_hooks_path.py` | agent-hook | `claude:SessionStart` |
| `check_hooks_path.py` | agent-hook | `codex:SessionStart` |
| `check_pr_mergeability.py` | agent-hook | `claude:PostToolUse` |
| `check_pr_mergeability.py` | agent-hook | `claude:SessionStart` |
| `check_pr_mergeability.py` | agent-hook | `codex:PostToolUse` |
| `check_pr_mergeability.py` | agent-hook | `codex:SessionStart` |
| `check_session_branch.py` | agent-hook | `claude:SessionStart` |
| `check_session_branch.py` | agent-hook | `codex:SessionStart` |
| `ci_budget_issue.py` | workflow | `weekly-maintenance.yml (measure-timings)` |
| `ci_early_status_probe.py` | agent-hook | `codex:PostToolUse` |
| `coverage_failure_issue.py` | workflow | `post-merge.yml (coverage-failure-issue)` |
| `dependabot_automerge.py` | workflow | `dependabot-automerge.yml (audit)` |
| `dependabot_labels.py` | preflight | `dependabot_labels` |
| `dependabot_labels.py` | workflow | `verify-pr.yml (verify-dependabot-labels)` |
| `devcontainer_pin_pr.py` | workflow | `devcontainer-pin-refresh.yml (refresh)` |
| `devcontainer_pin_pr.py` | workflow | `publish-devcontainer-images.yml (update-pins)` |
| `devcontainer_pin_pr.py` | workflow | `weekly-maintenance.yml (flake-pin-refresh)` |
| `flake_pin.py` | workflow | `weekly-maintenance.yml (flake-pin-refresh)` |
| `flake_pin_latest.py` | workflow | `weekly-maintenance.yml (flake-pin-refresh)` |
| `gate_cache_regime_advisor.py` | agent-hook | `claude:Stop` |
| `gate_decision_handoff_askuserquestion.py` | agent-hook | `claude:Stop` |
| `gate_generated_scripts_manual_edit.py` | preflight | `gate_generated_scripts_manual_edit` |
| `gate_generated_scripts_manual_edit.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `gate_gh_cli.py` | agent-hook | `claude:PreToolUse` |
| `gate_gh_cli.py` | agent-hook | `codex:PreToolUse` |
| `gate_handoff_retro_survey_askuserquestion.py` | agent-hook | `claude:Stop` |
| `gate_irreversible_bash.py` | agent-hook | `claude:PreToolUse` |
| `gate_irreversible_bash.py` | agent-hook | `codex:PreToolUse` |
| `gate_issue_classification_labels.py` | agent-hook | `claude:PreToolUse` |
| `gate_issue_classification_labels.py` | agent-hook | `codex:PreToolUse` |
| `gate_issue_close_comment.py` | agent-hook | `claude:PostToolUse` |
| `gate_issue_close_comment.py` | agent-hook | `claude:PreToolUse` |
| `gate_issue_close_comment.py` | agent-hook | `codex:PostToolUse` |
| `gate_issue_close_comment.py` | agent-hook | `codex:PreToolUse` |
| `gate_mcp_github_uncovered.py` | agent-hook | `claude:PreToolUse` |
| `gate_mcp_github_uncovered.py` | agent-hook | `codex:PreToolUse` |
| `gate_merge_safety.py` | agent-hook | `claude:PreToolUse` |
| `gate_merge_safety.py` | agent-hook | `codex:PreToolUse` |
| `gate_reserved_retro_scope.py` | agent-hook | `claude:PreToolUse` |
| `gate_reserved_retro_scope.py` | agent-hook | `codex:PreToolUse` |
| `gate_update_pr_branch.py` | agent-hook | `claude:PreToolUse` |
| `gate_update_pr_branch.py` | agent-hook | `codex:PreToolUse` |
| `gen_agent_hooks.py` | pre-commit | `gen-agent-hooks` |
| `gen_mcp_json.py` | agent-hook | `claude:SessionStart` |
| `generate_devcontainer_arch_overlays.py` | preflight | `generate_devcontainer_arch_overlays` |
| `github_paginate.py` | workflow | `backup-non-ascii-originals.yml (backup)` |
| `github_paginate.py` | workflow | `weekly-maintenance.yml (branch-cleanup)` |
| `github_paginate.py` | workflow | `weekly-maintenance.yml (measure-timings)` |
| `issue_anchors.py` | workflow | `devcontainer-pin-refresh.yml (refresh)` |
| `issue_anchors.py` | workflow | `generate-agents.yml (generate)` |
| `issue_anchors.py` | workflow | `monthly-maintenance.yml (remind)` |
| `issue_anchors.py` | workflow | `post-merge.yml (decision-tree)` |
| `issue_anchors.py` | workflow | `publish-devcontainer-images.yml (update-pins)` |
| `issue_anchors.py` | workflow | `weekly-maintenance.yml (dependency-threat-triage)` |
| `issue_anchors.py` | workflow | `weekly-maintenance.yml (flake-pin-refresh)` |
| `issue_anchors.py` | workflow | `weekly-maintenance.yml (security-control-drift)` |
| `issue_closure_fast_path.py` | agent-hook | `claude:PreToolUse` |
| `issue_closure_fast_path.py` | agent-hook | `codex:PreToolUse` |
| `issue_link.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `labels_apply.py` | workflow | `apply-labels.yml (apply)` |
| `labels_apply.py` | workflow | `weekly-maintenance.yml (security-control-drift)` |
| `measure_devcontainer_startup.py` | workflow | `measure-devcontainer-startup.yml (measure)` |
| `measure_tool_overlap.py` | workflow | `measure-tool-overlap.yml (measure)` |
| `nixpkgs_cooldown.py` | preflight | `nixpkgs_cooldown` |
| `nixpkgs_cooldown.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `plan_approval_gate.py` | agent-hook | `claude:PostToolUse` |
| `plan_language_context.py` | agent-hook | `claude:SessionStart` |
| `plan_language_context.py` | agent-hook | `codex:SessionStart` |
| `post_issue_comment.py` | workflow | `backup-non-ascii-originals.yml (backup)` |
| `post_issue_comment.py` | workflow | `monthly-maintenance.yml (remind)` |
| `post_issue_comment.py` | workflow | `weekly-maintenance.yml (measure-timings)` |
| `post_merge_new_session_prompt.py` | agent-hook | `claude:PostToolUse` |
| `post_merge_new_session_prompt.py` | agent-hook | `codex:PostToolUse` |
| `post_merge_retro_append.py` | agent-hook | `claude:PostToolUse` |
| `post_merge_retro_append.py` | agent-hook | `codex:PostToolUse` |
| `post_pr_create_body_fix.py` | agent-hook | `claude:PostToolUse` |
| `post_pr_create_body_fix.py` | agent-hook | `codex:PostToolUse` |
| `post_pr_create_ci_monitor.py` | agent-hook | `claude:PostToolUse` |
| `post_pr_create_ci_monitor.py` | agent-hook | `codex:PostToolUse` |
| `pr_body_close_keyword_gate.py` | agent-hook | `claude:PreToolUse` |
| `pr_body_close_keyword_gate.py` | agent-hook | `codex:PreToolUse` |
| `pr_upsert.py` | workflow | `generate-agents.yml (generate)` |
| `pr_upsert.py` | workflow | `post-merge.yml (decision-tree)` |
| `preflight_branch_base.py` | agent-hook | `claude:PreToolUse` |
| `preflight_branch_base.py` | agent-hook | `codex:PreToolUse` |
| `preflight_branch_base.py` | pre-commit | `preflight-branch-base` |
| `preflight_branch_base.py` | preflight | `preflight_branch_base` |
| `preflight_codex_github_footer.py` | agent-hook | `codex:PreToolUse` |
| `preflight_commit_session_branch.py` | agent-hook | `claude:PreToolUse` |
| `preflight_commit_session_branch.py` | agent-hook | `codex:PreToolUse` |
| `preflight_coverage.py` | agent-hook | `claude:PreToolUse` |
| `preflight_coverage.py` | agent-hook | `codex:PreToolUse` |
| `preflight_coverage.py` | pre-commit | `preflight-coverage` |
| `preflight_github_secrets.py` | agent-hook | `claude:PreToolUse` |
| `preflight_github_secrets.py` | agent-hook | `codex:PreToolUse` |
| `preflight_hook_event_keys.py` | pre-commit | `preflight-hook-event-keys` |
| `preflight_main_freshness.py` | agent-hook | `claude:PreToolUse` |
| `preflight_main_freshness.py` | agent-hook | `codex:PreToolUse` |
| `preflight_non_ascii.py` | agent-hook | `claude:PreToolUse` |
| `preflight_non_ascii.py` | agent-hook | `codex:PreToolUse` |
| `preflight_pr_body_required_sections.py` | agent-hook | `claude:PreToolUse` |
| `preflight_pr_body_required_sections.py` | agent-hook | `codex:PreToolUse` |
| `preflight_pr_template_shape.py` | agent-hook | `claude:PreToolUse` |
| `preflight_pr_template_shape.py` | agent-hook | `codex:PreToolUse` |
| `preflight_push_base.py` | agent-hook | `claude:PreToolUse` |
| `preflight_push_base.py` | agent-hook | `codex:PreToolUse` |
| `preflight_push_nonempty.py` | agent-hook | `claude:PreToolUse` |
| `preflight_push_nonempty.py` | agent-hook | `codex:PreToolUse` |
| `preflight_push_session_branch.py` | agent-hook | `claude:PreToolUse` |
| `preflight_push_session_branch.py` | agent-hook | `codex:PreToolUse` |
| `preflight_session_base_freshness.py` | agent-hook | `claude:PreToolUse` |
| `preflight_session_base_freshness.py` | agent-hook | `claude:SessionStart` |
| `preflight_session_base_freshness.py` | agent-hook | `codex:PreToolUse` |
| `preflight_session_base_freshness.py` | agent-hook | `codex:SessionStart` |
| `preflight_title_policy.py` | agent-hook | `claude:PreToolUse` |
| `preflight_title_policy.py` | agent-hook | `codex:PreToolUse` |
| `preflight_uv_version.py` | preflight | `preflight_uv_version` |
| `preflight_uv_version.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `prompt_context7_gate.py` | agent-hook | `claude:UserPromptSubmit` |
| `prompt_context7_gate.py` | agent-hook | `codex:UserPromptSubmit` |
| `prune_devcontainer_images.py` | workflow | `monthly-maintenance.yml (prune-devcontainer-images)` |
| `ruleset_drift.py` | workflow | `weekly-maintenance.yml (ruleset-drift)` |
| `ruleset_drift.py` | workflow | `weekly-maintenance.yml (security-control-drift)` |
| `rulesets_apply.py` | workflow | `apply-rulesets.yml (apply)` |
| `rulesets_apply.py` | workflow | `weekly-maintenance.yml (security-control-drift)` |
| `scan_allowlist_parser_parity.py` | preflight | `scan_allowlist_parser_parity` |
| `scan_allowlist_parser_parity.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_allowlist_rationale.py` | preflight | `scan_allowlist_rationale` |
| `scan_allowlist_rationale.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_apm_lock_drift.py` | preflight | `scan_apm_lock_drift` |
| `scan_apm_lock_drift.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `scan_apm_portability.py` | preflight | `scan_apm_portability` |
| `scan_apm_portability.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `scan_compile_from_source.py` | preflight | `scan_compile_from_source` |
| `scan_compile_from_source.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_design_philosophy_drift.py` | preflight | `scan_design_philosophy_drift` |
| `scan_design_philosophy_drift.py` | preflight | `scan_design_philosophy_drift_coupling` |
| `scan_design_philosophy_drift.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `scan_design_philosophy_drift.py` | workflow | `verify-pr.yml (verify-design-philosophy)` |
| `scan_devcontainer_tool_drift.py` | preflight | `scan_devcontainer_tool_drift` |
| `scan_devcontainer_tool_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_doc_workflow_refs.py` | preflight | `scan_doc_workflow_refs` |
| `scan_doc_workflow_refs.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_docs_inventory.py` | pre-commit | `scan-docs-inventory` |
| `scan_docs_inventory.py` | preflight | `scan_docs_inventory` |
| `scan_docs_inventory.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_flake_pin_drift.py` | preflight | `scan_flake_pin_drift` |
| `scan_flake_pin_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_hook_coverage_drift.py` | preflight | `scan_hook_coverage_drift` |
| `scan_hook_coverage_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_input_contract_drift.py` | preflight | `scan_input_contract_drift` |
| `scan_input_contract_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_issue_anchor_drift.py` | preflight | `scan_issue_anchor_drift` |
| `scan_issue_anchor_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_maintainability_metrics.py` | preflight | `scan_maintainability_metrics` |
| `scan_maintainability_metrics.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_markdown_links.py` | preflight | `scan_markdown_links` |
| `scan_markdown_links.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_mermaid_syntax.py` | pre-commit | `scan-mermaid-syntax` |
| `scan_mermaid_syntax.py` | preflight | `scan_mermaid_syntax` |
| `scan_mermaid_syntax.py` | workflow | `verify-mermaid.yml (gate)` |
| `scan_non_ascii.py` | workflow | `issue-pr-triage.yml (scan)` |
| `scan_nonexhaustive_invariant_drift.py` | preflight | `scan_nonexhaustive_invariant_drift` |
| `scan_nonexhaustive_invariant_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_preflight_drift.py` | preflight | `scan_preflight_drift` |
| `scan_preflight_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_provisioning_hook_serial.py` | preflight | `scan_provisioning_hook_serial` |
| `scan_provisioning_hook_serial.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_quality_standard_drift.py` | preflight | `scan_quality_standard_drift` |
| `scan_quality_standard_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_retro_followup_drift.py` | workflow | `daily-maintenance.yml (scan)` |
| `scan_secret_runbooks.py` | preflight | `scan_secret_runbooks` |
| `scan_secret_runbooks.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_secrets.py` | pre-commit | `scan-secrets` |
| `scan_secrets.py` | preflight | `scan_secrets` |
| `scan_secrets.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_session_path_drift.py` | preflight | `scan_session_path_drift` |
| `scan_session_path_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_test_presence_drift.py` | pre-commit | `scan-test-presence-drift` |
| `scan_test_presence_drift.py` | preflight | `scan_test_presence_drift` |
| `scan_test_presence_drift.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_workflow_action_pins.py` | preflight | `scan_workflow_action_pins` |
| `scan_workflow_action_pins.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_workflow_action_pins.py` | workflow | `weekly-maintenance.yml (dependency-freshness)` |
| `scan_workflow_gh_calls.py` | preflight | `scan_workflow_gh_calls` |
| `scan_workflow_gh_calls.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_workflow_gh_calls.py` | workflow | `weekly-maintenance.yml (dependency-freshness)` |
| `scan_workflow_injection.py` | pre-commit | `scan-workflow-injection` |
| `scan_workflow_injection.py` | preflight | `scan_workflow_injection` |
| `scan_workflow_injection.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_workflow_pip.py` | pre-commit | `scan-workflow-pip` |
| `scan_workflow_pip.py` | preflight | `scan_workflow_pip` |
| `scan_workflow_pip.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `scan_workflow_pip.py` | workflow | `weekly-maintenance.yml (dependency-freshness)` |
| `scan_workflow_unsigned_commit.py` | pre-commit | `scan-workflow-unsigned-commit` |
| `scan_workflow_unsigned_commit.py` | preflight | `scan_workflow_unsigned_commit` |
| `scan_workflow_unsigned_commit.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `script_ast_graph.py` | workflow | `post-merge.yml (decision-tree)` |
| `script_ast_graph.py` | workflow | `post-merge.yml (verify-docs-drift)` |
| `script_dependency_graph.py` | workflow | `post-merge.yml (decision-tree)` |
| `script_dependency_graph.py` | workflow | `post-merge.yml (verify-docs-drift)` |
| `script_trigger_map.py` | workflow | `post-merge.yml (decision-tree)` |
| `script_trigger_map.py` | workflow | `post-merge.yml (verify-docs-drift)` |
| `security_drift_report.py` | workflow | `weekly-maintenance.yml (security-control-drift)` |
| `session_resource_report.py` | agent-hook | `claude:PostToolUse` |
| `session_resource_report.py` | agent-hook | `codex:PostToolUse` |
| `skill_quality_gate.py` | pre-commit | `skill-quality-gate` |
| `skill_quality_gate.py` | preflight | `skill_quality_gate` |
| `skill_quality_gate.py` | workflow | `skill-quality.yml (skill-quality)` |
| `stop_new_session_handoff_prompt.py` | agent-hook | `claude:Stop` |
| `threat_intel_triage.py` | pre-commit | `threat-intel-coords` |
| `threat_intel_triage.py` | preflight | `threat_intel_coords` |
| `threat_intel_triage.py` | workflow | `weekly-maintenance.yml (dependency-threat-triage)` |
| `title_policy.py` | workflow | `verify-github-content.yml (gate)` |
| `title_policy.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `update_devcontainer_image_pins.py` | workflow | `publish-devcontainer-images.yml (update-pins)` |
| `uv_pin.py` | pre-commit | `uv-pin-drift` |
| `uv_pin.py` | preflight | `uv_pin_drift` |
| `uv_pin.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `uv_pin.py` | workflow | `weekly-maintenance.yml (dependency-freshness)` |
| `uv_pin.py` | workflow | `weekly-maintenance.yml (security-control-drift)` |
| `validate_json_syntax.py` | workflow | `apply-rulesets.yml (apply)` |
| `validate_json_syntax.py` | workflow | `weekly-maintenance.yml (ruleset-drift)` |
| `verify_apm_checksums.py` | preflight | `verify_apm_checksums` |
| `verify_apm_checksums.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `verify_dependabot_author.py` | workflow | `issue-pr-triage.yml (dependabot-author)` |
| `verify_linked_issue_titles.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `verify_readme_translation.py` | preflight | `verify_readme_translation` |
| `verify_readme_translation.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `verify_required_check_contexts.py` | preflight | `verify_required_check_contexts` |
| `verify_required_check_contexts.py` | workflow | `verify-pr.yml (verify-ruleset-sync)` |
| `verify_ruleset_sync.py` | preflight | `verify_ruleset_sync` |
| `verify_ruleset_sync.py` | workflow | `verify-pr.yml (verify-ruleset-sync)` |
| `verify_security_control_floor.py` | preflight | `verify_security_control_floor` |
| `verify_security_control_floor.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `verify_shard_coverage.py` | workflow | `verify-agents.yml (lint-scripts-pytest-gate)` |
| `verify_test_shard_markers.py` | preflight | `verify_test_shard_markers` |
| `verify_test_shard_markers.py` | workflow | `verify-agents.yml (lint-scripts-static)` |
| `verify_text_delta_section.py` | preflight | `verify_text_delta_section` |
| `verify_text_delta_section.py` | workflow | `verify-pr.yml (portable-pr-policy)` |
| `workflow_diagram.py` | preflight | `workflow_diagram_doc` |
| `workflow_diagram.py` | workflow | `post-merge.yml (decision-tree)` |
| `workflow_diagram.py` | workflow | `post-merge.yml (verify-docs-drift)` |

## Unreferenced scripts (dead script candidates)

33 script(s) are referenced by no scanned launch source (see the detection caveats above before treating one as dead):

`_allowlist.py`, `_ci_watch.py`, `_git.py`, `_github_api.py`, `_github_tool_names.py`, `_hook_runtime.py`, `_pr_commit_batch.py`, `_pr_merge.py`, `_ref_classifier.py`, `_retro_labels.py`, `_secret_patterns.py`, `_security_drift_families.py`, `_session_branches.py`, `_trusted_bots.py`, `backup_non_ascii.py`, `ccusage_pin.py`, `compare_cache_regimes.py`, `github_api.py`, `measure_prefix_tokens.py`, `mint_github_app_token.py`, `np_strategy_tracking.py`, `pr_body_builder.py`, `preflight_all.py`, `preflight_cache.py`, `preflight_pr_body.py`, `preflight_push_prek.py`, `preflight_replacement_pr.py`, `refresh_pr_branch.py`, `sanitize_history.py`, `scan_area_path_coverage.py`, `session_cost_structure.py`, `uv_download_checksum.py`, `waza_pin.py`
