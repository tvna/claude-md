# Issue/PR Body Standard - Contributor Runbook

> Design rationale: see [`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md). This runbook is the concrete body shape that carries the Facts / Assumptions discipline (principle P2) and the issue-citation discipline (principle P3) referenced by the meta-doc.

This document is the contributor- and agent-facing runbook for the body shape
of every issue and pull request in this repository. The label taxonomy in
[`docs/runbooks/issue-triage.md`](../runbooks/issue-triage.md) tells an agent **how to route**
an item from labels alone; this document tells a human or agent **what to
write inside the body** once routing has chosen "read the body".

Per [CLAUDE.md](../../CLAUDE.md) section 1, every change needs a goal and a
verification step. Per section 2, facts and speculation must be separated.
Per section 3, every commit and PR must cite an issue number. Per section 5,
each PR should touch only what it must. A fixed body shape is the cheapest
way to make those four rules visible to reviewers before a single line of
code is read.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `docs/standards/issue-pr-body-standard.md` *(this file)* | - | Body-shape runbook |
| `.github/PULL_REQUEST_TEMPLATE.md` | new PRs | PR template the standard describes |
| `.github/labels.json` | `/repos/tvna/claude-md/labels` | `type:*` axis the standard partitions on |
| `scripts/issue_link.py` | `verify-issue-link.yml` | Refs check (one piece of body policy that is already enforced) |
| `scripts/title_policy.py` | `verify-title-policy.yml` | ASCII-only and conventional-title check (titles, not bodies) |
| `scripts/_trusted_bots.py` | shared by gates | Single source of truth for the trusted-bot allowlist |

## Status

Two pieces of the body-policy contract are deliberately out of scope for
this runbook and tracked as sibling sub-issues under
[#197](https://github.com/tvna/claude-md/issues/197):

- Issue templates under `.github/ISSUE_TEMPLATE/` do not exist yet. Today,
  the de facto pattern is whatever the repo owner writes (see
  [#196](https://github.com/tvna/claude-md/issues/196),
  [#206](https://github.com/tvna/claude-md/issues/206)). This document is
  the spec future templates will conform to.
- A comprehensive body-policy gate that parses required H2 sections and
  fails the PR check when one is missing also does not exist yet. The
  only body-shape rule the harness enforces today is "the PR body must
  include a `Refs #N` line" via `scripts/issue_link.py` (see
  [Body-policy gate](#body-policy-gate) below).

Until those siblings land, this runbook is the authoritative reference for
what a well-formed body looks like.

## Issue body sections (all types)

Every issue body should contain the following H2 sections, in this order:

- `## Scope` - one paragraph that names the unit of work the issue covers.
  Per CLAUDE.md section 1, the scope is the goal; without it there is no
  way to know when the issue is done.
- `## Why` - one paragraph (or short bulleted list) that motivates the
  change. Per CLAUDE.md section 2, lines that describe verified state
  must be prefixed with `Fact:` and lines that describe a hypothesis or
  predicted consequence must be prefixed with `Speculation:`. Reviewers
  use the prefix to know which lines need pushback.
- `## Proposed work` - bulleted list of the concrete deliverables. Per
  CLAUDE.md section 5, this list should be the minimum that satisfies
  `Scope`; do not enumerate adjacent improvements here.
- `## Acceptance criteria` - bulleted list of checks that must be true
  before the issue can close. Per CLAUDE.md section 1, each criterion
  should be observable (a file exists, a command exits 0, a label is
  present); avoid criteria that require subjective judgement.
- `## Parent` - one line linking the umbrella `type:tracking` issue
  when the current issue is a scoped child. Omit this section when the
  issue is standalone.

## Type-specific guidance

The five `type:*` labels in `.github/labels.json` partition issues by
intent. The required H2 sections above apply to all five. The points
below describe extra emphasis a body of each type should carry.

### `type:feat`

`Scope` names the new behaviour or rule. `Why` calls out the gap the new
behaviour fills with a `Fact:` line citing the current state and a
`Speculation:` line for the predicted improvement. `Acceptance criteria`
includes at least one observable check (a workflow now exists, a label
now appears, a command now exits 0).

### `type:fix`

`Why` must contain a `Fact:` line that names the defect concretely - a
log line, an error message, a file path with an incorrect value, or a
reproduction step. Per CLAUDE.md section 2, "evidence earns a fix":
without a fact line, the issue is a speculative refactor request, not a
fix. `Acceptance criteria` must include "the original symptom no longer
reproduces" with the reproduction command.

### `type:refactor`

`Why` should make explicit that no behaviour change is intended (per the
label description). `Acceptance criteria` should include "existing tests
pass unchanged" so the no-behaviour-change claim is checkable.

### `type:docs`

`Scope` names the document or document set being added or revised.
`Acceptance criteria` should include either "the file exists at
`<path>`" or a content check ("section X is present and links to Y").
Examples in the body must be ASCII-only to keep the
`scan-non-ascii.yml` gate green.

### `type:tracking`

`Scope` names the umbrella concern. The body replaces `Proposed work`
with a `## Initial child issues` (or similar) list that links each
scoped child, and replaces `Acceptance criteria` with a
`## Completion criteria` section that names the condition under which
the umbrella itself can close (typically "no open child issues remain"
or "replaced by a newer tracking issue"). `Parent` is usually omitted
on a tracking issue.

## PR body sections

`.github/PULL_REQUEST_TEMPLATE.md` defines the required PR body shape.
The required H2 sections, in order, are:

- `## Summary` - one or two sentences that name what the PR changes and
  why. Mirrors the linked issue's `Scope` and `Why`.
- `## Related Issue` - a single `Refs #<number>` (or `Closes #<number>`,
  etc.) line. Per CLAUDE.md section 3, every PR must cite its issue.
  The keywords `Refs`, `Closes`, `Fixes`, and `Resolves` are accepted
  (case-insensitive).
- `## Facts` - observable evidence (diffs, command output, test names,
  log lines) per CLAUDE.md section 2. No speculation.
- `## Assumptions` - what the author is trusting but has not verified.
  Speculation must be tagged with `speculation:`.
- `## Risk & blast radius` - who or what is affected if the change is
  wrong, and how reversible it is, per CLAUDE.md section 4.
- `## Rollback` - the exact steps to revert or disable the change in
  prod.
- `## Verification` - one command/result pair per observation, in the
  shape below. Each entry is one fact about what was actually run.
  Type checks and linters verify shape, not behaviour; include at
  least one behaviour check when behaviour changed. Repository Python
  checks must run through `uv run` so dev dependencies come from
  `pyproject.toml` and `uv.lock` instead of the operator's ambient
  Python environment.

  ```
  - command: `uv run python -m pytest -q`
    result: `exit 0 (684 passed)`
  ```

  Successful results should start with a marker that
  `scripts/auto_retro.py` classifies as passing: `exit 0`, `OK:`,
  `passed`, `success`, `all checks`, `all tests`, or a pytest summary
  such as `684 passed in 1.23s`. Do not use free-form success prose
  such as `only matching lines remain`; write `exit 0 (...)` instead.
  If a command is blocked by local toolchain drift, record that fact
  outside `## Verification` unless the blocked check is itself the
  repair evidence to be audited by the next retrospective.

  PRs created on or after 2026-05-26 UTC are gated by
  `scripts/body_policy.py:verify_pr_verification_pairs` (see
  [Body-policy gate](#body-policy-gate) below). A `command:` line
  must be followed immediately by a `result:` line on the next line;
  the command value must be a single backticked code span.

- `## Checklist` - three H3 subsections separating items by automation
  layer. PRs created on or after 2026-05-26 UTC must include all three.

  - `### Bootstrap` - human cognition only; not automatable.
  - `### After-merge (CI)` - deterministic gates verified by CI;
    paired with command/result evidence in `## Verification`.
  - `### Post-merge (auto-retro signal)` - read by
    `scripts/auto_retro.py`. Unchecked items become repair-history
    rows in the auto-opened retrospective issue.

The HTML comment at the top of `PULL_REQUEST_TEMPLATE.md` is rendered
out of the final PR body and does not need to be preserved.

## Rationale (CLAUDE.md mapping)

| Body section | CLAUDE.md anchor | What it enforces |
|---|---|---|
| `Scope` (issue), `Summary` (PR) | section 1 | The goal is named before any work begins. |
| `Why` with `Fact:` / `Speculation:` tags | section 2 | Facts and speculation are visibly separated; reviewers know which lines need pushback. |
| `Proposed work` (issue), `Changes` (PR) | section 5 | The change touches only what it must; adjacent cleanups are not bundled in. |
| `Acceptance criteria` (issue), `Verification` (PR) | section 1, section 4 | Completion has an observable check; the blast radius of an unverified merge is bounded. |
| `Related Issue` / `Refs #N` (PR) | section 3 | Every PR cites its issue; deterministic-harness invariant. |
| `Parent` (issue) | section 5 | Umbrella relationships are explicit, so scope creep on a child does not silently expand the umbrella. |

## Worked examples

See [`docs/archive/issue-pr-body-examples.md`](../archive/issue-pr-body-examples.md) for one issue-body sample per type and a PR body sample. The examples are ASCII-only by construction.

## Body-policy gate

Two layers of the body-shape contract are enforced today.

### Enforced today: H2 section presence (baseline gate)

`.github/workflows/verify-body-policy.yml` shells out to
`scripts/body_policy.py verify` and checks that every required H2 (or
H3 for Issue Forms) heading from the lists above is present in the
body. Bodies whose `created_at` predates `BODY_POLICY_CUTOFF`
(currently `2026-05-26T00:00:00Z`) skip this check so the back-catalog
stays exempt.

### Enforced today: PR shape gate (post-2026-05-26)

The same workflow runs `verify_pr_verification_pairs` and
`verify_pr_checklist_subsections` and
`verify_pr_agent_attribution_footer` from `scripts/body_policy.py`
when `BODY_POLICY_SHAPE_CUTOFF` is set (currently
`2026-05-26T00:00:00Z`). PRs created on or after that moment must:

- contain at least one `- command: \`<inline>\`` line followed
  immediately by a `  result: <text>` line inside `## Verification`;
- contain `### Bootstrap`, `### After-merge`, and `### Post-merge`
  H3 subsections inside `## Checklist`, each with at least one
  `- [ ]` or `- [x]` item;
- end with a final non-empty line shaped as
  `_Generated by [<agent name>](<agent/session URL>)_`, or the
  Codex model-aware form
  `_Generated by [Codex](https://openai.com/codex) using <model>._`.

The footer is agent-agnostic. `Claude Code`, `Codex`, or a future agent
name may occupy the label slot; the URL must be supplied by the active
agent/session so reviewers can trace the PR body back to the agent run
that produced it. Codex GitHub write hooks additionally require the
model-aware form above so the post records both the generator and the
AI model identifier.

The hook `scripts/preflight_pr_template_shape.py` (bound in
`.claude/settings.json` to MCP PR create/update calls) runs the same
checks client-side so an operator can fix the body before the API
call instead of round-tripping through the workflow.

The hook `scripts/preflight_codex_github_footer.py` is bound only in
`.codex/hooks.json` to Codex GitHub write calls that carry a text
`body`. It requires the final line
`_Generated by [Codex](https://openai.com/codex) using <model>._`,
rejects duplicate Codex footers, and denies the write when no trusted
model metadata is available from the hook event or the
`CODEX_GITHUB_FOOTER_MODEL` / `CODEX_MODEL` / `OPENAI_MODEL` /
`AI_MODEL` environment variables.

### Enforced today: Refs check

`.github/workflows/verify-issue-link.yml` shells out to
`scripts/issue_link.py verify`. The script:

- strips HTML comments from the PR body (so `<!-- Refs #1 -->` is ignored);
- extracts `(Refs|Closes|Fixes|Resolves) #<number>` lines (case-insensitive,
  line-anchored);
- verifies each `#N` resolves via `gh api /repos/<repo>/issues/<number>`;
- exits 0 only when at least one reference is present and every reference
  resolves.

When the gate fails because no reference is present, the script prints:

```
::error::PR body has no issue reference. Add a line like
'Refs #<num>' or 'Closes #<num>' (case-insensitive keywords:
Refs, Closes, Fixes, Resolves). See CLAUDE.md section 3.
```

When a reference is present but the issue does not exist, the script prints:

```
::error::Referenced #<N> does not exist in tvna/claude-md.
```

The fix for either failure is to add or correct the `Refs #<number>` line
in the `Related Issue` section of the PR body, then push a new commit (or
edit the PR description, which re-runs the workflow).

### Enforcement surfaces for issue-number existence checks

Per [#314](https://github.com/tvna/claude-md/issues/314), the existence
check on `#N` references is enforced on exactly one surface and
intentionally not enforced on the others. The decision and its rationale
are recorded here so future contributors do not need to re-derive them.

| Surface | Status | Rationale |
|---|---|---|
| PR body | Enforced. | `verify-issue-link.yml` runs `scripts/issue_link.py verify`, which calls `gh api /repos/<repo>/issues/<N>` per ref and fails with `Referenced #N does not exist in <repo>.` for unresolved numbers. |
| PR title | Inversely enforced. | `scripts/preflight_title_policy.py` (Layer 2.5) and `scripts/title_policy.py` (`verify-title-policy.yml`) deny any `(#NNN)` token in the title per [#167](https://github.com/tvna/claude-md/issues/167) / [#214](https://github.com/tvna/claude-md/issues/214). With the token forbidden, no number reaches the title to existence-check. |
| Squash commit subject | Transitively covered. | GitHub's squash-merge default forms the subject as `<PR title> (#<PR-number>)`. The PR title is already gated, and `(#<PR-number>)` is the merge-event-issued PR number for this repository, so a separate existence check would be redundant. |
| Individual commit message | Intentionally not enforced. | Only one commit lands on `main` per PR (squash merge), and that commit carries a PR body that has already passed `verify-issue-link.yml`. Gating every intermediate commit would (a) force a `Refs #N` line into commits whose link is already covered transitively, and (b) duplicate a check that the squash step makes structurally guaranteed. |

If the squash-merge default on `main` is ever loosened (for example,
allowing merge commits or rebase merges), the "transitively covered" and
"intentionally not enforced" rows no longer hold and the table must be
re-evaluated.

### Adjacent gates

`scripts/title_policy.py` enforces ASCII-only titles and the Conventional
Commit naming convention (titles only - it does not read the body). It is
not part of the body-policy gate, but contributors who hit a body-policy
failure often also need to fix their title at the same time.

## Trusted-bot bypass

`scripts/_trusted_bots.py` is the single source of truth for the
allowlist that `scripts/issue_link.py` and `scripts/scan_non_ascii.py`
consult. The current allowlist is:

```python
_TRUSTED_BOT_LOGINS: frozenset[str] = frozenset({"dependabot[bot]"})
```

When the PR author login is in the allowlist, `scripts/issue_link.py`
prints `skipped: trusted bot author (<login>)` and exits 0 without
checking for `Refs #N`. The rationale is that `dependabot[bot]` opens
PRs from `.github/dependabot.yml` configuration on a schedule and
cannot be made to write a `Refs #N` line; the dependency PRs are
labelled and reviewed through a separate path (see
`docs/runbooks/dependabot-automerge.md`). `scripts/scan_non_ascii.py`
has its own scanner-only extension for Codecov-generated PR comments;
that exception does not apply to the issue-link or body-policy gates.

Extension policy from the module docstring: exact match only, no
wildcards, extend one entry at a time. Any PR that adds a login to
the frozenset must cite both [#137](https://github.com/tvna/claude-md/issues/137)
and [#139](https://github.com/tvna/claude-md/issues/139) so the
historical context of the carve-out stays visible.

## Verify

```sh
# 1. The doc itself is ASCII-only (it must pass scan-non-ascii.yml).
python -c "import pathlib; \
  assert pathlib.Path('docs/standards/issue-pr-body-standard.md').read_text().isascii()"

# 2. The Refs check passes on an example PR body.
printf '## Related Issue\n\nRefs #206\n' > /tmp/pr-body.md
python scripts/issue_link.py verify --repo tvna/claude-md \
  --body-file /tmp/pr-body.md

# 3. The H2 baseline gate accepts a candidate PR body.
python scripts/body_policy.py verify \
  --kind pull_request \
  --body-file /tmp/pr-body.md

# 4. The post-2026-05-26 shape gate accepts the same body, given a
#    cutoff and a created-at that exercises the new gate.
python scripts/body_policy.py verify \
  --kind pull_request \
  --body-file /tmp/pr-body.md \
  --shape-cutoff 2026-05-26T00:00:00Z \
  --created-at 2026-05-27T00:00:00Z
```

## References

- [`docs/runbooks/issue-triage.md`](../runbooks/issue-triage.md) - label taxonomy and routing
  table; bodies are read only after labels route the issue.
- [`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md) -
  the PR template this runbook describes.
- [`.github/labels.json`](../.github/labels.json) - the `type:*` axis the
  type-specific guidance partitions on.
- [`scripts/issue_link.py`](../scripts/issue_link.py) - Refs-check gate.
- [`scripts/_trusted_bots.py`](../scripts/_trusted_bots.py) - allowlist
  single source of truth.
- [CLAUDE.md](../../CLAUDE.md) - sections 1, 2, 3, 4, 5 (rationale tie-in).
- [#196](https://github.com/tvna/claude-md/issues/196) - sibling standard
  for workflow scripts (will back-link to this doc when its runbook lands).
- [#197](https://github.com/tvna/claude-md/issues/197) - umbrella tracking
  issue for both standards.
- [#206](https://github.com/tvna/claude-md/issues/206) - the issue this
  runbook closes.
- [#314](https://github.com/tvna/claude-md/issues/314) - decision to
  enforce `#N` existence on the PR body surface only and document the
  other surfaces as intentionally non-enforced.
