# Renovate migration PoC evidence (issue #279)

Parent: [#276](https://github.com/tvna/claude-md/issues/276)
Issue: [#279](https://github.com/tvna/claude-md/issues/279)

## Scope

This document records what an agent run could establish from primary
sources for the four open questions enumerated in issue #279, and lists
the steps a human operator must take to finish the PoC. The candidate
ruleset shape captured below is documentary only; it is not wired into
`.github/rulesets/` and is not picked up by `apply-rulesets.yml` (the
workflow enumerates `all-branches.json`, `dependabot.json`, `main.json`
and `scripts/rulesets_apply.py` only registers the same three names in
its `TARGETS` map). The actor_id placeholder is `0` and must be
replaced with a captured Installation `actor_id` before any dispatch.

## Status of each open question

| ID | Question | Status | Evidence anchor |
| --- | --- | --- | --- |
| Q1 | bypass actor registration path and `actor_id` retrieval | pending human follow-up | requires Mend Renovate App install; agent cannot install GitHub Apps |
| Q2 | Renovate `pep621` manager `uv.lock` support | answered | Q2 below |
| Q3 | rebase mechanism: force-push vs close-and-reopen | answered (with caveat) | Q3 below |
| Q4 | permission set the Mend Renovate App requests at install | answered | Q4 below |

## Q1 - bypass actor registration path (pending)

The agent run cannot install the Mend Renovate App on the repository
(installation is a web-only flow). Without an installation, the
`GET /repos/tvna/claude-md/installations` endpoint returns no Mend
entry and the Installation `actor_id` cannot be observed.

Human follow-up steps to close Q1:

1. From a repository administrator account, visit
   `https://github.com/apps/renovate` and install the Mend Renovate
   App, restricting access to the PoC branch only.
2. Run `gh api /repos/tvna/claude-md/installations` and locate the
   entry whose `app_slug` is `renovate`. Record the `target_id`
   (Installation actor id) and the full response body as a comment on
   issue #279.
3. Replace the `0` placeholder in the candidate ruleset (below) with
   the captured `actor_id`.

The unanswered part of Q1 is whether the GitHub Rulesets API accepts
that Installation `actor_id` with `actor_type: "Integration"`. The
Mend Renovate App is a third-party GitHub App, so the speculation in
issue #276 is that the Integration actor path applies. This must be
confirmed by dispatching `apply-rulesets` with `dry_run=true` after
the placeholder is replaced and inspecting the resulting job summary.

## Q2 - pep621 manager and uv.lock support (answered)

- Source: `https://raw.githubusercontent.com/renovatebot/renovate/main/lib/modules/manager/pep621/readme.md`
- Fetched: 2026-05-25 UTC
- Quote: "This manager handles dependency updates in `pyproject.toml`
  files and supports several toolsets. ... The manager supports `uv`
  (including `uv.lock` files and `uv` workspaces) alongside PDM and
  Hatch ecosystems."

Answer: the `pep621` manager updates `uv.lock` directly as part of its
supported toolset. The repository does not need to enable
`lockFileMaintenance` to get transitive bumps in `uv.lock`; the
manager invokes `uv` for lock-file updates as part of its normal
update path.

## Q3 - rebase mechanism (answered, with caveat)

- Source: `https://raw.githubusercontent.com/renovatebot/renovate/main/docs/usage/configuration-options.md`
- Fetched: 2026-05-25 UTC
- Quotes:
  - Line 754: "Manual rebases (requested via checkbox, Dependency
    Dashboard, or rebase label) always bypass this limit."
  - Line 1972: "Otherwise, if another bot or human shares the same
    email and pushes to one of Renovate's branches then Renovate
    will mistake the branch as unmodified and potentially force
    push over the changes."
  - Lines 4482-4504 document `rebaseLabel` and `rebaseWhen`
    (`auto` / `automerging` / `never` / `conflicted` /
    `behind-base-branch`). None of the documented values describes
    a close-and-reopen fallback.

Answer: Renovate's rebase mechanism is force-push on the existing
`renovate/*` branch. The documentation does not describe a
close-and-reopen fallback equivalent to the post-2026-05-24 Dependabot
behavior recorded in `docs/rulesets.md`. The implication for this
repository is that `non_fast_forward` enforcement on
`refs/heads/renovate/*` will block Renovate's rebase unless the Mend
Renovate App Installation actor is registered in `bypass_actors`,
exactly mirroring the pre-PR-#274 shape that
`.github/rulesets/dependabot.json` used to carry for Dependabot.

Caveat: the docs describe behavior under normal `git push`. They do
not enumerate what Renovate does when `git push --force-with-lease`
is rejected by branch protection. The PoC dispatch (human follow-up
step in Q1) should observe the actual server response and record it
on issue #279 as a comment.

## Q4 - Mend Renovate App permissions at install (answered)

- Source: `https://raw.githubusercontent.com/renovatebot/renovate/main/docs/usage/security-and-permissions.md`
- Fetched: 2026-05-25 UTC
- Quote (Global Permissions table, lines 33-44):

  | Permission        | The Mend Renovate App | Forking Renovate   | Why                                                           |
  | ----------------- | :-------------------: | :----------------: | ------------------------------------------------------------- |
  | Dependabot alerts |        `read`         |       `read`       | Create vulnerability fix PRs                                  |
  | Administration    |        `read`         |       `read`       | Read branch protections and to be able to assign teams to PRs |
  | Metadata          |        `read`         |       `read`       | Mandatory for all apps                                        |
  | Checks            |  `read` and `write`   |   not applicable   | Read and write status checks                                  |
  | Code              |  `read` and `write`   |       `read`       | Read for repository content and write for creating branches   |
  | Commit statuses   |  `read` and `write`   | `read` and `write` | Read and write commit statuses for Renovate PRs               |
  | Issues            |  `read` and `write`   | `read` and `write` | Create Dependency Dashboard or Config Warning issues          |
  | Pull Requests     |  `read` and `write`   | `read` and `write` | Create update PRs                                             |
  | Workflows         |  `read` and `write`   |   not applicable   | Explicit permission needed to update workflows                |

Answer: the Mend Renovate App requests nine global permissions, of
which six include write scope (Checks, Code, Commit statuses, Issues,
Pull Requests, Workflows). Compared to the Dependabot Integration the
new scopes are `Code: write` (branch creation under `renovate/*`),
`Workflows: write` (so Renovate can update pinned-Action SHAs in
workflow files), and `Administration: read` (branch-protection read).

Least-privilege check against `docs/security-control-inventory.md`:
`Workflows: write` is the broadest new scope. It is required for
Renovate to bump pinned third-party Action SHAs, which the repository
relies on (`scripts/scan_workflow_action_pins.py`). The current
`.github/dependabot.yml` has both `github-actions` and `uv`
ecosystems configured, so Dependabot already updates workflow files
today; the comparison of effective write surface is not
apples-to-apples because Dependabot's permissions are GitHub-managed
and not directly enumerable as a third-party App permission set. The
adopter (#276 decision PR) must record an explicit decision on
whether the Mend App's `Workflows: write` scope is acceptable.

## Candidate ruleset shape (documentary; DO NOT APPLY as-is)

The candidate `bypass_actors` shape, copied from
`.github/rulesets/dependabot.json` and adjusted for the `renovate/*`
prefix, would be:

```json
{
  "name": "renovate-branches",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/renovate/*"],
      "exclude": []
    }
  },
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    },
    {
      "actor_id": 0,
      "actor_type": "Integration",
      "bypass_mode": "always"
    }
  ],
  "rules": [
    {"type": "non_fast_forward"}
  ]
}
```

The `actor_id: 0` entry is a placeholder. Do not dispatch
`apply-rulesets` against any file that still contains it; `0` is not
a valid GitHub Apps Installation id and the Rulesets API will reject
the call. After Q1 is closed the placeholder must be replaced with
the captured Installation `actor_id`.

## Human follow-up checklist (closes the PoC)

- [ ] Install the Mend Renovate App on `tvna/claude-md`, restricted to
      the PoC branch.
- [ ] Run `gh api /repos/tvna/claude-md/installations` and post the
      response body as a comment on issue #279, ticking Q1.
- [ ] Replace `actor_id: 0` in this document's candidate JSON with the
      captured value and commit on the PoC branch.
- [ ] Temporarily replace `.github/rulesets/dependabot.json` with the
      captured candidate, dispatch `Apply rulesets` with
      `ruleset=dependabot` and `dry_run=true`, capture the planned
      diff from the job summary, then revert the SoT replacement.
      Post the captured summary as a comment on issue #279.
- [ ] Let Renovate open one PR on the PoC branch, tick the rebase
      checkbox on the Dependency Dashboard, and record whether the
      resulting push targets `refs/heads/renovate/*` with force-push
      or with close-and-reopen. Post the observation on issue #279
      (closes Q3 with primary evidence).
- [ ] On issue #276, flip the four open-question checkboxes to `[x]`
      with back-links to the issue #279 comments that supplied the
      evidence.
- [ ] Once all evidence is captured, close issue #279 and delete the
      PoC branch (per the issue's acceptance criteria).

## Scope of this PR (not the cutover)

This PR scaffolds primary-source evidence for issue #279 and is not
the cutover for issue #276. None of the files listed in the #276
Proposed work section (delete `.github/dependabot.yml`, rename
`dependabot-automerge.*`, add `.github/renovate.json5`, rename
`.github/rulesets/dependabot.json` to `renovate.json`, etc.) are
touched here. Those are the deliverables of the implementation PRs
that follow once issue #276's open questions are all closed.
