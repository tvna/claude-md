# Workflow Script Quality Standard

> Design rationale: see [`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md). This standard is the closest thing this repository has to a deterministic principle-P4 quality gate; the meta-doc cites it as the carrier of harness-lane quality for the artifact-code layer.

This document is the contributor- and agent-facing standard for Python
scripts under `scripts/` that are invoked from GitHub Actions workflows
under `.github/workflows/`. It defines the minimum quality gates every
new or modified workflow-called script must meet, and lists optional
enhancements that may be added when the script's blast radius or
external coupling warrants them.

Per [CLAUDE.md](../../CLAUDE.md) section 3, deterministic harness work
belongs in hooks and CI rather than reviewer memory; this standard is
the checklist a reviewer (human or agent) applies before a script
lands. Per section 4, the must-have list never strips a check that
prevents harm: dry-run defaults, secret handling, input validation,
and loud failure are all encoded as must-have items.

## Scope

A "workflow-called script" is any Python module under `scripts/` that
satisfies all of the following:

- It is invoked from at least one workflow under `.github/workflows/`
  via `python3 scripts/<name>.py ...`.
- It has a stable CLI contract (subcommands, flags, env vars) that the
  workflow YAML depends on.
- It may read repository state (files, GitHub API) and may produce
  side effects: GitHub API writes, status annotations, summary output,
  issue comments, or local file changes consumed downstream.

Shared library modules under `scripts/` whose name starts with an
underscore (`scripts/_github_api.py`, `scripts/_trusted_bots.py`) are
not workflow entry points and are not directly in scope. They should
nevertheless meet the same testing and validation expectations,
because the entry-point scripts inherit their behaviour.

Out of scope for this document:

- Shell-only workflow steps that do not call a Python module.
- Local developer tooling that is never invoked by a workflow.
- The `.apm/instructions/` source-of-truth tree, which has its own
  compilation contract.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `docs/standards/workflow-script-quality.md` *(this file)* | - | Standard runbook |
| `pyproject.toml` `[tool.pytest.ini_options]` | local + CI | `pythonpath = ["scripts"]`, `testpaths = ["tests"]` so test modules can `import <name>` directly |
| `scripts/_github_api.py` | shared library | Reusable HTTP boundary with retry and `Authorization: Bearer` handling |
| `scripts/_trusted_bots.py` | shared library | Single source of truth for the trusted-bot allowlist |
| `.github/workflows/verify-*.yml` | GitHub Actions | Read-only gate invocations (representative pattern) |
| `.github/workflows/apply-*.yml` | GitHub Actions | Write-side dispatch invocations with `dry_run` input (representative pattern) |

## Must-have checks

Every new or modified workflow-called script must satisfy each item
below before merge. These are gates, not suggestions: if an item is
intentionally skipped, the PR body must record why.

### M1. Module shape: pure functions on top, thin IO boundary at the bottom

Logic lives in pure functions that take primitive or dataclass inputs
and return primitive or dataclass outputs. The only side-effecting
surface is a single `main(argv)` function plus, at most, one
subprocess or HTTP boundary helper. Tests monkeypatch the boundary;
they do not need to monkeypatch the logic.

Reference implementation: `scripts/scan_non_ascii.py` follows the
pattern documented in its module docstring; `scripts/uv_pin.py` is the
prior art that pattern was extracted from.

### M2. Unit tests under `tests/test_<name>.py`

Every workflow-called script has a matching test module. `pytest -q`
from the repository root must exit 0. Tests exercise pure functions
directly; tests for the boundary use monkeypatch to inject fakes.

The `[tool.pytest.ini_options]` block in `pyproject.toml` already sets
`pythonpath = ["scripts"]` and `testpaths = ["tests"]`, so a test
module simply imports the script by basename:

```python
import issue_link
```

### M3. CLI contract tests

The argparse subcommand surface, required and optional flags, and
environment-variable fallbacks are locked by tests that exercise
`main(argv)` directly (or `subprocess.run` for end-to-end coverage of
exit codes). The workflow YAML invocation is part of the contract; if
the YAML calls `--body-file` and falls back to `PR_BODY`, both paths
must have a test.

Reference: `tests/test_issue_link.py` covers both the body-file path
and the env-var fallback path of `scripts/issue_link.py`.

### M4. Input validation at boundaries

Every input that crosses the workflow-to-script boundary is validated
before use. String booleans (`"true"` / `"false"`) are parsed with a
helper that rejects any other value. Numeric inputs are checked for
sign and range. Enumerated inputs are checked against a `frozenset`
allowlist. Unknown event types raise rather than producing an empty
result.

Reference: `scripts/branch_cleanup.py` `parse_dry_run` and
`parse_min_age_days` reject malformed inputs with `ValueError`;
`scripts/preflight_non_ascii.py` `_TARGET_TOOLS` is a `frozenset`
allowlist.

### M5. GitHub output and summary contracts

Scripts that need to surface results to GitHub Actions use the
documented contracts, not ad-hoc stdout parsing:

- Step summary: `--summary-file "$GITHUB_STEP_SUMMARY"` (the script
  writes Markdown to the path the runner provides).
- Step outputs: `--github-output "$GITHUB_OUTPUT"` (the script
  appends `name=value` lines to the path the runner provides).
- Errors: `::error::<message>` (and `::warning::`, `::notice::`) on
  stdout, so the GitHub Actions UI surfaces them inline.

Reference: `.github/workflows/apply-rulesets.yml` passes
`--summary-file "$GITHUB_STEP_SUMMARY"`;
`.github/workflows/branch-cleanup.yml` passes both
`--github-output "${GITHUB_OUTPUT}"` and writes the step summary via
shell redirection.

### M6. Dry-run / plan-only default for mutating scripts

Any script that can mutate GitHub state, repository files, or external
systems exposes a `--dry-run` mode (or equivalent plan-only
subcommand) and the workflow's `workflow_dispatch.inputs.dry_run`
defaults to `true`. The mutation path is enabled only by an explicit
`dry_run=false` from a privileged dispatch.

Read-only gates (the `verify-*.yml` family) do not need a dry-run
mode; they are already non-mutating by construction.

Reference: `.github/workflows/apply-rulesets.yml` and
`.github/workflows/branch-cleanup.yml` both default `dry_run` to
`true`; `scripts/rulesets_apply.py` and `scripts/branch_cleanup.py`
honour the flag.

### M7. Secret handling

Tokens and other secrets are read from environment variables, never
from CLI arguments (which would leak into `ps` listings and into
GitHub Actions step logs when echoed). The script does not print
secrets to stdout or stderr. HTTP calls funnel through
`scripts/_github_api.py` so the `Authorization: Bearer <token>`
header is constructed in exactly one place.

Workflows guard required secrets with a loud `Guard <SECRET>` step
that exits 1 with `::error::` when the secret is unset. Reference:
the `Guard RULESETS_PAT` step in
`.github/workflows/apply-rulesets.yml`.

### M8. Lint, type, and coverage gates

Scripts are written so they pass the repository's lint, type, and
coverage gates when those gates land. Concretely:

- Type hints on every public function signature and on every
  non-trivial local variable.
- No unused imports, no shadowed builtins, no bare `except:`.
- Pure functions are individually testable so coverage threshold gates
  can be met without integration tests.

The repository runs `pytest` with `pytest-cov` (#188, threshold in
`[tool.coverage.report]`), `ruff check` (#192, lint rules in
`[tool.ruff.lint]`), and `mypy` (#192, type rules in `[tool.mypy]`)
as the Python gates in CI. New scripts must pass all three on first
commit; the configuration of record is `pyproject.toml`. A subset of
pre-existing files is listed under `[[tool.mypy.overrides]]` with
`ignore_errors = true` and an inline rationale; those entries are
deferred type-debt and must be removed (not extended) as follow-up
PRs clean each cluster.

`scripts/scan_maintainability_metrics.py` (#200) runs alongside those
shape gates and enforces the first maintainability pilot: an 800-line
module-size budget for scripts, with explicit baseline debt documented
in `docs/standards/maintainability-metrics.md`.

`ruff check` includes the `S` (flake8-bandit) rule family (#190) so the
same gate also acts as a static security check for workflow-called
scripts: `subprocess` invocations, `urllib` HTTP boundaries, hardcoded
`/tmp` paths, and assertions in production code are flagged. When a
finding cannot be safely refactored away, suppress it inline with
`# noqa: S<NNN>` followed by a single-sentence justification on the
preceding comment line (search the tree for `# S310 justification:` or
`# S603 justification:` for the established phrasing). Test fixtures
that legitimately require the suppressed patterns (`assert`, dummy
token strings, `/tmp` labels) are covered by the file-scoped entries
under `[tool.ruff.lint.per-file-ignores]` rather than individual
`# noqa` lines. The self-test in `tests/test_ruff_security_gate.py`
pins this configuration and verifies that the gate still rejects a
deliberately unsafe sample.

### M9. Fail-loud vs fail-open policy

Each script declares in its module docstring whether it is a gate
(fails loud, exits non-zero on unexpected input) or a hook (fails
open, exits zero with an `::error::` annotation when input is
malformed so the hook never wedges the session).

- Gates: `scripts/title_policy.py`, `scripts/issue_link.py`,
  `scripts/scan_non_ascii.py`, `scripts/body_policy.py`.
- Hooks: `scripts/preflight_non_ascii.py` (its docstring states
  explicitly: "Fails open per CLAUDE.md section 4: any parse error or
  unexpected payload shape ... exits 0 with no decision").

Per CLAUDE.md section 4, "when a check IS warranted, fail loudly".
The hook exception exists only because a session-blocking hook bug
would be worse than the gate it backs up; the server-side gate
remains as backstop.

### M10. Standardised dependency and tool installation

Workflow jobs that run Python tooling install dependencies through a
single uv-managed channel. The dev dependency group in
`pyproject.toml` is the source of truth, `uv.lock` pins the resolved
graph, and every CI job that uses a script-quality tool reaches it
via `uv sync --locked` followed by `uv run <tool>`.

Canonical install primitives:

| Need | Primitive | Where it is declared |
|---|---|---|
| Repository-wide quality tools (pytest, ruff, mypy, ...) | `uv sync --locked` then `uv run <tool>` | `[dependency-groups].dev` in `pyproject.toml` |
| Pinned one-off CLI used only inside CI (apm-cli today) | `uv run --with "<pkg>==<X.Y.Z>" --exclude-newer "<N> days" <cmd>` | inline in the workflow YAML, version supplied via workflow env var |
| Editor-style tool with its own venv (prek today) | `uv tool run <tool>` | inline in the workflow YAML |

Direct `pip install`, `pip3 install`, `python -m pip install`, and
`python3 -m pip install` are forbidden in workflow YAML.
`scripts/scan_workflow_pip.py` is the deterministic gate (#289) and is
invoked from `verify-agents.yml`'s `lint-scripts-static` job. A
genuine one-off bypass appends `<!-- pip-install-ack -->` on the same
line and must be justified in the PR body; the marker is a review
artefact, not a silent escape hatch.

Procedure for adding a new script-quality tool:

1. Add the package to `[dependency-groups].dev` in `pyproject.toml`
   with a bounded major range (for example `>=1.11,<2`), and add an
   inline comment that cites the issue introducing the tool. Follow
   the existing entries for `ruff` and `mypy` as the prior art.
2. Run `uv lock` locally so `uv.lock` reflects the resolved graph;
   commit `pyproject.toml` and `uv.lock` together so reviewers see a
   single deterministic state change.
3. Add the CI step that exercises the tool via `uv run <tool>` to the
   appropriate workflow (typically a new step under
   `lint-scripts-static` or `lint-scripts-pytest` in
   `verify-agents.yml`). Reuse the existing `uv sync --locked` step
   in that job; do not introduce a second install primitive.
4. If the new tool needs a configuration block, place it in
   `pyproject.toml` alongside `[tool.ruff]` and `[tool.mypy]` so the
   single source of truth stays single.
5. Open the PR with `Refs #<issue>` and confirm
   `uv run python scripts/scan_workflow_pip.py verify` still passes
   locally before requesting review.

Reference: `pyproject.toml` `[dependency-groups].dev` and
`scripts/scan_workflow_pip.py` jointly enforce this gate today
(#192, #289, #195).

## Optional enhancements

The items below are not gates. Add them when the script's blast
radius, external coupling, or historical bug pattern warrants the
extra investment.

### O1. Property-based or fuzz tests

When the script parses user-authored prose or untrusted JSON, add
property-based tests (e.g. Hypothesis) that exercise the parser on
generated inputs. Consider this when the script has shipped a parser
bug, or when the parser sits on an injection-relevant boundary.

### O2. Fixture-driven external API tests

When the script consumes an external API, add a `--<source>-file`
flag that reads the same shape from disk so tests can run without
network access. Reference: `scripts/threat_intel_triage.py` exposes
`--osv-file` and `--kev-file` for exactly this purpose.

### O3. Workflow invocation drift verification

When the workflow YAML and the script's argparse surface drift,
silent breakage results. A periodic check that parses the YAML and
the argparse spec and asserts they agree closes the loop. Tracked by
issue #193.

### O4. Coverage thresholds

A per-module coverage floor catches regressions where new branches
land without tests. Tracked by issue #188. Until that lands, aim for
"every pure function has at least one positive and one negative
test."

### O5. Pydantic-based input modelling

For scripts that accept rich nested input (JSON event payloads, multi-
field configs), modelling the input with pydantic gives a single
declarative validation surface and better error messages than hand-
written `isinstance` checks. Tracked by issue #191.

### O6. GitHub API boundary contract tests

For scripts that talk to the GitHub API, contract tests that record
the request shape (method, URL, headers, body keys) catch regressions
when the boundary helper changes. Tracked by issue #194.

Note: the original O7 placeholder ("Standardised dependency and tool
installation") was promoted to must-have rule M10 above in #195. It is
no longer optional; new script-quality tools must follow the M10
procedure.

## Worked example: minimal script skeleton

```python
#!/usr/bin/env python3
"""<one-line purpose>.

The workflow `.github/workflows/<name>.yml` invokes this module.

Contract:
- Inputs: <flag list and env-var fallbacks>.
- Outputs: <stdout shape>, <summary file shape>, <exit codes>.
- Failure policy: fails <loud|open> per CLAUDE.md section 4.

Tested by `tests/test_<name>.py`. Refs #<issue>.
"""
from __future__ import annotations

import argparse
import os
import sys


def parse_dry_run(raw: str) -> bool:
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"Invalid dry_run value: {raw}")


def do_work(dry_run: bool) -> int:
    # Pure function: returns the intended exit code; no IO here.
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", required=True)
    args = parser.parse_args(argv)
    return do_work(parse_dry_run(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
```

## Worked example: minimal workflow invocation

```yaml
name: <name>

on:
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Plan only (no live changes)'
        type: boolean
        required: true
        default: true

permissions:
  contents: read

jobs:
  run:
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      REPO: ${{ github.repository }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
      - name: Run <name>
        run: |
          set -euo pipefail
          python3 scripts/<name>.py \
            --dry-run "${{ inputs.dry_run }}" \
            --summary-file "$GITHUB_STEP_SUMMARY"
```

For write-side scripts that need a privileged PAT, add a guard step
before the script invocation:

```yaml
      - name: Guard <PAT>
        run: |
          if [ -z "${GH_TOKEN}" ]; then
            echo "::error::<PAT> secret is not set."
            exit 1
          fi
```

## Worked example: minimal test fixture

```python
# tests/test_<name>.py
import pytest

import <name>


class TestParseDryRun:
    def test_true(self) -> None:
        assert <name>.parse_dry_run("true") is True

    def test_false(self) -> None:
        assert <name>.parse_dry_run("false") is False

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            <name>.parse_dry_run("yes")


class TestMainExitCode:
    def test_plan_mode_exits_zero(self) -> None:
        assert <name>.main(["--dry-run", "true"]) == 0
```

## Rationale (CLAUDE.md mapping)

| Standard item | CLAUDE.md anchor | What it enforces |
|---|---|---|
| M1 module shape | section 5 | Testable units; logic does not require the workflow to exercise it |
| M2-M3 tests | section 1, section 3 | Observable completion check; deterministic harness in place of reviewer memory |
| M4 input validation | section 2, section 4 | Reject unverified input at the boundary; never let ambiguous input drive a mutation |
| M5 GitHub contracts | section 3 | Deterministic output the harness can read without ad-hoc parsing |
| M6 dry-run | section 4 | Reversible default; mutation requires explicit `dry_run=false` |
| M7 secret handling | section 4 | Bounded tool surface; secrets never reach logs or process listings |
| M8 lint/type/coverage | section 3 | Deterministic gates close the loop before merge |
| M9 fail policy | section 4 | Loud failure on gates; explicit fail-open only where a wedged hook would be worse |
| M10 install path | section 3, section 4 | Single uv-managed install primitive; supply-chain bounded by `pyproject.toml` + `uv.lock` and enforced by `scan_workflow_pip.py` |

## References

- Parent tracking issue: #197 tracking(quality): continuously improve
  code quality.
- This document: #196 docs(scripts): define workflow script quality
  standard.
- Scoped child issues this standard anticipates:
  - #188 test(scripts): measure workflow script coverage
  - #189 test(scripts): add CLI contract tests for workflows
  - #190 security(scripts): add workflow script security scans
  - #191 refactor(scripts): model workflow inputs with pydantic
  - #192 ci(scripts): add static typing and lint gates
  - #193 ci(workflows): verify script invocation drift
  - #194 test(scripts): add GitHub API boundary tests
  - #195 ci(scripts): standardize dependency and tool installation (promoted to must-have M10)
- Related runbooks: `docs/standards/issue-pr-body-standard.md`,
  `docs/runbooks/issue-triage.md`, `docs/prd/non-ascii-defense.md`,
  `docs/runbooks/rulesets.md`.
