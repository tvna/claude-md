#!/usr/bin/env python3
"""Step registry for :mod:`preflight_all`; the gate set CI mirrors locally.

Issue #1670 extraction: ``preflight_all.py`` had reached its 800-line
maintainability budget (scripts/scan_maintainability_metrics.py), and the
:data:`STEPS` tuple grows by one entry per gate added, so every new gate
pushed the entrypoint over budget. The data and its :class:`Step` schema
live here so the executor module stays well under budget and the budget
gate keeps protecting both files. :mod:`preflight_all` re-exports
``STEPS`` and ``Step`` so existing ``preflight_all.STEPS`` /
``preflight_all.Step`` references (scan_preflight_drift.py,
scan_devcontainer_tool_drift.py, tests) resolve unchanged.

This module is pure data plus a frozen dataclass; it imports nothing
from :mod:`preflight_all`, so the re-export creates no import cycle.

Tested by ``tests/test_preflight_steps.py`` (data invariants) and, via
the re-export, ``tests/test_preflight_all.py``. Refs #1670, #493.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    """One verification gate runnable from preflight and CI alike."""

    name: str
    argv: tuple[str, ...]
    required_env: tuple[str, ...] = ()
    # When True, missing ``required_env`` or a missing executable on PATH
    # downgrades the step from failure to warning. Reserve for gates whose
    # local prerequisites legitimately differ from CI (network tokens,
    # uv-managed toolchain on a contributor laptop).
    soft: bool = False
    # External executables that must resolve on PATH for the step to run.
    # Treated the same as ``required_env`` for skip semantics.
    required_bin: tuple[str, ...] = field(default_factory=tuple)
    # When True, the step is expensive (the full pytest suite). Heavy steps run
    # only after every cheap step has passed (fail-fast: a sub-second gate
    # failure short-circuits the ~5-min suite, refs #985) and are gated by the
    # content-addressed skip cache in ``scripts/preflight_cache.py`` so an
    # unchanged working tree skips the re-run while keeping CI coverage parity.
    heavy: bool = False


# Order matches the order CI gates fire on a typical PR run: static
# repository-shape checks first (cheap, no toolchain), then static
# workflow / ruleset shape, then the uv-managed lint / type / test
# triple, then prek. ``verify_ruleset_sync`` requires the privileged
# RULESETS_PAT secret and is soft-skipped without it.
STEPS: tuple[Step, ...] = (
    Step(
        name="scan_apm_portability",
        argv=(
            "python3",
            "scripts/scan_apm_portability.py",
            "verify",
            "--path",
            ".apm/instructions/master.instructions.md",
            "--path",
            "CLAUDE.md",
            "--path",
            "AGENTS.md",
        ),
    ),
    Step(
        name="scan_apm_ascii",
        argv=(
            "python3",
            "scripts/scan_apm_ascii.py",
            "verify",
            "--path",
            ".apm/instructions/master.instructions.md",
            "--path",
            "CLAUDE.md",
            "--path",
            "AGENTS.md",
        ),
    ),
    Step(
        name="scan_repo_em_dash",
        argv=(
            "python3",
            "scripts/scan_repo_em_dash.py",
            "verify",
            "--git-tracked",
        ),
    ),
    Step(
        # Refs #1903. Repo-wide gate: no tracked prose file may carry a
        # space-hyphen-hyphen-space prose separator. Skips noqa lines,
        # Markdown table rows, and structured-data extensions (.yml, .yaml,
        # .sh, .json, .toml, .lock, .sql). Complements scan_repo_em_dash.py.
        # Refs #2069: this pre-push hook only fires before an agent push; the
        # CI scan-double-hyphen job re-runs the scan to cover post-merge commits.
        name="scan_repo_double_hyphen",
        argv=(
            "python3",
            "scripts/scan_repo_double_hyphen.py",
            "verify",
            "--git-tracked",
        ),
    ),
    Step(
        # Refs #2065. Diff-scoped gate: a new or changed docs/runbooks/*.md
        # must follow TEMPLATE.md's canonical section skeleton. PR_BODY is
        # unset locally and --body-file is omitted, the stricter default, so
        # a non-conforming runbook surfaces before push without honouring a
        # waiver. Base-ref shape mirrors CI's verify-pr.yml step.
        name="scan_runbook_template_drift",
        argv=(
            "python3",
            "scripts/scan_runbook_template_drift.py",
            "verify",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(name="verify_apm_checksums", argv=("python3", "scripts/verify_apm_checksums.py", "verify")),
    Step(name="scan_apm_lock_drift", argv=("python3", "scripts/scan_apm_lock_drift.py", "verify")),
    Step(
        name="uv_pin_drift",
        argv=("python3", "scripts/uv_pin.py", "drift"),
    ),
    Step(
        # Refs #1680. Static gate: fails when ``.python-version`` is not an
        # exact patch or its minor drifts from requires-python / ruff / mypy /
        # flake.nix. Mirrors the uv pin drift gate above; reads only the working
        # tree, so it runs hard locally and in CI alike.
        name="python_pin",
        argv=("python3", "scripts/python_pin.py", "verify"),
    ),
    Step(
        # Refs #1207. Runtime gate: fails when ``uv --version`` does not match
        # ``[tool.uv].required-version``. Complements the static drift gate
        # above; that one catches literal-value drift across the source
        # tree; this one catches the host-uv vs pin gap PR #1206 left open
        # for Claude Code's process PATH. ``soft=True`` so a contributor
        # laptop without uv warn-skips (the same posture as ruff/mypy below);
        # CI provisions uv via setup-uv before this step runs, so the gate is
        # hard there.
        name="preflight_uv_version",
        argv=("python3", "scripts/preflight_uv_version.py", "verify"),
        required_bin=("uv",),
        soft=True,
    ),
    Step(
        name="nixpkgs_cooldown",
        argv=("python3", "scripts/nixpkgs_cooldown.py", "verify"),
    ),
    Step(
        name="scan_workflow_pip",
        argv=("python3", "scripts/scan_workflow_pip.py", "verify"),
    ),
    Step(
        name="scan_workflow_action_pins",
        argv=("python3", "scripts/scan_workflow_action_pins.py", "verify"),
    ),
    Step(
        name="scan_workflow_gh_calls",
        argv=("python3", "scripts/scan_workflow_gh_calls.py", "verify"),
    ),
    Step(
        name="scan_scripts_gh_calls",
        argv=("python3", "scripts/scan_scripts_gh_calls.py", "verify"),
    ),
    Step(
        # Refs #2143 (PR #2141 retro, repair (a)). Fails when a gate surface
        # (workflow YAML, .githooks, .pre-commit-config.yaml, or the preflight
        # manifest) invokes `ruff format`. CI enforces `ruff check` only;
        # `ruff format` is intentionally not a gate, so reformatting files the
        # gate set does not format-check only widens the diff (CLAUDE.md S5).
        name="scan_ruff_format",
        argv=("python3", "scripts/scan_ruff_format.py", "verify"),
    ),
    Step(
        name="scan_workflow_injection",
        argv=("python3", "scripts/scan_workflow_injection.py", "verify"),
    ),
    Step(
        name="scan_workflow_unsigned_commit",
        argv=("python3", "scripts/scan_workflow_unsigned_commit.py", "verify"),
    ),
    Step(
        # Refs #1519. Offline PR-head mirror of the pull_request_target
        # threat-intel triage scan: fails when the parser yields a malformed
        # OSV coordinate (the #1511 class) that the base-checkout triage job
        # cannot catch on the PR. Stdlib-only and network-free, so it runs
        # the same here, in pre-commit, and on PR head via prek.
        name="threat_intel_coords",
        argv=("python3", "scripts/threat_intel_triage.py", "verify"),
    ),
    Step(
        # Refs #1256. Workflow correctness gate: actionlint validates
        # workflow syntax, ${{ }} expressions, and; with shellcheck on
        # PATH; the shell in every ``run:`` block. Complements the
        # security-focused scan_workflow_* gates above (syntax/shell
        # correctness is a different concern from pinning/injection). The
        # binaries come from flake.nix (sharedPackages); soft so a
        # contributor laptop without the nix shell warns-and-skips while CI,
        # which provisions both via nix, enforces it. shellcheck is a
        # required_bin because actionlint silently skips run-block linting
        # when it is absent, so the gate is only meaningful with both.
        name="actionlint",
        argv=("actionlint",),
        required_bin=("actionlint", "shellcheck"),
        soft=True,
    ),
    Step(
        name="scan_secret_runbooks",
        argv=("python3", "scripts/scan_secret_runbooks.py", "verify"),
    ),
    Step(
        name="scan_secrets",
        argv=("python3", "scripts/scan_secrets.py", "verify"),
    ),
    Step(
        name="scan_markdown_links",
        argv=("python3", "scripts/scan_markdown_links.py", "verify"),
    ),
    Step(
        name="scan_docs_inventory",
        argv=("python3", "scripts/scan_docs_inventory.py", "verify"),
    ),
    Step(
        # Refs #1325. Fails when a Markdown doc outside docs/archive/ cites a
        # .github/workflows/<name>.yml path that no longer exists; the drift
        # class #1319's workflow consolidation left behind.
        name="scan_doc_workflow_refs",
        argv=("python3", "scripts/scan_doc_workflow_refs.py", "verify"),
    ),
    Step(
        # Refs #1597. Parses every docs/ ```mermaid block via bun (the #1595
        # regression class). soft + required_bin so a no-bun laptop warn-skips,
        # mirroring the pre-commit soft-skip; verify-mermaid.yml is the hard gate.
        name="scan_mermaid_syntax",
        argv=("python3", "scripts/scan_mermaid_syntax.py", "verify"),
        required_bin=("bun",),
        soft=True,
    ),
    Step(
        name="scan_maintainability_metrics",
        argv=("python3", "scripts/scan_maintainability_metrics.py", "verify"),
    ),
    Step(
        name="scan_design_philosophy_drift",
        argv=(
            "python3",
            "scripts/scan_design_philosophy_drift.py",
            "verify",
            "--master",
            ".apm/instructions/master.instructions.md",
            "--doc",
            "docs/prd/agent-rules-design-philosophy.md",
            "--glossary",
            "docs/standards/ubiquitous-language.md",
        ),
    ),
    Step(
        name="dependabot_labels",
        argv=(
            "python3",
            "scripts/dependabot_labels.py",
            "verify",
            "--dependabot",
            ".github/dependabot.yml",
            "--labels",
            ".github/labels.json",
        ),
    ),
    Step(
        name="verify_required_check_contexts",
        argv=(
            "python3",
            "scripts/verify_required_check_contexts.py",
            "verify",
            "--sot-path",
            ".github/rulesets/main.json",
            "--workflows-dir",
            ".github/workflows",
        ),
    ),
    Step(
        # Compatibility coverage for workflows that still reference
        # scripts/auto_retro.py in pull_request path filters or verify jobs.
        # The command writes only to stdout (the decision-tree preview); the
        # per-script AST docs are owned by the post-merge automation (#1540).
        name="auto_retro_decision_tree_compat",
        argv=("python3", "scripts/auto_retro.py", "decision-tree"),
    ),
    Step(
        # Refs #1540. docs/generated/scripts/ is owned by the post-merge
        # automation; the pre-push gate no longer regenerates the per-script
        # AST docs. This inverse gate fails when a non-bot branch hand-edits
        # the folder. Runs after preflight_branch_base fetches origin/<base>.
        name="gate_generated_scripts_manual_edit",
        argv=("python3", "scripts/gate_generated_scripts_manual_edit.py", "verify"),
    ),
    Step(
        # Refs #2098 (Gap B). .agents/skills/ and .claude/skills/ are generated
        # by `apm compile` from the obra/superpowers pin; the PreToolUse gate
        # (gate_agents_skills_edit.py) blocks edits in an agent session, and this
        # is its post-merge-tree counterpart; it fails a branch that diffs a
        # managed tree without a matching apm.yml / apm.lock.yaml pin change.
        # Runs after preflight_branch_base fetches origin/<base>; mirrors the
        # verify-pr.yml step of the same name so the gate fires pre-push, not
        # only in CI.
        name="gate_agents_skills_edit",
        argv=("python3", "scripts/gate_agents_skills_edit.py", "verify"),
    ),
    Step(
        # Refs #1771. docs/generated/workflows/ is owned by the post-merge
        # automation, same single-producer model as docs/generated/scripts/
        # (#1540/#1543/#1546). The pre-push gate no longer regenerates the
        # workflow if-branch diagrams: the post-merge decision-tree job
        # generates them, verify-docs-drift drift-checks them, and
        # gate_generated_scripts_manual_edit forbids hand edits. Generating
        # here left a perpetually-untracked diagram for any workflow whose
        # generated doc had not yet landed on main, tripping the untracked-file
        # stop hook (the #1764 item-2 false-fire). The
        # test_no_step_generates_docs_generated gate keeps a generator from
        # re-entering this lane.
        name="scan_preflight_drift",
        argv=("python3", "scripts/scan_preflight_drift.py", "verify"),
    ),
    Step(
        # Refs #1087. Static gate enforcing M4 (boundary validation) and M9
        # (fail-loud/open) by requiring every workflow-called script to declare
        # a Contract: docstring block. Baseline debt lives in the script's
        # BASELINE_MISSING_CONTRACT and may only shrink.
        name="scan_input_contract_drift",
        argv=("python3", "scripts/scan_input_contract_drift.py", "verify"),
    ),
    Step(
        # Refs #1089. Fails when the workflow-script-quality standard and its
        # enforcement registry drift, or an `enforced`/`partial` must-have
        # names a backing gate that does not resolve.
        name="scan_quality_standard_drift",
        argv=("python3", "scripts/scan_quality_standard_drift.py", "verify"),
    ),
    Step(
        # Refs #1828. Fails when an `enforced`/`partial` row in
        # docs/standards/pr-body-quality.enforcement.toml names a backing gate
        # that does not exist, or an orphaned defect class is present.
        name="scan_pr_body_quality_drift",
        argv=("python3", "scripts/scan_pr_body_quality_drift.py", "verify"),
    ),
    Step(
        # Refs #1241/#1242/#1243 (and #1239, #178). Fails when a section 2/4
        # safety enumeration in master.instructions.md drops its
        # non-exhaustive marker, re-closing an open invariant into a finite
        # list.
        name="scan_nonexhaustive_invariant_drift",
        argv=("python3", "scripts/scan_nonexhaustive_invariant_drift.py", "verify"),
    ),
    Step(
        # Refs #1088. Fails when a scripts/*.py lacks its matching test module
        # (M2), a new GitHub-API script is absent from the boundary registry
        # (O6), or a workflow-invoked script has no CLI contract test (M3).
        name="scan_test_presence_drift",
        argv=("python3", "scripts/scan_test_presence_drift.py", "verify"),
    ),
    # Refs #1640. Fails on tracking-issue numbers hardcoded outside .github/tracking-issues.toml.
    Step(name="scan_issue_anchor_drift", argv=("python3", "scripts/scan_issue_anchor_drift.py", "verify")),
    Step(
        # Refs #615. Fails when a Claude hook script is absent from Codex
        # coverage and is not in the explicit allowlist in the script.
        name="scan_hook_coverage_drift",
        argv=("python3", "scripts/scan_hook_coverage_drift.py", "verify"),
    ),
    Step(
        # Refs #2133 (PR #2120 retro #2121, P1). Fails when a git PreToolUse
        # hook's if: predicate (Bash(*git commit*) etc.) is narrower than the
        # command surface the script declares in HOOK_GIT_SUBCOMMANDS, so a
        # widened matcher cannot silently go untriggered.
        name="scan_hook_predicate_surface_drift",
        argv=("python3", "scripts/scan_hook_predicate_surface_drift.py", "verify"),
    ),
    Step(
        # Refs #1103. Fails when a tool a gate needs at runtime (a Step
        # required_bin) is not provisioned in flake.nix, so the devcontainer
        # cannot silently lack a tool the gates depend on.
        name="scan_devcontainer_tool_drift",
        argv=("python3", "scripts/scan_devcontainer_tool_drift.py", "verify"),
    ),
    Step(
        # Refs #1296. Fails when a .devcontainer/<agent>-<arch>/devcontainer.json
        # overlay is missing or drifted from its base config, so the generated
        # per-arch entrypoints cannot diverge from the single-source base pin.
        name="generate_devcontainer_arch_overlays",
        argv=("python3", "scripts/generate_devcontainer_arch_overlays.py", "verify"),
    ),
    Step(
        # Refs #1170. Fails when a .devcontainer/network/*.allowlist host has
        # no inline triage rationale, so a new egress destination cannot be
        # admitted without the observe/evaluate/decide record in
        # docs/runbooks/devcontainer-tool-network-triage.md.
        name="scan_allowlist_rationale",
        argv=("python3", "scripts/scan_allowlist_rationale.py", "verify"),
    ),
    Step(
        # Refs #1257. Fails when the bash read_allowlist in
        # .devcontainer/scripts/_egress-lib.sh and scripts/_allowlist.py
        # resolve_hosts disagree on a *.allowlist file, so the single source
        # of truth stays single across the container start path (bash) and the
        # CI / rationale tooling (Python).
        name="scan_allowlist_parser_parity",
        argv=("python3", "scripts/scan_allowlist_parser_parity.py", "verify"),
    ),
    Step(
        # Refs #1761. Fails when a public scripts/*.py or .github/workflows/*.yml
        # matches only the broad catch-all area_paths entries in
        # .github/label-policy.toml and has no specific functional area
        # ownership. No base-ref needed: reads the working tree only.
        name="scan_harness_doc_coverage",
        argv=("python3", "scripts/scan_harness_doc_coverage.py", "verify"),
    ),
    Step(
        # Refs #1847. Validates .devcontainer/falco/custom-rules.yaml YAML
        # syntax, required fields, and known wrong field names (e.g. proc.exe
        # vs proc.exepath) before PR review, mirroring verify-falco-rules.yml.
        name="validate_falco_rules",
        argv=(
            "python3",
            "scripts/validate_falco_rules.py",
            "verify",
            "--file",
            ".devcontainer/falco/custom-rules.yaml",
        ),
    ),
    Step(
        # Refs #1153. Fails when a pinned binary's flake.nix SHA256 is
        # hardcoded under scripts/ or .github/workflows/, so flake.nix stays
        # the single source of truth and a bump cannot leave a stale copy.
        name="scan_flake_pin_drift",
        argv=("python3", "scripts/scan_flake_pin_drift.py", "verify"),
    ),
    Step(
        # Refs #1154. Fails when a tool is compiled from source (go/cargo
        # install) on the CI surface instead of fetching a pinned prebuilt --
        # the ~138s regression class from #1150. Ack a justified backstop.
        name="scan_compile_from_source",
        argv=("python3", "scripts/scan_compile_from_source.py", "verify"),
    ),
    Step(
        # Refs #1155. Fails when a pre-commit hook that provisions a shared
        # binary (entry runs install_*.sh) is not require_serial, so prek
        # cannot race parallel copies on the shared path (the #1150
        # PermissionError class).
        name="scan_provisioning_hook_serial",
        argv=("python3", "scripts/scan_provisioning_hook_serial.py", "verify"),
    ),
    Step(
        # Refs #1230. Fails when a scripts/*.sh writes $CLAUDE_ENV_FILE
        # directly instead of persisting PATH via persist_session_path from
        # scripts/_session_path.sh; the duplication that refactor removed.
        name="scan_session_path_drift",
        argv=("python3", "scripts/scan_session_path_drift.py", "verify"),
    ),
    Step(
        # Refs #2081. Fails when a type:* label in .github/label-policy.toml
        # has a stem that is not a commit type in .github/title-policy.toml,
        # so the two partial projections of the commit-type concept cannot
        # drift. type:tracking is exempt via a declared commit_type = false.
        name="scan_commit_type_label_drift",
        argv=("python3", "scripts/scan_commit_type_label_drift.py", "verify"),
    ),
    Step(
        # Refs #1099. Runs waza spec-compliance over every skill under
        # .agents/skills. spec failure = fail, token budget = warning only.
        # Needs the pinned waza binary (scripts/install_waza.sh); soft so a
        # contributor laptop without waza/Go warns-and-skips while CI, which
        # installs waza first, enforces it.
        name="skill_quality_gate",
        argv=("python3", "scripts/skill_quality_gate.py", "verify"),
        required_bin=("waza",),
        soft=True,
    ),
    Step(
        # Refs #545. Static check that every tests/test_*.py declares
        # exactly one module-scope shard marker so the lint-scripts-pytest
        # matrix neither skips a file nor double-counts one. Runs before
        # the pytest matrix in CI; mirrored here so contributors see the
        # failure pre-push.
        name="verify_test_shard_markers",
        argv=("python3", "scripts/verify_test_shard_markers.py"),
    ),
    Step(
        # Refs #178. Fails when a scheduled control family in
        # .github/security-control-floor.toml sits below the detect-and-file
        # floor without an exempt_reason, mirroring the verify-agents.yml
        # lint-scripts-static gate so the floor is checked pre-push too.
        name="verify_security_control_floor",
        argv=("python3", "scripts/verify_security_control_floor.py"),
    ),
    Step(
        # Refs #1387. Fails when the security-control inventory drifts from the
        # tree (an unlisted privileged surface or a dangling scripts/ reference),
        # mirroring the verify-agents.yml lint-scripts-static gate so currency is
        # checked pre-push too.
        name="verify_control_inventory_currency",
        argv=("python3", "scripts/verify_control_inventory_currency.py", "verify"),
    ),
    Step(
        # Refs #1378. Fails when the OWASP Agentic Top 10 (ASI01-ASI10) mapping in
        # the security-control inventory loses a status row, mirroring the
        # verify-agents.yml lint-scripts-static gate so the mapping is checked
        # pre-push too.
        name="owasp_asi_mapping",
        argv=("python3", "scripts/owasp_asi_mapping.py", "verify"),
    ),
    Step(
        # Refs #745. Fetches the live base branch and fails before push when
        # HEAD does not contain it, matching GitHub's out-of-date branch gate.
        name="preflight_branch_base",
        argv=("python3", "scripts/preflight_branch_base.py", "verify"),
    ),
    Step(
        # Refs #2012. Measures docs/INDEX.md in the test-merge of HEAD with the
        # freshly fetched live base (git merge-tree --write-tree, no working-tree
        # mutation), catching additive merge-time budget overflow (the #2007
        # class) that the working-tree scan_docs_inventory budget gate cannot
        # see. Runs after preflight_branch_base so a behind/conflicting base is
        # reported by that gate first. preflight-only (no pull_request: workflow
        # invokes it; same posture as preflight_branch_base).
        name="preflight_merge_index_budget",
        argv=("python3", "scripts/preflight_merge_index_budget.py", "verify"),
    ),
    Step(
        # Refs #476. PR body is optional locally (PR_BODY env unset means
        # the opt-out marker is absent, which is the stricter default --
        # contributors who run preflight see drift before push). The
        # base-ref shape mirrors CI's portable-pr-policy.yml step.
        name="verify_readme_translation",
        argv=(
            "python3",
            "scripts/verify_readme_translation.py",
            "verify",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(
        # Refs #1178. PR body is optional locally (PR_BODY unset means no
        # Text delta section, the stricter default so an instruction-text
        # change without the section surfaces before push). The base-ref
        # shape mirrors CI's portable-pr-policy.yml step; cutoff/created-at
        # are omitted so the local run always enforces.
        name="verify_text_delta_section",
        argv=(
            "python3",
            "scripts/verify_text_delta_section.py",
            "verify",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(
        # Refs #1190. Diff-coupling gate: a change to the principle source
        # must touch the design-philosophy matrix (or carry a
        # philosophy-matrix-ack line in the PR body). PR_BODY is unset
        # locally, the stricter default, so a master edit without the
        # matrix surfaces before push. Base-ref shape mirrors CI's
        # portable-pr-policy.yml step.
        name="scan_design_philosophy_drift_coupling",
        argv=(
            "python3",
            "scripts/scan_design_philosophy_drift.py",
            "verify-coupling",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(
        # Refs #2011/#1754. Doc-graph co-change gate promoted to pre-push: a
        # change to a doc-dependencies.toml node with a blocking dependent
        # (e.g. design_philosophy_prd -> ubiquitous_language) must co-change
        # that dependent. PR_BODY is unset locally, the stricter default, so a
        # doc-graph-waiver is absent and the co-change miss surfaces before
        # push rather than only in validate-doc-graph.yml CI (the #1989
        # first-head failure class). Base-ref shape mirrors the CI workflow;
        # reads origin/main fetched by preflight_branch_base. Was previously
        # CI-only via the scan_preflight_drift ALLOWLIST; promotion per #2011.
        name="gate_doc_graph_pr",
        argv=(
            "python3",
            "scripts/gate_doc_graph_pr.py",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(
        # Refs #1670. Net-growth gate: a PR whose .apm/instructions/**
        # diff grows (added chars > removed chars) must carry a plain-text
        # text-growth-ack line in the PR body. PR_BODY is unset locally,
        # the stricter default, so an unjustified net-positive instruction
        # edit surfaces before push. Base-ref shape mirrors CI's verify-pr.yml
        # step; cutoff/created-at are omitted so the local run always enforces.
        name="verify_instruction_text_growth",
        argv=(
            "python3",
            "scripts/verify_instruction_text_growth.py",
            "verify",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(
        # Refs #89. Bidirectional drift gate: the universal text changes iff
        # apm.yml version bumps. Pre-push cannot see PR labels (they are
        # repository state, not git-tracked), so --labels is omitted and
        # PR_LABELS is unset locally; the gate then treats labels=None and
        # skips only the label-match while keeping the text-vs-version iff and
        # the clean single-component bump check. CI's verify-pr.yml step adds
        # PR_LABELS so the label-match runs there. Base-ref shape mirrors CI.
        name="verify_source_version_bump",
        argv=(
            "python3",
            "scripts/verify_source_version_bump.py",
            "verify",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(
        name="verify_ruleset_sync",
        argv=(
            "python3",
            "scripts/verify_ruleset_sync.py",
            "verify",
            "--repo",
            "tvna/claude-md",
            "--base-ref",
            "main",
            "--sot-path",
            ".github/rulesets/main.json",
            "--ruleset-name",
            "main-protection",
        ),
        required_env=("GH_TOKEN_API",),
        soft=True,
    ),
    Step(
        name="ruff",
        argv=("uv", "run", "ruff", "check", "scripts", "tests"),
        required_bin=("uv",),
        soft=True,
    ),
    Step(
        name="mypy",
        argv=("uv", "run", "mypy", "scripts", "tests"),
        required_bin=("uv",),
        soft=True,
    ),
    Step(
        # Refs #985. Parallelised across cores with pytest-xdist (``-n auto``)
        # to cut the ~290s serial wall-clock without dropping a single test --
        # the same full universe CI runs (sharded across matrix legs) runs here
        # (sharded across local workers). xdist lives in the ``local`` uv group,
        # so the run activates it explicitly. ``heavy=True`` routes this step
        # through the fail-fast + skip-cache path in ``main``.
        name="pytest",
        argv=("uv", "run", "--group", "local", "python", "-m", "pytest", "-q", "-n", "auto"),
        required_bin=("uv",),
        soft=True,
        heavy=True,
    ),
    Step(
        # Refs #952/#1800. Per-file 90 % coverage floor for changed
        # scripts/*.py. Runs ``pytest --cov --cov-report=json`` when
        # coverage.json is absent OR stale (older than a scripts/** or
        # tests/** source file, Refs #2075); reuses a fresh report otherwise.
        # ``heavy=True`` so it runs in the skip-cached heavy phase after all
        # cheap gates pass. CI equivalent: verify-agents.yml ``coverage`` job
        # (``Per-file coverage floor`` required status check).
        name="preflight_coverage",
        argv=("uv", "run", "python", "scripts/preflight_coverage.py"),
        required_bin=("uv",),
        soft=True,
        heavy=True,
    ),
    Step(
        name="prek",
        argv=("uv", "tool", "run", "prek", "run", "--all-files", "--show-diff-on-failure"),
        required_bin=("uv",),
        soft=True,
    ),
)
