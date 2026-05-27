"""Contract test: the two ``_MERGE_FROM_MAIN_PREFIXES`` tuples agree.

Issue #515 codifies the design intent for the merge-from-main preflight
introduced in Issue #491 (PR #503). Two modules independently maintain
a ``_MERGE_FROM_MAIN_PREFIXES`` tuple:

* ``scripts/preflight_pr_no_merge_commits.py`` -- the blocking gate that
  rejects merge-from-main commits at PR push time.
* ``scripts/auto_retro.py`` -- the reporting classifier that tags
  rebase-debt rows in the retrospective Repair history table.

Both must agree on what counts as a merge-from-main subject. If the
gate's set is broader than the classifier's, retro reports under-count
real rebase debt; if the classifier's is broader, the gate lets
recognized-as-rebase-debt commits through. The maintenance rule and the
rationale for keeping the duplication (rather than collapsing into a
shared symbol) are documented in
``docs/runbooks/rebase-debt-recovery.md`` under the
"``_MERGE_FROM_MAIN_PREFIXES`` lock-step rule" section.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import auto_retro
import preflight_pr_no_merge_commits


class TestMergeFromMainPrefixesLockstep:
    def test_tuples_agree_as_sets(self) -> None:
        """The two tuples MUST contain the same prefixes (order-independent).

        When this test fails, extend whichever tuple is missing entries
        so both sides agree, then update
        ``docs/runbooks/rebase-debt-recovery.md`` if a new branch
        convention (e.g. ``trunk``) was introduced. Do NOT silence the
        test by editing only one tuple.
        """
        gate_prefixes = set(preflight_pr_no_merge_commits._MERGE_FROM_MAIN_PREFIXES)
        classifier_prefixes = set(auto_retro._MERGE_FROM_MAIN_PREFIXES)
        assert gate_prefixes == classifier_prefixes, (
            "merge-from-main prefix lists drifted. "
            f"only in preflight_pr_no_merge_commits: {sorted(gate_prefixes - classifier_prefixes)!r}; "
            f"only in auto_retro: {sorted(classifier_prefixes - gate_prefixes)!r}. "
            "See docs/runbooks/rebase-debt-recovery.md (lock-step rule)."
        )

    def test_tuples_are_non_empty(self) -> None:
        """Guard against a future refactor that empties either tuple.

        An empty tuple makes the gate inert (every merge subject would
        only be caught by the parent-count > 1 fallback) and the
        classifier blind. The contract test above would still pass on
        ``set() == set()``, so this independent assertion stays.
        """
        assert preflight_pr_no_merge_commits._MERGE_FROM_MAIN_PREFIXES, (
            "preflight_pr_no_merge_commits._MERGE_FROM_MAIN_PREFIXES must not be empty"
        )
        assert auto_retro._MERGE_FROM_MAIN_PREFIXES, "auto_retro._MERGE_FROM_MAIN_PREFIXES must not be empty"
