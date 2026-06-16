"""Tests for ``scripts/preflight_steps.py``.

The step registry was extracted from ``scripts/preflight_all.py`` (issue
#1670) so the executor module stays within the maintainability budget.
These tests pin the data invariants of the extracted :data:`STEPS` tuple
and the :class:`Step` schema directly against the new module; the
executor behaviour (``run_all``, caching, fail-fast) stays covered by
``tests/test_preflight_all.py`` via the re-export.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import preflight_all
import preflight_steps
import pytest

pytestmark = pytest.mark.shard_preflight


class TestStepsRegistry:
    def test_steps_nonempty(self) -> None:
        assert len(preflight_steps.STEPS) > 0

    def test_step_names_are_unique(self) -> None:
        names = [s.name for s in preflight_steps.STEPS]
        assert len(names) == len(set(names))

    def test_every_step_has_argv(self) -> None:
        for step in preflight_steps.STEPS:
            assert step.argv, f"step {step.name!r} has empty argv"

    def test_no_step_generates_docs_generated(self) -> None:
        # Issue #1771 (Refs #1764): docs/generated/ is owned by the post-merge
        # automation as a single-producer surface -- docs/generated/scripts/
        # (#1540/#1543/#1546) and docs/generated/workflows/ (#1771) alike. The
        # pre-push lane must regenerate nothing there: generating left a
        # perpetually-untracked diagram that tripped the untracked-file stop
        # hook. This gate keeps a generator command from silently re-entering
        # STEPS, the way workflow_diagram_doc lingered after its siblings were
        # removed. Each entry is (script basename, write subcommand).
        forbidden_producers = {
            ("script_ast_graph.py", "all-doc"),
            ("script_dependency_graph.py", "all-doc"),
            ("script_trigger_map.py", "all-doc"),
            ("workflow_diagram.py", "diagram-doc"),
            ("doc_graph_viz.py", "all-doc"),
        }
        for step in preflight_steps.STEPS:
            tokens = list(step.argv)
            scripts = {
                token.rsplit("/", 1)[-1]
                for token in tokens
                if token.endswith(".py")
            }
            for script, subcommand in forbidden_producers:
                if script in scripts and subcommand in tokens:
                    raise AssertionError(
                        f"step {step.name!r} invokes the docs/generated/ "
                        f"producer '{script} {subcommand}'. docs/generated/ is "
                        "owned by the post-merge automation; the pre-push lane "
                        "must not regenerate it (Refs #1771, #1764)."
                    )

    def test_new_growth_gate_is_registered(self) -> None:
        # Issue #1670: the net-growth gate must ship in the local preflight
        # set so an unjustified instruction-text growth surfaces pre-push.
        by_name = {s.name: s for s in preflight_steps.STEPS}
        assert "verify_instruction_text_growth" in by_name
        step = by_name["verify_instruction_text_growth"]
        assert step.argv == (
            "python3",
            "scripts/verify_instruction_text_growth.py",
            "verify",
            "--base-ref",
            "origin/main",
        )


class TestReexport:
    def test_preflight_all_reexports_steps(self) -> None:
        # Existing references rely on preflight_all.STEPS / preflight_all.Step
        # resolving after the extraction (scan_preflight_drift.py,
        # scan_devcontainer_tool_drift.py, tests/test_preflight_all.py).
        assert preflight_all.STEPS is preflight_steps.STEPS
        assert preflight_all.Step is preflight_steps.Step
