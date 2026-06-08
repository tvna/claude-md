# Runbook: default workflow permissions

Apply / verify / rollback runbook for the repository-level **default workflow
permissions** setting, managed declaratively from
[`.github/actions-permissions/workflow.json`](../../.github/actions-permissions/workflow.json).
Refs #1488, parent #178.

This is distinct from
[`workflow-permissions-audit.md`](workflow-permissions-audit.md), which audits
the per-job `permissions:` blocks declared inside each workflow YAML. This
runbook governs the *repository* toggle exposed at
`Settings -> Actions -> General -> Workflow permissions`.

## What is governed

The GitHub REST endpoint
`GET/PUT /repos/{owner}/{repo}/actions/permissions/workflow` exposes two fields,
both declared in the SoT file:

| Field | SoT value | Meaning |
|---|---|---|
| `default_workflow_permissions` | `read` | Least-privilege default scope for `GITHUB_TOKEN` when a job does not declare its own `permissions:`. |
| `can_approve_pull_request_reviews` | `true` | Whether GitHub Actions may create and approve pull requests. |

`can_approve_pull_request_reviews=false` is what made the `triage-report` job
(Post-merge automation) fail with
`HTTP 403: GitHub Actions is not permitted to create or approve pull requests`
(run 27163991424). Declaring it in the SoT plus the weekly drift detector makes
that regression detectable instead of silent.

## Source of truth

`.github/actions-permissions/workflow.json` carries exactly the two governed
keys. The apply path validates the shape (`read|write`, boolean) and rejects
unexpected keys before any live call.

## Apply (privileged, dispatch-gated)

Dispatch the **Apply rulesets** workflow
(`.github/workflows/apply-rulesets.yml`) with:

- `enable_workflow_permissions = true`
- `dry_run = true` first -> the run prints the SoT-vs-live diff and the current
  field values, and makes no live change.
- After reviewing the plan, dispatch again with `dry_run = false` to issue the
  `PUT`. The step re-reads the endpoint and records the resulting state in the
  job summary.

The underlying CLI (run inside the workflow, not by hand):

```
python3 scripts/rulesets_apply.py workflow-permissions \
  --repo "$REPO" \
  --sot-file .github/actions-permissions/workflow.json \
  --mode plan|apply \
  --summary-file "$GITHUB_STEP_SUMMARY"
```

## Drift detection (read-only, weekly)

The `security-control-drift` job in
`.github/workflows/weekly-maintenance.yml` runs the detector read-only:

```
python3 scripts/rulesets_apply.py workflow-permissions \
  --repo "$REPO" \
  --sot-file .github/actions-permissions/workflow.json \
  --mode drift \
  --summary-file "$GITHUB_STEP_SUMMARY"
```

`--mode drift` exits `1` when the live setting diverges from the SoT. The
exit code is folded into `scripts/security_drift_report.py` as the
`workflow-permissions` control family, which is at the `detect-and-file` floor
(`.github/security-control-floor.toml`): a divergence auto-files a
`fix(workflow-permissions-drift): ...` issue and shows up in the rolling
comment on #178.

## Required secret

Both the apply (`PUT`) and the read-only detector (`GET`) use `RULESETS_PAT`,
the same fine-grained PAT already provisioned for the ruleset workflows. The
endpoint requires the **Administration** repository permission (read for `GET`,
write for `PUT`), which the existing token already carries:

- `ruleset-apply` environment: `RULESETS_PAT` with Administration **write**
  (used by the apply step here).
- `ruleset-verify` environment: `RULESETS_PAT` with Administration **read**
  (reused by the weekly read-only detector).

No new secret is introduced. See
[`rulesets.md`](rulesets.md) "Required secret" for the issuance, storage,
minimum-permission, and <=90-day rotation procedure; rotation is tracked in
#1381.

## Rollback

- To revert the *managed intent*: `git revert` the commit that changed
  `.github/actions-permissions/workflow.json`, then re-dispatch apply with
  `dry_run=false` to push the prior values back to the live setting.
- To revert the *live setting* only, immediately: toggle
  `Settings -> Actions -> General -> Workflow permissions` in the UI, then make
  the SoT match so the weekly detector does not re-flag drift.

## Verification

- Unit tests: `uv run python -m pytest tests/test_rulesets_apply.py
  tests/test_security_drift_report.py`.
- Floor gate: `python3 scripts/verify_security_control_floor.py`.
- Live `PUT`/dry-run cannot run in CI or a sandbox (it needs the live GitHub
  endpoint and `RULESETS_PAT`); it is verified by the dispatch-gated apply run
  above.
