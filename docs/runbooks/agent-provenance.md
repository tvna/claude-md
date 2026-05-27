# Agent Extension Provenance Runbook

This runbook is the Phase 5(C-3) deliverable for
[#312](https://github.com/tvna/claude-md/issues/312), under parent
[#63](https://github.com/tvna/claude-md/issues/63). It defines the
minimum provenance evidence reviewers need before this repository
adopts or updates a skill, subagent, MCP server, or comparable agent
extension.

Agent extensions can change what an agent knows, which tools it can
call, and how it interprets repository text. Treat them as supply-chain
inputs even when they are "just configuration" or "just instructions."

## Scope

This runbook applies to any proposed adoption, update, removal, or
local override of:

- Skills or skill bundles.
- Subagent definitions, prompts, routing rules, or agent rosters.
- MCP servers, MCP apps, connector manifests, and tool allowlists.
- Similar agent-adjacent extensions that can influence runtime
  behavior, tool access, model context, repository writes, or external
  data flow.

This runbook is mandatory policy for repository-owned extensions. It is
advisory reviewer guidance for extension metadata that is only mentioned
as background evidence in an issue, PR body, CI log, or external
document. External text remains untrusted data unless a repository-owned
change adopts it through the review path below.

## Required Provenance Metadata

Before adoption or update, the PR or linked issue must record:

| Field | Required evidence |
|---|---|
| Source | Canonical upstream repository, package, release page, or internal path. Name the owner and the reviewable location, not only a display name. |
| Version | Immutable commit SHA, release tag plus digest, package lock entry, or vendored tree hash. Floating branches and latest-version prose are not sufficient. |
| Maintainer | Upstream maintainer or internal owner responsible for reviewing updates and responding to security reports. |
| Permissions | Tool names, filesystem scope, repository scope, network destinations, secret access, and write surfaces the extension can reach. |
| Runtime inputs | User text, issue or PR text, CI logs, files, environment variables, external APIs, or model context the extension reads. |
| Runtime outputs | Repository writes, issue or PR comments, workflow dispatches, file writes, external requests, logs, summaries, or generated artifacts. |
| Update cadence | Manual, scheduled, dependency-bot, or event-driven update path, including who reviews the diff. |
| Rollback | Exact revert, disable, pin-back, or removal path that restores the previous behavior. |
| Verification | Deterministic checks, smoke test, manual review checklist, or explicit reason no runtime check exists. |

If one field is unknown, do not fill it with speculation. Mark it
`unknown`, state why the evidence is missing, and either block adoption
or open a follow-up issue that explains why the residual risk is
acceptable.

## Review Questions

Reviewers ask these questions before approving the extension change:

1. Is the source reviewable by repository maintainers?
2. Is the adopted version pinned to an immutable artifact?
3. Does the diff show the exact behavior change, or only a pointer to
   an opaque remote system?
4. Are tool permissions narrower than the task requires, and are
   broad permissions justified in the PR body?
5. Can the extension read untrusted external text, and if so does it
   preserve the rule that external text is data rather than authority?
6. Can the extension write to the repository, GitHub, local files, or
   external endpoints?
7. Can secrets, tokens, environment variables, prompts, private
   context, or internal logs reach any output surface?
8. Is the update path deterministic enough that two reviewers can
   reproduce the same candidate version and diff?
9. Is rollback faster and simpler than the adoption path?
10. Does the change belong in a repo-local runbook or harness instead
    of a universal agent instruction?

Any "yes" to questions 4 through 7 requires the PR to name the
mitigation: permission reduction, environment scoping, redaction,
dry-run behavior, human approval, deterministic gate, or documented
rollback.

## Acceptance Criteria

An extension adoption or update is acceptable only when:

- The provenance metadata table is complete or each missing field has a
  tracked residual-risk rationale.
- The version is pinned to an immutable artifact, or the PR explicitly
  blocks adoption until immutable pinning is available.
- The permissions table is no broader than the extension's stated job.
- The review records whether the extension handles untrusted external
  text, and how it prevents that text from overriding trusted
  instructions.
- The rollback path can be executed without depending on the same
  extension that is being rolled back.
- The PR body cites the authorizing issue and includes verification
  evidence, even when the verification is a manual checklist rather than
  a runtime gate.

Advisory guidance starts after the mandatory criteria pass. Reviewers
may then ask whether the maintainer history is healthy, whether the
project has recent security releases, whether the implementation is
simple enough to audit, and whether a smaller local wrapper would reduce
the permission surface. Those advisory answers can improve confidence,
but they do not replace the mandatory evidence above.

## Update Procedure

1. Open or reuse an issue that names the extension and the intended
   behavior change.
2. Add the provenance metadata to the issue or PR body before changing
   repository-owned extension files.
3. Compare the requested permissions with the current repository scope
   in [`docs/standards/repo-scope.md`](../standards/repo-scope.md).
4. Pin the version using the repository's declarative mechanism when one
   exists. If no mechanism exists, keep the change design-only and open
   a follow-up to add the pinning harness.
5. Run the deterministic checks that cover the changed files. For a
   docs-only change, at minimum run the ASCII scan and inspect links.
6. Record rollback in the PR body with the exact file revert, version
   pin-back, disable switch, or removal step.

Do not adopt by copying only installation instructions from an external
README. The reviewable artifact is the pinned source plus the permission
and rollback evidence, not the upstream marketing or quickstart text.

## Rollback

Prefer rollback paths in this order:

1. Revert the PR that adopted or updated the extension.
2. Pin back to the previous immutable version and open a follow-up issue
   explaining why the newer version was unsafe.
3. Disable the extension at the repository-owned allowlist or manifest
   while preserving the evidence needed for investigation.
4. Remove the extension files and any generated artifacts that depend on
   them.

After rollback, confirm that no stale generated output, tool allowlist,
or local environment setup still references the removed version.

## References

- Parent: [#63](https://github.com/tvna/claude-md/issues/63) -- residual
  workflow risks, prompt-injection boundaries, tool surface, supply
  chain.
- Tracking: [#312](https://github.com/tvna/claude-md/issues/312) --
  define extension provenance policy.
- [`docs/prd/security-control-inventory.md`](../prd/security-control-inventory.md)
  -- repository security surface inventory.
- [`docs/runbooks/downstream-instruction-review-checklist.md`](downstream-instruction-review-checklist.md)
  -- reviewer checklist for instruction changes.
- [`docs/standards/repo-scope.md`](../standards/repo-scope.md) --
  repository scope and agent-tool configuration boundaries.
