# SAST Tooling: CodeQL for Dataflow Taint Coverage

Tracked by [#1237](https://github.com/tvna/claude-md/issues/1237).

This standard records the decision to adopt **CodeQL** as the dataflow
(taint) static-analysis layer for the workflow scripts, and the explicit
rejection of Pyre and Pysa. It exists so the choice; and the alternatives
weighed against it; survive as a reviewable record rather than reviewer
memory (CLAUDE.md section 1).

## Problem

The `scripts/` tree runs under `pull_request_target` and handles
`GITHUB_TOKEN`/PAT. CLAUDE.md section 2 already classifies issue/PR bodies,
webhook payloads, and CI logs as untrusted data, so the real threat shape is
**untrusted source -> dangerous sink** (subprocess, urllib/HTTP, file writes,
GitHub API). Observed surface across `scripts/`: subprocess in 33 files,
urllib/HTTP in 24 files, token/environ references in 68 files.

Existing static controls; mypy (type gate, #192), ruff `S`/flake8-bandit
(pattern-based security lint, #190), and the pre-commit scanners
(scan-secrets, scan-workflow-injection, scan-workflow-pip); do **not**
perform interprocedural dataflow analysis. bandit-style checks are pattern
matches, not source->sink tracking. That dataflow gap is the problem.

## Adopted rule

- A CodeQL **advanced setup** workflow
  (`.github/workflows/codeql.yml`) analyzes the Python in `scripts/` using
  the `security-extended` query suite, scoped by
  `.github/codeql/codeql-config.yml` (`paths: [scripts]`).
- Advanced setup (not default setup) is mandatory here: the repo standard
  requires SHA-pinned actions and least-privilege `permissions:`, which
  default setup's hidden, GitHub-managed workflow cannot express.
- The CodeQL actions are SHA-pinned; the existing Dependabot
  `github-actions` weekly update keeps the pins fresh, so no extra update
  machinery is added.
- **Posture: informational first.** The workflow is intentionally not a
  required check. It graduates to required only after the baseline is clean,
  mirroring the coverage graduation policy in
  [`workflow-script-quality.md`](workflow-script-quality.md).

## Rejected alternatives

- **Pyre (standalone type checker): rejected.** It overlaps the existing
  mypy gate; migrating mypy -> pyre is churn against CLAUDE.md sections 4
  and 5 with little marginal value. Pyre is only justified as the Pysa
  engine, not on its own.
- **Pysa (taint analysis): rejected for now.** Pysa requires the Pyre engine
  plus hand-authored `.pysa` taint models for custom sources (e.g. "issue
  body from the GitHub API"), with ongoing false-positive tuning. The
  exploitable surface is also narrowed in practice because production
  subprocess calls use a fixed-argv shape (see the per-file-ignores note in
  `pyproject.toml`), reducing string-interpolation injection paths. CodeQL
  recovers the bulk of the dataflow gap with GitHub-native Python taint
  query packs and no bespoke model maintenance.

## Scope boundaries

- `tests/` is excluded from analysis: its fixtures carry deliberately
  insecure patterns (subprocess, `/tmp` paths, asserts) that would be false
  positives. This matches the `tests/*` per-file-ignores in `pyproject.toml`.
- Registration of CodeQL as a `security-control-floor.toml` family is
  **deferred**. That floor governs scheduled drift-detection families that
  auto-file a per-family issue; CodeQL is a PR/scheduled scanner of a
  different shape. Revisit registration in a follow-up once CodeQL graduates
  to a required check.

## Verification

CodeQL analysis runs on GitHub-hosted runners and cannot complete inside the
remote-execution container; verification therefore happens in CI on the PR,
not locally. A green workflow alone is not proof of coverage; confirm via
the Security tab / SARIF that files under `scripts/` were actually analyzed.
