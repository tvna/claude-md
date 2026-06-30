# Adaptive-coaching observation store

The store accumulates anonymous signal locally so a reflection quiz has enough
data to be fair. It does not trigger anything on its own: the quiz fires only when
the person asks to reflect. Entry point `adaptive-store.sh`, backed by the
`sqlite3` CLI (`choco install sqlite`). By default record only coded metadata —
never prompt text, code, or file paths. Opt-in context capture (below) can also
store an abstracted summary — passed on stdin via `--context-stdin`, secret-redacted
— when the operator enables it.

## Contents

- Commands
- Readiness: two gates
- Categories
- Context capture and rotation
- Storage and volatility
- What it captures (and what it does not)

## Commands

Use `${CLAUDE_PLUGIN_ROOT}` (Codex substitutes `${PLUGIN_ROOT}`).

Record an observation:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/adaptive-store.sh" record --category <category> [--signal <coded-label>]
```

Optionally attach an abstracted context summary — stored only when context capture
is enabled, abstracted to what a later reflection needs and always secret-redacted
first (redact known secrets yourself before passing it). Pass it on **stdin** via
`--context-stdin`, never as an argv value, so the unredacted text is not exposed in
a process listing:

```bash
printf '%s' "<abstracted summary>" | CLAIRVOYANCE_STORE_CONTEXT=1 bash "${CLAUDE_PLUGIN_ROOT}/hooks/adaptive-store.sh" record --category <category> --context-stdin
```

Record a quiz outcome (same category as the observation it scores):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/adaptive-store.sh" record --category <category> --outcome correct|incorrect
```

On a reflection request, check whether enough has accumulated for a fair quiz:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/adaptive-store.sh" status
```

`status` prints JSON with `ready: true` only once **both** gates pass: the
session grace period and the adaptive-signal threshold (below). `--category` is
required on every `record`; an outcome-only record is rejected.

The SessionStart hook calls `record-session` on each session to advance the
grace period — the skill does not need to. (`record-session` bumps the anonymous
session count; it takes no flags.) The hook pushes no coaching of its own.

## Readiness: two gates

A reflection quiz is delivered only when the person asks AND **both** gates hold,
so a first-time user with thin data is never quizzed:

- **Session grace:** at least `$CLAIRVOYANCE_SESSION_THRESHOLD` chat sessions
  have elapsed (default 50; 0 disables the grace period).
- **Adaptive signal:** at least `$CLAIRVOYANCE_COACH_THRESHOLD` observations have
  accumulated (default 5).

`status` reports `sessions`, `session_threshold`, `count`, and `threshold`
alongside `ready` so the split is visible.

## Categories

`avoidance`, `mislabeled-technical`, `loss-aversion`, `values-conflict`,
`no-experiment`, `authority-dependence`, `other`. Anything outside this list is
folded to `other`; the optional `--signal` is sanitised to a short `[a-z0-9-]`
token so no free text persists.

## Context capture and rotation

- **Context capture (opt-in).** `CLAIRVOYANCE_STORE_CONTEXT=1` (default off) stores
  the stdin `--context-stdin` summary so a later reflection can reproduce the
  concrete moment — abstract it to what the experience needs, no more. It is always run through a
  best-effort secret scrub first (cloud keys, JWTs, tokens, `key=value` secrets,
  PRIVATE KEY lines). That scrub is a backstop, not a guarantee — the caller is the
  primary redactor.
- **Rotation.** The store is bounded so it never grows without limit:
  `CLAIRVOYANCE_MAX_OBSERVATIONS` (default 500) keeps the newest N rows and
  `CLAIRVOYANCE_MAX_AGE_DAYS` (default 180) drops older rows; `0` disables either.

## Storage and volatility

Persists on the local workstation (`%LOCALAPPDATA%\clairvoyance` on Windows;
`$CLAIRVOYANCE_DATA_DIR` overrides). Volatility is tolerated: ephemeral or remote
sessions simply do not persist, and an unavailable store means hold the quiz, not
fail.

## What it captures (and what it does not)

The store is **trigger evidence, not a transcript.** "Anonymous" here means
content-scrubbed coded metadata (no prompt, code, or paths) held locally on the
person's own machine and never transmitted — not a de-identified shared dataset.

By default it answers *"is there enough recurring signal of this kind to coach
fairly now?"*, not *"what exactly happened"* — the concrete scenario is rebuilt
from the **live session context**, not the store. With context capture enabled, an
abstracted, secret-redacted context *is* retained — only as detailed as the
experience needs — which is what lets a later reflection reproduce the concrete
moment; that trades some privacy for fidelity and stays local-only.

Keep `signal` at **category level** (e.g. `defer-irreversible`), never a project
or scenario identifier (e.g. `acme-payments-cutover`): the sanitiser guarantees
charset and length, not semantic anonymity. See `docs/hooks.md` for the data
model, lifecycle diagram, and known limitations.
