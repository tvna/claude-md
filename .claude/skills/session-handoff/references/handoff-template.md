# Handoff template

Fill every section. Keep it self-contained: the next session should not need this
conversation. Do not use fenced code blocks anywhere in the handoff — use
4-space-indented blocks for multi-line commands and `inline code` for short
snippets, so the prompt pastes into a chat input without breaking.

## Sections, in order

# Handoff: [Scope]

## Context
- Issue: #NNNN
- Branch: `branch-name` (existing; do not create a new branch)
- Closes: #NNNN

## Background
2-4 sentences: what failed or remains, when, and the observable symptom. Name the
session or PR where it was observed if known.

## Files to read before implementing
Read in this order, each fully before writing any code:
1. `path/to/primary.py`: role in one line
2. `path/to/test.py`: role in one line

## Implementation
The precise change: which variable, function, or string, the new value or
behaviour, and why it is the minimum sufficient change. If options exist, name
them A/B/C, recommend one, and give the reason. Do not add files, hooks, or
abstractions beyond what is described.

## Verification
Run after implementing:

    uv run pytest tests/relevant_test.py -v

Expected: all tests pass.

## PR creation
Read `.github/PULL_REQUEST_TEMPLATE.md` before drafting. Suggested title:

    fix(scope): description (Closes #NNNN)

## Acceptance criteria
- [ ] Criterion 1 (deterministic: command or observable output)
- [ ] CI green on the pushed branch

## Example

# Handoff: fix flaky cache TTL test

## Context
- Issue: #412
- Branch: `fix/cache-ttl-flake` (existing; do not create a new branch)
- Closes: #412

## Background
`test_cache_expiry` fails about 1 in 5 runs since #398 introduced a real clock.
The assertion compares against a timestamp captured after the cache write, so a
slow write makes the TTL look expired. Observed in CI run 11472.

## Files to read before implementing
1. `app/cache.py`: the cache holding the TTL logic
2. `tests/test_cache.py`: holds the flaky `test_cache_expiry`

## Implementation
In `tests/test_cache.py`, freeze the clock with the existing `freezegun` fixture
instead of reading the wall clock, so write duration cannot affect the TTL
comparison. Minimum sufficient: change only the test setup, not `app/cache.py`.

## Verification
Run after implementing:

    uv run pytest tests/test_cache.py -v

Expected: `test_cache_expiry` passes 20 of 20 runs.

## PR creation
Read `.github/PULL_REQUEST_TEMPLATE.md`. Suggested title:

    test(cache): stabilise cache expiry test with a frozen clock (Closes #412)

## Acceptance criteria
- [ ] `uv run pytest tests/test_cache.py -v` passes
- [ ] CI green on the pushed branch
