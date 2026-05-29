# Repo Scope — Purpose Statement and Tool-Specific Config Prohibition

> Design rationale: see [`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md). This document is the concrete content-based prohibition that grounds the Q1 disqualifier in the meta-doc's decision tree.

This document is the operator-facing companion to [#58](https://github.com/tvna/claude-md/issues/58) — the governance decision that declares this repo's purpose and forbids agent-tool-specific configuration files. The deterministic enforcement (CI gate) is parked as Phase 4 of #58; until it lands, this runbook plus the widened `.gitignore` / `.claudeignore` are the enforcement.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.gitignore` | repo working tree | Canonical exclude list — git refuses to track matched paths. **This is the source of truth.** |
| `.claudeignore` | (no official Claude Code support — see *Note on `.claudeignore`* below) | Forward-looking mirror, kept on speculation. Not authoritative. |
| `docs/standards/repo-scope.md` *(this file)* | — | Runbook: purpose statement, prohibition list, rationale, update procedure |

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
| `.codex/` except `.codex/hooks.json` | Codex |
| `.github/copilot-instructions.md` | GitHub Copilot |
| `.windsurfrules` | Windsurf |
| `.codeium/` | Codeium |

The list is non-exhaustive. When a new tool emerges, follow the *Update procedure* below.

### Open Q1 resolution — `docs/` is also covered

`docs/` is a permitted directory for operator runbooks (this file, `docs/runbooks/rulesets.md`, `docs/ai-triage-routing.md`), but a hypothetical `docs/claude-code-tricks.md` would still violate the prohibition because its **content** is tool-specific. Both the path-based exclusion (the table above) and this content-based rule apply.

## Existing carve-outs that stay valid

| Path | Why |
|---|---|
| `.github/` | Repo governance (workflows, rulesets, labels, PR template). Not agent-tool config. |
| `docs/` | Operator runbooks. Subject to the *Open Q1 resolution* rule above. |
| `claude-md.code-workspace` ([#49](https://github.com/tvna/claude-md/issues/49)) | VS Code multi-root workspace pointer. Editor metadata, not agent config. |
| `.claude/settings.local.json` | Documented developer-local file. The broader `.claude/` directory rule transitively keeps it out of commits — the historical entry remains documented here so future contributors understand it predated the broader rule. |
| `.claude/settings.json` ([#109](https://github.com/tvna/claude-md/issues/109)) | **Narrow file-level carve-out** to host deterministic lifecycle hooks. The broader `.claude/` directory rule still applies to every other path under `.claude/` (e.g. `.claude/hooks/`, `.claude/commands/`). See *Security tradeoff* below. |
| `.codex/hooks.json` ([#604](https://github.com/tvna/claude-md/issues/604), [#606](https://github.com/tvna/claude-md/issues/606)) | **Narrow file-level carve-out** to host deterministic Codex lifecycle hooks that mirror existing repo-owned Claude hook scripts where Codex supports the event shape. The broader `.codex/` directory rule still applies to every other path under `.codex/`. |

### Codex import of the `.claude/settings.json` guard

Codex inherits the same governance principle through a Codex-specific hook primitive:

- **Fact.** This repository already targets Codex through the compiled `AGENTS.md` surface (`apm.yml: target: [claude, codex]`).
- **Fact.** `.claude/settings.json` is allowed only because it is a reviewed, deterministic hook trigger for Claude Code sessions.
- **Fact.** Codex documents repo-local hooks in `.codex/hooks.json`; #604 records the matching governance primitive, and #606 adds the first reviewed implementation slice.
- **Rule.** Only `.codex/hooks.json` is carved out. It may invoke repo-owned deterministic scripts under `scripts/` where behavior is tested for Codex payloads or is payload-independent. All other `.codex/` paths remain prohibited.
- **Implication.** Codex-specific preferences, local credentials, prompts, model choices, or UI configuration stay outside the repo. Universal behavior continues to flow through `.apm/instructions/master.instructions.md` and the generated `AGENTS.md`.

### Security tradeoff for `.claude/settings.json`

The `.claude/settings.json` carve-out is conscious risk-acceptance, recorded under CLAUDE.md §4 ("Simplicity, **bounded by safety**"):

- **Risk accepted.** A committed hook can run arbitrary shell at session start; `permissions` / `model` / `apiKeyHelper` keys carry their own security surface. A misconfigured or malicious change here would execute before the operator types a single command.
- **Why we accept it.** The alternative — provisioning via the Claude Code on the Web UI's setup script — moves the same shell *outside* code review entirely. The Web UI is not under git history, not diffable against CI, and not reproducible when an environment is recreated. Treating an in-repo `settings.json` as the trigger pulls the hook surface back under PR review.
- **Bounded mitigations.**
  1. Only this one file is carved out — `.claude/hooks/`, `.claude/commands/`, and any other subdir remain prohibited. Hook logic that does not fit inline lives under `scripts/` (already permitted) and is invoked from `settings.json`.
  2. Content remains subject to the *Open Q1 resolution* rule above. `settings.json` content that exists solely for one agent tool's UX (slash-command catalogues, model selection, custom permissions tuning, etc.) is still out of scope — only **deterministic provisioning** (CI parity, dependency install) belongs here.
  3. PR review enforces 1–2 until a CI lint is added (tracked as a future phase under #58). The uv-pin drift gate in `.github/workflows/verify-agents.yml` (landed in [#112](https://github.com/tvna/claude-md/issues/112)) is a precedent — a narrow deterministic check that complements PR review without trying to police hook content as a whole.

## Rationale

- **Submodule consumers are tool-agnostic.** Downstream projects pull this repo as a git submodule to get the compiled CLAUDE.md / AGENTS.md. Committing `.cursor/` or `.aider*` would force a tool choice on those consumers.
- **`apm.yml: target: [claude, codex]`.** The repo explicitly compiles for multiple agent tools. Pinning configuration to one tool contradicts that contract.
- **Performance measurement bias** (Phases 2-3 of #58). Tool-specific files inject agent behaviour outside the universal master source and would pollute the measurement signal.

## Note on `.claudeignore` — kept as speculation, not as an official primitive

`.claudeignore` is **not** documented as a Claude Code primitive in the official documentation. The only file-ignore mechanism the [Claude Code Settings page](https://code.claude.com/docs/en/settings) describes is the `respectGitignore` option for the `@` file picker, which consults `.gitignore`. There is no claim by Anthropic that Claude Code consults `.claudeignore`.

Independent reporting ([The Register, 2026-01-28](https://www.theregister.com/software/2026/01/28/claude-code-ignores-ignore-rules-meant-to-block-secrets/4336684)) further indicates that even if `.claudeignore` is read in some configurations, it is not reliably honoured — `.env` files have been reported as readable despite a `.claudeignore` entry.

This repo keeps `.claudeignore` anyway for two reasons:

1. **Historical state.** The file pre-dates this runbook (commit `f513b88`, "Add ignore files", 2026-05-18). Removing it would expand the scope of #60 and is deferred to a future cleanup if/when one is opened.
2. **Forward-looking convention.** If Anthropic ever ships `.claudeignore` as a supported primitive, the entries are already in place.

**`.gitignore` is the canonical enforcement; `.claudeignore` is a courtesy mirror.** Reviews and CI must use `git check-ignore -v` (the *Verify* recipe below) as the source of truth. Do **not** rely on `.claudeignore` to keep secrets or tool-specific config out of Claude Code's view — use `.gitignore` plus, where stricter enforcement is required, `permissions.deny` in `.claude/settings.json` (managed settings).

The history of this acknowledgement: [#58 comment](https://github.com/tvna/claude-md/issues/58#issuecomment-4502888322) records that the original PR #81 treated `.claudeignore` as authoritative without a primary source — i.e. the framing was hallucination-derived. This note exists so future contributors don't relitigate that finding from scratch.

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
   - `docs/standards/repo-scope.md` (this file) — prohibition table entry
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
- `docs/runbooks/rulesets.md` ([#18](https://github.com/tvna/claude-md/issues/18)) — runbook format template
- `docs/ai-triage-routing.md` ([#34](https://github.com/tvna/claude-md/issues/34)) — secondary template
- `apm.yml` — `target: [claude, codex]` evidence for tool-agnostic stance
- `README.md` — "universal, individual-level guidelines" mandate
- [Claude Code Settings](https://code.claude.com/docs/en/settings) — primary source for `respectGitignore` (the only documented Claude Code ignore mechanism)
- [#58 comment](https://github.com/tvna/claude-md/issues/58#issuecomment-4502888322) — record of the `.claudeignore` primary-source review
