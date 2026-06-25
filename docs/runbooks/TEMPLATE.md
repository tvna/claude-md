# Runbook Template

Use this template for every new runbook so operators find the same sections
in the same order. Copy the body below the divider into a new
`docs/runbooks/<name>.md`, fill each section, and register the file in
[`../INDEX.md`](../INDEX.md). Remove a section only when it genuinely does not
apply, and replace it with a one-line reason rather than leaving it blank.

See [`README.md`](README.md) for which documents belong in this lane.

---

## Template

---

# [Runbook title]

## Scope

[Which operation this runbook covers and the conditions under which an
operator should reach for it. One short paragraph.]

## Why

[Why this procedure exists: the operation it performs or the risk it
contains. State the value an operator gets from following it.]

## Why not

[When NOT to use this procedure, and why an alternative approach was not
adopted. If a simpler manual step or a different runbook is the right tool in
some cases, name it here.]

## Procedure

[Numbered steps. Use `inline code` for short commands; use a fenced or
4-space-indented block for multi-line commands. Keep each step independently
checkable.]

1. [Step one]
2. [Step two]

## Verification

[A deterministic observation that proves the procedure succeeded: a command
plus its expected output, not "looks fine". CLAUDE.md section 1 forbids an
indirect signal standing in for proof.]

## Rollback

[How to undo the operation. Required: every runbook either states a rollback
path or explicitly records why the operation is irreversible. Per CLAUDE.md
section 3, prefer `git revert` of the original change over hand-authored
inverse edits when reverting committed work.]

## References

[Related standards, runbooks, and the tracking issue (full canonical URL or
`#NNNN`).]
