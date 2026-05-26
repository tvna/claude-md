# Archive retention policy

This file documents how `docs/archive/` is curated. The lane exists to
preserve frozen historical evidence -- closed retrospectives, calibration
material, and once-active sections that have been promoted out of the
live PRD -- in a form that future readers can trust as a faithful
snapshot of repository state at the time the entry was added.

Design rationale and the principle this policy serves are in
[`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md);
specifically the retrospective framework that classifies pre-merge
repairs against the earliest deterministic gate that should have
prevented each one.

## Append-only

Existing entries in `docs/archive/` are not edited. They are not
re-formatted, not re-linked when other files in `docs/` move, not
re-titled, and not deleted. The only permitted modifications are:

- Adding a new entry (one new file per merged PR's retrospective, or a
  promoted section from the live PRD lane).
- Adding a year sub-directory (see the cutover below) and moving older
  entries into it as a one-time relocation, preserving filenames.

If a retrospective's narrative cites pre-restructure paths such as
`docs/security-control-drift-report.md`, those references are correct
as-of the merge date recorded inside the file itself. They are not
updated to the post-restructure path even when clicking them in the
current tree would 404. The retrospective is a timestamped record, not
a navigation entry.

Corrections to a published retrospective are made as a follow-up
retrospective in a new file, with the old file linked from the new one
and left in place.

## Naming

| Entry kind | Filename | Notes |
|---|---|---|
| PR retrospective | `retrospective-pr-<N>.md` | `<N>` is the GitHub PR number of the subject PR (not the tracking issue number). One file per subject PR. |
| Promoted PRD section | original section slug | Used when a section of an active PRD is promoted to the archive (for example `decision-tree-replay.md` was promoted from `agent-rules-design-philosophy.md` section 5). |
| Calibration material | descriptive slug | Worked-example bodies and similar calibration files (for example `issue-pr-body-examples.md`) follow the slug they had when promoted. |

Filenames are stable across the optional `YYYY/` cutover described
below; the relocation does not rename files, only nests them.

## auto_retro placement convention

`.github/workflows/auto-retro.yml` fires on PR merge and invokes
`scripts/auto_retro.py`, which opens a tracking issue containing the
retrospective skeleton (subject PR metadata, observed repair history,
linked gates). That tracking issue is the source of truth for the
retrospective; the file under `docs/archive/` is the captured record
produced as part of resolving the tracking issue.

The script itself does not write into `docs/archive/`. The placement
convention is operator-side:

- One file per tracking issue, named `retrospective-pr-<N>.md` where
  `<N>` matches the subject PR number that the tracking issue covers.
- Added in the same PR that closes the tracking issue, so the issue
  closure and the archived record land together.
- ASCII-only body (`.github/workflows/scan-non-ascii.yml` is required
  on `main`).

No change to `scripts/auto_retro.py` is required to maintain this
convention; it operates entirely on GitHub-side issue bodies and is
independent of the lane folder name. The convention is documented here
so the operator step is reproducible without reading the prior
retrospectives' filenames.

## YYYY/ sub-folder cutover

When the number of entries directly under `docs/archive/` exceeds about
30, the lane is reorganized into year sub-directories keyed by the
retrospective creation year (the year of the subject PR merge for
retrospective entries; the year of promotion for promoted sections).

- Layout after cutover: `docs/archive/2026/retrospective-pr-<N>.md`,
  `docs/archive/2027/retrospective-pr-<N>.md`, and so on.
- The cutover is performed once as a single PR using `git mv` to
  preserve rename history. Filenames are unchanged; only the directory
  depth changes.
- `docs/INDEX.md` is updated in the same PR to reference the new paths.
- Entries promoted from live PRDs (such as `decision-tree-replay.md`)
  live under the year of their promotion, not the year of the
  underlying source material.

The threshold of about 30 is a soft cap: the cutover is performed when
`ls docs/archive/` is no longer useful at a glance, which in practice
aligns with this count. The cutover is not automated; it is an
explicit governance step taken once per directory generation.

## Cross-references

- [docs/INDEX.md](../INDEX.md) -- the four-lane index that enumerates
  every document under `docs/`.
- [docs/prd/agent-rules-design-philosophy.md](../prd/agent-rules-design-philosophy.md)
  -- the meta-runbook whose retrospective framework defines what each
  archived retrospective records.
- [docs/runbooks/retrospective-noise-flooding-procedure.md](../runbooks/retrospective-noise-flooding-procedure.md)
  -- the operator procedure for distinguishing signal vs noise across
  the archived retrospectives.
