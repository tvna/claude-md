# Retrospective -- PR #237 Auto-Retro Workflow Repair-Free Merge

This document is the retrospective for [#238](https://github.com/tvna/claude-md/issues/238) -- the post-merge review of PR [#237](https://github.com/tvna/claude-md/pull/237), which is Part 1 of issue [#234](https://github.com/tvna/claude-md/issues/234) ("centralize post-merge follow-up tracking"). The retrospective framework lives in CLAUDE.md section 3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR.

## Scope

- Target PR: [#237](https://github.com/tvna/claude-md/pull/237), merged as commit `4fa1b0a` on 2026-05-23T22:34:38Z.
- Requested issue: [#234](https://github.com/tvna/claude-md/issues/234) -- auto-open retrospective issue on merge (Part 1 of a 2-PR plan).
- Out of scope: the substance of the merged `scripts/auto_retro.py` / `.github/workflows/auto-retro.yml` / `tests/test_auto_retro.py` -- those were accepted as-merged.

## Repair history

PR #237 landed via a single commit on branch `claude/sweet-noether-2W8Jb` with **zero pre-merge repairs**. No reviewer comments, no PR-level comments, no review threads, and no failed CI check runs. The deterministic gates (`gate`, `verify`, `detect`, `scan`, `lint-scripts`) all passed on the first attempt; the `audit` and a second `verify` job correctly reported `skipped` because their path filters did not match the diff. The PR was open for 9 minutes (opened `22:25:57Z`, merged `22:34:38Z`).

| # | Repair | What the reviewer caught |
|---|---|---|
| -- | (none) | (none) |

## Classification

| Repair | Classification | Reasoning |
|---|---|---|
| (none) | n/a | No repair occurred. PR #237 landed in one shot; the harness, not the operator, was the prevention layer. |

## Earliest prevention point

Not applicable -- there are no repairs to prevent. The deterministic gates that exercised on this PR and reported clean were:

- `verify-body-policy.yml` -- PR body contains every required H2 in `_PR_REQUIRED` (`Facts`, `Assumptions`, `Risk & blast radius`, `Rollback`, `Verification`, `Checklist`).
- `verify-issue-link.yml` -- `Refs #234` present (intentional `Refs` not `Closes`, because Part 2 closes the umbrella).
- `verify-apm-drift.yml` -- diff did not touch `.apm/**`, so source-output equivalence was unaffected.
- `verify-apm-portability.yml` -- diff did not touch the compile output, so the portability check did not need to fire.
- `scan-non-ascii.yml` -- net-new files and PR body are ASCII-only.
- `lint-scripts.yml` -- `scripts/auto_retro.py` passed ruff + mypy.
- `pytest` via `gate.yml` -- 699 passed (77 new in `test_auto_retro.py`, 622 pre-existing, no regressions).

## No-repair reproduction path

PR #237 is itself the canonical reproduction path for the family "net-new script + workflow + tests, no rule edits". The next PR of this shape should:

1. **Plan phase**: enumerate facts and assumptions in the PR body before writing code; tag every line that is a guess with `speculation:` so reviewers see the surface area immediately (CLAUDE.md section 2).
2. **Edit phase**: prefer net-new files over edits when the change is additive. PR #237 added 3 files and modified 0; this minimizes blast radius and makes `git revert <sha>` a single-step rollback.
3. **Pattern match**: when a sibling pattern already exists in the harness (`scripts/scan_non_ascii.py` and `scripts/auto_retro.py` share the pure-function-top / `gh_api` subprocess-bottom shape), mirror it so reviewers can verify by analogy.
4. **Test phase**: run the targeted suite (`uv run pytest tests/test_<new_module>.py -v`) AND the full suite (`uv run pytest -q`); report both numbers in the PR body's `## Verification` block.
5. **Body phase**: open the PR with every required H2 section populated. The `verify-body-policy` gate enforces structure; the reviewer enforces honesty (no speculation hiding under `## Facts`).
6. **CI phase**: wait for `gate.yml` to report all jobs green. Post-merge verification items in the `## Verification` block (e.g. "observe `auto-retro.yml` fire on the next non-bot, non-retro PR merge") become the retro issue itself -- that issue IS the proof, not a separate audit.

## Gates exercised alongside this retrospective

| Gate | Outcome on PR #237 |
|---|---|
| `auto-retro.yml` (the PR's own delivery) | Fired post-merge at `22:34:43Z` on commit `4fa1b0a`; opened retro issue #238 successfully. This single observation confirms acceptance criteria 1 and 3 of the source PR's `## Verification` block (fires once on non-bot non-retro merge; auto-opened body passes `verify-body-policy`). |
| `verify-body-policy` (on issue #238) | Auto-opened body contains all five `_ISSUE_COMMON_REQUIRED` sections (`Scope`, `Facts`, `Proposed work`, `Verification`, `Acceptance criteria`). |
| Idempotency via `/search/issues` | Not yet exercised in production (no PR has been re-opened + re-merged). Acceptance criterion 2 of PR #237's verification block remains `[ ]` until that path is naturally triggered. |

## Follow-up issues

(none) -- no missing deterministic gate, unclear agent instruction, or external/human decision was surfaced by PR #237. The no-repair outcome is the artifact.

## References

- Retro issue: [#238](https://github.com/tvna/claude-md/issues/238) (this document closes it).
- Source PR: [#237](https://github.com/tvna/claude-md/pull/237) (merge commit `4fa1b0a`).
- Parent issue: [#234](https://github.com/tvna/claude-md/issues/234) -- auto-open retrospective issue on merge (Part 2 still pending).
- Framework: CLAUDE.md section 3, codified in commit `daa5179` (#225).
- Sibling retrospective: `retrospective-pr-229.md`.
