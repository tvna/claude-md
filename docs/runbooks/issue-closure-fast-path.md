# Issue Closure Fast Path

When closing a GitHub issue, start with the shortest evidence loop that can
confirm resolution.  This runbook bounds the investigation to direct
merged-PR evidence before expanding to parent or sibling issues (issue #187).

## How the hook drives this

`scripts/issue_closure_fast_path.py` fires as a **PreToolUse** hook
whenever `mcp__github__issue_write` is called with `state: closed`.  It
searches GitHub for merged PRs that reference the issue number and surfaces
the result as `additionalContext` -- never as a deny.

| Hook output | Meaning |
|---|---|
| `FAST-PATH OK` | Exactly one merged PR references the issue. Attach the PR URL in the closing comment. |
| `FAST-PATH INFO` | Multiple merged PRs found. Confirm which one(s) directly resolve the issue. |
| `FAST-PATH WARNING` | No merged PR found. Verify resolution by another means before closing. |

## Manual fast path (without the hook)

If the hook is unavailable, follow these steps in order:

1. **Resolve the issue number** from the URL, including any query parameters.
   Use only the concrete issue number -- do not begin by reading parent or
   sibling issues.

2. **Search for merged PRs** that reference it:
   ```sh
   gh search prs --repo tvna/claude-md --state merged -- "#<issue_number>"
   ```

3. **If exactly one PR matches**, verify:
   - `state` is `MERGED`.
   - PR title or body explicitly references `#<issue_number>`.

4. **Comment with the evidence** and close the issue:
   ```sh
   gh issue comment <issue_number> --body "Resolved by <PR URL> (merged <date>)."
   gh issue close <issue_number>
   ```

5. **Inspect parent or sibling issues only if** step 2 returns no merged-PR
   evidence for the concrete issue.

## When to skip this runbook

- The issue was closed as a duplicate: state the duplicate number in the
  comment instead of citing a PR.
- The issue is will-not-fix / out-of-scope: state the rationale explicitly.

In both cases, no merged-PR evidence is required, but the closing comment
must include the reason so the decision is auditable.
