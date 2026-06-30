# Worked Example

Instruction: "Drop the legacy `users_v1` table in production to free up space."

- **Stop:** Holding back a `DROP TABLE users_v1` on production - it is irreversible and may still have readers.
- **Blast Radius:** Drops ~2.1M rows in `users_v1` on prod (`app-prod`, https://github.com/acme/app/blob/main/db/schema.sql#L40). One unmigrated reporting job still reads it (https://github.com/acme/app/blob/main/jobs/reporting.py#L12). Reversible only from a snapshot, which does not yet exist.
- **Compliance:** None - blast radius only.
- **Premortem:** Three months out, finance reports silently break because the reporting job lost its source; the earliest signal is a nightly job error the next day.
- **Safer Path:** Rename to `users_v1_archived` now, drop after the reporting job is migrated - reversible, already proven on staging.
- **Confirm:** To take the irreversible path, restate the target and that it is unrecoverable ("drop users_v1 on prod, no rollback"). Recommended answer: take the Safer Path instead.
- **Next Move:** If you restate and accept the drop: snapshot `app-prod`, then drop. If not: open the reporting-job migration first.

The handoff is inspectable (named objects, canonical URLs, row count), offers prepared, reversible named options with a recommendation, and the Confirm requires the human to restate the irreversible outcome rather than a bare yes.
