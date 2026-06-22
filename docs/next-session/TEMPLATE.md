# Session Handoff Prompt Template

Use this template for every handoff prompt so sessions start with the same
structure and quality bar.

**Formatting rule**: do not use fenced code blocks (triple backtick) inside
this file. Use 4-space-indented blocks for multi-line commands and `inline
code` for short snippets. This prevents Markdown renderers from breaking the
outer fence when the file is pasted into a chat input.

---

## Template

---

# Handoff: [Scope]

## Context

- Issue: #NNNN
- Branch: `branch-name` (existing; do not create a new branch)
- Closes: #NNNN

## Background

[2-4 sentences: what failed, when, what the observable symptom was.
Include the session or PR where it was observed if known.]

## Files to read before implementing

List in read order. Read every file fully before writing a single line.

1. `path/to/primary-target.py`: role in one line
2. `path/to/related-file.py`: role in one line
3. `path/to/test-file.py`: role in one line

## Implementation

[Describe the change as precisely as possible: which variable, function, or
string to change, the new value or behaviour, and why that is the minimum
sufficient change. If multiple options exist, name them A/B/C, state the
recommended one, and give the reason.]

Do not add files, hooks, or abstractions beyond what is described here.

## Verification

Run after implementing:

    uv run pytest tests/relevant_test.py -v

Expected: all tests pass. If a test asserts the exact text of a string you
changed, update the assertion to match the new text; do not revert the fix.

## PR creation

Read `.github/PULL_REQUEST_TEMPLATE.md` before drafting the body.

Suggested title:

    fix(scope): description (Closes #NNNN)

## Acceptance criteria

- [ ] Criterion 1 (deterministic: command or observable output)
- [ ] Criterion 2
- [ ] CI green on the pushed branch
