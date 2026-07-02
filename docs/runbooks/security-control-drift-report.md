# Security control drift report; Runbook

Operator-facing companion to
[`.github/workflows/weekly-maintenance.yml`](../../.github/workflows/weekly-maintenance.yml)
and [`scripts/security_drift_report.py`](../../scripts/security_drift_report.py).
Tracks [#180](https://github.com/tvna/claude-md/issues/180) under parent
[#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK coverage).

## Scope

One scheduled report that surfaces drift across the security-control families
already enumerated in [`docs/prd/security-control-inventory.md`](../prd/security-control-inventory.md).
The workflow does **not** duplicate any detector: it invokes the existing
read-only entry points (`ruleset_drift.py detect`, `labels_apply.py plan`,
`apm compile` + `git diff`, `uv_pin.py drift`, `uv_pin.py stale`), then
aggregates the outcomes into a single Markdown table and posts (or updates)
a rolling comment on the parent tracking issue.

Per-family detectors keep their own gates. The `rulesets` family files via its
own `ruleset-drift` weekly-maintenance job (SoT drift / unknown ruleset issues).
To meet the `detect-and-file` floor (`.github/security-control-floor.toml`), the
`security-control-drift` job also runs `security_drift_report.py
file-family-issues` after aggregation. As of #1726 this **reconciles a single
rolling issue per target family** (`labels`, `apm-instructions`,
`uv-pin-literal`, `workflow-permissions`) instead of filing a fresh issue each
run, mirroring the `ruleset-drift` reconcile pattern:

- drifting + no open rolling issue -> create one (stable, date-free title);
- drifting + open rolling issue(s) -> keep the oldest, close any extras as
  superseded (this consolidates the legacy dated duplicates filed before #1726);
- explicitly covered (clean) + open rolling issue(s) -> **auto-close** them;
- explicitly covered + none -> stay silent;
- detector error / unknown -> leave any open rolling issue untouched.

The step is driven by two aggregate outputs: `drift_families` (the families in
drift) and `covered_families` (families with an EXPLICIT clean status). Only a
covered family is auto-closed; a family whose detector errored appears in neither
list, so a transient failure cannot auto-close and thereby hide an active drift
issue (a #1730 review finding). The step runs unconditionally (no
`drift_families != ''` gate) so a family that becomes clean can have its issue
auto-closed without an operator.
The aggregator itself never auto-remediates the underlying control (labels are
still applied only via the manual `apply-labels.yml` dispatch); only the
`file-family-issues` step manages the per-family issue lifecycle, and the
rolling-comment path never opens an issue.

## Why

This single scheduled report exists so drift across several security-control
families is visible in one place on a fixed cadence, instead of each family's
drift being noticed only when someone happens to run its detector. It
deliberately reuses the existing read-only detector entry points rather than
duplicating them, so the report adds visibility without adding a second source
of truth to maintain. The push trigger on control-family SoT paths shortens the
detection window from up to a week to near-immediate.

## Why not

This report is a visibility aggregator, not an enforcement gate and not a
remediator. Do not rely on it to block a bad change at PR time: each family
keeps its own authoritative gate (the `ruleset-drift` job, the PR-time
`lint-scripts-static` OWASP check, `verify-pr.yml`), and those are where a
violation is actually stopped. Do not expect it to fix drift either; it only
reconciles a rolling per-family issue and updates a comment. When you need to
apply a control (for example apply labels), use that family's manual dispatch
(`apply-labels.yml`), not this job.

## Trigger

| Trigger | Cron | Effect |
|---|---|---|
| `schedule` | `0 20 * * 0` (UTC); Mon 05:00 JST | Always assembles the report and updates the rolling comment on #178 (the dry-run field is forced to `false`). |
| `workflow_dispatch` | manual | Select `task=security-control-drift`; the `security_control_dry_run` input defaults to `true` (no comment) so an operator can preview the table in the step summary before publishing. |
| `push` (on `main`; control-family SoT paths) | event-driven (#1390) | A change to `.github/rulesets/**`, `.github/labels.json`, `.apm/instructions/**`, `pyproject.toml`, `CLAUDE.md`, or `AGENTS.md` runs this job immediately (dry-run forced to `false`), so drift is caught near the change instead of up to a week later. Every other weekly job is skipped on push. |

The weekly maintenance workflow intentionally runs these jobs on the same
JST Monday 05:00 trigger to reduce scheduled workflow sprawl.

## Families covered

| Family | Detector entry point | Notes |
|---|---|---|
| `rulesets` | `scripts/ruleset_drift.py detect` | Requires `RULESETS_PAT` (read-only PAT, same secret as the `ruleset-drift` job). Outputs `drift_count` / `unknown_count`. |
| `labels` | `scripts/labels_apply.py plan` | Uses `GITHUB_TOKEN` (metadata read suffices). Summary file is parsed for `plan-only` / `report-only` rows. |
| `apm-instructions` | `apm compile` + `git diff --exit-code CLAUDE.md AGENTS.md` | Compile is pinned via `APM_CLI_VERSION` env (resolved from `flake.nix` by `.github/actions/resolve-apm-version`, see `scripts/flake_pin.py version --tool apm`) and `uv run --with apm-cli==<pin> --exclude-newer "14 days"` to suppress transient drift, mirroring `verify-pr.yml`. |
| `uv-pin-literal` | `scripts/uv_pin.py drift` | Asserts the pin literal lives only in `pyproject.toml`. |
| `uv-pin-staleness` | `scripts/uv_pin.py stale` | Informational; emits `::warning::` when the pin trails upstream latest. |
| `owasp-asi-mapping` | `scripts/owasp_asi_mapping.py verify` | Tree-only completeness check that `docs/prd/security-control-inventory.md` carries an ASI01-ASI10 status row per item (peer axis to the ATT&CK mapping). Authoritative enforcement is the PR-time `lint-scripts-static` gate; this weekly row is a redundant visibility signal, so a drift here is unreachable on `main`. |

## Families pending (recorded as `pending` rows)

| Family | Status reason |
|---|---|
| `title-policy` (`verify-pr.yml` `portable-pr-policy` job for PR titles; `verify-github-content.yml` for issue titles) | PR-gate only; no scheduled drift surface beyond PR review. |
| `non-ascii` (`issue-pr-triage.yml` / `scan`, `preflight_non_ascii.py`) | PR-gate only. |
| `dependabot-labels` (`verify-pr.yml`) | PR-gate only. |
| `required-checks` (live vs `.github/rulesets/main.json`) | Tracked separately by [#120](https://github.com/tvna/claude-md/issues/120); intentionally out of scope here. |

## Rolling comment

- Lives on parent issue [#178](https://github.com/tvna/claude-md/issues/178).
- Single comment identified by the HTML marker
  `<!-- security-control-drift-report -->` at the top of the body.
- On each cron run the workflow `GET`s the issue's comments, locates the
  marker, and either `PATCH`es the existing comment in place or `POST`s a
  new one if absent. The aggregator never opens a new issue.

## Procedure

Two operator tasks run against this report: preview the assembled table before
it publishes, and act on a row that shows drift.

### Dry-run preview

1. Go to **Actions -> Weekly maintenance -> Run workflow**.
2. Select `task=security-control-drift` and leave `security_control_dry_run` as `true` (default).
3. After the run completes, open the run page and read the **Summary** tab
  ; the assembled Markdown table is appended to `$GITHUB_STEP_SUMMARY`.
4. Confirm the table rows look as expected. No comment is posted on #178
   while `dry_run=true`.

### Investigating a `drift` row

| Row | Where to act |
|---|---|
| `rulesets` | Follow the per-family issue filed by the `ruleset-drift` weekly-maintenance job (SoT-vs-live drift or unknown-ruleset). See `docs/runbooks/rulesets.md`. |
| `labels` | Dispatch `apply-labels.yml` with `dry_run=false` after reviewing the plan summary. See `docs/runbooks/issue-triage.md`. |
| `apm-instructions` | Locally run `uv run --with "apm-cli==<pin>" --exclude-newer "14 days" apm compile` and commit the regenerated `CLAUDE.md` / `AGENTS.md`. |
| `uv-pin-literal` | Remove the offending pin literal outside `pyproject.toml`, or update `pyproject.toml`. See `docs/standards/remote-environment.md`. |
| `uv-pin-staleness` | Informational. Bump `[tool.uv].required-version` in `pyproject.toml` when ready to adopt the newer uv. |
| `owasp-asi-mapping` | Restore the dropped ASI01-ASI10 status row in `docs/prd/security-control-inventory.md`. This should be unreachable on `main` (the PR-time `lint-scripts-static` gate blocks an incomplete mapping); a `drift` row here means the gate was bypassed or the detector itself changed. |

A row with `status=error` means the detector itself failed (network blip,
transient API error, etc.); inspect the corresponding step log on the run
page. The aggregator deliberately keeps reporting (`exit 0`) so a single
detector failure does not hide the status of the remaining families.

## Verification

Confirm the report ran and reflects current state:

- The rolling comment on #178 (marked `<!-- security-control-drift-report -->`)
  carries a recent timestamp matching the latest scheduled or push-triggered
  run.
- A dry-run dispatch (`task=security-control-drift`,
  `security_control_dry_run=true`) renders the family table in the run's
  **Summary** tab with no unexpected `error` row.
- For a family showing a clean (`covered`) status, no stale rolling issue
  remains open for it; the `file-family-issues` step auto-closes covered
  families.

## Pause / Resume

This is a recurring weekly (plus push-triggered) automation.

- **Pause.** **Actions -> Weekly maintenance -> Disable workflow** stops both
  the scheduled run and the push-triggered run. Before pausing, note the
  timestamp of the current rolling comment on #178 so that on resume you can
  tell whether any run was missed.
- **Resume.** Re-enable the workflow. The next scheduled or push-triggered run
  rebuilds the table from live detector output and `PATCH`es the same rolling
  comment in place, so no backfill is needed; a missed week leaves no gap beyond
  the delayed signal.

## Rollback

The aggregator is read-only and idempotent; it only `GET`s detector
outputs and `PATCH`es / `POST`s a single comment on a tracking issue. To
roll back, disable the workflow via **Actions -> Weekly maintenance -> Disable
workflow**; no repository state changes need reverting.

## References

- [`.github/workflows/weekly-maintenance.yml`](../../.github/workflows/weekly-maintenance.yml) --
  the `security-control-drift` job this runbook drives.
- [`scripts/security_drift_report.py`](../../scripts/security_drift_report.py) --
  the read-only aggregator entry point.
- [`docs/prd/security-control-inventory.md`](../prd/security-control-inventory.md) --
  the control-family inventory the report rolls up.
- [`docs/runbooks/attack-coverage-review-cadence.md`](attack-coverage-review-cadence.md) --
  the monthly structured-review channel that sits alongside this weekly
  live-signal channel.
- [`docs/runbooks/rulesets.md`](rulesets.md); the `rulesets` family's own drift
  job and runbook.
- [#180](https://github.com/tvna/claude-md/issues/180) under parent
  [#178](https://github.com/tvna/claude-md/issues/178); MITRE ATT&CK coverage
  tracking issues.
