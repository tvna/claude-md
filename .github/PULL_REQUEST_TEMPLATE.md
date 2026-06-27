<!--
Conclusion first (BLUF: Bottom Line Up Front). The Summary below is the
single most important block: a reviewer should be able to read it alone
and know what changed, whether it is verified, and how risky it is. Keep
the detail (Facts, evidence, rollback) further down; keep the issue link
(Related Issue) at the very end per GitHub convention.

PR body shape is enforced by scripts/body_policy.py (server-side via
.github/workflows/verify-pr.yml, portable-pr-policy job) and mirrored
client-side by scripts/preflight_pr_template_shape.py. The H2 headings
are an allowlist: only the sections in this template may appear. See
docs/standards/issue-pr-body-standard.md.

Note: the GitHub MCP write tools strip a bare angle-bracket placeholder
(e.g. <sha>) as an unknown HTML tag, deleting it entirely (fenced code
blocks included). When authoring through those tools, name the value in
plain words instead. See docs/standards/issue-pr-body-standard.md.
-->

## Summary

<!--
The conclusion, in one or two sentences: what this PR changes, whether
verification passed, and the risk level. Lead with the outcome, not the
journey.
GOOD: "Adds the H2 allowlist gate; pytest green (684 passed); low risk, CI-only, single git revert to roll back."
BAD:  "Updates the code." / "Various improvements." / any sentence that describes the journey rather than the outcome.
-->

-

<!--
Facts; CLAUDE.md section 2.
State only what is observable: diffs, command output, test names, log lines.
No speculation in this section. If you cannot point to evidence, move the
line to Assumptions below.
GOOD: "- Fact: scripts/body_policy.py line 58 defines 9 required PR sections."
BAD:  "- The change should improve performance." (unverified; move to Assumptions with a Speculation: tag)
-->
## Facts

-

<!--
Assumptions; CLAUDE.md section 2.
List what you are trusting but did not verify (library behavior, runtime
environment, upstream contracts, reviewer intent). Tag each line with
"speculation:" when it is a guess rather than a documented fact.
GOOD: "- Speculation: upstream library behavior is unchanged because no release notes mention it."
BAD:  "- Fact: this will work correctly." (unverified claim presented as a fact; tag it Speculation: instead)
-->
## Assumptions

-

<!--
Risk and blast radius; CLAUDE.md section 4.
Who or what is affected if this change is wrong, and how reversible is it?
Call out destructive or irreversible operations (deletes, force-push,
schema migrations, outbound sends, payments).
-->
## Risk and blast radius

-

<!--
Rollback; CLAUDE.md section 4.
Exact steps to revert or disable this change when it misbehaves in prod.
For low-risk changes a single `git revert <sha>` is fine; say so explicitly.
For risky changes list the feature flag, config toggle, or migration-down
command a responder would run.
-->
## Rollback

-

