# Freshness Precondition Gate Refresh and Auto-Refresh Design

Refs #894
Refs #654
Refs #859

This document is the repo-local concrete companion to the universal-text
rule added for #894. The universal text (master section 3) carries only the
tool-agnostic principle: *a time-boxed precondition gate must be refreshed
immediately before each guarded operation, and the durable fix folds that
refresh into the gate itself.* This document names the concrete gate, the
concrete failure, and the future skill that closes the loop.

## Scope

This design covers the client-side freshness preflight that guards branch
creation: `scripts/preflight_main_freshness.py`, registered as a
`PreToolUse` hook for `mcp__github__create_branch` in `.claude/settings.json`.

In scope:

- Why the per-session `record` model expires mid-flow in a multi-PR session.
- The interim agent contract (issue #894 Option A), restated in abstract
  form in the universal text.
- The durable auto-refresh design (issue #894 Option B) that is intended to
  be promoted into a skill.

Out of scope:

- Changing the 60-minute TTL value itself (issue #894 Option C). Raising the
  TTL only widens the window; it does not remove the mid-flow expiry class,
  so it is recorded as rejected, not adopted.
- Editing `docs/prd/agent-rules-design-philosophy.md`. That document has its
  own update procedure (its section 9) and is not touched by this PR.

## Facts

- `scripts/preflight_main_freshness.py` writes a stamp
  (`.git/MAIN_FRESHNESS_STAMP`) on the `record` subcommand and denies
  `mcp__github__create_branch` when the stamp is missing or older than
  `DEFAULT_TTL_SECONDS` (3600 s = 60 min). Refs #654.
- The `record` step is invoked manually or at session start; nothing
  re-records it automatically between guarded operations.
- A multi-PR flow that spans more than the TTL between two branch creations
  always hits at least one stale-stamp denial unless the agent re-records
  first. Observed in the session for #859, between the PR #876 merge and the
  PR #880 branch creation.
- `fetch_and_record()` already performs the deterministic currency proof the
  auto-refresh needs: it runs `git fetch origin main`, resolves the SHA, and
  writes the stamp. The denial path (`build_deny_reason`) and the refresh
  path share the same module today.

## Assumptions

- speculation: The mid-flow denial is most expensive not as latency but as
  misdiagnosis risk; the agent can read the denial as a branch-protection
  failure and take an incorrect recovery action.
- speculation: Auto-refresh is safe to fold into the gate only when the
  refresh is itself deterministic and verifiable (a successful `git fetch`
  plus SHA resolution). A refresh that cannot prove currency must still deny
  rather than silently stamp a stale view of `main`.
- speculation: The auto-refresh belongs in a skill rather than inline hook
  code so the currency-proof-then-refresh sequence is reusable by any
  time-boxed gate, not just the branch-creation one.

## Lane mapping

The issue #894 Option A wording ("before every `mcp__github__create_branch`
call ... run `python scripts/preflight_main_freshness.py record`") names a
vendor tool and a repository script. Walking the decision tree in
`docs/prd/agent-rules-design-philosophy.md` section 4:

- Q1 (tool-agnostic?): No; it names `mcp__github__create_branch` and a
  concrete script path. The rule is therefore demoted out of the universal
  text in its literal form.
- The abstract, tool-agnostic form ("refresh a time-boxed precondition
  immediately before each guarded operation; fold the refresh into the gate")
  is what lands in the universal text.
- This document carries the concrete form: the named gate, the named tool,
  the named TTL, and the named session evidence.

That split is the whole point of "abstract Option A": the principle is
universal, the nouns are repo-local.

## Interim contract (Option A, abstracted)

Until the auto-refresh lands, the agent satisfies the gate per operation:
re-establish the freshness observation immediately before each guarded branch
creation rather than once per session. In this repository that is
`python3 scripts/preflight_main_freshness.py record` run before each
`mcp__github__create_branch` in a multi-PR flow. The universal text states
the principle; this line states the command.

## Future skill-ification plan (Option B, durable)

The durable fix promotes the per-operation refresh into the gate so currency
is harness-enforced rather than agent-remembered. The intended shape:

1. **Currency proof.** Before denying a stale or missing stamp, attempt a
   deterministic refresh: `git fetch origin main` and resolve the SHA
   (`fetch_and_record()` already does this).
2. **Auto-record on proof.** If the fetch succeeds, write a fresh stamp and
   allow the operation. The window can no longer expire mid-flow because the
   gate re-establishes it on demand.
3. **Deny only on unprovable currency.** If the fetch fails (offline, auth
   failure, diverged remote), keep the hard deny with the existing
   `build_deny_reason` message. Fail loud, never silently stamp.

This sequence; prove currency, then refresh, else deny; is the reusable
unit. The skill-ification premise is that this unit is packaged as a skill
so any future time-boxed precondition gate (not only branch creation) can
adopt auto-refresh without re-implementing the fetch-and-prove logic. The
universal-text rule is written to anticipate that promotion: it already
says the durable form is "harness-enforced, not agent-remembered."

When the skill lands, the interim per-operation `record` instruction becomes
redundant and this document's "Interim contract" section is retired.

## Acceptance criteria

- [x] The universal instruction text carries the abstract time-boxed-gate
      refresh principle (master section 3; compiled into `CLAUDE.md` /
      `AGENTS.md`).
- [x] A repo-local document carries the concrete create_branch / freshness
      mapping and the future auto-refresh skill plan (this file).
- [ ] (future issue) `preflight_main_freshness.py` gains an auto-refresh mode
      that re-records when `main` is verifiably current and denies only when
      currency cannot be proven.

## Verification

This PR is documentation plus the governed universal-text edit. The checks
that prove it are deterministic:

```sh
# Universal artifacts are the verbatim apm compile output and carry no
# repo-local nouns.
uv run --with "apm-cli==$(python3 scripts/flake_pin.py version --tool apm)" --exclude-newer "14 days" apm compile
git diff --exit-code; CLAUDE.md AGENTS.md
python3 scripts/scan_apm_portability.py verify \
  --path .apm/instructions/master.instructions.md \
  --path CLAUDE.md --path AGENTS.md
python3 scripts/verify_apm_checksums.py verify

# Docs inventory and links resolve.
python3 scripts/scan_docs_inventory.py verify
python3 scripts/scan_markdown_links.py verify
```

The auto-refresh behavior is out of scope for this PR and is not claimed to
be implemented; it is tracked as the future issue in the acceptance criteria.

## References

- #894; this issue: stamp expires mid-session, blocking create_branch in
  multi-PR flows. Source of Option A / B / C.
- #654; the freshness preflight that introduced the 60-minute TTL gate.
- #859; the multi-PR session where the mid-flow denial was observed
  (between PR #876 and PR #880).
- `scripts/preflight_main_freshness.py`; the concrete gate.
- `.claude/settings.json`; the `PreToolUse` hook registration.
- `docs/prd/agent-rules-design-philosophy.md`; the lane decision tree this
  document follows; not modified here.
