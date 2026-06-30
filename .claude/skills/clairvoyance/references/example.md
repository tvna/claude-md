# Worked example: owner decision handoff

## Input

Tell the owner what choices they have.

- Deployment needs a production API key.
- The staging path works.
- The agent cannot create or view production secrets.
- The owner can issue the key, defer release, or approve a staging-only demo.

## Output

**Verdict:** You need to unblock production — issue the production API key, defer the release, or approve a staging-only demo. I recommend issuing the key if the release is time-sensitive.

**Evidence:** Deployment requires a production API key; staging works end to end; the agent role cannot create or view production secrets, so only you can supply it.

**System Context:** The blocker sits at the production-secrets boundary the agent cannot cross by design. Staging is unaffected; only the production release is gated.

**Options:**
- **Issue the key:** you create the production API key; deployment proceeds now.
- **Defer release:** hold production; staging stays available for review.
- **Staging-only demo:** approve a staging demo now and decide on production separately.

**Risks:** Issuing the key puts a live production secret in play (rotation is yours to own). Deferring delays delivery. A staging demo can be mistaken for production readiness.

**Reversibility:** All three reverse: a key can be rotated, a deferral resumed, a staging demo promoted later.

**Next Move:** If the release is time-sensitive, issue the production API key and approve deployment; otherwise tell me to defer or set up the staging-only demo.

**Open Questions:** Is this release time-sensitive enough to justify issuing a production secret now?
