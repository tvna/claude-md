# Workflow Permissions Audit (least privilege matrix)

This file is the deliverable for [#181](https://github.com/tvna/claude-md/issues/181). It records, for every workflow under `.github/workflows/`, the trigger, the token or secret used, the minimum repository permissions the workflow actually needs to do its job, the permissions currently declared in YAML, the mismatch (if any) between the two, and the follow-up issue tracking any remediation.

Companion inventory: [`docs/prd/security-control-inventory.md`](../prd/security-control-inventory.md) (the surface-level [#179](https://github.com/tvna/claude-md/issues/179) baseline). Parent: [#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK coverage tracking). Related: [#56](https://github.com/tvna/claude-md/issues/56) (PAT handling).

## How to read this document

- **Workflow**; filename under `.github/workflows/`.
- **Trigger**; primary `on:` events. Push-style triggers (`pull_request`, `pull_request_target`, `issues`, `issue_comment`, `pull_request_review_comment`, `schedule`) and `workflow_dispatch` / `workflow_call` are listed verbatim. Path filters and event types are summarized only when material to the risk.
- **Token / secret**; what the workflow authenticates with. `GITHUB_TOKEN` is the default workflow token; named PATs (`LABELS_PAT`, `RULESETS_PAT`) are fine-grained tokens scoped to a GitHub Environment. "none" means no token-bearing API call is made.
- **Minimum required**; the least privilege permission set inferred from the operations the workflow actually performs (see *Inference rules* below). Listed as `<scope>: read|write` lines, comma-separated, in the same scope vocabulary GitHub uses for `permissions:` blocks.
- **Current declared**; the union of the top-level `permissions:` block and any job-level overrides. `(top-level)` and `(job: <name>)` qualifiers are added when scopes differ between levels.
- **Mismatch / residual risk**
  - `none`; declared matches minimum.
  - `over-grant: <scope>`; declared permission is broader than required; risk if the workflow is compromised.
  - `under-grant: <scope>`; declared permission is narrower than required; would surface as a runtime API failure.
  - `implicit default`; no `permissions:` block is declared; the workflow runs with the repository default permissions (which today is the GitHub default for new repos). Treated as a residual risk requiring an explicit declaration even when the default happens to be sufficient.
  - Additional risk notes (PAT scope, `pull_request_target` from forks, supply-chain `curl`) are appended after the primary classification.
- **Follow-up**; issue number(s) for tracked remediation. Existing issues are reused per #178's "reuse instead of duplicate" rule; no new issues are opened by this audit.

### Inference rules used to derive *minimum required*

Each operation a workflow performs maps to the smallest scope/access that operation requires. The mapping below was applied uniformly across the matrix:

| Operation seen in workflow | Minimum scope required |
|---|---|
| `actions/checkout` against the workflow ref (default branch or PR head) | `contents: read` |
| `actions/checkout` with `ref:` pointing at a different branch (e.g. `dependabot-automerge.yml`) | `contents: read` |
| `git push` (including `--force-with-lease`) | `contents: write` |
| `gh api GET /repos/...` (default-branch lookup, issue/PR metadata read) | `contents: read` |
| `gh api` against `/repos/.../rulesets`, `/repos/.../labels` (write side) | covered by a fine-grained PAT (not `GITHUB_TOKEN`); workflow scope only needs `contents: read` |
| `gh issue create` / `gh issue edit` on issues | `issues: write` |
| `gh issue edit` label add/remove on PRs | `issues: write`, `pull-requests: write` |
| `gh pr comment` / `gh pr edit` / `gh pr review` / requestChanges | `pull-requests: write` |
| `gh pr merge --auto` | `pull-requests: write` |
| `gh pr create` | `pull-requests: write` (and `contents: write` for the push that precedes it) |
| `docker login ghcr.io` + image push with `GITHUB_TOKEN` | `packages: write` |
| Reading event payload (`github.event.*`) only | no scope required beyond `contents: read` for checkout |
| `curl` to public release endpoints (e.g. astral-sh/uv tarball) | no GitHub scope; supply-chain risk noted separately |

A workflow that does only `checkout` plus a pure local script (no API call, no `gh` invocation) needs `contents: read` and nothing else.

## Permission matrix

| Workflow | Trigger | Token / secret | Minimum required | Current declared | Mismatch / residual risk | Follow-up |
|---|---|---|---|---|---|---|
| `apply-labels.yml` | `workflow_dispatch` (inputs `dry_run` default true, `prune` default false) | `LABELS_PAT` via `secrets.LABELS_PAT`, scoped to `labels-apply` Environment | `contents: read` | `contents: read` | `none`. Residual: `LABELS_PAT` (fine-grained, `Issues: Read and write`) lives in `labels-apply` Environment; rotation guidance in `docs/runbooks/issue-triage.md`. Dispatch is `main`-ref guarded. | #181 (this audit), #182 (privileged-op runbook) |
| `apply-rulesets.yml` | `workflow_dispatch` (inputs `ruleset`, `dry_run` default true, `enable_auto_delete` default false) | `RULESETS_PAT` via `secrets.RULESETS_PAT`, scoped to `ruleset-apply` Environment | `contents: read` | `contents: read` | `none`. Residual: `RULESETS_PAT` carries `Administration: Read and write` (admin-level); only place where repo settings can be PATCHed. Dispatch is `main`-ref guarded; `dry_run` default; `enable_auto_delete` is opt-in. | #56 (PAT handling), #181, #182 |
| `post-merge.yml` / `open-retro` | `pull_request_target: [closed]` (filter `merged == true`) | `GITHUB_TOKEN` | `contents: read`, `issues: write`, `pull-requests: write` | `contents: read`, `issues: write`, `pull-requests: write` | `none`. Residual: `pull_request_target` runs with the write token even when triggered by fork PRs; risk mitigated by `merged == true` filter (only merged PRs from the base repo reach this) and by the concurrency group keyed on PR number. | (none) |
| `publish-devcontainer-images.yml` | `push` to `main` with devcontainer/toolchain path filters + `workflow_dispatch` | `GITHUB_TOKEN` | build/publish: `contents: read`, `packages: write`; pin PR: `contents: write`, `pull-requests: write` | build/publish: `contents: read`, `packages: write`; pin PR: `contents: write`, `pull-requests: write` | `none`. Residual: publishes executable devcontainer images and non-runnable BuildKit cache tags to GHCR with `npx @devcontainers/cli@0.86.1`; the CLI version is exact-pinned in workflow env and the runnable images are tagged with both `main` and the source commit SHA. The generated pin commit and the PR are both authored by the GitHub App bot: the pin job mints a short-lived installation token at runtime via `actions/create-github-app-token` from `DEVCONTAINER_PIN_APP_ID` / `DEVCONTAINER_PIN_APP_PRIVATE_KEY` (Environment `devcontainer-image-pins`), so the PR author is `<app-slug>[bot]` and the commit identity is resolved to match; the branch push still uses the persisted-checkout `github-actions[bot]`. Completion is delegated to the `Auto-merge devcontainer pin PR` keeper (native auto-merge stays OFF). See #850, #1401. | #664, #696, #850, #1401 |
| `weekly-maintenance.yml` / `branch-cleanup` | `schedule` (weekly) + `workflow_dispatch` (task-gated inputs) | `GITHUB_TOKEN` via `env.GH_TOKEN` | `contents: read`, `issues: write`, `pull-requests: read` | `contents: read`, `issues: write`, `pull-requests: read` | `none`. Residual: survey-only today (no delete path); if [#31](https://github.com/tvna/claude-md/issues/31) Goal D lands a deletion path, `contents: write` against non-default branches would be required and a privileged-op runbook ([#182](https://github.com/tvna/claude-md/issues/182)) would apply. | #31 (delete path), #182 |
| `dependabot-automerge.yml` | `pull_request_target` (opened/synchronize/reopened/ready_for_review/labeled/unlabeled), filter `user.login == dependabot[bot]` | `GITHUB_TOKEN` via `env.GH_TOKEN` | `contents: read`, `pull-requests: write` | `contents: read`, `pull-requests: write` | `none`. Residual: `pull_request_target` write token is gated by the dependabot-only filter and by the allowlist in `.github/dependabot-automerge.json`. | (none) |
| `generate-agents.yml` | `workflow_dispatch` + `workflow_call` (input `mode`); weekly schedule is called by `weekly-maintenance.yml` | `GITHUB_TOKEN` via `env.GH_TOKEN` (set only on push/PR steps) | generate mode: `contents: write`, `pull-requests: write`. verify mode: `contents: read` only. | top-level `contents: write`, `pull-requests: write` | `over-grant: contents: write, pull-requests: write (on verify-mode invocations)`. The same workflow is reused as a callable for `verify-agents.yml` with `mode: verify`, which only diffs `CLAUDE.md` / `AGENTS.md` and never pushes; the broader scope is carried unnecessarily on that path. Residual: `curl` to `astral-sh/uv` release tarball is a supply-chain surface (already pinned by `uv_pin.py` per #112). | #181 (this audit), #183 (downstream review checklist) |
| `weekly-maintenance.yml` / `ruleset-drift` | `schedule` (weekly) + `workflow_dispatch` | `RULESETS_PAT` via `env.GH_TOKEN_API` (read-only use), `GITHUB_TOKEN` via `env.GH_TOKEN` (for issue filing) | `contents: read`, `issues: write` | `contents: read`, `issues: write` | `none`. Residual: `RULESETS_PAT` (admin scope) is consumed by a scheduled workflow without an Environment boundary; the apply workflows put the same PAT behind the `ruleset-apply` Environment, this one does not. The script only reads (`/repos/.../rulesets`), but PAT exposure scope is unchanged. | #56, #181 (Environment-scope this read PAT) |
| `issue-pr-triage.yml` / `scan` | `issues`, `pull_request_target`, `issue_comment`, `pull_request_review_comment` | `GITHUB_TOKEN` via `env.GH_TOKEN` | `contents: read`, `issues: write`, `pull-requests: write` | `contents: read`, `issues: write`, `pull-requests: write` | `none`. Residual: `pull_request_target` write token from fork PRs; gated by `actor != github-actions[bot]` and by trusted-bot allowlist in `_trusted_bots.py`. Documented in `docs/runbooks/non-ascii-defense.md`. | (none) |
| `weekly-maintenance.yml` / `security-control-drift` | `schedule` (weekly) + `workflow_dispatch` (task-gated input `security_control_dry_run` default true) | `RULESETS_PAT` via `env.GH_TOKEN_API` (read-only), `GITHUB_TOKEN` via `env.GH_TOKEN` (for posting rolling comment on #178) | `contents: read`, `issues: write` | `contents: read`, `issues: write` | `none`. Residual: same `RULESETS_PAT` exposure pattern as `ruleset-drift` (scheduled, not Environment-scoped). `curl` to astral-sh/uv supply chain (pinned per #112). | #56, #181 (PAT scoping), #180 (already closed by this workflow itself) |
| `weekly-maintenance.yml` / `dependency-threat-triage` | `schedule` (weekly) + `workflow_dispatch` (task-gated input `task=dependency-threat-triage`) | `GITHUB_TOKEN` via `env.GH_TOKEN` | `contents: read`, `issues: write` | `contents: read`, `issues: write` | `none`. Residual: posts one idempotent aggregated finding comment to the #178 umbrella (marker `<!-- threat-intel-aggregate v1 -->`); replaced the retired per-event `issue-pr-triage.yml` / `triage` job in #1645, so the prior `pull_request_target` fork-token exposure no longer applies. | #170 (sustained ops) |
| `verify-agents.yml` | `pull_request` | `GITHUB_TOKEN` via `env.GH_TOKEN` (in `lint-scripts` stale check only) | `contents: read` | `contents: read` | `none`. Agent instruction compile and prek moved to the `portable-pr-policy` job in `verify-pr.yml`; this workflow now covers repository-specific script checks only. | (none) |
| `verify-pr.yml` / `portable-pr-policy` | `pull_request` | `GITHUB_TOKEN` via `env.GH_TOKEN` (issue-link step only) | `contents: read`, `issues: read`, `pull-requests: read` | `(job: portable-pr-policy)` `contents: read`, `issues: read`, `pull-requests: read` (top-level `permissions: {}`) | `none`. Residual: `curl` to astral-sh/uv supply chain (pinned per #112); PR body is read from the event payload, and issue-link resolves referenced issues with the repository token. Consolidated in #1319; job `name:` preserved so the `Portable PR policy / gate` required context still resolves. | (none) |
| `verify-pr.yml` / `verify-design-philosophy` | `pull_request` | none | `contents: read` | `(job: verify-design-philosophy)` `contents: read` (top-level `permissions: {}`) | `none`. Consolidated in #1319. | (none) |
| `verify-pr.yml` / `verify-dependabot-labels` | `pull_request` | none | `contents: read` | `(job: verify-dependabot-labels)` `contents: read` (top-level `permissions: {}`) | `none`. Consolidated in #1319 (the workflow-level path filter was dropped on consolidation; the static check is cheap and now runs on every PR). | (none) |
| `verify-pr.yml` / `verify-ruleset-sync` | `pull_request` | `RULESETS_PAT` via `env.GH_TOKEN_API` (read-only use), scoped to the `ruleset-verify` Environment | `contents: read` | `(job: verify-ruleset-sync)` `contents: read` (top-level `permissions: {}`) | `none` on the workflow token. Residual: `RULESETS_PAT` (admin scope) is consumed on a `pull_request` trigger, gated by the `ruleset-verify` Environment; the job only reads (`/repos/.../rulesets`) to compare the live `main-protection` ruleset against the PR base ref's SoT. Consolidated in #1319. | #56, #120, #181 |
| `verify-github-content.yml` | `issues` (opened/edited/reopened) | `GITHUB_TOKEN` via `env.GH_TOKEN` | `contents: read`, `issues: read` | `contents: read`, `issues: read` | `none`. PR title/body/link checks moved to the `portable-pr-policy` job in `verify-pr.yml`; this workflow now covers issue title/body shape only. | (none) |

## Notes on privileged-mutation workflows

The three workflows below are the only ones whose declared minimum is `contents: read` while the *actual* mutation power they carry comes from an Environment-scoped fine-grained PAT. Their risk profile is therefore controlled by the PAT scope, the Environment gate, and the dispatch authorization criteria; not by the workflow `permissions:` block. The matrix above lists their workflow scope as `none` mismatch because the workflow token is correctly minimized; the residual surface is the PAT and its handling.

- `apply-labels.yml`; `LABELS_PAT` (`Issues: Read and write`); `labels-apply` Environment; dispatch `main`-ref guarded; `dry_run` default true; `prune` opt-in. See `docs/runbooks/issue-triage.md`.
- `apply-rulesets.yml`; `RULESETS_PAT` (`Administration: Read and write`); `ruleset-apply` Environment; dispatch `main`-ref guarded; `dry_run` default true; `enable_auto_delete` opt-in. See `docs/runbooks/rulesets.md`.
- `generate-agents.yml`; `GITHUB_TOKEN` (not a separate PAT), but the top-level `contents: write` + `pull-requests: write` are real mutation rights. The mitigation is that the workflow opens a PR rather than committing directly, so any change still goes through CI gates before reaching `main`.

## Note on generate workflow widening

`generate-agents.yml` declares `contents: write` and `pull-requests: write` at the top level because its primary generate mode pushes a branch and opens a PR. Earlier revisions also reused that workflow from `verify-agents.yml` in `mode: verify`, which attached the broader scopes to a read-only verification path. That reuse path has been removed: `verify-agents.yml` now runs repository script checks directly with `contents: read`, while agent instruction compile and prek moved to the `portable-pr-policy` job in `verify-pr.yml`.

The remaining least-privilege question is whether `generate-agents.yml` should be split into separate verify/generate workflows or keep the broader generate-mode declaration. That broader generate-mode surface remains tracked under #181.


## Note on `pull_request_target` exposure

Three `pull_request_target` surfaces carry write-capable tokens even for fork PRs:

- `post-merge.yml`; gated by `merged == true` (fork PRs cannot self-merge into base without maintainer review).
- `dependabot-automerge.yml`; gated by `user.login == dependabot[bot]`.
- `issue-pr-triage.yml` / `scan`; gated by `actor != github-actions[bot]` plus trusted-bot allowlist; intentional in this design (#102, `docs/runbooks/non-ascii-defense.md`). (The per-event `triage` job that also ran here was retired in #1645; threat-intel triage now runs in the scheduled `weekly-maintenance.yml` / `dependency-threat-triage` job, which is not `pull_request_target`.)

These workflows all check out the SoT (base branch) rather than the PR head, which is the standard `pull_request_target` mitigation. The audit confirms that pattern holds in every case above; no `pull_request_target` workflow checks out the PR head with the write-capable token attached.

## Gap summary

Follow-up issues this audit references (every "Follow-up" cell maps to one of the rows below; no new issues are opened by this audit):

| Issue | Scope (per its body) | Rows in matrix that reference it |
|---|---|---|
| #31 | Branch cleanup phased rollout (Goal D is the deletion path) | `weekly-maintenance.yml` / `branch-cleanup` |
| #56 | Ruleset PAT handling and privileged-dispatch hardening | `apply-rulesets.yml`, `weekly-maintenance.yml` |
| #170 | Sustained external threat-intelligence triage operations | `weekly-maintenance.yml` / `dependency-threat-triage` |
| #181 | Workflow permissions and PAT audit (least privilege matrix) | self-referenced; matrix rows that surface a `mismatch` other than `none`: `generate-agents.yml`, `weekly-maintenance.yml` |
| #182 | Privileged-operation runbook checklist (dry-run / authorization / rollback / audit) | `apply-labels.yml`, `apply-rulesets.yml`, `weekly-maintenance.yml` / `branch-cleanup` (delete path) |
| #183 | Downstream instruction review checklist | `generate-agents.yml` |

Surfaces explicitly marked `none` (no follow-up): `post-merge.yml`, `dependabot-automerge.yml`, `issue-pr-triage.yml` / `scan`, `weekly-maintenance.yml` / `dependency-threat-triage`, `verify-pr.yml` / `portable-pr-policy`, `verify-pr.yml` / `verify-design-philosophy`, `verify-pr.yml` / `verify-dependabot-labels`, `verify-github-content.yml`. The `verify-pr.yml` / `verify-ruleset-sync` job carries a `none` workflow-token mismatch but a residual `RULESETS_PAT` surface tracked under #56 / #181.

## Note on companion inventory

`docs/prd/security-control-inventory.md` Section 1 was originally written against 15 workflows. The inventory drifts from this matrix as workflows are added, removed, or grouped; the audit-side fan-out is tracked here. The inventory will be brought back in sync by a separate PR; updating it for surface-count parity is out of the scope of this audit (which is permissions-only).

## Verification

The exact rg command from the Verification section of [#181](https://github.com/tvna/claude-md/issues/181):

```bash
rg -n "permissions:|GITHUB_TOKEN|secrets\.|PAT|gh api|curl|workflow_dispatch|environment:" .github docs scripts
```

Expected reviewer behavior:

- Every match inside `.github/workflows/*.yml` falls into one of the rows in the *Permission matrix* above; matches in the same file appear together under that file's row.
- Matches in `docs/**` are documentation of these same workflows (notably `docs/runbooks/issue-triage.md`, `docs/runbooks/rulesets.md`, `docs/runbooks/branch-cleanup.md`, `docs/runbooks/non-ascii-defense.md`, `docs/runbooks/security-control-drift-report.md`, `docs/standards/workflow-script-quality.md`, `docs/standards/remote-environment.md`, `docs/prd/security-control-inventory.md`) and are absorbed by the matrix's *Token / secret* and *Mismatch* columns (the workflow row points at the documenting file via the script reference or the PAT name).
- Matches in `scripts/**` are the implementation of the same surfaces (`labels_apply.py`, `rulesets_apply.py`, `ruleset_drift.py`, `security_drift_report.py`, `scan_non_ascii.py`, `auto_retro.py`, `issue_link.py`, `branch_cleanup.py`, `dependabot_labels.py`, `_github_api.py`, `install-uv.sh`, `plan_language_context.py`); each is exercised by the workflow that imports it, so it is absorbed by the matrix indirectly. The `install-uv.sh` `curl` match is the SessionStart hook, separately documented in `docs/standards/remote-environment.md`.
- Matches that the matrix does not cover are a defect in this audit and should be added by a follow-up PR that updates this file.

Reviewers should also confirm:

- `ls .github/workflows/` files are each a row in the matrix (the surface-count is tracked separately per the companion-inventory note above).
- Every workflow has an explicit `permissions:` block (no `implicit default` rows in the matrix). Verified.
- Every `over-grant` row carries a follow-up issue number.

Closes #181.
