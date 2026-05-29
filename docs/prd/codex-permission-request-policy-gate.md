# Codex PermissionRequest Policy Gate Design

Refs #711
Refs #617
Refs #604

## Scope

This design scopes a future Codex `PermissionRequest` hook adapter. It does
not enable the hook. The future implementation may only proceed after the
shared policy predicate, fixtures, tests, Claude parity evidence, and rollback
path are present in the implementation PR.

The Codex-specific entry point is the event and payload adapter. The
authorization rule itself must be a shared repository policy predicate, not a
Codex-only branch in `.codex/hooks.json` or a Codex-only script path.

## Facts

- #604 tracks repository hook parity for Codex.
- #617 accepts `PermissionRequest` only as a child-issue candidate.
- #711 scopes this child issue as a planning step, not as hook enablement.
- `.claude/settings.json` and `.codex/hooks.json` are both reviewed carve-outs
  for deterministic repository-owned hook triggers.
- Existing Codex hook config may mirror Claude hook scripts only when behavior
  is payload-independent or tested for both payload shapes.

## Assumptions

- speculation: `PermissionRequest` is useful only when a repository-owned
  policy can return deterministic allow, deny, and no-decision verdicts at the
  approval boundary.
- speculation: Claude may not need the same event entry point when an existing
  Claude hook, permission rule, or CI gate already enforces the same policy
  guarantee.
- speculation: Existing `PreToolUse` hooks should remain the body-shape and
  preflight enforcement surface.

## Required Architecture

The future implementation must split three responsibilities:

1. **Shared predicate.** Repository-owned code receives normalized inputs and
   returns `allow`, `deny`, or `no-decision`. This predicate owns the policy.
2. **Codex adapter.** Codex `PermissionRequest` parsing maps the event payload
   into the shared predicate input. This adapter owns only event-shape glue.
3. **Claude parity path.** The implementation PR must identify the existing
   Claude hook, permission rule, or CI gate that provides the same policy
   guarantee, or link a follow-up issue that blocks broad rollout until parity
   is resolved.

The policy predicate must be testable without either hook runtime. Hook tests
then prove each runtime adapter calls the same predicate with the expected
normalized fields.

## Fixture And Test Contract

The implementation PR must include fixture-backed tests for:

- allow, deny, and no-decision verdicts from the shared predicate.
- malformed JSON, which must return no decision rather than wedging the session.
- unsupported payload, which must return no decision.
- a Codex-shaped `PermissionRequest` payload that proves the adapter is narrow.
- Claude parity evidence through an existing fixture-backed hook test,
  permission-rule test, CI-gate test, or linked follow-up issue.
- `.codex/hooks.json` matcher behavior, proving the event and tool matcher are
  narrower than a broad catch-all permission gate.

The implementation must not update `.codex/hooks.json` until these tests exist
and prove the matcher is narrow.

## Rollback

The implementation PR must include a rollback command that removes the Codex
hook registration while leaving the shared predicate tests available for future
repair. The expected form is:

```sh
git revert <merge-sha>
```

If the implementation touches more than `.codex/hooks.json`, the PR must also
list the exact files that are safe to leave in place after revert and the files
that must be removed by a follow-up repair.

## Targeted Verification

The implementation PR must run targeted verification before requesting review:

```sh
python3 -m pytest tests/test_codex_hooks_config.py -q
python3 -m pytest <shared-policy-test-file> -q
python3 -m pytest <claude-parity-test-file> -q
```

The PR may replace the placeholder test paths with concrete files introduced
by the implementation. Type checks and linters may be included, but they do not
replace the fixture-backed behavior checks above.

## Non-Goals

- Do not implement or enable the `PermissionRequest` hook in this design PR.
- Do not create a Codex-only policy that lacks a Claude parity explanation.
- Do not broaden existing `PreToolUse` hooks to approximate approval-time
  behavior.
