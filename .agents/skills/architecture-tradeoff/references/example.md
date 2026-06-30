# Worked example: architecture trade-off

## Input

Explain the trade-off and recommend the next move.

- Option A keeps validation inside the checkout API handler.
- Option B moves validation into a shared domain service.
- The handler path has lower churn and can ship today.
- The shared service reduces duplication across web and mobile checkout.
- Mobile checkout will not adopt the service for at least two weeks.
- The current bug affects only web checkout.
- Both options can be reverted, but Option B touches more callers.

## Output

**Verdict:** Ship Option A now (validation in the checkout handler) and defer Option B until mobile is ready to adopt the shared service.

**Evidence:** The bug affects only web checkout; Option A has lower churn and ships today; Option B's payoff (web/mobile dedup) is two weeks out; Option B touches more callers.

**System Context:** Validation lives in the checkout handler today. Option B widens the blast radius to more callers immediately while the second consumer (mobile) does not exist yet.

**Options:**
- **A — Validate in handler (recommended):** smallest sufficient fix for the web-only bug; ships today.
- **B — Shared domain service:** removes duplication but lands a broad refactor before mobile can use it.

**Future Story:** Option A keeps the door open — once mobile is ready, extract the now-proven validation into the shared service as a deliberate second step, both surfaces adopting it together.

**Premortem:** If B ships today and fails in 3 months, the likely cause is a regression rippling through callers that adopted the service unevenly while mobile lagged; early warning is web regressions traced to mobile-intended changes.

**Risks:** A leaves short-term duplication (bounded). B is a wide-radius change with no near-term second consumer.

**Reversibility:** Both revert; B's revert is costlier because more callers are touched.

**Next Move:** Land the validation fix in the handler to close the web bug today; schedule the shared-service extraction to coincide with mobile adoption.
