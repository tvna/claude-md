# Reserved auto-retro scope: deny gate and its one in-session exception

This standard records why the reserved-scope deny gate
([`scripts/gate_reserved_retro_scope.py`](../../scripts/gate_reserved_retro_scope.py))
and the in-session retrospective-create path (design D1) collide, and the
single narrow allow-exception that lets them coexist. It exists so an agent
touching either side does not re-derive the conflict from PR history; the
reasoning previously lived only in PR #1590 and the gate module docstring.

The two implementations this standard ties together live in
[`scripts/gate_reserved_retro_scope.py`](../../scripts/gate_reserved_retro_scope.py)
and [`scripts/auto_retro.py`](../../scripts/auto_retro.py).

## The two coupled mechanisms

- **Reserved-scope deny gate (Refs #1395).** A PreToolUse hook on
  `mcp__github__issue_write` denies any `create` whose title carries the
  reserved `auto-retro` Conventional Commit scope. The scope is reserved for
  the CI `open-retro` job in `.github/workflows/post-merge.yml`, which opens
  retrospectives through `scripts/auto_retro.py run` over the `gh` REST
  boundary; never through `mcp__github__issue_write`. The gate exists because
  PR #1394 minted an agent-authored `chore(auto-retro): ...` tracking issue that
  satisfied `auto_retro.is_retro_issue_title`, so the linking PR tripped the
  `verify-no-direct-retro-pr` CI gate as a direct PR off an un-triaged retro.

- **In-session retro-create path (design D1, Refs #1581 / PR #1590).** The
  post-merge automation only sees CI-visible repairs (PR diff, CI logs, review
  threads). A class of process repair; a wrong-branch re-placement fixed by
  hand, a discarded-drift cleanup, any near-miss that produced no failing check
 ; leaves no such trace. Design D1 splits the responsibility: the post-merge
  job owns CI-visible repairs; the pre-merge handoff survey
  ([`scripts/gate_handoff_retro_survey_askuserquestion.py`](../../scripts/gate_handoff_retro_survey_askuserquestion.py))
  opens the canonical retro IN-SESSION for operator-visible ones. Both converge
  on the same canonical retro issue.

## The conflict

Opening the canonical retro in-session is an agent `mcp__github__issue_write`
create whose title carries the reserved `auto-retro` scope; exactly the shape
the deny gate blocks by default. Without an exception, design D1 cannot reach
its own canonical retro issue.

## The narrow allow-exception

The gate permits exactly one title and denies every other `auto-retro` title:

- **Covers:** the exact canonical handoff title
  `chore(auto-retro): review PR #<N> repair loops`; the literal
  `auto_retro.build_retro_title` emits, matched by
  `auto_retro.is_canonical_handoff_retro_title`. The allow-list reuses that
  single-source predicate so it can never drift from the title producer.
- **Excludes:** every other `auto-retro`-scoped title, including near-miss
  variants and legacy `fix(auto-retro)` shapes. They stay denied so an agent
  cannot mint an arbitrary issue that downstream automation mistakes for an
  auto-opened retrospective.

## Why the exception is safe

- **Dedup still recognises it.** Because the in-session retro uses the canonical
  shape, the CI dedup (`auto_retro.find_existing_retro`) finds it and suppresses
  the post-merge duplicate for the same `PR #<N>`.
- **No direct-PR false positive.** The standalone in-session retro carries no
  implementing PR, so it never trips `verify-no-direct-retro-pr`, which only
  fires on a PR that links a retro issue.
- **Tool-surface boundary, not event sniffing.** The deny gate fires only on the
  agent's own `mcp__github__issue_write` calls; the CI path never crosses that
  surface, so no event-source detection is needed.

## Evidence required to use the exception

- The title MUST be exactly the `build_retro_title` shape; any deviation is
  denied by design.
- Before creating, check for an existing retro for `PR #<N>`: comment on it if
  one exists, otherwise create it with that exact title. This keeps the
  in-session path idempotent with the post-merge dedup.

## References

- [#1395](https://github.com/tvna/claude-md/issues/1395); why the deny gate
  exists (the #1394 `verify-no-direct-retro-pr` false positive).
- [#1581](https://github.com/tvna/claude-md/issues/1581); design D1, the
  auto-retro responsibility split between CI-visible and operator-visible
  repairs.
- [#1590](https://github.com/tvna/claude-md/pull/1590); the PR that
  implemented D1 and the narrow allow-exception (Closes #1581).
- [#1593](https://github.com/tvna/claude-md/issues/1593); the retrospective
  (R3) whose follow-up recorded this conflict in a design doc.
- [`docs/runbooks/pre-merge-retro-survey.md`](../runbooks/pre-merge-retro-survey.md)
 ; operator procedure for the in-session survey that uses the exception.
- [`docs/runbooks/auto-retrospective-automation.md`](../runbooks/auto-retrospective-automation.md)
 ; the post-merge automation the survey complements.
