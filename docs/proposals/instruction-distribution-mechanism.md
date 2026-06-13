# Instruction Distribution Mechanism

Tracking issue: [#1678](https://github.com/tvna/claude-md/issues/1678)

This proposal records how downstream projects should import the compiled
`CLAUDE.md` / `AGENTS.md` from this master repository, why the previously
documented submodule + symlink method is retracted, and which mechanism is
adopted now versus deferred. It is a `proposals/` document (not `prd/`) because
one open question remains: when the deferred reusable-workflow option (B)
graduates. See the graduation note at the end.

## Problem

- Fact (primary doc): Claude Code on the web starts each session from a fresh
  `git clone`. The official documentation states "Cloud sessions start from a
  fresh clone of your repository. Anything committed to the repo is available."
  and lists `CLAUDE.md` as "Part of the clone". The page contains no mention of
  submodules or `--recurse-submodules`.
- Fact (observed, git 2.43.0): a parent repository stores a submodule as a
  gitlink (mode 160000, a commit pointer only), not file contents. After a
  plain `git clone` (without `--recurse-submodules`) the submodule directory is
  empty, so a `CLAUDE.md` symlinked into it is a broken link and the project
  instructions are silently not loaded.
- Fact: the README documented exactly this submodule + symlink method, so a new
  web-session consumer following it reproduces the silent no-load failure.
- Fact: this repository had published no GitHub releases, so release-asset
  distribution is net-new infrastructure.

The acceptance constraints for any replacement: the imported file must be a
committed real file (no symlink, no submodule); updates flow through a PR behind
the consumer code-owner review gate (no auto-merge); fetch is version-pinned and
integrity-verified; actions are SHA-pinned.

## Options considered

| Option | Mechanism | Supply-chain safety | Central management | Complexity / blast radius | YAGNI fit |
|---|---|---|---|---|---|
| A: shipped template | Retract submodule; document a committed-real-file method; ship a copyable scheduled sync workflow (PR-#428-equivalent) in `docs/`, fetching a tag-pinned artifact. | Medium (tag-pinned fetch) | Low (each consumer copies) | Small | High |
| B: reusable `workflow_call` + composite action | Master publishes the sync logic; consumers add a thin `uses: tvna/claude-md/...@<sha>` caller. | Medium-high (SHA-pinned `uses`) | High | Medium (consumer write-permission and token requirements propagate) | Low (over-built for one consumer) |
| C: tagged release artifacts + sha256 | On tag, publish `CLAUDE.md` / `AGENTS.md` / `SHA256SUMS` as release assets; consumers pin version + verify digest. | High (immutable assets + digest) | Medium | Medium (new release process) | Low (new process, but pairs with A) |

## Decision

**Adopt A + C now; defer B.** Fetch is pinned by **git tag + sha256
verification** against the published `SHA256SUMS`.

- A removes the reproducible failure immediately and gives consumers a correct,
  copyable path whose result is a committed real file.
- C makes the artifact source an immutable, integrity-verifiable release rather
  than a moving `main`, satisfying the version-pin + digest constraint without
  depending on `main`-following.
- A and C compose: the shipped template fetches the C release asset for a pinned
  tag and verifies it against the release's `SHA256SUMS` before committing it.

Rationale ties to CLAUDE.md section 4 (minimum that solves the problem while
preserving supply-chain safety) and section 3 (deterministic gates first, then
scale): the release publish and the consumer template are both PR-gated and
SHA-pinned; no auto-merge anywhere.

## What lands

- `.github/workflows/publish-instructions-release.yml` plus
  `scripts/publish_instruction_release.py` (first-party REST publisher, chosen
  over a third-party release action so no new supply-chain dependency is added;
  the upload stays on the single `_github_api` HTTP boundary, must-have M7).
- `docs/runbooks/consumer-instruction-sync.md` -- the operator procedure and the
  copyable sync workflow template.
- README (three languages) retraction of submodule + symlink and the
  committed-real-file method.

## Deferred: option B (reusable workflow / composite action)

B is deferred, not rejected. Re-open condition: **two or more downstream
consumers exist, or measured copy-paste drift between consumer sync workflows**.
Until then, the shipped template (A) keeps the consumer surface a single copied
file with no master-side runtime coupling.

## Open question and graduation path

- Open: the trigger for B's graduation (the re-open condition above) is not yet
  observable, so this document stays in `proposals/`.
- Graduation: once B is decided (adopted or formally rejected), move the settled
  decision to `docs/prd/`; if the consumer procedure needs a stricter adopted
  contract (artifact format, tag scheme), promote that part to
  `docs/standards/`. Update `docs/INDEX.md` on any move.

## References

- [`docs/runbooks/consumer-instruction-sync.md`](../runbooks/consumer-instruction-sync.md) -- consumer procedure and template.
- [`.github/workflows/publish-instructions-release.yml`](../../.github/workflows/publish-instructions-release.yml) -- the master release workflow.
- [`scripts/publish_instruction_release.py`](../../scripts/publish_instruction_release.py) -- the first-party release publisher.
- [`docs/runbooks/downstream-instruction-review-checklist.md`](../runbooks/downstream-instruction-review-checklist.md) -- security review for instruction-shipping PRs.
- [`README.md`](../../README.md) -- the consumer-facing integration section this proposal updates.
