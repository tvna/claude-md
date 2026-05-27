# Maintainability Metrics Standard

This standard defines the repository's lightweight maintainability
metrics for Python scripts under `scripts/`. It complements
`docs/standards/workflow-script-quality.md`: lint, type, security, and
coverage gates verify code shape and test reach, while these metrics
track whether script structure is staying reviewable over time.

Issue #200 calls for useful metrics before broad scorecards. The first
deterministic pilot is module size because it is cheap to measure,
easy to explain in review, and tightly coupled to this repository's
existing rule that workflow-called scripts keep pure logic separated
from IO boundaries.

## Metric Inventory

| Metric | Signal | Current decision |
|---|---|---|
| module size | Large files are harder to review, test, and split at IO boundaries. | Pilot as a failing CI gate, with explicit baseline debt. |
| cyclomatic complexity | Deep branches make CLI and payload handling harder to reason about. | Candidate follow-up; reject as a gate until the baseline is measured and noisy parser branches are separated from command plumbing. |
| duplication | Repeated parsing, annotation, and GitHub API code hides drift. | Candidate follow-up; report first because generated examples and test fixtures can create false positives. |
| import graph shape | Cycles and broad shared helpers blur ownership boundaries. | Candidate follow-up; report first after deciding whether underscore-prefixed helper modules are the allowed shared boundary. |
| side-effect isolation | Functions that mix parsing, mutation, and rendering are hard to test deterministically. | Candidate follow-up; needs AST heuristics or code review checklist support before it can fail CI safely. |

## Pilot: Module Size

The pilot gate is `scripts/scan_maintainability_metrics.py verify`,
invoked from `.github/workflows/verify-agents.yml` in the
`lint-scripts-static` job.

Policy:

- Fails CI for any non-deferred Python module under `scripts/` above
  800 physical lines.
- Reports only for explicitly listed baseline debt, with a reason in
  `DEFERRED_OVERSIZE_MODULES`.
- Uses physical lines rather than parsed statements so large docstrings,
  examples, and dispatch tables still count against review burden.

Initial baseline:

| File | Status | Rationale |
|---|---|---|
| `scripts/auto_retro.py` | Reports only | Legacy retrospective aggregator currently combines parsing, GitHub IO, and rendering. It should be split in a follow-up PR before the module-size budget is tightened. |
| `scripts/threat_intel_triage.py` | Reports only | Legacy multi-source intelligence gate currently combines OSV, KEV, NVD, EPSS, and malicious-package adapters. Those adapters should be split before the module-size budget is tightened. |

## Threshold Rationale

The 800-line budget is intentionally above the existing cluster of
large-but-reviewable scripts and below the outliers that combine
multiple responsibilities. As of the pilot, all non-deferred scripts
sit below 800 physical lines; `scripts/auto_retro.py` and
`scripts/threat_intel_triage.py` are documented baseline debt rather
than precedent for future modules.

Changing this threshold requires updating this document, the scanner's
constant, and the tests in the same PR. Any new deferred exception must
state why the module cannot be split in the current PR and what later
work removes the exception.

## Verification

Run the deterministic checks locally before opening a PR:

```bash
uv run python scripts/scan_maintainability_metrics.py verify
uv run python -m pytest tests/test_scan_maintainability_metrics.py
```

The scanner is intentionally dependency-free and lives in the existing
uv-managed tool path; no new package or lockfile churn is required.
