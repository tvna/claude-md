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
  signature on the squash-merge commit**; not by signing feature-branch
  commits.
- No signing key is placed in any agent / CI runner container. Agent commits
  (`claude/*`) and human feature-branch commits stay unsigned on their feature
  branches and inherit the GitHub squash signature on merge.
- **Bot-generated PR workflows are the exception**: they author their commits
  through the GitHub API (`createCommitOnBranch`) under a GitHub App
  installation token, which GitHub signs (`Verified`) with the App bot
  (`tvna-bot`) as author. See [Bot-generated PR commits](#bot-generated-pr-commits-app-bot-signed).

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

## Web / remote agent sessions (Claude Code on the web)

Claude Code web (remote) sessions push feature-branch commits through the
managed git proxy. These commits are treated exactly like any other
`claude/*` feature-branch commit: they stay **unsigned on the branch** and
inherit GitHub's web-flow signature when the PR is squash-merged. A PR built
solely from web-session commits is therefore mergeable once it is green and
up to date with `main`; the squash commit GitHub creates is `Verified` and
satisfies `required_signatures`. This holds when the only unsigned objects are
the commits being squashed; for the unsigned-*ancestor* exception (for example
an in-session `Merge origin/main` commit), see the exception bullet below.

Client-side signing inside the session is both unnecessary and ineffective,
so it is **not** part of this standard:

- A session may have an SSH signing key configured, but its committer identity
  (`noreply@anthropic.com`) is not a GitHub account that has registered that
  key as a *signing* key. GitHub marks such a commit `Unverified`, and an
  `Unverified` signature does **not** satisfy `required_signatures`; only the
  squash-merge web-flow signature does. Provisioning a key into the session
  would not change this without also re-homing the committer identity onto a
  GitHub account that owns the registered signing key, which the keyless
  invariant below deliberately avoids.
- A pre-merge `mergeable_state` of `behind` or `blocked` on such a PR is a
  base-staleness, review-thread-resolution, or code-owner-review condition --
  not a signature block. Resolve it by rebasing onto `main`
  (`git fetch origin main && git rebase origin/main`) and squash-merging; do
  not attempt to re-sign the branch commits. Refs
  [#1496](https://github.com/tvna/claude-md/issues/1496),
  [#1494](https://github.com/tvna/claude-md/issues/1494).
- **Exception (unsigned ancestor commits).** The squash property above assumes
  the branch's only unsigned objects are the commits being squashed. A branch
  that has accumulated an unsigned *ancestor* it no longer rewrites; for
  example an in-session `Merge origin/main` commit, or the legacy
  `github-actions[bot]` ancestor in
  [#1560](https://github.com/tvna/claude-md/issues/1560); can instead have the
  merge box report `Commits must have verified signatures` and block the squash;
  `gh pr merge --squash` then fails with `the base branch policy prohibits the
  merge`. Two resolutions, in order of preference:
  1. **Primary; repo-admin `--admin` override.** A repository administrator
     merges with `gh pr merge <pr-number> --squash --admin`. Per the
     [`gh pr merge` manual](https://cli.github.com/manual/gh_pr_merge), `--admin`
     uses administrator privileges to "merge a pull request that does not meet
     requirements", so it bypasses *every* unmet `main.json` requirement on the
     PR; not only the unsigned-ancestor signature block but also required
     status checks, review-thread resolution, and code-owner review. The
     administrator MUST therefore treat `--admin` as a signature-block clearer
     only, and independently confirm the PR is otherwise ready first: required
     checks green, review threads resolved, code-owner review present, and the
     exact head SHA being merged. The signature invariant below holds regardless
    ; GitHub still creates the squash commit and signs it web-flow `Verified`,
     so no GPG/local signing is involved and no ruleset is relaxed. This is the
     live-observed resolution for the unsigned-ancestor block (Refs
     [#1780](https://github.com/tvna/claude-md/issues/1780),
     [#1727](https://github.com/tvna/claude-md/issues/1727)). It is
     **repo-admin only**: because `bypass_actors: []`, non-admin actors --
     including remote agent / web sessions; cannot self-merge and must use
     option 2 or request an admin merge.
  2. **Fallback (no admin override available); recreate the branch.** Because
     `non_fast_forward` forbids rewriting the unsigned ancestor in place,
     **recreate the branch off current `main` so the stale unsigned ancestor is
     dropped** (a delete+create or a replacement PR), exactly as the
     triage-report flow does with `recreate=True` (see
     [Bot-generated PR commits](#bot-generated-pr-commits-app-bot-signed)). The
     recreated feature commits follow the normal keyless path; they stay
     **unsigned** and inherit the squash signature; do **not** try to sign them
     (ineffective, per the first bullet above).

  In neither case relax `required_signatures` or add a `bypass_actors` entry to
  force the merge; that breaks the normative invariant below. The `--admin`
  override does **not** do this: it leaves the ruleset intact and still yields a
  `Verified` squash commit on `main`. Confirm the squash-signature behaviour per
  "Verify before enforcing" before relying on it.

## In-session signing-readiness gate (retro #1987)

The remote execution environment for Claude Code on the Web (and the Codex /
Devin cloud equivalents) configures `commit.gpgsign = true` with an SSH signer
*program* (`gpg.format = ssh`, `gpg.ssh.program` -> `/tmp/code-sign`). When that
signer is healthy, in-session feature-branch commits carry a `gpgsig` header;
they still follow the keyless invariant above and inherit GitHub's squash
signature on `main`, so the in-session header is belt-and-suspenders, not the
thing `required_signatures` relies on.

The hazard the gate addresses is a **mismatch between configuration and
reality**: `commit.gpgsign = true` is set, but a `git commit` lands UNSIGNED and
*silent* (exit 0, no `gpgsig` header). PR #1985's first commit (8d4919f) did
exactly this, and because force-push and branch deletion are both blocked by the
`all-branches-no-force-push` ruleset the unsigned base commit could not be
rewritten; recovery required a squash-merge. The cost of one silent unsigned
commit on a ruleset-protected branch is therefore effectively irreversible.

`scripts/check_commit_signing_ready.py` is the deterministic gate, wired into
every agent (`.claude/settings.json`, `.codex/hooks.json`, `.devin/hooks.v1.json`
via `scripts/agent_hooks_source.json`) in two layers:

- **SessionStart (warn).** In a remote session, if signing is required but a live
  test-sign comes back `unsigned`, it emits a loud `additionalContext` warning so
  a cold/broken signer is fixed *before* any commit.
- **PreToolUse `git commit` (block).** It DENIES the commit only when a live
  test-sign has just demonstrated an `unsigned` outcome, so the block is a proven
  true positive, not a prediction. An explicit reviewed unsigned commit can still
  proceed with a `# unsigned-ack` marker (the same opt-in
  `scripts/gate_unsigned_commit_bash.py` honors).

**Why a live test-sign, not a key-file check (primary-source finding).** Retro
#1987 hypothesised that 8d4919f was unsigned *because* the session key
`/home/claude/.ssh/commit_signing_key.pub` was empty (0 bytes). A live probe in
the same environment refuted this: with that key file still 0 bytes,
`git commit -S` produces a commit that DOES carry a `gpgsig` header, because the
signer is the `gpg.ssh.program` program, not the `.pub` file. The empty key is a
routine steady state here, not the fault. A file-size check would therefore both
false-positive (fire every session while signing works) and miss the real cause:
a *cold signer* early in the session that warms up shortly after (later #1985
commits signed correctly). The only sound signal is to exercise the real signing
path and inspect the result; the gate makes one `--allow-empty -S` commit in a
throwaway temp repo (never touching the real repository or any key material) and
checks for the `gpgsig` header. This is CLAUDE.md section 1's "live proof, not a
proxy" applied to a signer. Blast radius is bounded: the active probe runs only
in remote sessions (so a local-dev pinentry passphrase is never poked), the
block fires only on a demonstrated unsigned outcome, and every infrastructure
error fails open.

### Retro #1987 Fact classification

| Fact (PR #1985) | Classification | Disposition |
|---|---|---|
| 1. One full approach (SessionStart skill-mirror hook) built, then replaced by a governance carve-out after the operator paused to validate overturning `.claude/*` governance. | external/human decision (partially automatable) | See "Governance-overturn decision path" below. |
| 2. First commit (8d4919f) landed unsigned because signing was not yet working; later commits signed once the signer was warm. | missing deterministic gate | Closed by `scripts/check_commit_signing_ready.py` (this section). |
| 3. Force-push and branch deletion are blocked by the ruleset, so the unsigned base commit could not be rewritten; resolved by squash-merge. | unclear agent instruction | The squash-merge recovery and the no-force-push base-update path are documented in [`docs/runbooks/remote-session-base-update.md`](../runbooks/remote-session-base-update.md) and the unsigned-ancestor exception above. |
| 4. PR body creation took several retries against deterministic gates (title policy, classification labels, angle-token drop, required sections, verification line, footer dedup). | missing deterministic gate (already built) | The gates fired as designed; the repair was learning their contract, captured in [`docs/runbooks/pr-body-policy-recovery.md`](../runbooks/pr-body-policy-recovery.md). |
| 5. Codex review flagged the parity test compared only `SKILL.md`; fixed to compare the full skill tree (683ad77). | missing deterministic gate (closed in-PR) | Fixed within PR #1985; no carryover. |

### Out-of-date-base workflow (merge-into-base, never force-push)

On a `claude/*` branch the `all-branches-no-force-push` ruleset (`bypass_actors:
[]`) makes `git rebase origin/main` + force-push unavailable. The base is brought
forward by **merging `origin/main` into the branch** (a merge commit is fine; the
final squash flattens it) or by the server-side `update_pull_request_branch`
path. The full procedure, including the conflict probe, lives in
[`docs/runbooks/remote-session-base-update.md`](../runbooks/remote-session-base-update.md);
`scripts/preflight_session_base_freshness.py` shifts the out-of-date-base
detection left to SessionStart and the first commit so the late-rebase loop is
anticipated rather than hit at push.

### Governance-overturn decision path

When a task wants to change `.claude/*` (or other code-owner-governed
instruction files) and a structural constraint blocks the obvious approach
(force-push/branch-deletion denied by ruleset, or cross-agent parity), start from
the **governance carve-out** option, not from overturning the governance: scope
the smallest reviewed change to the governed files and let it pass the code-owner
merge gate (CLAUDE.md section 2: trusted instruction state changes only through
the proposal -> review -> merge path). PR #1985 first built a SessionStart hook to
deploy skills into `.claude/skills/`, then paused and adopted a carve-out
instead. This is an external/human decision (the operator owns whether to overturn
governance) and only partially automatable; the automatable part is surfacing the
constraint early, which the ruleset-aware preflights above already do.

## Normative invariant (reviewers MUST enforce)

`main.json` MUST remain squash-only for this standard to hold. **Adding
any non-squash merge method to `allowed_merge_methods`, or granting a
`bypass_actors` entry, breaks the keyless-signing assumption** (such a
merge could admit an unsigned commit onto `main`). A change that does so
MUST either be rejected or paired with a committer-side signing program
and a revision of this standard.

## Bot-generated PR commits (App-bot signed)

Workflows that open automated PRs (`generate-agents.yml`,
`post-merge.yml` decision-tree and triage-report jobs, and the
devcontainer pin / flake-bump flows) do **not** use a runner `git push`.
A commit pushed via `git` from a runner is authored by the persisted
`github-actions[bot]` token and is **not** signed; `git` cannot mint
GitHub's web-flow signature, and a GitHub App account cannot hold its own
signing key. Instead these workflows author the commit through the GitHub
GraphQL `createCommitOnBranch` mutation (`scripts/pr_upsert.py` ->
`upsert_files_pr` / `upsert_single_file_pr`) under a short-lived GitHub App
installation token minted by `actions/create-github-app-token` from the
`devcontainer-image-pins` Environment secrets
(`DEVCONTAINER_PIN_APP_ID` / `DEVCONTAINER_PIN_APP_PRIVATE_KEY`).

GitHub signs API-created commits (`Verified`) with the App bot
(`tvna-bot`) as author, and the mutation appends onto the branch tip
(`expectedHeadOid`), so the all-branches `non_fast_forward` ruleset is
honored without a force-push. This gives bot PR branches signed,
App-authored commits *before* merge, on top of the squash-merge signature
they still inherit on `main`. Refs
[#1437](https://github.com/tvna/claude-md/issues/1437),
[#1466](https://github.com/tvna/claude-md/issues/1466).

The triage-report refresh flow (`auto_retro.py triage-report-pr`) instead
calls the upsert with `recreate=True`: on each drift its fixed branch is
deleted and re-created off `main` with a single signed commit, never
accumulating ancestry. The append variant left a legacy unsigned ancestor
(an old `github-actions[bot]` `git push` commit) permanently on the reused
branch, which `required_signatures` rejected while `non_fast_forward`
blocked rewriting it; the branch could only be cleared by deletion. A
delete+create is not a force-push, so `non_fast_forward` still holds. The
decision-tree generated-docs branch keeps the append path (its history
carries no unsigned ancestor). Refs
[#1560](https://github.com/tvna/claude-md/issues/1560).

These App-bot PRs are auto-merged uniformly by a single keeper,
`scripts/bot_pr_automerge.py merge` (workflow `tvna-bot-automerge.yml`),
which squash-merges every open PR whose author login is `tvna-bot[bot]`
once it reaches `mergeable_state == clean`. The keeper fixes the merge
method to `squash`, so the keyless signing invariant above is preserved: it
never admits a non-squash merge that could land an unsigned commit on
`main`, and it adds no `bypass_actors`. The merge is gated entirely by
branch protection. Refs
[#1539](https://github.com/tvna/claude-md/issues/1539).

The deterministic regression guard is
`scripts/scan_workflow_unsigned_commit.py` (wired into pre-commit and the
`Verify repository scripts` workflow): it fails when any workflow `run:`
block contains `git push`, so the unsigned authoring path cannot be
reintroduced. An audited exception carries an inline `# unsigned-ack`.

## What is explicitly NOT required

- No GPG/SSH signing key for bot or agent commits. (For optional human
  local signing, SSH signing `gpg.format = ssh` is the lighter choice,
  but it is not required by this standard. The automated Nix-based setup
  for devcontainers and macOS is documented in
  [`docs/runbooks/commit-signing.md`](../runbooks/commit-signing.md).)
- No committer-side key-management program. The App-bot signing above
  relies only on the existing App installation token; the agent (`claude/*`)
  and human feature-branch commits remain unsigned and inherit the GitHub
  squash signature on merge. The earlier rejection of a per-committer
  signing-key program still stands; what changed (Refs #1437) is that
  bot-generated PR commits now use the keyless, server-side
  `createCommitOnBranch` path instead of a runner `git push`.

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
