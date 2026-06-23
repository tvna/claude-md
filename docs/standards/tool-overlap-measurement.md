# Tool Overlap Measurement Standard

Tracked by [#1618](https://github.com/tvna/claude-md/issues/1618), the
measurement follow-up to [#1610](https://github.com/tvna/claude-md/issues/1610).

[#1610](https://github.com/tvna/claude-md/issues/1610) provisioned three mature
single-binary tools to run **alongside** the bespoke deterministic gates they
overlap, and deliberately deferred the output comparison. This standard records
the contract for that comparison: what is measured, how it is recorded, how long
the window runs, and the rule that turns the recorded evidence into a
keep / replace / drop decision. It exists so the decision; and the data behind
it; survives as a reviewable record rather than reviewer memory (CLAUDE.md
section 1), and so anomaly detection is a table scan, not prose reading
(CLAUDE.md section 6).

## Why measure before deciding

Each new tool overlaps an existing gate but is not obviously a superset of it:

| Pair name | New tool | Existing gate(s) | Scanned scope |
|---|---|---|---|
| `workflow-static` | zizmor | [`scan_workflow_injection.py`](../../scripts/scan_workflow_injection.py) + [`scan_workflow_action_pins.py`](../../scripts/scan_workflow_action_pins.py) | `.github/workflows/` |
| `markdown-links` | lychee (`--offline`) | [`scan_markdown_links.py`](../../scripts/scan_markdown_links.py) | `DOC_GLOBS` markdown |
| `secrets` | betterleaks (`--redact=100`) | [`scan_secrets.py`](../../scripts/scan_secrets.py) | working tree, gitignore-respected |

Whether a new tool can **replace** a gate, must **run alongside** it, or should
be **dropped** is an empirical question. The measurement collects the evidence
to answer it instead of guessing. Nothing is removed during the window.

## What is measured (and recorded)

[`scripts/measure_tool_overlap.py`](../../scripts/measure_tool_overlap.py) runs
each new tool and its paired gate over the **same scope**, normalizes both sides
to `(rule_id, path, line)` findings, and records, per pair per run:

- each side's finding count (distinct `(path, line)` locations),
- the diff partition over locations; `agree`, `new-tool-only`,
  `existing-gate-only`; as both counts (in the record) and full listings (in
  the Markdown artifact), and
- each side's wall-clock duration.

Locations, not rule ids, key the diff: the two sides use different rule
vocabularies, so location coincidence is the meaningful overlap signal.

### Storage: matches the host-unit DuckDB convention

Records follow the existing metrics convention
([host-unit-duckdb-metrics.md](host-unit-duckdb-metrics.md)). The collector
emits a JSON record array whose keys are exactly the columns of the
`tool_overlap_measurement` table in
[`metrics/duckdb/schema/v3/schema.sql`](../../metrics/duckdb/schema/v3/schema.sql)
(schema v3, additive over v1/v2). The operator ingests the JSON into the
host-local DuckDB store locally; the workflow uploads the JSON as an artifact
rather than writing the DB, because ephemeral CI is out of scope for the
host-local store (the #826 decision). This is the report-plus-JSON shape
[`scripts/analyze_ci_timings.py`](../../scripts/analyze_ci_timings.py) set the
precedent for.

### Redaction (mandatory)

betterleaks is a secret scanner; its raw findings can contain live secret
values. The measurement records only non-sensitive **count / path / rule id**,
never a secret value (CLAUDE.md section 4, #88):

- betterleaks runs with `--redact=100`, so `Match`/`Secret` are redacted at the
  source, and
- the collector's parser reads only `RuleID`, the repo-relative `File`, and
  `StartLine`; it never reads the value fields, so the redaction boundary
  lives in our code, not only in the tool flag.

The secret value never reaches a record, the JSON, the Markdown, a log, the
step summary, the uploaded artifact, the commit, or the PR.

## Measurement window and stopping condition

- **Window.** Run the collector at least once per week for at least four weeks
  (>= 4 data points per pair), via the scheduled workflow, plus any manual
  `workflow_dispatch` runs. Manual runs accumulate into the same series.
- **Stopping condition.** Stop a pair's measurement once its `new-tool-only`
  and `existing-gate-only` sets are stable; the same locations across two
  consecutive runs at the same `commit_sha`; and at least the four-week
  minimum is met. A pair whose diff is still moving keeps measuring.

## Decision rule (keep / replace / drop)

Read the per-pair series in
[`metrics/duckdb/schema/v3/schema.sql`](../../metrics/duckdb/schema/v3/schema.sql)'s
`v_tool_overlap` view (or the Markdown table). For a settled pair:

- **REPLACE candidate.** `existing_gate_only_count == 0` across the whole window
  (the new tool covers everything the gate flags) **and** `new_tool_only_count`
  is consistently > 0 (it adds coverage). Propose replacing the gate in a
  separate follow-up issue; not in the measurement issue.
- **KEEP both.** `new_tool_only_count > 0` **and** `existing_gate_only_count > 0`
  across the window (each side has unique coverage). Keep running both.
- **DROP candidate (new tool).** `new_tool_only_count == 0` across the whole
  window (the new tool never adds anything the gate misses). Propose not
  adopting the new tool.

Two caveats the reader must weigh, recorded here as **facts** about the current
wiring (not speculation):

- The scopes are aligned but not identical. betterleaks scans Python files that
  `scan_secrets` delegates to ruff, so `secrets` `new-tool-only` findings
  include `.py` matches by construction; that is coverage the gate intentionally
  cedes, not a gate defect.
- zizmor audits a far broader surface than injection + unpinned-uses (for
  example `dangerous-triggers`, `artipacked`, `excessive-permissions`), so
  `workflow-static` `new-tool-only` is expected to be large; the REPLACE test
  only asks whether the gate's narrow surface is a subset, not whether the
  counts match.

The decision itself, and any removal or replacement, is **out of scope for the
measurement phase** (#1618) and belongs to a separate follow-up issue. This
phase only records.

## How to run

- **Locally / in a web session** (where the three binaries are provisioned by
  the [#1610](https://github.com/tvna/claude-md/issues/1610) SessionStart
  installers):

  ```sh
  python3 scripts/measure_tool_overlap.py \
    --scope-root . \
    --host-id "$CLAUDE_MD_HOST_ID" \
    --output records.json \
    --report report.md
  # then ingest locally (duckdb is not a repo dependency):
  ./metrics/duckdb/init.sh
  # apply the INSERT OR REPLACE template in the v3 schema file with records.json
  ```

- **In CI**: the scheduled / dispatchable
  [`.github/workflows/measure-tool-overlap.yml`](../../.github/workflows/measure-tool-overlap.yml)
  installs the pinned binaries, runs the collector, appends the Markdown table
  to the step summary, and uploads `records.json` + `report.md` as artifacts.

## SoT layout

| File / path | Purpose |
|---|---|
| `docs/standards/tool-overlap-measurement.md` *(this file)* | Adopted contract: what is measured, storage, redaction, window, stopping condition, decision rule |
| [`scripts/measure_tool_overlap.py`](../../scripts/measure_tool_overlap.py) | Deterministic collector: run each pair, diff, time, emit JSON records + Markdown report |
| [`metrics/duckdb/schema/v3/schema.sql`](../../metrics/duckdb/schema/v3/schema.sql) | Additive v3 schema: `tool_overlap_measurement` table + `v_tool_overlap` view + ingest template |
| [`.github/workflows/measure-tool-overlap.yml`](../../.github/workflows/measure-tool-overlap.yml) | Scheduled / dispatchable measurement run; uploads the artifacts |
| [`tests/test_measure_tool_overlap.py`](../../tests/test_measure_tool_overlap.py) | Static-contract + functional tests, including the adversarial redaction test |
