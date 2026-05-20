# Repo Scope — Purpose Statement and Tool-Specific Config Prohibition

This document is the operator-facing companion to [#58](https://github.com/tvna/claude-md/issues/58) — the governance decision that declares this repo's purpose and forbids agent-tool-specific configuration files. The deterministic enforcement (CI gate) is parked as Phase 4 of #58; until it lands, this runbook plus the widened `.gitignore` / `.claudeignore` are the enforcement.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.gitignore` | repo working tree | Canonical exclude list — git refuses to track matched paths |
| `.claudeignore` | Claude tooling | Mirror of the agent-tool-specific section of `.gitignore` |
| `docs/repo-scope.md` *(this file)* | — | Runbook: purpose statement, prohibition list, rationale, update procedure |

## Declared purpose

> This repository exists for (1) editing the universal CLAUDE.md / AGENTS.md master source, and (2) measuring the performance impact of those edits.

Anything that does not serve (1) or (2) is out of scope. The master source is `.apm/instructions/master.instructions.md`, compiled by `apm compile` into `CLAUDE.md` and `AGENTS.md` (see `apm.yml`).

## Prohibition

Agent-tool-specific configuration files and directories MUST NOT be committed to this repository, anywhere in the tree (including under `docs/` — see *Open Q1 resolution* below).

| Path / pattern | Tool |
|---|---|
| `.claude/` | Claude Code |
| `.cursor/`, `.cursorrules` | Cursor |
| `.aider*` (e.g. `.aider.conf.yml`, `.aider.chat.history.md`) | Aider |
| `.continue/` | Continue |
| `.github/copilot-instructions.md` | GitHub Copilot |
| `.windsurfrules` | Windsurf |
| `.codeium/` | Codeium |

The list is non-exhaustive. When a new tool emerges, follow the *Update procedure* below.

### Open Q1 resolution — `docs/` is also covered

`docs/` is a permitted directory for operator runbooks (this file, `docs/rulesets.md`, `docs/ai-triage-routing.md`), but a hypothetical `docs/claude-code-tricks.md` would still violate the prohibition because its **content** is tool-specific. Both the path-based exclusion (the table above) and this content-based rule apply.

## Existing carve-outs that stay valid

| Path | Why |
|---|---|
| `.github/` | Repo governance (workflows, rulesets, labels, PR template). Not agent-tool config. |
| `docs/` | Operator runbooks. Subject to the *Open Q1 resolution* rule above. |
| `claude-md.code-workspace` ([#49](https://github.com/tvna/claude-md/issues/49)) | VS Code multi-root workspace pointer. Editor metadata, not agent config. |
| `.claude/settings.local.json` | Documented developer-local file. The broader `.claude/` directory rule transitively keeps it out of commits — the historical entry remains documented here so future contributors understand it predated the broader rule. |

## Rationale

- **Submodule consumers are tool-agnostic.** Downstream projects pull this repo as a git submodule to get the compiled CLAUDE.md / AGENTS.md. Committing `.cursor/` or `.aider*` would force a tool choice on those consumers.
- **`apm.yml: target: [claude, codex]`.** The repo explicitly compiles for multiple agent tools. Pinning configuration to one tool contradicts that contract.
- **Performance measurement bias** (Phases 2-3 of #58). Tool-specific files inject agent behaviour outside the universal master source and would pollute the measurement signal.

## Verify

Confirm a candidate path is excluded by both ignore files:

```sh
# git ignore check — must print a matching rule
git check-ignore -v <path>

# Claude tooling mirror — must match the same pattern
grep -F "<pattern>" .claudeignore
```

End-to-end exercise in a fresh worktree:

```sh
mkdir .cursor && touch .cursor/rules
git status --porcelain        # must print nothing
rm -rf .cursor
```

Repeat for each pattern in the prohibition table.

## Update procedure

To add a new prohibited path (new agent tool, or newly-discovered tool-specific path pattern):

1. Open a sub-issue of [#58](https://github.com/tvna/claude-md/issues/58) describing the tool and the path pattern (per CLAUDE.md §3).
2. Open a single PR that touches **all three**:
   - `.gitignore` — canonical exclude
   - `.claudeignore` — mirror exactly
   - `docs/repo-scope.md` (this file) — prohibition table entry
3. The *Verify* recipe above must pass for the new pattern.
4. Reference the parent governance issue (#58) on the `Refs #` line of the PR body.

## Rollback

To remove a prohibited path entry (if a tool is deprecated or the prohibition no longer applies):

1. Open a sub-issue of #58 explaining why the prohibition is being lifted.
2. PR removes the entry from `.gitignore`, `.claudeignore`, and the prohibition table here.
3. CI must remain green.

Re-adding a lifted entry later uses the same *Update procedure*.

## References

- [#58](https://github.com/tvna/claude-md/issues/58) — parent tracking issue (purpose, prohibition, phase plan)
- [#60](https://github.com/tvna/claude-md/issues/60) — Phase 1 deliverable (this runbook + ignore widening)
- `docs/rulesets.md` ([#18](https://github.com/tvna/claude-md/issues/18)) — runbook format template
- `docs/ai-triage-routing.md` ([#34](https://github.com/tvna/claude-md/issues/34)) — secondary template
- `apm.yml` — `target: [claude, codex]` evidence for tool-agnostic stance
- `README.md` — "universal, individual-level guidelines" mandate
