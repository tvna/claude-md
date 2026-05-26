# Security control drift report — Runbook

Operator-facing companion to
[`.github/workflows/security-control-drift-report.yml`](../.github/workflows/security-control-drift-report.yml)
and [`scripts/security_drift_report.py`](../scripts/security_drift_report.py).
Tracks [#180](https://github.com/tvna/claude-md/issues/180) under parent
[#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK coverage).

## Purpose

One scheduled report that surfaces drift across the security-control families
already enumerated in [`docs/security-control-inventory.md`](./security-control-inventory.md).
The workflow does **not** duplicate any detector: it invokes the existing
read-only entry points (`ruleset_drift.py detect`, `labels_apply.py plan`,
`apm compile` + `git diff`, `uv_pin.py drift`, `uv_pin.py stale`), then
aggregates the outcomes into a single Markdown table and posts (or updates)
a rolling comment on the parent tracking issue.

Per-family detectors keep their own gates and own per-family issue-filing
paths (e.g. `ruleset-drift.yml` continues to file SoT drift / unknown
ruleset issues on the existing weekly cron). This aggregator only reports;
it never opens a new issue and never auto-remediates.

## Trigger

| Trigger | Cron | Effect |
|---|---|---|
| `schedule` | `0 23 * * 0` (UTC) — Mon 08:00 JST | Always assembles the report and updates the rolling comment on #178 (the `dry_run` field is forced to `false`). |
| `workflow_dispatch` | manual | Assembles the report; `dry_run` input defaults to `true` (no comment) so an operator can preview the table in the step summary before publishing. |

Cron offset rationale: `branch-cleanup.yml` runs at `0 20 * * 0` and
`ruleset-drift.yml` at `0 21 * * 0`. The aggregator is scheduled at
`0 23 * * 0` so the detectors it reads (notably `uv_pin.py stale`, which
calls `astral-sh/uv` release API) are not contending with the ruleset
detection step.

## Families covered

| Family | Detector entry point | Notes |
|---|---|---|
| `rulesets` | `scripts/ruleset_drift.py detect` | Requires `RULESETS_PAT` (read-only PAT, same secret as `ruleset-drift.yml`). Outputs `drift_count` / `unknown_count`. |
| `labels` | `scripts/labels_apply.py plan` | Uses `GITHUB_TOKEN` (metadata read suffices). Summary file is parsed for `plan-only` / `report-only` rows. |
| `apm-instructions` | `apm compile` + `git diff --exit-code -- CLAUDE.md AGENTS.md` | Compile is pinned via `APM_CLI_VERSION` env (`0.12.1`) and `uv run --with apm-cli==<pin> --exclude-newer "14 days"` to suppress transient drift, mirroring `verify-apm-drift.yml`. |
| `uv-pin-literal` | `scripts/uv_pin.py drift` | Asserts the pin literal lives only in `pyproject.toml`. |
| `uv-pin-staleness` | `scripts/uv_pin.py stale` | Informational; emits `::warning::` when the pin trails upstream latest. |

## Families pending (recorded as `pending` rows)

| Family | Status reason |
|---|---|
| `title-policy` (`verify-title-policy.yml`) | PR-gate only; no scheduled drift surface beyond PR review. |
| `non-ascii` (`scan-non-ascii.yml`, `preflight_non_ascii.py`) | PR-gate only. |
| `dependabot-labels` (`verify-dependabot-labels.yml`) | PR-gate only. |
| `required-checks` (live vs `.github/rulesets/main.json`) | Tracked separately by [#120](https://github.com/tvna/claude-md/issues/120); intentionally out of scope here. |

## Rolling comment

- Lives on parent issue [#178](https://github.com/tvna/claude-md/issues/178).
- Single comment identified by the HTML marker
  `<!-- security-control-drift-report -->` at the top of the body.
- On each cron run the workflow `GET`s the issue's comments, locates the
  marker, and either `PATCH`es the existing comment in place or `POST`s a
  new one if absent. The aggregator never opens a new issue.

## Dry-run preview

1. Go to **Actions → Security control drift report → Run workflow**.
2. Leave `dry_run` as `true` (default).
3. After the run completes, open the run page and read the **Summary** tab
   — the assembled Markdown table is appended to `$GITHUB_STEP_SUMMARY`.
4. Confirm the table rows look as expected. No comment is posted on #178
   while `dry_run=true`.

## Investigating a `drift` row

| Row | Where to act |
|---|---|
| `rulesets` | Follow the per-family issue filed by `ruleset-drift.yml` (SoT-vs-live drift or unknown-ruleset). See `docs/rulesets.md`. |
| `labels` | Dispatch `apply-labels.yml` with `dry_run=false` after reviewing the plan summary. See `docs/issue-triage.md`. |
| `apm-instructions` | Locally run `uv run --with "apm-cli==<pin>" --exclude-newer "14 days" apm compile` and commit the regenerated `CLAUDE.md` / `AGENTS.md`. |
| `uv-pin-literal` | Remove the offending pin literal outside `pyproject.toml`, or update `pyproject.toml`. See `docs/remote-environment.md`. |
| `uv-pin-staleness` | Informational. Bump `[tool.uv].required-version` in `pyproject.toml` when ready to adopt the newer uv. |

A row with `status=error` means the detector itself failed (network blip,
transient API error, etc.); inspect the corresponding step log on the run
page. The aggregator deliberately keeps reporting (`exit 0`) so a single
detector failure does not hide the status of the remaining families.

## Rollback

The aggregator is read-only and idempotent — it only `GET`s detector
outputs and `PATCH`es / `POST`s a single comment on a tracking issue. To
roll back, disable the workflow via **Actions → Security control drift
report → Disable workflow**; no repository state changes need reverting.
