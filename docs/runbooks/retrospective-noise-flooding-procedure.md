# Retrospective noise and flooding visibility -- procedure

Operator-facing companion to the retrospective documents in
[`docs/archive/retrospective-pr-*.md`](../archive/) and the auto-retro
harness in [`scripts/auto_retro.py`](../scripts/auto_retro.py).
Deliverable for [#315](https://github.com/tvna/claude-md/issues/315);
part of [#63](https://github.com/tvna/claude-md/issues/63) Phase 8(D-3).

## 1. Purpose and non-goals

**Purpose.** Give retrospective writers a reproducible procedure for
spotting noise-commit and flooding patterns on a merged PR, and for
mapping those findings into the existing repair-classification
taxonomy from CLAUDE.md section 3. The procedure is applied during
the retrospective that the auto-retro harness opens after every
non-bot, non-retro merge.

**Non-goals.**

- Adding a new deterministic gate. Per #63 Phase 8(D-3), this phase
  delivers guidance only. Any deterministic follow-up that surfaces
  from applying this procedure is filed as a separate sub-issue of
  #63 (see [section 5](#5-when-to-file-a-follow-up-gate)), never
  bundled into the design-doc PR.
- Replacing the auto-retro repair-history pre-fill. The
  `_build_repair_history_table` function in
  [`scripts/auto_retro.py`](../scripts/auto_retro.py) already detects
  five signal classes (CI failures, fix-up commits with the canonical
  `fix(...)` commit on a fix-typed PR split out as a separate
  `Fix commit` row -- see #413, merge-from-main, multi-commit PR, and
  failed Verification pairs) and writes them into the retro issue
  body. This procedure layers human judgment on top of those signals;
  it does not duplicate them.
- Re-classifying the three repair-taxonomy categories. The taxonomy
  (missing deterministic gate / unclear agent instruction / external
  or human decision that cannot be automated) is owned by CLAUDE.md
  section 3 and mirrored in
  [`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md)
  section 6.4. This procedure consumes the taxonomy, it does not
  extend it.

## 1a. Auto-retro decision tree rendering

Before splitting `scripts/auto_retro.py`, render the current
orchestrator decision tree from the code-owned representation:

```bash
python scripts/auto_retro.py decision-tree
```

The command writes Mermaid `flowchart TD` text to stdout. Paste the
output into a PR description, issue comment, or Markdown scratch file
when reviewing whether a proposed split preserves the existing
skip/append/open flow. Signal branches are generated from
`auto_retro._SIGNAL_NAMES`, so the diagram follows the same signal
universe that `compute_repair_signals` and the label-derived prior
consume.

## 2. Signals to inspect

A merged PR carries a noise or flooding pattern when one or more of
the five signals below fires. The signals are listed in increasing
order of operator effort: the first three are read directly from the
auto-retro repair-history table; the last two require a one-line `gh`
or `git log` query.

| # | Signal | Where to read it | What it means |
|---|--------|------------------|---------------|
| S1 | High commit count on a single PR | Auto-retro repair-history table `Multi-commit PR` row; or `git log --oneline <base>..<head> | wc -l` | The PR did not squash to a single intent. Either the author iterated in public (legitimate when each commit is a discrete step) or the branch absorbed unrelated work. Note: the `multi_commit_pr` gate that triggers auto-retro creation subtracts merge-from-main commits from the count, so rebase debt forced by the squash-only, linear-history policy does not fire the gate on its own; the repair-history table still records the merge-from-main rows for review visibility. |
| S2 | Low-information commit subjects | Auto-retro `Iteration commit` row (the canonical `fix(...)` commit on a fix-typed PR is rendered as `Fix commit` instead and is exempt from this count -- see #413); or scan commit subjects for `wip`, `fix`, `fixup!`, `squash!`, `update`, `more`, `tweak`, generic verbs with no scope | Subjects that do not state intent erase the audit trail. A reviewer cannot reconstruct what each commit changed without diffing it. |
| S3 | Repeated repair commits | Auto-retro `Iteration commit` row with three or more entries (the canonical `fix(...)` commit on a fix-typed PR is exempt -- see #413); or `git log --grep='^fix' <base>..<head>` count | Repeated `fix(...)` commits on the same PR indicate the deterministic gates caught defects late. The pattern points at a missing earlier gate or an unclear agent instruction. |
| S4 | Force-update churn | `git reflog show origin/<branch>` from the local checkout if available; or the PR `force-pushed` timeline events visible in the GitHub UI | Force pushes rewrite the audit log. A small number is normal (rebase onto main, fix-up squash before merge). A large number obscures which version a reviewer approved. |
| S5 | Unrelated churn in the diff | `git diff --stat <base>..<head>` against the PR scope stated in the closing issue | Files outside the PR scope appearing in the diff (e.g. a docs PR that also touches `scripts/`, an APM-source PR that also rewrites `tests/`) widens blast radius beyond what the closing issue authorized. |

The signals are independent. A PR may fire only S1 (legitimate
multi-commit landing) without firing S2 through S5, in which case the
retrospective records the signal but classifies it as not a noise
pattern. The signals become a noise pattern when **two or more fire
on the same PR**, because each signal alone has a benign
interpretation; co-firing collapses the benign explanation.

S1 policy-artifact rows: the auto-retro repair-history table tags
`Merge from main` rows with a leading `[policy-artifact]` token in the
"What the reviewer / gate caught" column. Rows carrying this marker
are structural side-effects of the squash + linear-history +
strict-status-checks combination in `.github/rulesets/main.json` --
a branch that falls behind main has no force-push option, so
merge-from-main is the only safe path. Operators may skip these rows
when filling the section 3 classification column; the row is recorded
for review visibility but does not need a `missing deterministic gate`
/ `unclear agent instruction` / `external or human decision` tag.
Refs issue #400.

### 2.1 Severity thresholds (rule of thumb)

The thresholds below are operator rules of thumb derived from the
existing retrospective corpus (`docs/archive/retrospective-pr-229.md`
through `retrospective-pr-257.md`). They are not deterministic
gates; a retrospective writer may override any threshold with a
recorded rationale.

| Signal | Green | Yellow | Red |
|--------|-------|--------|-----|
| S1 commit count | 1 commit | 2 to 4 commits | 5 or more commits without a stated reason |
| S2 low-info subjects | 0 low-info subjects | 1 low-info subject | 2 or more low-info subjects |
| S3 repair commits | 0 `fix(`/`fixup!`/`squash!` | 1 to 2 repair commits | 3 or more repair commits |
| S4 force pushes | 0 to 2 force pushes | 3 to 4 force pushes | 5 or more force pushes |
| S5 unrelated churn | All diff paths trace to closing-issue scope | 1 file outside stated scope with a one-line rationale in PR body | 2 or more files outside scope, or any path outside scope with no rationale |

A PR is a noise-pattern candidate when at least one signal is red, or
when two or more signals are yellow. Green-across-the-board PRs need
no separate noise section in the retrospective; the existing
repair-history table is sufficient.

## 3. Classification mapping

When a noise pattern fires, classify each signal into the existing
repair taxonomy from CLAUDE.md section 3. The mapping below is the
default routing; a retrospective writer may pick a different
classification when the worked evidence on the PR justifies it.

| Signal | Default classification | Why |
|--------|------------------------|-----|
| S1 high commit count | External or human decision | The author chose to land the work in multiple commits. The harness cannot decide for them how many commits a unit of work deserves; the retrospective records the choice and whether it served reviewers. |
| S2 low-information subjects | Unclear agent instruction | The agent rule "cite the issue number in every commit and PR" (CLAUDE.md section 3) implies a useful subject. A vague subject means the instruction did not catch the case. Tightening the wording, or adding a commit-subject lint, addresses it. |
| S3 repeated repair commits | Missing deterministic gate | If a gate caught the defect on commit N+1 that did not catch it on commit N, the gate fires too late or another gate is missing. The retrospective names the earliest gate that should have fired. |
| S4 force-update churn | Missing deterministic gate (default) or unclear agent instruction (when caused by re-running an unclear step) | Repeated force pushes typically signal an agent loop without a stable target. The harness can detect the churn but not prevent it; classify as missing gate when a pre-push check would have caught the underlying defect, otherwise as unclear instruction. |
| S5 unrelated churn | Unclear agent instruction (default) or external or human decision (when the author intentionally bundled work and stated the rationale in the PR body) | CLAUDE.md section 5 says "touch only what you must." Unrelated churn means the instruction did not constrain scope; the retrospective records the wording gap or, when the author argued for the bundling, accepts it as a human decision. |

The classification feeds directly into the section 6.4 lane-mapping
table in
[`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md),
which tells the retrospective writer which ownership lane (harness,
universal text, or repo-local doc) carries the durable fix.

## 4. Worked examples

The two examples below are drawn from the existing retrospective
corpus and show what a non-noise PR and a candidate noise PR look
like under this procedure.

### 4.1 Worked example -- non-noise (PR #237)

`docs/archive/retrospective-pr-237.md` documents PR #237 as a
single-commit, zero-repair merge. Running the section 2 checklist:

- S1 commit count: 1 commit. Green.
- S2 low-info subjects: 0. Green.
- S3 repair commits: 0. Green.
- S4 force pushes: 0 observable. Green.
- S5 unrelated churn: the diff is three net-new files
  (`scripts/auto_retro.py`, `.github/workflows/auto-retro.yml`,
  `tests/test_auto_retro.py`) all inside the closing issue #234
  scope. Green.

All signals green, so the retrospective does not need a separate
noise-and-flooding section. The existing repair-history sentinel row
("no automated repair signals detected") is sufficient.

### 4.2 Worked example -- candidate noise (hypothetical shape)

A hypothetical PR that lands a `docs/*.md` typo fix in 7 commits
with subjects `fix`, `more`, `wip`, `update`, `fix2`, `tweak`,
`final` and touches an unrelated `scripts/threat_intel_triage.py`
file would score:

- S1: 7 commits. Red.
- S2: 7 low-info subjects. Red.
- S3: 1 `fix(`-shaped commit (the rest are bare `fix`). Yellow.
- S4: not observable from the retrospective alone; flag as unknown.
- S5: `scripts/threat_intel_triage.py` is outside the docs-typo
  scope. Yellow (one file out of scope).

Two red signals plus two yellow signals: this is a noise pattern.
Classification routing per section 3:

- S1 -> external or human decision: the author chose 7 commits;
  the retrospective records the rationale (or its absence).
- S2 -> unclear agent instruction: the commit-subject convention
  was not enforced. Follow-up: tighten the wording in
  `.apm/instructions/master.instructions.md`, or add a subject lint
  to the harness.
- S5 -> unclear agent instruction: the scope-discipline rule
  ("touch only what you must") did not constrain the diff.
  Follow-up: file a sub-issue of #63 proposing either a stricter
  wording or a CI gate that diffs the PR file list against the
  closing-issue title.

The retrospective writer then walks section 5 to decide whether
each follow-up is design-doc-only or earns a separate gate issue.

## 5. When to file a follow-up gate

Apply the questions below in order. The first answer that fires
decides whether to file a separate sub-issue of #63 for a
deterministic follow-up, or to leave the retrospective entry as
guidance only.

```
Q1. Did the noise pattern repeat across two or more retrospectives?

    No  -> Guidance only. Record the signal in the retrospective
           and stop. A single occurrence is not enough evidence to
           justify a new gate (CLAUDE.md section 4: "no error
           handling for impossible scenarios -- but 'impossible'
           means physically impossible, not 'I cannot currently
           imagine it'"; the inverse also holds, a single
           occurrence is not yet a proven recurrence).

    Yes -> Q2.

Q2. Can the signal be detected by a deterministic check (a script,
    a workflow, a hook, a ruleset)?

    No  -> Guidance only, and flag the signal as a candidate for
           future deterministic enforcement when a check becomes
           feasible. Record the rationale.

    Yes -> Q3.

Q3. Would the deterministic check fire on the historical PR corpus
    without false positives that would have blocked legitimate
    merges?

    No  -> Guidance only. False positives on legitimate PRs are
           more damaging than the noise pattern itself. Record the
           failure mode and revisit when the check can be tightened.

    Yes -> File a new sub-issue of #63 proposing the gate.
           Reference this section by anchor. The sub-issue follows
           the issue body standard in
           docs/standards/issue-pr-body-standard.md and the lane-mapping
           guidance in docs/prd/agent-rules-design-philosophy.md
           section 6.4.
```

The Q1-through-Q3 decision tree is the contract that keeps Phase
8(D-3) a design-doc-only deliverable while still leaving a clear
escalation path. The escalation never bundles a new gate into the
design-doc PR; the gate, if warranted, is its own PR closing its
own sub-issue.

### 5.1 Retro sentinel auto-close (deterministic backstop)

The Q1 escalation produced [#414](https://github.com/tvna/claude-md/issues/414)
after the 17-retro batch of 2026-05-24 to 2026-05-26 surfaced a
noise-dominated stream. The deterministic follow-up is the
**Strategy B sentinel** wired in
[`.github/workflows/auto-retro-sentinel.yml`](../../.github/workflows/auto-retro-sentinel.yml)
and backed by `sentinel_run` in
[`scripts/auto_retro.py`](../../scripts/auto_retro.py).

The sentinel runs on a daily cron tick and closes open retros that
have stayed **untouched** beyond the inactivity window (default
14 days, overridable via the `AUTO_RETRO_SENTINEL_DAYS` env var).
"Untouched" means BOTH of these signals fire on the retro:

- every acceptance-criteria checkbox in the retro body is still
  `[ ]` (no operator marked any progress), AND
- the retro has no comments from logins outside the trusted-bot
  allowlist (no operator wrote a triage note instead of editing
  the body).

A closed retro carries a `<!-- auto-retro-sentinel:closed -->`
marker comment that names the inactivity threshold and the reopen
instruction. The marker is the idempotency anchor: a subsequent
cron tick that finds the same retro reopened by an operator will
skip it because the marker comment is still present.

Operator implication: when the retrospective writer (per
[section 6](#6-cadence-and-ownership)) intentionally records a
no-actionable-repair verdict, they should close the retro manually
rather than wait for the sentinel -- the manual close preserves
the operator's reasoning in the close comment, while the sentinel
close only records the inactivity timeout. The sentinel is the
deterministic backstop for retros that fall off the operator's
radar, not the primary disposition channel.

## 6. Cadence and ownership

This procedure runs once per merge, inside the retrospective that
the auto-retro harness opens. The retrospective writer is the
operator who lands the next PR after the merge (or the
solo-developer themselves in the current repository state).

The procedure has no scheduled cadence outside the per-merge cycle;
its evidence base grows monotonically with each
`docs/archive/retrospective-pr-*.md` file that lands.

## 7. References

- [#315](https://github.com/tvna/claude-md/issues/315) -- the
  closing sub-issue for which this document is the deliverable.
- [#63](https://github.com/tvna/claude-md/issues/63) -- parent
  catalog for the transparency-paradox threat model; this document
  is the Phase 8(D-3) entry.
- [`scripts/auto_retro.py`](../scripts/auto_retro.py) -- auto-retro
  harness; its `_build_repair_history_table` function pre-fills the
  signals consumed by [section 2](#2-signals-to-inspect) (S1, S2,
  S3).
- [`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md)
  section 6.4 -- the retrospective-classification-to-lane mapping
  table consumed by [section 3](#3-classification-mapping).
- [`docs/standards/issue-pr-body-standard.md`](../standards/issue-pr-body-standard.md) --
  body shape for the follow-up sub-issue produced by
  [section 5](#5-when-to-file-a-follow-up-gate).
- [`docs/archive/retrospective-pr-237.md`](../archive/retrospective-pr-237.md)
  -- the non-noise worked example in section 4.1.
- CLAUDE.md section 3 -- the three-category repair taxonomy
  consumed by section 3.
- CLAUDE.md section 5 -- the "touch only what you must" rule
  consumed by signal S5 classification.
