# README translation drift gate

> Issue #476 (`feat(harness): add README translation-drift gate ...`). Companion to `scripts/verify_readme_translation.py` and the `Validate README translation parity` step in `.github/workflows/verify-pr.yml`.

This runbook documents the deterministic gate that prevents `README.md`
from drifting away from `README.ja.md` and `README.zh.md` PR-by-PR, and
the opt-out marker authors use when an English-only edit is legitimate.

## Overview

Before this gate landed, `README.md` had absorbed five substantive
changes that never propagated to either translation. The translations
diverged silently because no workflow asserted the trio moves together
and reviewers had no deterministic signal to catch the drift. Per
[CLAUDE.md](../../CLAUDE.md) section 3, "build the harness first":
translation parity must not depend on operator memory.

### SoT layout

| File | Target | Purpose |
|---|---|---|
| `docs/runbooks/readme-translation-drift.md` *(this file)* | - | Runbook describing the gate and the opt-out procedure |
| `scripts/verify_readme_translation.py` | CI | Deterministic gate that compares `git diff --name-only base..HEAD` against the README allowlist |
| `tests/test_verify_readme_translation.py` | local + CI | Unit tests for the pure functions and the CLI exit codes |
| `.github/workflows/verify-pr.yml` | GitHub Actions | Hosts the `Validate README translation parity` step inside the `gate` job |
| `README.md` / `README.ja.md` / `README.zh.md` | repo root | The three files whose modification sets the gate guards |

## Gate behavior

The gate runs on every `pull_request` event (opened, edited,
synchronize, reopened, ready_for_review). It computes the changed-file
set against the PR base ref, intersects it with
`{README.md, README.ja.md, README.zh.md}`, and applies the rules
below.

| `README.md` changed | Both translations changed | Skip marker | Exit | Outcome |
|---|---|---|---|---|
| no | - | - | 0 | OK (no README touched) |
| yes | yes | - | 0 | OK (trio moved together) |
| yes | no | yes | 0 | OK (opt-out recorded in PR body) |
| yes | no | no | 1 | Drift detected, see `::error::` line |
| no | yes (one or both) | - | 0 | OK (translation-only PR allowed) |

Translation-only edits are intentionally not blocked: the gate guards
the English-only-edit failure mode (the historical drift cause), not
the inverse. Reviewers catch translation-only churn through normal
review.

### Where it runs

The step lives inside the `gate` job of
`.github/workflows/verify-pr.yml`. The job's existing
required-status-check context `Portable PR policy / gate` (pinned in
`.github/rulesets/main.json`) covers this step too -- no ruleset
change was needed when the gate landed.

The job already checks out with `fetch-depth: 0`, so
`git diff origin/<base>..HEAD` is reachable without an extra checkout step.

### Failure surface

Example `::error::` line emitted on drift:

```
::error::README.md was modified without matching updates to
README.ja.md, README.zh.md. Either edit the missing translation(s) in
the same PR, or add the literal marker
'<!-- readme-translation-ack -->' to the PR body with a rationale.
See docs/runbooks/readme-translation-drift.md and Issue #476.
```

Per CLAUDE.md section 4 the gate fails loud (exit 1) so the
`Portable PR policy / gate` required check goes red and the PR
cannot merge.

## Opt-out marker

Authors who deliberately ship an English-only README edit add the
literal marker

```
<!-- readme-translation-ack -->
```

anywhere in the PR body. Matching is case-insensitive and tolerates
extra whitespace inside the comment, so all of the following qualify:

- `<!-- readme-translation-ack -->`
- `<!--readme-translation-ack-->`
- `<!--   Readme-Translation-ACK   -->`

The marker is itself an HTML comment, so it does not render in the
GitHub PR description while still being machine-detectable. The
pattern mirrors `<!-- partial -->` (Issue #216) and the other
`-ack` markers in this repo (`<!-- non-ascii-ack -->`,
`<!-- action-pin-ack -->`, `<!-- pip-install-ack -->`).

### When the marker is appropriate

- The edit is genuinely English-only (typo, code-fence renderer fix, a
  link target that does not exist in the translated docs yet) and the
  PR body explains why no translation is required.
- A follow-up issue is filed to catch the translations up later. Cite
  that issue number on the same line or in a `Refs #<n>` line so
  reviewers see the open commitment.

### When the marker is NOT appropriate

- Substantive content addition (new section, new bullet, new code
  block). These must land with translations in the same PR; that is
  exactly the drift the gate was built to stop.
- "Will translate later" with no follow-up issue. The marker becomes a
  silent escape hatch the moment it stops carrying a rationale.

Reviewers should treat the marker like any other `-ack` line: confirm
the rationale is visible in the PR body, and push back when an edit is
substantive enough that the translation should ride along.

## Translation update procedure

The default is "edit all three files in the same PR". The expected
update flow:

1. Edit `README.md` first.
2. Add the equivalent content to `README.ja.md` and `README.zh.md` in
   the same commit. The headings already mirror each other one-to-one,
   so the position is usually obvious.
3. If a translation cannot be finished in this PR (e.g. specialised
   terminology requires a separate review), file a follow-up issue,
   add a placeholder bullet of the form
   `- (TBD: <one-line English summary>)` in the translation, and refer
   to the follow-up issue from the placeholder so it is not lost.
4. Run `python3 scripts/verify_readme_translation.py verify
   --base-ref origin/main --body-file /dev/null` locally to confirm
   the gate is green before pushing.

Reviewers should sanity-check that the translated bullet says
substantively the same thing as the English bullet, that the headings
still match, and that any link targets resolve in both languages.
