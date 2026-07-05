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
import scan_workflow_llm_budget
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
        "scan_workflow_llm_budget",
        lambda t: bool(scan_workflow_llm_budget.scan_text(t, ["claude -p"])),
        "claude -p 'do the thing'",
        "claude \\\n  -p 'do the thing'",
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

# Shell scanners outside the ``scan_workflow_*`` naming convention that still
# scan a two-token shell command on a gate surface. Listed explicitly so the
# scanner surface is not silently narrowed to the workflow family.
_EXTRA_SCANNERS = ("scan_ruff_format",)

# ``scan_workflow_*`` modules that do NOT match a two-token shell command, so a
# backslash continuation cannot apply to them. Each carries a one-line rationale;
# the ratchet in :func:`test_scanner_surface_is_classified` keeps the set from
# outliving its modules. Refs #2164, Codex review on PR #2175.
EXEMPT_SCANNERS: dict[str, str] = {
    "scan_workflow_action_pins": (
        "Scans `uses:` action-pin references (SHA/tag), not shell run: command "
        "tokens; a backslash continuation cannot split an action pin."
    ),
    "scan_workflow_injection": (
        "Scans GitHub ${{ }} template-expression injection, evaluated by Actions "
        "before the shell; not a two-token shell command split by a continuation."
    ),
}


def _scanner_surface() -> set[str]:
    """Return the known shell-command scanner surface, structurally (not by import).

    The surface is every ``scripts/scan_workflow_*.py`` (the naming convention for
    workflow run: scanners) plus the gate-surface scanners in
    :data:`_EXTRA_SCANNERS`. Basing the completeness mirror on this surface rather
    than on who imports ``_shell_lines`` is the point: a new scanner that does a
    physical-line scan and forgets the shared flattener never imports it, yet still
    lands in this surface, so the absence is observable (Codex review on PR #2175).
    A shell scanner added outside the ``scan_workflow_*`` convention must be added
    to :data:`_EXTRA_SCANNERS`.
    """
    surface = {p.stem for p in SCRIPTS_DIR.glob("scan_workflow_*.py")}
    surface.update(_EXTRA_SCANNERS)
    return surface


def _module_imports_shell_lines(module_name: str) -> bool:
    """Return True if ``scripts/<module_name>.py`` imports the shared flattener."""
    source = (SCRIPTS_DIR / f"{module_name}.py").read_text(encoding="utf-8")
    return _IMPORTS_SHELL_LINES.search(source) is not None


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


def test_scanner_surface_is_classified() -> None:
    """Every shell-command scanner is registered in GATES or explicitly exempt.

    The drift guard that forces a new shell-scanning gate into the continuation
    contract. Unlike an import-based mirror, this is structural: a new scanner that
    scans run: text with a physical-line regex and forgets the shared flattener
    never imports ``_shell_lines``, yet still lands in :func:`_scanner_surface`, so
    its absence from both GATES and :data:`EXEMPT_SCANNERS` fails here, catching
    the exact regression this contract guards (Codex review on PR #2175).
    """
    registered = {gate.module_name for gate in GATES}
    surface = _scanner_surface()
    unclassified = sorted(surface - registered - set(EXEMPT_SCANNERS))
    assert not unclassified, (
        f"shell-command scanner(s) {unclassified} are neither registered in GATES "
        f"(add a GateCase with single-line and `\\`-continuation samples) nor in "
        f"EXEMPT_SCANNERS with a rationale. A scanner over shell run: text must "
        f"flatten continuations via scripts/_shell_lines.flatten_shell_continuations; "
        f"if it scans something else (action pins, ${{ }} expressions), exempt it "
        f"explicitly (issue #2164)."
    )
    stale = sorted(set(EXEMPT_SCANNERS) - surface)
    assert not stale, (
        f"EXEMPT_SCANNERS lists modules no longer in the scanner surface: {stale}. "
        f"Remove them so the exemption set only shrinks."
    )


def test_registered_gates_use_shared_helper() -> None:
    """Each registered gate routes through the shared flattener, not a private copy.

    Registration in GATES means the gate delegates continuation handling to the
    single source of truth; this catches a gate that re-introduces its own
    ``_logical_lines``-style copy while staying in the registry (issue #2164).
    """
    not_importing = sorted(
        gate.module_name for gate in GATES if not _module_imports_shell_lines(gate.module_name)
    )
    assert not not_importing, (
        f"registered gate(s) {not_importing} no longer import _shell_lines; route "
        f"them through scripts/_shell_lines.flatten_shell_continuations rather than a "
        f"private copy (issue #2164)."
    )
