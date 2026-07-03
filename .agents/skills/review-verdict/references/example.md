# Worked example: review verdict

## Input

Review this PR and tell me if it is ready, with architecture impact.

- PR changes `src/auth/session.ts` and `tests/session.test.ts`.
- Entry point is `POST /api/session/refresh`.
- The change rotates refresh tokens earlier in the request path.
- Unit tests cover success and expired-token cases.
- No integration test covers concurrent refresh requests.
- A failed rollout can be reverted with one commit.

## Output

**Verdict:** Not Ready — the rotation is sound but lacks a concurrent-refresh integration test on the production auth path.

**Findings:**
1. (High) No integration test covers concurrent `POST /api/session/refresh` requests, yet the change rotates refresh tokens earlier in the request path — a race could invalidate a valid in-flight token.
2. (Info) Success and expired-token cases are unit-tested.

**Evidence:** Changed `src/auth/session.ts`, `tests/session.test.ts`; entry point `POST /api/session/refresh`; unit tests assert success and expired paths; no test exercises two overlapping refreshes.

**System Context:** Rotating tokens earlier widens the window where two concurrent requests observe different token states. Callers are any client refreshing a session; user impact is unexpected logout under concurrency.

**Risks:** The concurrency race is unproven; the gap surfaces in production, not CI.

**Reversibility:** Low — reverts with one commit.

**Next Move:** Add an integration test for concurrent refresh before merge; if shipping urgently, accept the risk explicitly and track the test as a fast follow.
