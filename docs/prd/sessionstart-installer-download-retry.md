# SessionStart installer download retry with fail-loud fallback

## Purpose

Make the SessionStart binary installers (`scripts/install-*.sh`) resilient to
transient network failures by retrying the curl download up to three times with
exponential backoff, and surfacing an unrecoverable failure loudly without
blocking session startup.

## Background

Each of the ten SessionStart installers under `scripts/` (uv, rtk, apm,
actionlint, waza, ccusage, bun, zizmor, lychee, betterleaks) downloads a pinned
release with a single bare `curl` call (for example `install-bun.sh:105`,
`install-uv.sh:45`). curl does not retry by default, so a transient network
error aborts the install with no in-session recovery. The failure surfacing is
also inconsistent: some scripts hard-fail under `set -euo pipefail`, others only
warn, and none injects a visible message into the session. Seven of the ten
hooks are registered with `async: true` in `.claude/settings.json`.

## Target Users

Operators running Claude Code on the Web (and Codex cloud) sessions, where these
installers are the only path that provisions the pinned tools, and the agents
whose gates depend on those tools being present.

## Use Cases

- A release CDN blip drops one download during session start; the installer
  retries and succeeds without operator intervention.
- A download fails permanently (asset removed, sustained outage); the operator
  sees a loud, actionable failure with the exact manual recovery command, and
  the session still starts.

## Goals

- On curl download failure, retry up to 3 times (initial attempt plus 3
  retries = 4 total) with exponential backoff (2s, 4s, 8s).
- On exhausted retries, fail loud (stderr banner plus best-effort in-session
  message) but fail open (session startup continues).
- One shared implementation for all ten installers (SSOT), guarded against drift.

## Success Metrics

- A simulated single-failure-then-success download completes via the retry path
  (asserted by test).
- A simulated permanent failure returns non-zero, prints the loud stderr banner,
  and emits a valid SessionStart `additionalContext` JSON object on stdout
  (asserted by test).
- The drift gate fails CI if any `install-*.sh` reintroduces a bare curl
  download outside the shared helper.

## Non-Goals

- No change to pinned versions, SHA256 verification, archive extraction, or the
  idempotency (`command -v`) checks. Only the download invocation is wrapped.
- No guaranteed in-session message for async hooks (best-effort only; see
  Requirements). No deferred-notification machinery.
- No change to which environments the installers run in.

## Requirements

Functional:

1. New shared helper `scripts/_retry.sh`, sourced (not executed) by every
   installer, exposing one function. It takes the download URL, destination
   path, a human tool label, and the manual reinstall command.
2. The helper runs the curl download (`curl -fsSL URL -o DEST`) for up to four
   attempts. After
   attempts 1-3 it sleeps `base * 2^(n-1)` seconds (2s, 4s, 8s with the default
   base) before the next attempt. On the first success it returns 0.
3. The backoff base delay is read from an env var (default 2; tests set it to 0)
   so the suite runs without real sleeps.
4. On exhausted retries the helper:
   a. writes a loud, ASCII stderr banner naming the tool, URL, attempt count,
      the manual reinstall command, and the gate impact;
   b. writes exactly one SessionStart `additionalContext` JSON object to stdout,
      escaped via `python3 -c` `json.dumps`;
   c. returns non-zero.
5. Each installer replaces its bare `curl ... -o ...` download line with a call
   to the helper, followed by `|| exit 0` so a final failure never aborts the
   session.
6. New drift gate `scripts/scan_install_curl_retry_drift.py` fails when any
   `install-*.sh` contains a bare `curl ... -o` download outside the helper. It
   is wired into `.pre-commit-config.yaml` and the PR verify workflow.

Non-functional:

- stdout of each installer stays JSON-only (existing scripts already route logs
  to stderr), preserving the SessionStart `additionalContext` contract.
- The helper fails open on its own internal errors (a helper bug must never
  wedge session start), consistent with the other SessionStart hooks.

## Why

A single sourced helper keeps the retry-and-fail-loud behavior identical across
all ten installers and lets one drift gate enforce the invariant, matching the
repository's SSOT-plus-gate discipline (CLAUDE.md section 3). Wrapping only the
download line keeps the change surface narrow (CLAUDE.md section 5) and leaves
the supply-chain SHA256 verification untouched. The dual stderr-plus-context
surfacing satisfies fail-loud (CLAUDE.md section 4) while exit-0 keeps the
installer fail-open, the same posture the existing hooks already take.

## Why not

- Per-script `curl --retry` flags avoid a helper but cannot carry the fail-loud
  `additionalContext` emission, would re-implement the loud banner ten times,
  and let the invariant drift with no single gate.
- Forcing the seven async hooks to sync to guarantee message delivery trades a
  bounded startup slowdown for reliability the stderr channel already provides;
  rejected as over-engineering for the value.
- A deferred-notification file read by a later sync hook guarantees async
  visibility but adds a second hook and shared-state file for a best-effort
  nicety; rejected per YAGNI (CLAUDE.md section 4).

## Considered Alternatives

- **curl native `--retry 3 --retry-all-errors --retry-delay`** (fact: curl
  supports these flags): minimal per-script edit, but no shared fail-loud path
  and no single drift anchor. Rejected.
- **Async-to-sync conversion for guaranteed visibility**: reliable in-session
  message for all ten, at up to ~14s added startup latency per failing tool
  across more hooks. Rejected; stderr is the primary loud channel.
- **Deferred-notification machinery**: reliable async visibility via a marker
  file plus a surfacing hook. Rejected as disproportionate.

## Acceptance Criteria

- `scripts/_retry.sh` exists and is sourced by all ten `install-*.sh`.
- A test asserts: fail-N-then-succeed completes via retries with the expected
  attempt count; permanent failure returns non-zero, prints the loud stderr
  banner, and emits valid `additionalContext` JSON on stdout.
- `scripts/scan_install_curl_retry_drift.py` (with its own test) passes on the
  converted tree and fails on a reintroduced bare curl download; it is wired
  into pre-commit and CI.
- No installer's pinned version, SHA256, or idempotency check is changed.

## Scope

In scope: `scripts/_retry.sh`, the ten `install-*.sh` edits, the drift gate and
its test, the retry helper test, and the pre-commit/CI wiring. Out of scope:
everything in Non-Goals.

## Priority

Medium. Reliability improvement for remote sessions; no security regression and
no behavior change on the success path.

## Tradeoff

Sync download installers (uv, actionlint, bun) add up to ~14s of startup latency
each on a permanent failure (sum of the backoff delays); the seven async
installers do not block startup.

## Graduation Path

Once the drift gate and helper are adopted and stable, the bare-curl-ban rule
moves to `docs/standards/` as an adopted contract, and this document remains the
decision record in `docs/prd/`.

## Tracking issues

#2038
