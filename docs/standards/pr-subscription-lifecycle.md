# PR Subscription Lifecycle Standard

This standard defines the repository-owned terminal-state signal for a
merged PR after the auto-retro pipeline has opened or reused its
retrospective issue. The goal is to give subscribed sessions and human
operators one current, machine-readable mark to inspect without reading
PR history.

The implementation lives in [`scripts/auto_retro.py`](../../scripts/auto_retro.py)
and [`.github/workflows/post-merge.yml`](../../.github/workflows/post-merge.yml).

## Purpose And Non-Goals

**Purpose.** Document the harness contract for signaling that a merged
PR has reached its terminal state, so subscribed Claude sessions and
human operators have a single deterministic mark to read.

**Non-goals.**

- Prescribing receiver behavior. Whether a subscribed Claude session
  consumes the `pull_request.labeled` webhook by calling
  `unsubscribe_pr_activity` is platform / session policy and lives
  outside this repository.
- Replacing the auto-retro back-link comment. The label is a second,
  machine-readable signal layered on top of the existing PR -> retro
  reverse pointer; the comment remains the human-visible entry point.

## Signal

The label `ops:retro-opened` is added to the source PR by
`scripts/auto_retro.py::apply_terminal_label` immediately after
`post_back_link_comment` returns successfully. The SoT entry lives in
[`.github/labels.json`](../../.github/labels.json) and is reconciled onto
the repository by `apply-labels.yml`.

A PR carrying this label has, by construction:

- been merged with `merged == true`,
- had a retrospective issue created (or an existing one reused), and
- received a back-link comment pointing at the retro.

The label is therefore a single-bit terminal-state mark. Absence does
not imply the PR is non-terminal; presence implies the auto-retro
pipeline ran end-to-end.

## Emission Contract

- Emission is the harness's responsibility. The constant
  `_TERMINAL_LABEL` in `scripts/auto_retro.py` and the SoT entry in
  `.github/labels.json` are kept aligned by
  `tests/test_auto_retro.py::test_terminal_label_aligned_with_labels_json`.
- Label add is naturally idempotent at the GitHub API layer, so a
  re-run on the same PR is a no-op.
- Failure to add the label is downgraded to `::warning::` and does
  not roll back the retro issue or the back-link comment. The retro
  audit trail is the primary deliverable; the label is secondary.

## Out Of Scope

- Close-without-merge PRs. The `merged == true` guard at
  `.github/workflows/post-merge.yml` excludes them, so rationale
  comments on non-merged closes continue to surface in subscribed
  sessions as before.
- Removing or renaming the label after emission. Once applied, the
  label persists until a human or a future workflow removes it.

## References

- [#387](https://github.com/tvna/claude-md/issues/387); original
  terminal-signal issue.
