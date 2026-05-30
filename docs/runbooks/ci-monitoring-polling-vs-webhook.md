# CI monitoring: polling vs webhook

This runbook clarifies the two CI monitoring paths available in this repository
so operators can choose the right one for their latency and reliability needs.

## 1. Polling/heartbeat monitor (post_pr_create_ci_monitor hook)

**What it is.** After `mcp__github__create_pull_request` returns, the
`PostToolUse` hook (`scripts/post_pr_create_ci_monitor.py`) launches
`gh pr checks --watch` as a detached background process.

**Event source.** GitHub REST API — polled on a fixed interval by the `gh`
CLI until all check runs settle.

**Delivery path.** Subprocess → `/tmp/claude-md-pr-ci-monitor-<pr>.log`.

**Retry on failure.** None. The process is fire-and-forget. If it dies, no
automatic restart occurs.

**Failure mode.** If `Popen` raises `OSError`, the hook emits an
`additionalContext` error and exits 0 (fail-open). The operator must run
`gh pr checks <pr> --watch` manually.

**Latency.** Depends on the `gh` poll interval (≥ 10 s). Not suitable for
near-real-time alerting.

**When to use.** Default fallback. Ensures a polling monitor is always
running immediately after PR creation, with no additional operator action.

## 2. Webhook-backed monitor (subscribe_pr_activity MCP tool)

**What it is.** The Claude Code session subscribes to PR events via the
`subscribe_pr_activity` MCP tool. GitHub delivers `check_suite`,
`workflow_run`, `pull_request_review`, and `issue_comment` events to the
session via push.

**Event source.** GitHub App webhook — push delivery on each qualifying event.

**Delivery path.** GitHub HTTP POST → Claude Code session event queue.

**Retry on failure.** GitHub redeliver mechanism (up to 3 attempts with
exponential back-off).

**Failure mode.** If delivery fails after retries, the event is lost unless
the operator manually re-checks CI. The session receives no notification.

**Latency.** Near real-time (typically < 1 s after the event fires on GitHub).

**When to use.** Whenever webhook semantics are required — e.g., the operator
expects to be notified immediately when CI fails or a review is posted, rather
than waiting for the next poll cycle.

## 3. Choosing between them

| Requirement                          | Use                       |
|--------------------------------------|---------------------------|
| Immediate notification on CI failure | `subscribe_pr_activity`   |
| Works without extra operator action  | polling hook (automatic)  |
| Audit log of check output to disk    | polling hook (log file)   |
| Survives session restart             | polling hook (subprocess) |
| Review / comment events              | `subscribe_pr_activity`   |

The two paths are complementary. The polling hook always runs; add
`subscribe_pr_activity` on top when push-based delivery is needed.

## 4. Early-failure watch phase vs steady-state heartbeat

A PR monitor has two phases, and conflating them is what let PR #778's CI
failure go unnoticed until a 30-minute heartbeat fired
([issue #781](https://github.com/tvna/claude-md/issues/781)):

- **Early-failure watch phase (initial CI discovery).** The moment a PR is
  opened, the polling hook launches `gh pr checks --watch`, which blocks and
  reports as soon as the required checks settle. Treat this immediate (or
  short-interval) watch as the authoritative first signal: keep checking
  until the required checks reach a terminal state, or a timeout window
  expires. An already-failed check is therefore detected without waiting for
  any long heartbeat interval.
- **Steady-state heartbeat (follow-up).** Only after that initial CI signal
  is known should a longer session-level heartbeat interval (for example
  `FREQ=MINUTELY;INTERVAL=30`) take over. The heartbeat is for ongoing
  follow-up — re-runs, new pushes, late reviews — not for first CI discovery.

**The gap to avoid.** Do not make a long heartbeat the *only* monitor on a
freshly opened PR. A 30-minute interval as the first signal can leave a
broken PR idle for up to half an hour. The hook's `additionalContext` names
the early-failure watch phase explicitly so the agent stays on the immediate
watch until checks are terminal before relaxing to the heartbeat cadence.

## 5. Preventing confusion

- Operator-facing output from the polling hook **always** uses the phrase
  "polling/heartbeat CI monitor" so operators can distinguish it from a
  webhook monitor at a glance.
- The hook output also names `subscribe_pr_activity` as the webhook
  alternative. This blocks the ambiguity identified in
  [issue #756](https://github.com/tvna/claude-md/issues/756).
- Tests in `tests/test_post_pr_create_ci_monitor.py` assert that the
  `additionalContext` field contains "polling/heartbeat", "NOT
  webhook-backed", and "subscribe_pr_activity" on every code path.
