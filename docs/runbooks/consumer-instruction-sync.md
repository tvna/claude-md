# Consumer Instruction Sync

Tracking issue: [#1678](https://github.com/tvna/claude-md/issues/1678)

This runbook is for a downstream project that wants the compiled `CLAUDE.md` /
`AGENTS.md` from this master repository. It replaces the retracted submodule +
symlink method (see
[`docs/proposals/instruction-distribution-mechanism.md`](../proposals/instruction-distribution-mechanism.md)
for why that method fails on a fresh clone). The result of this procedure is a
**committed real file** -- never a symlink, never a submodule -- so it survives a
fresh `git clone` such as a Claude Code on the web session.

## How it works

1. The master publishes a tagged release (`instructions-v*`) with three assets:
   `CLAUDE.md`, `AGENTS.md`, and `SHA256SUMS`.
2. The consumer runs a scheduled workflow that fetches those assets for a
   **pinned tag**, verifies each file against `SHA256SUMS`, writes the result as
   a committed real file, and opens a PR.
3. The PR is reviewed and merged behind the consumer's own code-owner gate. Do
   not auto-merge: a change to the universal instructions is a human-reviewed
   event.

## Where the synced file goes

- **No project-specific delta:** sync `CLAUDE.md` to the repository root
  `CLAUDE.md` (and `AGENTS.md` to `AGENTS.md`). The whole file is the master
  copy.
- **With a project-specific delta:** sync to a vendored path, e.g.
  `.agents/claude-md-master/CLAUDE.md`, and keep the consumer's own root
  `CLAUDE.md` as a small file that imports it and adds the delta:

  ```markdown
  @.agents/claude-md-master/CLAUDE.md

  ## Project-specific rules
  - (only the delta for this project)
  ```

  The sync workflow overwrites only the vendored file, so the consumer's root
  `CLAUDE.md` is never clobbered. Both files are committed real files.

## Pinning and integrity

- Pin a specific release **tag** (for example `instructions-v1.0.0`) in the
  workflow `env`. Bump it deliberately in a reviewed PR; do not follow `main`.
- Every fetched file is verified against the release's `SHA256SUMS` with
  `sha256sum -c`. A mismatch fails the job loudly -- it never commits an
  unverified file.
- For full supply-chain pinning, also record the expected sha256 of
  `SHA256SUMS` itself in the workflow and check it before trusting the manifest;
  the tag is immutable, so the manifest at a tag does not change.

## Copyable sync workflow template

Copy this into the consumer repository as `sync-claude-md.yml` inside its
`.github/workflows/` directory, and adjust the marked values. Pin every action
to a full commit SHA: the SHAs below are illustrative -- verify the current SHA
from each action's releases before use.

```yaml
name: Sync agent instructions

on:
  schedule:
    - cron: "0 6 * * 1"  # weekly; adjust as needed
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: false

env:
  MASTER_REPO: tvna/claude-md
  # Pin a specific release tag. Bump deliberately in a reviewed PR.
  INSTRUCTIONS_TAG: instructions-v1.0.0

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      # Recommended: restrict egress to the GitHub download hosts.
      - name: Harden runner
        uses: step-security/harden-runner@<COMMIT_SHA>  # vX.Y.Z -- pin to a full commit SHA
        with:
          egress-policy: audit

      - name: Checkout consumer repository
        uses: actions/checkout@<COMMIT_SHA>  # v6.0.3 -- pin to a full commit SHA
        with:
          persist-credentials: false

      - name: Fetch and verify release assets
        env:
          MASTER_REPO: ${{ env.MASTER_REPO }}
          INSTRUCTIONS_TAG: ${{ env.INSTRUCTIONS_TAG }}
        run: |
          set -euo pipefail
          base="https://github.com/${MASTER_REPO}/releases/download/${INSTRUCTIONS_TAG}"
          tmp="$(mktemp -d)"
          for f in CLAUDE.md AGENTS.md SHA256SUMS; do
            curl -fsSL "${base}/${f}" -o "${tmp}/${f}"
          done
          # Verify every payload file against the release manifest. A mismatch
          # exits non-zero and the job fails before anything is committed.
          ( cd "$tmp" && sha256sum -c SHA256SUMS )
          # Land the verified files as committed real files (no symlink).
          # No-delta layout: write to the repository root.
          cp "${tmp}/CLAUDE.md" CLAUDE.md
          cp "${tmp}/AGENTS.md" AGENTS.md
          rm -rf "$tmp"

      - name: Open a pull request on change
        uses: peter-evans/create-pull-request@<COMMIT_SHA>  # vX.Y.Z -- pin to a full commit SHA
        with:
          branch: chore/sync-claude-md
          title: "chore: sync agent instructions from tvna/claude-md"
          commit-message: "chore: sync agent instructions (${{ env.INSTRUCTIONS_TAG }})"
          body: |
            Syncs CLAUDE.md / AGENTS.md from ${{ env.MASTER_REPO }}
            release ${{ env.INSTRUCTIONS_TAG }}, verified against SHA256SUMS.

            Review and merge behind the code-owner gate. Do not auto-merge.
          labels: instructions-sync
```

## Token and review notes

- The workflow uses the consumer repository's own `GITHUB_TOKEN` (or a
  consumer-owned App) with `contents: write` + `pull-requests: write`. No token
  from the master repository is needed: the release assets are public downloads.
- Cite the consumer repository's own tracking issue in the PR body per its body
  policy; do not hardcode a master-repository issue number.
- Keep auto-merge disabled for this PR. The code-owner review is the merge gate.

## Verify

After copying the template into a consumer repo, confirm the synced file is a
real file, not a symlink:

```sh
test -f CLAUDE.md && ! test -L CLAUDE.md && echo "OK: committed real file"
```

## References

- [`docs/proposals/instruction-distribution-mechanism.md`](../proposals/instruction-distribution-mechanism.md) -- the options, decision, and the retraction rationale.
- [`.github/workflows/publish-instructions-release.yml`](../../.github/workflows/publish-instructions-release.yml) -- the master release workflow that produces the assets this template consumes.
- [`README.md`](../../README.md) -- the consumer-facing summary that links here.
