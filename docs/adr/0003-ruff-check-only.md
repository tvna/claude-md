# 0003. ruff enforced as check-only; `ruff format` kept off gate surfaces

Date: 2026-07-02
Refs: [#2224](https://github.com/tvna/claude-md/issues/2224),
[#2143](https://github.com/tvna/claude-md/issues/2143),
[#2141](https://github.com/tvna/claude-md/issues/2141),
[#2065](https://github.com/tvna/claude-md/issues/2065),
[#192](https://github.com/tvna/claude-md/issues/192),
[#190](https://github.com/tvna/claude-md/issues/190)

## Status

Accepted. Approved by the repository owner (@tvna) during the #2224 session:
presented with the current check-only state and the two directions (formalize
check-only, or adopt `ruff format`), the owner selected recording the existing
check-only unification as this ADR. This ADR does not change behaviour; it
captures a decision already enforced by gates since #2141 (retro #2143).

## Context

The repository runs ruff as a deterministic quality gate. ruff ships two
distinct operations: `ruff check` (lint; diagnoses rule violations) and
`ruff format` (an opinionated reformatter). They are independent surfaces:
enabling one does not imply the other.

The enforced state is check-only:

- CI runs `uv run ruff check scripts tests` (`.github/workflows/verify-agents.yml`,
  the "Run ruff lint gate" step). The rule selection lives in
  `[tool.ruff.lint]` in `pyproject.toml` (families `F E W I B A UP SIM RET PTH
  RUF S`, #192, with the `S`/flake8-bandit security family from #190).
- The local mirror is the `ruff` step
  `("uv", "run", "ruff", "check", "scripts", "tests")` in
  `scripts/preflight_steps.py`, run by `preflight_all.py` on pre-push.
- `pyproject.toml` has no `[tool.ruff.format]` section; `.pre-commit-config.yaml`
  has no ruff hook; the workspace sets `editor.formatOnSave: false`.

`main` is intentionally not `ruff format` clean. The trigger for making the
exclusion explicit (#2141, retro #2143, refs #2065): during a cherry-pick an
agent ran `uv run ruff format` on a test file, producing a wide reflow diff
that carried no lint signal and inflated the change surface. Because
`ruff format` had no gate either enforcing or forbidding it, the reformat
looked as legitimate as a real fix. This is the "fix noise" a mixed
check/format posture produces: a reflow of never-format-checked files widens
the diff against a non-format-clean base while adding no quality signal
(CLAUDE.md section 5).

## Decision

We will enforce ruff as **check-only** and keep `ruff format` off every gate
surface.

1. The only ruff gate is `ruff check scripts tests`, configured through
   `[tool.ruff.lint]` in `pyproject.toml`.
2. No gate surface (workflow YAML, `.githooks`, `.pre-commit-config.yaml`, or
   the `scripts/preflight_steps.py` manifest) may invoke `ruff format` or
   `ruff format --check`. This is enforced by `scripts/scan_ruff_format.py`
   (`verify` subcommand), which runs in CI as the "Assert ruff is enforced as
   check-only" step and as the `scan_ruff_format` preflight step, and is pinned
   by `tests/test_scan_ruff_format.py`.
3. Adopting a `ruff format` gate later remains possible, but only as a
   deliberate, owner-reviewed change: it requires reformatting `main` to be
   format-clean in the same change and carrying the `<!-- ruff-format-ack -->`
   marker that `scan_ruff_format.py` recognizes. The exclusion is the default,
   not a permanent ban.

## Why

- **Removes the fix-noise class at its source.** With `ruff format` off all
  gate surfaces and `main` not format-clean, no agent or contributor is nudged
  to run a reflow, so wide reformat diffs cannot masquerade as fixes. The
  smallest-diff posture (CLAUDE.md section 5) is preserved by a gate, not by
  memory.
- **`ruff check` is the operation that carries quality and security signal.**
  The lint families (including the `S` security family, #190) catch real
  defects; the formatter only normalizes whitespace and line breaks. The gate
  budget is spent on the operation that finds problems.
- **The decision is now deterministic, not remembered.** Before this ADR the
  rationale lived only in the `scan_ruff_format.py` docstring, workflow and
  preflight comments, and retro issues #2143/#2141/#2065. Recording it here
  gives the check-only choice a single authoritative reference and closes the
  gap the suspicion of "mixed check/format" pointed at: it was under-documented,
  not mis-enforced.

## Why not

- Adopting `ruff format` as a gate would require a one-time repository-wide
  reflow of `main` and would then guard whitespace normalization the lint gate
  already tolerates, trading a large, low-signal diff for little added quality.
  It also reverses the #2141/#2143 decision and would need explicit owner
  review, so it is not the default.
- Leaving `ruff format` merely "not configured" (no gate either way, the
  pre-#2141 state) is what allowed the noisy reformat to slip through in the
  first place. Silence is not the same as a decision; the `scan_ruff_format`
  gate converts the intent into enforcement.

## Consequences

- Easier: ruff diffs stay narrow and lint-focused; a stray `ruff format` on a
  gate surface fails locally (pre-push) and in CI with a message that explains
  the check-only contract, rather than landing as diff noise.
- Easier: contributors and agents have one authoritative decision record for
  "why doesn't this repo run `ruff format`?", reducing the chance the question
  is re-litigated ad hoc.
- Harder: `main` is not formatter-normalized, so whitespace and line-break
  style is governed only by the lint families (e.g. `line-length = 120`,
  E-family), not by a canonical formatter. Contributors must not rely on
  format-on-save to match repository style; `editor.formatOnSave` is `false` by
  design.
- Harder: adopting the formatter in the future is a deliberate migration
  (reflow `main`, add the gate, carry the ack marker), not a one-line config
  flip. This ADR is the record that would then be superseded.

## Considered Alternatives

- **Adopt `ruff format` and gate on `ruff format --check`.** Rejected as the
  default. Fact: it requires reformatting `main` in the same change and adding a
  gate surface that `scan_ruff_format.py` currently forbids without the
  `<!-- ruff-format-ack -->` marker. Speculation: the one-time reflow diff would
  be large and low-signal, and would contradict the section-5 smallest-diff
  discipline this repository optimizes for. Remains available as a future
  owner-reviewed decision, not foreclosed.
- **Leave `ruff format` unconfigured and ungated (pre-#2141 state).** Rejected:
  this is precisely the posture that let a wide reformat pass as a fix. An
  absent gate is agent memory, not enforcement (CLAUDE.md section 3).
- **Document the decision only in the script docstring and comments (status quo
  before this ADR).** Rejected: the rationale was real but scattered across
  `scan_ruff_format.py`, workflow/preflight comments, and retro issues, so the
  decision was hard to discover and easy to re-question. An ADR is the
  single-source-of-truth lane for owner-approved decisions (#1049).