<!--
Text delta; required ONLY when this PR changes universal instruction text
(.apm/instructions/**, CLAUDE.md, or AGENTS.md). When it does, ADD a section
exactly like the following (heading included), filled in. It is enforced by
scripts/verify_text_delta_section.py inside the portable-pr-policy job of
verify-pr.yml, which needs
all three: a signed character-count change, what context the change adds, and
what context it removes (say "moved" when a concept only relocated). Omit the
section entirely when the PR touches no instruction text.

## Text delta

- chars: <e.g. +20 or -3>
- Added context: <wording/concepts introduced>
- Removed context: <wording/concepts dropped; say "moved" if relocated>
-->

<!--
Verification; CLAUDE.md section 1.
Each entry is one observed verification, listed as a `command:` line and
its `result:` line. Treat these as Facts-tier evidence (CLAUDE.md section
2): only what was actually run, no plans, no speculation. Multiple
entries are encouraged when multiple commands were run.

Required shape (enforced by scripts/body_policy.py verify_pr_verification_pairs
for PRs created on or after 2026-05-26):

- command: `<inline-code>`
  result: `<exit 0, OK marker, N passed summary, or explicit failure>`

GOOD:
- command: `uv run python -m pytest -q`
  result: `684 passed in 12.3s`
BAD:  leaving command or result as empty backtick pairs (the template default ``); replace both with actual run output before creating the PR.
-->
## Verification

- command: ``
  result: ``

<!--
Checklist; CLAUDE.md section 3.
Three H3 subsections separate items by automation layer. Required shape
enforced by scripts/body_policy.py verify_pr_checklist_subsections for
PRs created on or after 2026-05-26.
-->
## Checklist

### Bootstrap

<!--
Human cognition only. The author must judge each item; no CI or hook can
verify them. Leaving any item unchecked is a deliberate signal that the
author has not yet finished bounding the change.
-->

- [ ] Facts vs. Assumptions split is honest (no speculation lurking in Facts)
- [ ] Risk and blast radius assessed; Rollback steps are runnable
- [ ] Issue number recorded on the `Closes #` line below (or `Refs #` with rationale per the template comment)
- [ ] Replacement PR preflight passed when this PR replaces another PR for the same issue/session (`scripts/preflight_replacement_pr.py verify`, Issue #632)

### After-merge (CI)

<!--
Deterministic gates. CI verifies these. The Verification section above
should already contain matching command/result pairs for each item.
Check the box only when the matching pair is present.
-->

- [ ] `uv run python -m pytest -q` exits 0 (paired in Verification above)
- [ ] CI green on the merge commit (all required status checks)
- [ ] CLAUDE.md / AGENTS.md regenerated if applicable (`apm compile` produced no diff)
- [ ] If this PR touches `.apm/instructions/**`, `CLAUDE.md`, or `AGENTS.md`: `verify-pr.yml` (`portable-pr-policy` job) green (covers both portability scan and `apm compile` drift); any `portability-ack:` marker cites its authorizing sub-issue and reviewer applied `docs/runbooks/downstream-instruction-review-checklist.md`

### Post-merge (auto-retro signal)

<!--
Operator checklist filled AFTER observing the merge. The merge-time
auto-retro (the open-retro job of .github/workflows/post-merge.yml) no longer scans this
subsection; per #418, the items below are unchecked at merge time by
design, so treating them as repair signals at that moment produced
structural false positives. A deferred re-scan workflow (#421) will
revisit this subsection later and append rows to the retro issue for
items that remain unchecked once the observation window has closed.
-->

- [ ] Linked issue closed by the merge (or `Refs #` with rationale recorded)
- [ ] auto-retro issue opened by the open-retro job of `.github/workflows/post-merge.yml`
- [ ] No follow-up `fix(...)` PR needed within 24h of merge

<!--
Resource Consumption; CLAUDE.md section 3 / section 6.
The resource cost of producing this PR, measured as a per-PR window: the
time and tokens spent since the previous PR-create in this session (or since
session start for the first PR), not the cumulative session total; so a
session that opens several PRs does not re-count an earlier PR's tokens
(#1435). Generate it with `python3 scripts/session_resource_report.py` (which
reads the current Claude Code session id, the per-PR checkpoint advanced by
the create_pull_request hook, the CCR_SPAWN_TIMESTAMP_MS session-start epoch,
and `ccusage session --json`) and paste the output over the lines below.

The Model(s) line is the redacted capability tier (Opus-class / Sonnet-class
/ Haiku-class, or other-class for any other model), never the exact model id:
the generator collapses the ccusage modelsUsed id deterministically so the
canonical output carries the tier and the verbatim version string is never
written into the body. Do not hand-edit it back to a precise id.

When no session data is available; a human-authored PR with no ccusage
session, or ccusage absent; the generator emits the
`unavailable (no session data)` form shown below; keep that marker rather
than deleting the section. The section is required on every PR; trusted-bot
authors (dependabot) are skipped by scripts/body_policy.py, so their PRs
need not carry it.
-->
## Resource Consumption

- Elapsed (since previous PR or session start): unavailable (no session data)
- Total tokens: unavailable (no session data)
- Cost (USD): unavailable (no session data)
- Model(s): unavailable (no session data)

<!--
Related Issue; CLAUDE.md section 3. Kept last (before the footer) per
GitHub convention: the closing keyword reads naturally at the end of the
body and the conclusion (Summary) stays at the top.

Per CLAUDE.md section 3, every PR must reference its issue (`#<number>`).
The line below is validated by the issue-link step inside the
portable-pr-policy job of .github/workflows/verify-pr.yml on every
`pull_request` event and enforced as a required status check on `main`
via the `Portable PR policy / gate` context (see
.github/rulesets/main.json).

The reference lives on the `Closes #<number>` / `Refs #<number>` line in
this body ONLY; it must NOT be duplicated in the PR title. A `(#NNN)`
token in the title is rejected by scripts/title_policy.py
(portable-pr-policy job of verify-pr.yml) per #167 / #214, because this
body line is the
single source of truth for the issue link. "Cite the issue number in every
PR" (CLAUDE.md section 3) means this body line, not the title. Exception:
a `revert(<scope>): ...` title may keep a `(#NNN)` token that names the
reverted PR/commit; that reference identifies the rolled-back change, not
a redundant copy of this issue link.

Default: `Closes #<number>` so the linked issue auto-closes on merge.
GitHub auto-closes on: Closes, Closed, Fixes, Fixed, Resolves, Resolved
(case-insensitive, including conjugations).

Use `Refs #<number>` instead ONLY when this PR is partial work whose
merge must NOT close the linked issue, AND one of the following holds:
  - the linked issue carries the `type:tracking` label (umbrella issue
    that lives on while children land), OR
  - add a literal `<!-- partial -->` line below to opt out of the
    closing-keyword gate (see scripts/issue_link.py and #216).
-->
## Related Issue

Closes #

<!--
Agent attribution; required by scripts/body_policy.py for PRs created on
or after 2026-05-26. Replace the label and URL with the agent/session that
created or last corrected this body, for example Claude Code. Codex-authored
GitHub posts must use the model-aware Codex form.
Note: under the web harness (CLAUDE_CODE_REMOTE=true) create_pull_request
auto-appends exactly one footer, so the create body must carry NO manual
footer; update_pull_request is not auto-appended and still requires one
trailing footer. See docs/standards/issue-pr-body-standard.md (Refs #1025).
-->
_Generated by [Agent Name](agent-session-url)_
