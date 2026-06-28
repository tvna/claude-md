"""Shared continuation-bypass contract for the shell/YAML-scanning gates.

Issue #2164 retrospective for PR #2163, repair (a). The first version of
``scan_ruff_format`` scanned physical lines, so a ``ruff format`` split across a
POSIX shell ``\\`` continuation slipped through; the same bypass was latent in
every sibling gate that matches a two-token shell command on a single physical
line. The durable fix routes every such gate through
``scripts/_shell_lines.flatten_shell_continuations`` (the single source of
truth) and pins the behaviour here.

This module is the author-side gate the retrospective identified as the earliest
deterministic check that would have caught the original bug: for every
shell-scanning gate, a known single-token-split continuation form must be caught
just like its single-line form. A new shell-scanning gate that forgets
continuation handling fails :func:`test_registry_covers_shell_lines_importers`
(it imports the shared helper but is absent from the registry) or
:func:`test_gate_catches_continuation_form` (it does not flatten), at author test
time rather than in adversarial review. Refs #2164, #2163, #2143.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
import scan_ruff_format
import scan_workflow_gh_calls
import scan_workflow_pip
import scan_workflow_unsigned_commit

pytestmark = pytest.mark.shard_preflight

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


class GateCase(NamedTuple):
    """A shell-scanning gate and matched single-line / continuation samples.

    ``module_name`` is the ``scripts/<name>.py`` stem (matched against the set of
    modules importing ``_shell_lines``). ``catches`` returns True when the gate
    flags *text*. ``single_line`` is a violation on one physical line;
    ``continuation`` is the same command split across a ``\\`` continuation.
    """

    module_name: str
    catches: Callable[[str], bool]
    single_line: str
    continuation: str


GATES: tuple[GateCase, ...] = (
    GateCase(
        "scan_ruff_format",
        lambda t: bool(scan_ruff_format.scan_text(t)),
        "uv run ruff format scripts",
        "uv run ruff \\\n  format scripts",
    ),
    GateCase(
        "scan_workflow_pip",
        lambda t: bool(scan_workflow_pip.scan_text(t)),
        "pip install requests",
        "pip \\\n  install requests",
    ),
    GateCase(
        "scan_workflow_gh_calls",
        lambda t: bool(scan_workflow_gh_calls.scan_run_text(t)),
        "gh api repos/o/r",
        "gh \\\n  api repos/o/r",
    ),
    GateCase(
        "scan_workflow_unsigned_commit",
        lambda t: bool(scan_workflow_unsigned_commit.scan_run_text(t)),
        "git push origin main",
        "git \\\n  push origin main",
    ),
)

_IMPORTS_SHELL_LINES = re.compile(r"^\s*(?:from|import)\s+_shell_lines\b", re.MULTILINE)


def _modules_importing_shell_lines() -> set[str]:
    """Return the stems of ``scripts/*.py`` modules importing ``_shell_lines``."""
    return {
        path.stem
        for path in SCRIPTS_DIR.glob("*.py")
        if _IMPORTS_SHELL_LINES.search(path.read_text(encoding="utf-8"))
    }


@pytest.mark.parametrize("gate", GATES, ids=lambda g: g.module_name)
def test_gate_catches_single_line_form(gate: GateCase) -> None:
    """Sanity: each registered gate flags its single-line violation sample."""
    assert gate.catches(gate.single_line), (
        f"{gate.module_name} did not flag its single-line sample "
        f"{gate.single_line!r}; the registry sample is stale."
    )


@pytest.mark.parametrize("gate", GATES, ids=lambda g: g.module_name)
def test_gate_catches_continuation_form(gate: GateCase) -> None:
    """The durable property: a `\\`-continuation split must be caught too.

    A gate that scans physical lines (not logical lines) fails here. Route it
    through ``_shell_lines.flatten_shell_continuations`` like its siblings.
    """
    assert gate.catches(gate.continuation), (
        f"{gate.module_name} missed a shell continuation: the command "
        f"{gate.single_line!r} split across a `\\` continuation slipped through. "
        f"Flatten continuations via scripts/_shell_lines.flatten_shell_continuations "
        f"before matching (issue #2164)."
    )


def test_registry_covers_shell_lines_importers() -> None:
    """Every gate importing the shared helper must be registered here.

    This is the drift guard that forces a new shell-scanning gate into the
    continuation contract: importing ``_shell_lines`` without a :data:`GATES`
    entry fails loudly, mirroring the CONTRACT_REGISTRY mirror tests in
    tests/test_workflow_cli_contracts.py.
    """
    registered = {gate.module_name for gate in GATES}
    importers = _modules_importing_shell_lines()
    unregistered = sorted(importers - registered)
    assert not unregistered, (
        f"scripts modules import _shell_lines but are not in the continuation "
        f"contract registry: {unregistered}. Add a GateCase entry (with matched "
        f"single-line and `\\`-continuation samples) so the continuation bypass "
        f"cannot recur in that gate (issue #2164)."
    )
    stale = sorted(registered - importers)
    assert not stale, (
        f"GATES registry has entries that no longer import _shell_lines: "
        f"{stale}. Remove them so the registry stays a true mirror."
    )
