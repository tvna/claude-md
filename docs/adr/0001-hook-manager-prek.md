# ADR-0001: prek over pre-commit as the git hook manager

Status: Accepted
Date: 2026-06-17
Refs: [#408](https://github.com/tvna/claude-md/issues/408), [#1049](https://github.com/tvna/claude-md/issues/1049)

## Context

This repository guards pushes to the remote with a set of deterministic checks
(branch-base freshness, coverage floor, static lints). Two hook manager packages
were evaluated as the local enforcement layer:

| | [`pre-commit/pre-commit`](https://github.com/pre-commit/pre-commit) | [`j178/prek`](https://github.com/j178/prek) |
|---|---|---|
| Implementation | Python | Rust (single binary) |
| Execution model | Serial | Parallel (same-priority hooks) |
| Hook startup | ~351 ms | ~77 ms (4.5× faster) |
| Cold install | ~187 s (Airflow baseline) | ~18 s (10× faster) |
| Cache footprint | ~1.6 GB (per-repo venvs) | ~810 MB (shared toolchains) |
| Config format | `.pre-commit-config.yaml` | `.pre-commit-config.yaml` + `prek.toml` |

In a Claude Code remote session, each `git push` invocation passes through a
`PreToolUse` hook chain. Any hook output is returned to the model as Bash tool
result text and counted against the context budget. A framework that produces
verbose startup messages or runs checks serially therefore costs more tokens per
push than a concise, parallel one.

## Decision

Use **prek** (`j178/prek`) as the hook manager for this repository.

## Rationale

1. **Concise tool output** — a Rust binary emits no Python runtime preamble or
   environment-setup chatter. Every line of framework overhead that does not
   carry check signal is a token consumed by the model without value.

2. **Faster per-hook execution** — at 4.5× the per-hook speed, hook results
   return to the model sooner. Wall-clock speed and context consumption are
   independent, but a shorter blocking operation reduces the latency window
   during which the model must hold the push context open.

3. **Parallel hook execution** — hooks at the same `priority` level run
   concurrently. Their combined output arrives in one batch rather than
   accumulating sequentially, keeping the result block compact.

4. **Zero runtime dependency at invocation time** — `uvx prek` fetches and
   runs the binary without a separate install step, matching the `uv`-first
   toolchain policy already in place. No Python virtualenv activation or
   dependency resolution messages appear in the tool output.

5. **Drop-in config compatibility** — the existing `.pre-commit-config.yaml`
   is read by prek without modification, so the pre-push hook definitions
   (`preflight-branch-base`, `preflight-coverage`) required no changes.

## Token cost comparison (per push)

Hook output consumed by the model is the primary token variable.
With both tools configured identically for `pre-push` stage:

| Source | pre-commit | prek |
|--------|-----------|------|
| Framework startup messages | Present (Python traceback-capable) | Absent |
| Hook result lines | Same | Same |
| Environment setup | Logged per hook | None (shared toolchain) |
| **Total framework overhead** | **~5–15 lines per run** | **~0 lines** |

The check-result content (pass/fail + diff on failure) is identical between the
two tools; only the framework overhead differs.

## Consequences

### Positive

- Each push incurs less tool-output token cost due to absent framework overhead.
- CI cold-install time drops ~10×; re-push wall-clock drops ~4× per hook.
- Cache footprint halves, reducing ephemeral container startup time.

### Negative

- prek is a younger project than pre-commit; edge-case bugs may surface earlier.
- Some advanced pre-commit hooks with unusual `language:` values may not yet be
  fully supported (verify before adding new hooks).
- Requires the `prek` binary; mitigated by `uvx prek` zero-install invocation.

## Considered Alternatives

### Keep `pre-commit`

Rejected. Python-based startup produces framework noise in every Bash tool
result. Serial execution means hook output accumulates line by line rather than
arriving as a compact batch. No functional gap justifies the additional
token overhead.

## Implementation

- Hook definitions: [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)
- Operator runbook: [`docs/runbooks/prek.md`](../runbooks/prek.md)
- Pre-push gate design: [`docs/standards/pre-push-gate-performance.md`](../standards/pre-push-gate-performance.md)
- CI gate: `Run prek` step in `.github/workflows/verify-pr.yml`
