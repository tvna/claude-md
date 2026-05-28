# Dependency Freshness and Lockfile Drift

Tracked by #201.

This repository treats dependency freshness as a recurring quality track, not
as an ad hoc bump task. The goal is to keep toolchain inputs reproducible while
surfacing stale pins early enough that routine dependency work stays small.

## Dependency Sources

| Source | Owner | Drift risk | Current control |
|---|---|---|---|
| `pyproject.toml` | Humans | Python dependency bounds or `[tool.uv].required-version` can change without the matching lockfile or workflow policy. | PR CI runs `uv sync --locked`; `scripts/uv_pin.py drift` keeps the uv binary pin centralized. |
| `uv.lock` | uv resolver / humans | The lockfile can lag behind `pyproject.toml` or Dependabot updates. | PR CI runs `uv sync --locked`; Dependabot opens weekly `uv` ecosystem updates. |
| `.github/workflows/*.yml` | Humans / Dependabot | Action references can drift to mutable tags or unreviewed tool installers. | `scripts/scan_workflow_action_pins.py verify` blocks unpinned external actions; Dependabot opens weekly `github-actions` updates. |
| `scripts/install-uv.sh` | Humans | Remote-session uv install logic can diverge from CI's pinned uv source. | `scripts/uv_pin.py read` is the single source of truth for the installer and CI. |
| Generated install commands in workflows | Humans | Repeated install snippets can grow conflicting tool versions. | Workflow uv install values must come from `scripts/uv_pin.py read`, not literals. |

## Blocking Gates

These checks must stay CI-blocking on pull requests:

- `uv sync --locked` fails when `pyproject.toml` and `uv.lock` disagree.
- `scripts/uv_pin.py drift` fails when the uv pin literal appears outside
  `pyproject.toml` or a workflow assigns the uv installer value from a literal.
- `scripts/scan_workflow_action_pins.py verify` fails when external actions are
  not pinned to a full commit SHA with a tag comment.
- `scripts/scan_workflow_pip.py verify` fails when workflows install Python
  dependencies outside the uv-managed path.

Type checks and linters can confirm the scripts still parse and match local
style, but they do not prove dependency freshness. The behavioral proof is the
locked environment sync plus the repository-shape gates above.

## Scheduled Reporting

`.github/workflows/dependency-freshness-report.yml` runs weekly and on manual
dispatch. It repeats the blocking drift checks and emits a warning-only uv
upstream staleness annotation through `scripts/uv_pin.py stale`.

The report is intentionally non-mutating:

- It does not open dependency PRs; Dependabot owns routine `uv` and
  `github-actions` update PRs.
- It does not auto-bump `[tool.uv].required-version`; that pin remains a
  one-line human-reviewed PR because Dependabot does not natively update it.
- It does not suppress PR CI failures. If the scheduled report finds a drift
  issue, the repair belongs in the same blocking gate that would have caught it
  on a PR.

## Relationship to Existing Automation

Dependabot remains the update source for `uv.lock` and GitHub Actions SHAs. The
auto-merge policy in `docs/runbooks/dependabot-automerge.md` stays separate:
dependency freshness reporting can identify stale or drifting inputs, but
auto-merge decides whether a Dependabot PR is safe to merge without human
intervention.

The uv binary pin follows `docs/standards/remote-environment.md`. That runbook
is the source of truth for why `[tool.uv].required-version` is exact and why
remote sessions install the same version used by CI.

## Repair Routing

When a freshness report fails or warns:

- Lockfile mismatch: update `uv.lock` with the same uv version pinned in
  `pyproject.toml`, then rerun `uv sync --locked`.
- uv pin drift: remove the duplicate literal or source the value from
  `scripts/uv_pin.py read`.
- stale uv warning: open a scoped PR that changes only
  `[tool.uv].required-version` unless the new uv release requires lockfile or
  script changes.
- action pin drift: update the workflow `uses:` reference to a full commit SHA
  and keep the trailing tag comment for reviewer readability.
