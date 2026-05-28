# Replacement PR Preflight

Use this runbook before an agent closes a PR and opens a replacement for the
same issue or session. The goal is shortest reproducible repair time, not a
clean-looking GitHub commit log.

## Stop Conditions

- If any candidate PR for the same issue/session is already merged, stop all
  PR creation. Write the retrospective note instead.
- If the session is about to open a second replacement PR, record a root-cause
  note before continuing.
- If the operator says STOP, drain already-running commands only. Do not make a
  new GitHub mutation unless the operator explicitly asks for that mutation.

## Required Root-Cause Note

The note must contain these exact headings:

```text
Root cause:
Existing PR cannot be repaired in place:
Replacement is lower risk because:
```

The note may live in the parent issue, active repair issue, or PR close comment.

## Command

Live check:

```bash
GH_TOKEN=... python3 scripts/preflight_replacement_pr.py verify \
  --repo tvna/claude-md \
  --issue 632 \
  --root-cause-note /path/to/root-cause.md
```

Fixture check:

```bash
python3 scripts/preflight_replacement_pr.py verify \
  --repo tvna/claude-md \
  --issue 632 \
  --candidates-json /path/to/candidates.json
```

Close-comment marker:

```bash
python3 scripts/preflight_replacement_pr.py close-marker \
  --issue 632 \
  --superseded-pr 624 \
  --replacement-pr 625
```

The marker output is stable so retrospective automation can classify replacement
churn without relying on operator memory.

## Retrospective Signals

Record these values when the guard blocks or allows a replacement after the
first candidate PR exists:

- `candidate_count`
- `replacement_count`
- `closed_superseded_count`
- `merged_prs`
- `first_pr_created_at`
- `elapsed_seconds`

Classify the incident as `pre-merge replacement churn` when no candidate has
merged yet, and as `post-terminal stale continuation` when a candidate had
already merged before the next PR mutation.
