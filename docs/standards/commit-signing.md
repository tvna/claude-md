# Commit Signing on `main`

Tracked by [#32](https://github.com/tvna/claude-md/issues/32) (parent
[#18](https://github.com/tvna/claude-md/issues/18) Phase 5).

This standard defines the adopted rule for commit-signature verification
on the default branch and the invariant that keeps it satisfiable without
a per-committer signing-key program. The apply / verify / rollback
procedure lives in [`docs/runbooks/rulesets.md`](../runbooks/rulesets.md).

## Adopted rule

- `.github/rulesets/main.json` declares the `required_signatures` rule, so
  every commit object on `main` must carry a verified signature.
- Signature verification on `main` is satisfied by **GitHub's web-flow
  signature on the squash-merge commit** -- not by signing feature-branch
  commits.
- No signing key is placed in any agent / CI runner container. Bot commits
  (`generate-agents.yml`) and agent commits (`claude/*`) stay unsigned on
  their feature branches and inherit the GitHub squash signature on merge.

## Why this is satisfiable (invariant)

`main.json` enforces, with `bypass_actors: []`:

- `pull_request` with `allowed_merge_methods: ["squash"]` (squash-only),
- `required_linear_history`,
- `non_fast_forward` and `deletion` blocking.

Because the branch is squash-only and direct pushes are blocked, every
commit that lands on `main` is the squash commit GitHub creates at merge
time, and GitHub signs that commit with its web-flow key (`Verified`).
Unsigned feature-branch commits never become commit objects on `main`.

The PR-time sync gate (`scripts/verify_ruleset_sync.py`) inspects only
`required_status_checks` contexts, so adding `required_signatures` to the
source-of-truth JSON does not self-fail any PR. Source-of-truth ahead of
live is the normal phased-rollout lag window; the live apply is the
operator's staged step (see the runbook).

## Normative invariant (reviewers MUST enforce)

`main.json` MUST remain squash-only for this standard to hold. **Adding
any non-squash merge method to `allowed_merge_methods`, or granting a
`bypass_actors` entry, breaks the keyless-signing assumption** (such a
merge could admit an unsigned commit onto `main`). A change that does so
MUST either be rejected or paired with a committer-side signing program
and a revision of this standard.

## What is explicitly NOT required

- No GPG/SSH signing key for bot or agent commits. (For optional human
  local signing, SSH signing `gpg.format = ssh` is the lighter choice,
  but it is not required by this standard.)
- No change to `.github/workflows/generate-agents.yml`. The alternative --
  migrate the bot to the Contents API for auto-signed commits plus an
  agent key-management program -- was evaluated and rejected as higher
  operational cost with no enforcement benefit under squash-only merge.

## Verify before enforcing

The squash-signature mechanism is GitHub-documented behaviour (fact); the
conclusion that it fully satisfies `required_signatures` for this
repository is confirmed by the operator before enforcement: dispatch
`Apply rulesets` with `dry_run=true`, squash-merge a throwaway PR, and
confirm the resulting `main` commit shows `Verified`. Only then apply
with `dry_run=false`. See [`docs/runbooks/rulesets.md`](../runbooks/rulesets.md).

## Scope notes

- `github-actions[bot]` commits are GitHub-signed only when GitHub creates
  the commit (API / web UI / squash merge), not when pushed via `git` from
  a runner. This repository relies on the squash-merge path.
- Vigilant Mode is a per-account display setting (marks unsigned commits
  `Unverified`); it is not ruleset enforcement and is out of scope.
- Reopen / reevaluate triggers (carried from #32): a suspected
  commit-spoofing incident, periodic reevaluation, or migration to a
  multi-committer setup.
