# Offline PR-Head Mirror Gates for pull_request_target Checks

Refs #1519
Refs #1511
Refs #1501
Refs #1276

This document is the repo-local design record for a class of deterministic
gate: an **offline, PR-head mirror** of a server-side check that otherwise
runs only with base-branch code. It generalizes the concrete gate added for
#1519 (threat-intel OSV coordinate validation) into a reusable pattern, so
that when similar gates are added the design stays consistent instead of
being re-derived each time.

It belongs in `docs/prd/` rather than `docs/standards/` because it records
*why* the gate exists and *how to design the next one*; the adopted rule
itself lives in code (`scripts/threat_intel_triage.py verify`), the
pre-commit config, and CI, not in this prose.

## The problem class

Several of this repository's privileged checks run under
`pull_request_target` so they can hold write scopes and secrets while
triaging an untrusted PR. The canonical example is the `triage` job in
`.github/workflows/issue-pr-triage.yml`. Its `actions/checkout` step
specifies no `ref:`, so it checks out the **base** branch (main) -- both the
*code* that runs and the *files* it scans.

The consequence is a structural blind spot. On a PR, such a job exercises
neither the PR's modified code nor the PR's modified inputs:

- A PR that **breaks the scanner code** (e.g. edits
  `scripts/threat_intel_triage.py`) is still graded by the base copy of that
  code.
- A PR that **adds an input the scanner mis-handles** (e.g. a workflow line
  that a parser false-matches) is never scanned, because the base checkout
  does not contain that line.

In both cases the PR check stays GREEN and the breakage surfaces only
*after* merge, when the scheduled or push-triggered run on main finally
executes the new code against the new files. #1511 was exactly this: an
unanchored regex false-matched a prose line into a garbage OSV coordinate
(ecosystem `` ` ``, name `line`, version `in`); OSV querybatch rejected the
whole batch with HTTP 400 and hid every finding. The #1511 fix corrected the
parser but added no gate that would have caught it before merge -- a missing
deterministic gate (CLAUDE.md section 3).

## The rejected "obvious" fix

The tempting fix is to add `ref: ${{ github.head_ref }}` to the
`pull_request_target` checkout so the job runs PR-head code. This is
**rejected on security grounds**: it executes untrusted PR-author code in a
context that holds `issues: write` / `pull-requests: write` and repository
secrets -- the textbook `pull_request_target` privilege-escalation
anti-pattern (CLAUDE.md section 4 safety boundary). `verify-agents.yml`
already forbids interpolating `github.head_ref` for the same reason. Running
PR-head code is only safe when it is **offline and unprivileged**, which is
what the mirror gate provides.

## The pattern: an offline PR-head mirror gate

Mirror the *input-validation* portion of the privileged check as a pure,
offline gate that **does** run on PR head, because it needs no secrets and
makes no network calls. It runs in the same untrusted-PR contexts the repo
already trusts for offline checks: `pre-commit`, `prek run --all-files`
(required check on PR head in `verify-pr.yml`), and the local
`scripts/preflight_all.py` bundle.

A conforming gate has five parts. Use this as the checklist when adding a new
one:

1. **Pure validator** -- a function that takes the already-parsed inputs and
   returns the malformed entries (does not raise, makes no network call, reads
   no secrets). For #1519 this is `validate_osv_coordinates(dependencies) ->
   list[(Dependency, reason)]`. Its allowlists/contracts are a checked-in
   mirror of the external service's input contract (the OSV "Defined
   Ecosystems" list), treated as untrusted reference data, not fetched live.
2. **Defense-in-depth call on the live path** -- the privileged scanner
   itself calls the validator immediately before the network submission, so
   the real run fails loud *offline*, naming the offending source file,
   instead of as an opaque downstream error (HTTP 400). The downstream error
   handler stays as a backstop.
3. **A `verify` CLI subcommand** -- runs discovery + validation against
   `--repo-root .` and exits non-zero on any malformed entry. Stdlib-only so
   it runs under a bare interpreter, with no project venv required.
4. **A pre-commit hook** wired to the relevant input globs, mirrored onto the
   PR head by the existing `prek run --all-files` required check. No new
   workflow file is added -- the gate rides an existing required check
   (surface minimization, CLAUDE.md sections 4-5).
5. **A real-repo integration test** -- runs the PR-head parser over the
   PR-head repo tree and asserts zero malformed entries. This is the
   regression guard that would have caught #1511, and it also fails loud if a
   *legitimate* input (e.g. a newly added OSV ecosystem) is missing from the
   validator's allowlist, so the allowlist cannot silently drift.

The gate is deliberately a *mirror*, not a *replacement*: the privileged
`pull_request_target` job still runs post-merge with full network and
secrets. The mirror only moves the **deterministic, offline** slice of that
work earlier, onto the PR head, where it is both safe to run and able to see
the PR's own changes.

## When to apply it

Apply this pattern whenever a `pull_request_target` (or otherwise
base-checkout) workflow runs a scanner over repository files or code that a
PR can change, and a deterministic offline check could catch a malformed
input or a broken parser before merge. If the check needs secrets or network
to decide pass/fail, it is **not** a candidate -- only the offline,
deterministic slice qualifies.

## Registry of offline PR-head mirror gates

Add a row when a new gate adopts this pattern, so the set stays inspectable
and consistently designed.

| Gate | Mirrors | Validator | CLI | Refs |
| --- | --- | --- | --- | --- |
| threat-intel OSV coordinates | `triage` job in `issue-pr-triage.yml` (OSV querybatch submission) | `validate_osv_coordinates` in `scripts/threat_intel_triage.py` | `threat_intel_triage.py verify` | #1519, #1511 |

## Open questions / future work

- If a third gate adopts this pattern, factor the shared "validator + verify
  subcommand + pre-commit + real-repo test" scaffolding into a small helper
  rather than copying it, and record the refactor here.
- The validator allowlists (e.g. `_KNOWN_OSV_ECOSYSTEMS`) are checked-in
  mirrors of an external contract. A future enhancement could add a
  *separate, non-gating* scheduled job that diffs the mirror against the live
  source and opens an issue on drift -- keeping the gate offline while still
  surfacing staleness. This stays out of the PR-head gate by design.
