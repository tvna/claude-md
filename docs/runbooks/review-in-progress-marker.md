# Automated reviewer in-progress marker gate

## Scope

This runbook covers the "Block merge while an automated reviewer's
in-progress marker is present" required check (`scripts/scan_review_in_progress_marker.py`,
wired into the `Portable PR policy / gate` job of `.github/workflows/verify-pr.yml`).
Read this when that check is red, or when deciding whether to extend the
marker to another automated reviewer.

## Why

PR #2309 was merged 103 seconds after it was opened, while most required
checks were still `queued` or `in_progress` and `mergeable_state` was
`blocked`. The repository owner suspected an automated reviewer's status
marker had been misread as "review complete" before it actually finished.

Investigating issue #2312 confirmed the mechanism live on scratch PR #2319:
`chatgpt-codex-connector[bot]` (the OpenAI Codex GitHub review app; already
carved out in `.github/trusted_bots.toml` for #1731) adds an "eyes" (👀)
reaction to the PR's top-level body 6 seconds after PR creation, marking its
review as in progress. When the review finishes, it removes that reaction
and replaces it with either:

- a **"+1" (👍) reaction** on the PR, if it has no suggestions, or
- a **review comment** whose body starts with a lightbulb-emoji "Codex
  Review" heading, if it has suggestions.

Both transitions were observed directly via `GET
/repos/{owner}/{repo}/issues/{number}/reactions` and `GET
/repos/{owner}/{repo}/pulls/{number}/reviews`: the eyes reaction from PR
#2319 was removed and replaced by a "+1" 2 minutes 6 seconds after it
appeared. This gate turns that observation into a deterministic,
hard-blocking required check so a PR cannot merge while the eyes reaction is
present, closing the gap that let PR #2309 merge mid-review.

GitHub Copilot's PR review feature is not configured in this repository (no
Copilot login is registered in `.github/trusted_bots.toml`), so this gate
covers only the confirmed Codex marker. Extend
`[review_in_progress_marker]` in `.github/trusted_bots.toml` if Copilot
review (or another automated reviewer) is enabled later and is confirmed to
use the same eyes-reaction convention; do not add a login on speculation
alone (CLAUDE.md section 2).

## Why not

- **Absence-based detection** (blocking merge whenever no completion marker
  has appeared yet) was considered and rejected: without a positive
  in-progress signal, a PR the automated reviewer never touches (a fork,
  a reviewer outage, a repo where the review is disabled) would block
  forever. The confirmed "eyes" reaction is a genuine positive signal, so
  this gate never blocks a PR the reviewer isn't actively working on.
- **A time-boxed grace period** (auto-pass once N minutes have elapsed
  without a completion marker) was the fallback design before the eyes
  reaction was confirmed; it is unnecessary now that a real in-progress
  signal exists, and would have reintroduced exactly the premature-merge
  race this gate exists to close.

## Procedure

1. **If this check is red ("review-in-progress marker present")**: an
   automated reviewer is actively analyzing the PR. Wait for it to finish
   (typically a few minutes; 2m6s in the observed sample), then re-run the
   check.
2. **The check does not re-run itself automatically once the marker
   clears.** The eyes-to-completion transition (a reaction add/remove) does
   not fire any of the `pull_request` webhook event types this workflow
   listens to (`opened, edited, synchronize, reopened, ready_for_review,
   labeled, unlabeled`), so the required check stays red until one of:
   - re-run the failed job from the GitHub Actions UI ("Re-run jobs"), or
   - push a new commit, or
   - make any trivial edit to the PR title or body (fires the `edited`
     event).
3. **Owner override**: there is no override flag. The owner's stated
   preference (issue #2312) is a hard block with no bypass; if a genuine
   emergency requires bypassing it, use the repository's standard required-
   check bypass path (an admin merge with bypass, logged and justified),
   not a change to this gate.
4. **Confirm the marker yourself** (for triage): `GET
   /repos/{owner}/{repo}/issues/{number}/reactions` and look for a
   `content: "eyes"` entry whose `user.login` is `chatgpt-codex-connector`
   or `chatgpt-codex-connector[bot]`.

## Verification

- `uv run pytest tests/test_scan_review_in_progress_marker.py -q`
- `uv run python scripts/scan_review_in_progress_marker.py verify` with
  `REPO`, `PR_NUMBER`, and `GH_TOKEN` set against a PR currently carrying
  the eyes reaction: exits 1 with an `::error::` line. Against a PR without
  it (not yet reviewed, or already completed): exits 0 with an `OK:` line.
- A live scratch PR under active Codex review shows the "Portable PR policy
  / gate" required check red while the eyes reaction is present, then green
  after a re-run once the reaction is replaced.

## Pause / Resume

This is a stateless per-PR check with no long-running process to pause; it
re-evaluates fresh on every workflow run. To temporarily disable it
repo-wide, remove the "Block merge while an automated reviewer's
in-progress marker is present" step from `verify-pr.yml`'s
`portable-pr-policy` job; there is no partial-pause mode.

## Rollback

Revert the commit(s) that introduced this gate
(`scripts/scan_review_in_progress_marker.py`, the `verify-pr.yml` step, the
`.gitapex/ssot.json` entry, and the `[review_in_progress_marker]` table in
`.github/trusted_bots.toml`) via `git revert`. No data migration; the check
is advisory-free (pure read of PR reactions), so reverting it has no other
side effects.

## References

- Issue #2312 (this gate's design issue).
- Refs #2309 (the premature-merge incident that prompted the investigation).
- Refs #1731 (`chatgpt-codex-connector` trusted-bot carve-out precedent).
- `scripts/scan_review_in_progress_marker.py`; the gate implementation.
- `.github/trusted_bots.toml`; the `[review_in_progress_marker]` login
  allowlist.
- `.github/workflows/verify-pr.yml`; the `portable-pr-policy` job wiring.
