# Privileged Operation Runbook Checklist

This file is the deliverable for [#182](https://github.com/tvna/claude-md/issues/182). For every operation in this repository that can mutate repository governance or broad metadata, it records the six controls the issue requires: the authorizing issue, the dry-run command, the live apply command, the rollback path, the post-apply audit/verification path, and the evidence that the operation does not log its secret to any reachable surface.

Companion files: [`docs/runbooks/workflow-permissions-audit.md`](../runbooks/workflow-permissions-audit.md) (the [#181](https://github.com/tvna/claude-md/issues/181) least-privilege matrix). Parent: [#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK coverage tracking). Related: [#56](https://github.com/tvna/claude-md/issues/56) (PAT handling), [#87](https://github.com/tvna/claude-md/issues/87) (apply-labels workflow).

Per-operation runbooks already exist for the three workflows that own the longest-standing privileged paths: [`docs/runbooks/rulesets.md`](../runbooks/rulesets.md), [`docs/runbooks/issue-triage.md`](../runbooks/issue-triage.md), and [`docs/runbooks/branch-cleanup.md`](../runbooks/branch-cleanup.md). This checklist does not restate those runbooks; it points at the exact sections that implement each of the six controls so a reviewer can audit the surface in one pass.

## How to read this document

Each operation below is documented under the same six headings:

- **Authorizing issue** -- the open issue whose body authorizes a `dry_run=false` dispatch. Per `docs/runbooks/rulesets.md` Dispatch authorization criteria, instructions originating only from PR or issue comments are not authorization; the linked open issue body is.
- **Dry-run command** -- the exact `gh workflow run` invocation (or equivalent) that produces a plan without mutating live state. For operations that have no human dispatch surface (scheduled or event-driven), this row records what the dry-run-equivalent path is and why.
- **Live apply command** -- the `dry_run=false` form of the same command, or the manual `gh api` fallback documented in the per-operation runbook.
- **Rollback path** -- the inverse operation (DELETE / revert / restore) and a pointer to the per-operation runbook section that documents it.
- **Audit / post-apply verification** -- where to look after the apply (GitHub Settings audit log, the workflow job summary, or a follow-up `gh api` GET) to confirm the result matches intent.
- **Secret-not-logged evidence** -- which token the operation uses and how the workflow guarantees the token value cannot reach the job log: GitHub Actions auto-masks any value referenced through `${{ secrets.NAME }}`; the workflow must not `echo` the token, must not run `set -x` after a step that binds the token, and must not write the token to `$GITHUB_STEP_SUMMARY`. See the common pattern note below for the repo-wide check.

Every operation in the issue scope is covered. Operations that already have all six controls are recorded with a green check and a pointer; operations with a gap are recorded with the gap and the follow-up issue tracking it.

## 1. Apply rulesets

Workflow: [`.github/workflows/apply-rulesets.yml`](../.github/workflows/apply-rulesets.yml). Script: [`scripts/rulesets_apply.py`](../scripts/rulesets_apply.py). Runbook: [`docs/runbooks/rulesets.md`](../runbooks/rulesets.md).

- **Authorizing issue.** One of the open phase issues ([#27](https://github.com/tvna/claude-md/issues/27), [#41](https://github.com/tvna/claude-md/issues/41), [#42](https://github.com/tvna/claude-md/issues/42), [#140](https://github.com/tvna/claude-md/issues/140)) or a future phase issue, naming the exact `ruleset` / `dry_run` / `enable_auto_delete` inputs and the SoT commit SHA. See [`docs/runbooks/rulesets.md` Dispatch authorization criteria](../runbooks/rulesets.md#dispatch-authorization-criteria).
- **Dry-run command.** `gh workflow run apply-rulesets.yml --ref main -f ruleset=<name> -f dry_run=true -f enable_auto_delete=false`. The job summary prints either a "POST planned" row (first-time apply) or a per-field unified diff of `name` / `target` / `enforcement` / `conditions` / `bypass_actors` / `rules`.
- **Live apply command.** Same invocation with `dry_run=false`, re-dispatched only after the dry-run diff matches the linked SoT JSON byte-for-byte. See [`docs/runbooks/rulesets.md` Apply via workflow](../runbooks/rulesets.md#apply-via-workflow-primary).
- **Rollback path.** `gh api --method DELETE /repos/tvna/claude-md/rulesets/<id>`. Non-destructive: the SoT JSON in git is unchanged, and re-running the workflow restores the previous state via the POST path. See [`docs/runbooks/rulesets.md` Rollback](../runbooks/rulesets.md#rollback).
- **Audit / post-apply verification.** (a) `gh api /repos/tvna/claude-md/rulesets/<id>` confirms live equals the committed JSON. (b) Settings -> Logs -> Audit log filtered to the last hour must show one `repository_ruleset.create|update|destroy` matching the dispatch and one `environment.deployment_approval` matching the `ruleset-apply` environment approver. See [`docs/runbooks/rulesets.md` Post-apply audit log review](../runbooks/rulesets.md#post-apply-audit-log-review).
- **Secret-not-logged evidence.** `RULESETS_PAT` is bound only via `env.GH_TOKEN: ${{ secrets.RULESETS_PAT }}` at the top of the workflow; every step uses `gh` / `gh api`, which reads the token from the environment without echoing it. The repo-wide grep in the common pattern note below confirms no `echo "$GH_TOKEN"` or `echo "$RULESETS_PAT"` exists. The `Guard RULESETS_PAT` step ([`apply-rulesets.yml:43-50`](../.github/workflows/apply-rulesets.yml)) tests presence (`-z "${GH_TOKEN}"`) without printing the value.

Residual: `RULESETS_PAT` carries `Administration: Read and write`; dispatch is `main`-ref guarded and the `ruleset-apply` Environment gate requires an approver.

## 2. Apply labels (non-prune)

Workflow: [`.github/workflows/apply-labels.yml`](../.github/workflows/apply-labels.yml). Script: [`scripts/labels_apply.py`](../scripts/labels_apply.py). Runbook: [`docs/runbooks/issue-triage.md`](../runbooks/issue-triage.md).

- **Authorizing issue.** Per [#87](https://github.com/tvna/claude-md/issues/87) and [#84](https://github.com/tvna/claude-md/issues/84), the dispatching change is the merged PR that edited `.github/labels.json`; the PR body or its referenced issue records the intent. Apply with `prune=false` is non-destructive on existing issue assignments and follows the same authorization model as a normal commit.
- **Dry-run command.** `gh workflow run apply-labels.yml --ref main -f dry_run=true -f prune=false`. Emits the plan-only matrix (POST/PATCH rows, no DELETE rows). See [`docs/runbooks/issue-triage.md` Apply](../runbooks/issue-triage.md#apply).
- **Live apply command.** Same invocation with `dry_run=false, prune=false`. Reconciles by POST (new labels) and PATCH (color/description drift).
- **Rollback path.** Per-label `gh api --method DELETE /repos/tvna/claude-md/labels/<name>` for an accidentally-created label, or revert the SoT edit and re-dispatch. See [`docs/runbooks/issue-triage.md` Rollback](../runbooks/issue-triage.md#rollback).
- **Audit / post-apply verification.** The three `diff` recipes in [`docs/runbooks/issue-triage.md` Verify](../runbooks/issue-triage.md#verify): live label set equals SoT, per-label color/description matches, and every open non-PR issue passes the cardinality check on `layer:*` / `type:*` / `state:*` / `severity:*` / `threat:*`. Settings audit log shows `repo.add_label` / `repo.update_label` entries for the labels modified.
- **Secret-not-logged evidence.** `LABELS_PAT` is bound only via `env.GH_TOKEN: ${{ secrets.LABELS_PAT }}`. The `Guard LABELS_PAT` step ([`apply-labels.yml:34-40`](../.github/workflows/apply-labels.yml)) tests presence without printing the value. Same masking guarantee as `RULESETS_PAT` (see the common pattern note).

## 3. Prune labels (destructive)

Same workflow and script as Section 2, dispatched with `prune=true`.

- **Authorizing issue.** A dedicated open issue or phase task must authorize prune (for example [#84](https://github.com/tvna/claude-md/issues/84) Phase 4 retired the `agent:*` labels). Authorization explicitly names which labels the dry-run plan must show under `plan-only (DELETE)`; any other DELETE row in the plan blocks the live dispatch.
- **Dry-run command.** `gh workflow run apply-labels.yml --ref main -f dry_run=true -f prune=true`. The plan-only matrix now includes DELETE rows; confirm only the authorized names appear.
- **Live apply command.** Same invocation with `dry_run=false, prune=true`.
- **Rollback path.** **Partially destructive.** Re-dispatching the workflow restores the label definition (color, description) if the name is added back to SoT, but **does not** restore per-issue or per-PR assignments -- those were removed by GitHub when the label was deleted and must be re-applied manually. See [`docs/runbooks/issue-triage.md` Rollback](../runbooks/issue-triage.md#rollback) for the exact warning text.
- **Audit / post-apply verification.** Same three `diff` recipes in [`docs/runbooks/issue-triage.md` Verify](../runbooks/issue-triage.md#verify), plus `repo.remove_label` entries in the Settings audit log matching the authorized prune set.
- **Secret-not-logged evidence.** Same as Section 2.

## 4. Branch cleanup -- survey mode (current)

Workflow: `branch-cleanup` job in [`.github/workflows/weekly-maintenance.yml`](../.github/workflows/weekly-maintenance.yml). Script: [`scripts/branch_cleanup.py`](../scripts/branch_cleanup.py). Runbook: [`docs/runbooks/branch-cleanup.md`](../runbooks/branch-cleanup.md).

- **Authorizing issue.** [#31](https://github.com/tvna/claude-md/issues/31) (tracking). The current workflow has no live mutation path; the schedule and dispatch surface are both read-only with respect to branches.
- **Dry-run command.** `gh workflow run weekly-maintenance.yml --ref main -f task=branch-cleanup -f branch_cleanup_dry_run=true -f branch_cleanup_min_age_days=60`. Produces the candidate table in `$GITHUB_STEP_SUMMARY` and updates the rolling summary issue per [`docs/runbooks/branch-cleanup.md` Summary issue convention](../runbooks/branch-cleanup.md#summary-issue-convention).
- **Live apply command.** Not implemented. Flipping `dry_run=false` is a no-op; the workflow declares `permissions: contents: read` and contains no `gh api DELETE /git/refs/...` call. See [`docs/runbooks/branch-cleanup.md` Current phase: dry-run only](../runbooks/branch-cleanup.md#current-phase-dry-run-only).
- **Rollback path.** Not applicable (no delete path).
- **Audit / post-apply verification.** `$GITHUB_STEP_SUMMARY` per run is the durable per-run audit trail; the rolling summary issue is a convenience surface. The selection criteria in [`docs/runbooks/branch-cleanup.md` Selection criteria](../runbooks/branch-cleanup.md#selection-criteria) define the expected candidate set.
- **Secret-not-logged evidence.** Uses default `GITHUB_TOKEN` only (no PAT). Auto-masked by GitHub Actions.

## 5. Branch cleanup -- deletion path (future, gap)

Tracked under [#31](https://github.com/tvna/claude-md/issues/31) Goal D. **All six controls below are requirements for the follow-up PR that introduces the delete path, not properties of the current workflow.**

When Goal D lands, the delete-enabled workflow must:

1. Widen permissions to `contents: write` (required to call `DELETE /git/refs/heads/...`).
2. Add a `ruleset-apply`-style GitHub Environment gate (separate Environment, e.g. `branch-cleanup-apply`) to make the dispatch authorization explicit.
3. Implement `dry_run=true` as the genuine default plan-only path (no DELETE call).
4. Implement `dry_run=false` only behind both the Environment approval and a `main`-ref guard, mirroring `apply-rulesets.yml`.
5. Document the rollback path -- `gh api --method POST /repos/tvna/claude-md/git/refs -f ref="refs/heads/<branch>" -f sha="<last_commit_sha>"` within the 90-day ref retention window, using the SHA the summary comment recorded -- in [`docs/runbooks/branch-cleanup.md` Rollback](../runbooks/branch-cleanup.md#rollback) (already present).
6. Record `git.delete` / `protected_branch.destroy` entries in the Settings audit log and surface the run URL in the rolling issue comment.

This audit does not open a new follow-up issue for the gap; [#31](https://github.com/tvna/claude-md/issues/31) Goal D is the existing tracker, and [`docs/runbooks/workflow-permissions-audit.md`](../runbooks/workflow-permissions-audit.md) already records the same dependency.

## 6. Generated instruction publication

Workflow: [`.github/workflows/generate-agents.yml`](../.github/workflows/generate-agents.yml). PR-time verification: [`.github/workflows/verify-agents.yml`](../.github/workflows/verify-agents.yml). Generates `CLAUDE.md` and `AGENTS.md` from `.apm/` SoT.

- **Authorizing issue.** The PR that introduced or last updated `.apm/`, `apm.yml`, or any APM source file. The workflow does not write to `main` directly: in `mode: generate` it opens a PR named `chore: regenerate agent instructions` against `main`, so any change still passes the standard review and required-status-check loop before landing.
- **Dry-run command.** `gh workflow run verify-agents.yml --ref <pr-branch>`, which calls `generate-agents.yml` with `mode: verify`. The verify path runs the full `apm compile` and then `git diff --exit-code -- CLAUDE.md AGENTS.md`, failing the PR check if regeneration would differ. See `verify-agents.yml:33-42`.
- **Live apply command.** Scheduled through `weekly-maintenance.yml` every Monday at 05:00 JST, or `gh workflow run generate-agents.yml --ref main` (default `mode: generate`). Both paths open a PR; neither pushes directly to `main`.
- **Rollback path.** `git revert <merge-sha>` on `main` for the `chore: regenerate agent instructions` PR. Because the workflow re-derives the files on the next schedule from SoT, the revert is only durable if it is accompanied by a corresponding revert of the `.apm/` change that caused the regeneration.
- **Audit / post-apply verification.** The PR diff is the verification surface (a reviewer reads exactly what `apm compile` produced). On the verify path, the `verify-agents.yml` gate blocks any PR whose `.apm/` changes would generate a different `CLAUDE.md` / `AGENTS.md` than the PR itself ships. No Settings audit log entry is meaningful here because the operation is a normal `git push` from `github-actions[bot]`.
- **Secret-not-logged evidence.** Uses default `GITHUB_TOKEN` only (no PAT). The `curl` to the astral-sh/uv release tarball is pinned per [#112](https://github.com/tvna/claude-md/issues/112) via `scripts/uv_pin.py`, eliminating the version-drift supply-chain surface.

Residual: `generate-agents.yml` declares `contents: write` and `pull-requests: write` at the top level because the generate mode needs them; the verify mode reuses the workflow with `mode: verify` and inherits the wider scope unused. Over-grant is tracked under [#181](https://github.com/tvna/claude-md/issues/181) and a downstream review checklist is tracked under [#183](https://github.com/tvna/claude-md/issues/183).

## 7. Dependency lock and tool bootstrap updates

Sources: `pyproject.toml`, `uv.lock`, `scripts/install-uv.sh`, `scripts/uv_pin.py`, and the [`dependabot.yml`](../.github/dependabot.yml) configuration that opens PRs against them.

- **Authorizing issue.** [#112](https://github.com/tvna/claude-md/issues/112) (uv pin policy) governs the `[tool.uv].required-version` pin; the merged PR that updates `pyproject.toml` or `uv.lock` is the authorizing change. Dependabot PRs are filtered by the allowlist in [`.github/dependabot-automerge.json`](../.github/dependabot-automerge.json) before [`.github/workflows/dependabot-automerge.yml`](../.github/workflows/dependabot-automerge.yml) enables auto-merge.
- **Dry-run command.** A dependabot PR is itself the plan: it changes the lockfile or version pin, runs the full CI suite (verify-agents, portable-pr-policy), and waits for review before merging. There is no separate `dry_run=true` dispatch because the PR-and-CI cycle is the dry-run.
- **Live apply command.** Merging the PR. `scripts/install-uv.sh` reads the post-merge `[tool.uv].required-version` on the next SessionStart hook invocation and installs that exact version; `uv sync --locked` then resolves all transitive dependencies from the merged `uv.lock`.
- **Rollback path.** `git revert <merge-sha>` of the dependabot PR, or a manual PR that pins back to the previous version. The next SessionStart hook downgrades `uv` to the reverted pin because [`install-uv.sh`](../scripts/install-uv.sh) compares `uv --version` against the pin on every invocation.
- **Audit / post-apply verification.** Dependabot is the audit trail: every dependency update is a PR with diff, CI status, and review history. [`scripts/uv_pin.py`](../scripts/uv_pin.py) `drift` enforces that no literal uv version string lives outside `[tool.uv].required-version` in `.github/workflows/`, `scripts/`, and `docs/`, blocking partial updates.
- **Secret-not-logged evidence.** No PAT is involved. `install-uv.sh` uses `curl -fLsS` (silent, fails on HTTP error, no token in URL) against a public GitHub release URL; `dependabot-automerge.yml` uses default `GITHUB_TOKEN` only. `set -euo pipefail` is set at the top of `install-uv.sh` without `set -x`, so command expansions are not echoed.

## 8. Threat-intelligence triage

Workflow: [`.github/workflows/issue-pr-triage.yml`](../.github/workflows/issue-pr-triage.yml) / `triage`. Script: [`scripts/threat_intel_triage.py`](../scripts/threat_intel_triage.py). Runbook: [`docs/runbooks/issue-triage.md` `threat:*`](../runbooks/issue-triage.md#threat-0-to-2).

- **Authorizing issue.** [#170](https://github.com/tvna/claude-md/issues/170) (sustained operations). The workflow runs automatically on `issues` and `pull_request_target` events; no dispatch exists.
- **Dry-run command.** Not provided as an input. The workflow's outputs are deterministic given a fixed `(uv.lock, pyproject.toml, OSV.dev snapshot, GHSA snapshot, OSSF malicious-packages snapshot, CISA KEV snapshot, FIRST EPSS snapshot)` -- the same inputs produce the same `recommended_labels` and `remove_labels` outputs. `scripts/threat_intel_triage.py` exposes `--osv-file`, `--kev-file`, `--ghsa-file`, `--malpkg-file`, and `--epss-file` fixture inputs (used by `tests/test_threat_intel_triage.py`) so the routing logic can be exercised locally without live network access; this is the dry-run-equivalent surface for the script. EPSS is advisory-only per [#173](https://github.com/tvna/claude-md/issues/173) and never changes the label decision, so its snapshot affects only the summary table.
- **Live apply command.** Automatic on event. `gh issue edit <number> --add-label "<recommended>"` and `--remove-label "<stale>"` are the only mutations.
- **Rollback path.** `gh issue edit <number> --remove-label "threat:intel-needed"` (or `threat:response-needed`) by a maintainer. Because the workflow re-runs on the next `labeled` / `unlabeled` event, a permanent override requires either fixing the input (the OSV/KEV signal that caused the label) or filtering the label out of the script's classification rule.
- **Audit / post-apply verification.** Each run writes the OSV / KEV correlation table to `$GITHUB_STEP_SUMMARY`; the label change itself is visible in the issue timeline (`labeled` / `unlabeled` events). No Settings audit log is involved (label add/remove is normal `gh issue edit` activity).
- **Secret-not-logged evidence.** Uses default `GITHUB_TOKEN` only (no PAT). The labels payload is read via `toJSON(github.event.issue.labels || github.event.pull_request.labels)` into a tempfile, not interpolated into shell, eliminating the title/body shell-injection vector that crafted labels could otherwise exploit.

Residual: `pull_request_target` runs with write-capable token even on fork PRs; the workflow has no actor filter. Tracked under [#170](https://github.com/tvna/claude-md/issues/170) (sustained ops) and [#181](https://github.com/tvna/claude-md/issues/181) (the over-grant of `pull-requests: read` that the script does not actually use).

## 9. Auto-open retrospective issue on merge

Workflow: [`.github/workflows/post-merge.yml`](../.github/workflows/post-merge.yml). Script: [`scripts/auto_retro.py`](../scripts/auto_retro.py). Tests: [`tests/test_auto_retro.py`](../tests/test_auto_retro.py). Tracking: [#149](https://github.com/tvna/claude-md/issues/149).

- **Authorizing issue.** [#149](https://github.com/tvna/claude-md/issues/149) (umbrella) and the per-PR change issues that introduced the workflow ([#234](https://github.com/tvna/claude-md/issues/234)), the repair-history pre-fill ([#343](https://github.com/tvna/claude-md/issues/343)), and the policy-artifact-only noise skip ([#594](https://github.com/tvna/claude-md/issues/594)). The workflow runs automatically on `pull_request_target: closed` events with `github.event.pull_request.merged == true`; no human dispatch exists. The deterministic skip rules in `should_skip` (`scripts/auto_retro.py`) prevent self-recursion (retro-typed PRs), bot-authored merges, and PRs with no repair signal. The post-signal repair-history gate also skips standalone retros when the generated rows are only exempt `[policy-artifact]` rows such as merge-from-main and multi-commit policy artifacts, unless a review repair, CI failure, verification failure, or iteration commit makes the retro actionable.
- **Dry-run command.** Not exposed as an input. The pre-merge dry-run-equivalent surface is `tests/test_auto_retro.py`, which mocks the `gh_api` boundary and exercises every branch of `run()`. For a specific event payload, `python3 scripts/auto_retro.py run --event-file <fixture.json> --repo tvna/claude-md` exits without side effects on the read-only paths (skip / existing-retro short-circuit) and surfaces the parse decisions only.
- **Live apply command.** Automatic on `pull_request_target: closed`. The only mutation is `POST /repos/<owner>/<repo>/issues` to open a new retrospective issue, idempotency-gated by `find_existing_retro`.
- **Rollback path.** Two surfaces:
  - **Pause / resume.** `gh workflow disable .github/workflows/post-merge.yml --ref main` halts further auto-creates without touching existing retro issues; `gh workflow enable .github/workflows/post-merge.yml --ref main` resumes. Use this for a runaway-issue incident where the cause is still under investigation.
  - **Revert the implementation.** `git revert <merge-sha>` of the workflow or script PR removes the deterministic trigger. Runaway retro issues are identifiable by label `type:docs + layer:meta` plus title prefix `chore(auto-retro)` (legacy retros use `fix(auto-retro)`; Refs #1069); close individually via `gh api --method PATCH /repos/tvna/claude-md/issues/<n> -f state=closed -f state_reason=not_planned`. The retrospective body is recoverable from the workflow run log, so a wrongful close is reversible by re-opening.
- **Audit / post-apply verification.** Each run writes a one-section table to `$GITHUB_STEP_SUMMARY` recording the source PR, action (`created` / `skip`), and detail (existing retro number on duplicate, repair-signal aggregate on no-signal skip, or policy-artifact-only skip detail). The durable per-merge cadence trail is `docs/archive/retrospective-pr-*.md`; an unexpected gap or burst there is the first symptom of a regression.
- **Secret-not-logged evidence.** Uses default `GITHUB_TOKEN` only (no PAT). Auto-masked by GitHub Actions. The script never `echo`es the token, and `gh api` reads the token from the environment without printing it.

Residual: `pull_request_target` runs with a write-capable token on every closed PR. The `merged == true` job-level gate plus the `should_skip` bot/retro filter cap the blast radius; further hardening (e.g. an actor-based filter) is tracked under [#181](https://github.com/tvna/claude-md/issues/181).

## Common pattern: secret-not-logged evidence

All token-using workflows (`apply-rulesets.yml`, `apply-labels.yml`, `weekly-maintenance.yml`, and the `verify-ruleset-sync` job in `verify-pr.yml`) bind the token only through `env.GH_TOKEN: ${{ secrets.NAME }}` at the workflow or job level. GitHub Actions automatically masks any value passed through `${{ secrets.* }}` from job logs, replacing it with `***`. The repo-wide check is:

```sh
rg -n 'echo[[:space:]]+["$].*(GH_TOKEN|RULESETS_PAT|LABELS_PAT)|set -x' .github/workflows scripts
```

At the time this audit was written, every match is one of:

- `echo "::error::RULESETS_PAT secret is not set..."` -- prints the secret **name** as a literal string inside a guard step that runs only when the secret is absent (`apply-rulesets.yml:48`, `weekly-maintenance.yml`, and the `Guard RULESETS_PAT` step of the `verify-ruleset-sync` job in `verify-pr.yml`).
- `echo "::error::LABELS_PAT secret is not set..."` -- same pattern in `apply-labels.yml:38`.
- `echo "$HOME/.local/bin" >> "$GITHUB_PATH"` -- appends a directory to PATH; does not touch the token.

No `echo "$RULESETS_PAT"`, `echo "$LABELS_PAT"`, `echo "$GH_TOKEN"`, or `set -x` after a token-bearing step exists in the repository. Any addition that introduces one is a regression against this audit and must be removed before merge.

## Gap summary

This audit does not open new follow-up issues. Per CLAUDE.md Section 3 (reuse instead of duplicate) and per the precedent set by [#181 / PR #257](https://github.com/tvna/claude-md/pull/257), each gap below maps to an existing tracker:

| Gap | Operation | Existing tracker |
|---|---|---|
| No live delete path; needs Environment gate, dry-run, rollback, audit when added | Branch cleanup -- deletion path | [#31](https://github.com/tvna/claude-md/issues/31) Goal D |
| Top-level `contents: write` / `pull-requests: write` over-granted on the verify-mode reuse path | Generated instruction publication | [#181](https://github.com/tvna/claude-md/issues/181), [#183](https://github.com/tvna/claude-md/issues/183) |
| `pull_request_target` write-capable token without actor filter | Threat-intelligence triage | [#170](https://github.com/tvna/claude-md/issues/170), [#181](https://github.com/tvna/claude-md/issues/181) |
| `RULESETS_PAT` reused by scheduled read-only workflows without Environment scoping | (Cross-operation) `weekly-maintenance.yml` ruleset and security-control jobs | [#56](https://github.com/tvna/claude-md/issues/56), [#181](https://github.com/tvna/claude-md/issues/181) |

Operations that have all six controls today and require no follow-up: apply rulesets, apply labels (non-prune), prune labels, branch cleanup (survey mode), dependency lock / tool bootstrap, auto-open retrospective issue on merge.

## Verification

The exact `rg` command from the Verification section of [#182](https://github.com/tvna/claude-md/issues/182):

```bash
rg -n "dry_run|prune|DELETE|rollback|audit log|workflow_dispatch|RULESETS_PAT|LABELS_PAT|delete|apply" docs .github scripts
```

Expected reviewer behavior:

- Every match inside `.github/workflows/*.yml` falls into one of the eight numbered sections above; matches under the same workflow appear together under that section.
- Matches in `docs/**` are the per-operation runbooks this checklist references (`rulesets.md`, `issue-triage.md`, `branch-cleanup.md`, `workflow-permissions-audit.md`, `security-control-inventory.md`, `security-control-drift-report.md`, `remote-environment.md`) and are absorbed by the section that links to each.
- Matches in `scripts/**` are the implementation of the same surfaces (`rulesets_apply.py`, `labels_apply.py`, `branch_cleanup.py`, `threat_intel_triage.py`, `uv_pin.py`, `install-uv.sh`); each is exercised by the workflow that imports it, so it is absorbed by the matrix indirectly.
- Matches the checklist does not cover are a defect in this audit and should be added by a follow-up PR that updates this file.

Reviewers should also confirm:

- Every privileged operation in the issue scope (apply rulesets, apply labels, prune labels, branch cleanup, generated instruction publication, dependency lock / tool bootstrap, threat-intelligence triage, auto-open retrospective issue on merge) appears as a numbered section above.
- Every numbered section names all six controls (authorizing issue, dry-run, live apply, rollback, audit / verification, secret-not-logged evidence) or explicitly records the gap and the existing follow-up issue.
- The `rg` command in the Common pattern section above returns only the safe matches enumerated there.

Closes #182.
