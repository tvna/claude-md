# Dependabot Auto-Merge

Tracked by #185.

Dependabot auto-merge is audit-first. The workflow always evaluates
Dependabot PRs against `.github/dependabot-automerge.json`, but it only
requests GitHub auto-merge when `enabled` is set to `true` and every policy
condition passes.

Current allowlist:

- `github-actions`: patch and minor updates, touching only
  `.github/workflows/*`.
- `uv`: patch updates, touching only `pyproject.toml` and/or `uv.lock`.

The workflow refuses auto-merge when:

- the author is not exactly `dependabot[bot]`;
- the branch is not `dependabot/*`;
- the PR is a draft;
- any `severity:*` label is present;
- the title does not expose a semver `from ... to ...` update;
- changed files fall outside the ecosystem allowlist;
- the update type is not allowed for that ecosystem.

The non-ASCII scanner remains independent. Auto-merge policy must not suppress
the advisory comment path from #136.

To enable live auto-merge, change `.github/dependabot-automerge.json`:

```json
"enabled": true
```

Keep that change in a separate PR after observing the audit summaries on live
Dependabot PRs.
