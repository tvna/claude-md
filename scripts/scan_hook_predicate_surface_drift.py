#!/usr/bin/env python3
"""Detect drift between a git hook's ``if:`` predicate and its command surface.

Refs #2133 (PR #2120 retrospective #2121, P1). git-family PreToolUse hooks are
pre-filtered by an ``if:`` predicate declared in
``scripts/agent_hooks_source.json`` (``Bash(*git commit*)``,
``Bash(*git push*)``, or the broad ``Bash(*git *)``). The predicate runs BEFORE
the hook script, so a script only ever sees commands the predicate admits. When
a script's own command surface is broader than its predicate, widening that
surface is silently inert: the hook never fires for the new subcommands.

PR #2120 hit exactly this. ``check_commit_signing_ready.py`` broadened its
matcher from ``commit`` to ``commit/merge/rebase/cherry-pick/revert/am/pull``,
but the hook still ran under ``if: Bash(*git commit*)``, so ``git merge`` never
invoked the script and the widened matcher guarded nothing until the predicate
was broadened to ``Bash(*git *)``. Nothing caught that gap; the matcher and the
predicate are edited in two different places (the script and the source JSON).

The invariant this gate enforces: **every git ``if:`` hook predicate must admit
the script's declared command surface.** Each git-hook script exposes a
module-level constant ``HOOK_GIT_SUBCOMMANDS``:

* a ``frozenset[str]`` of the git subcommands the script acts on
  (e.g. ``frozenset({"commit"})``), or
* the sentinel :data:`ANY_GIT` (the string ``"*"``) when the script acts on
  arbitrary git commands (``git switch``/``checkout``/...), which can only be
  pre-filtered safely by the broad ``Bash(*git *)`` predicate.

Declaration policy, scoped to keep the blast radius minimal while still closing
the PR #2120 class:

* A hook behind the broad ``Bash(*git *)`` predicate admits every git command,
  so it can never under-cover; declaring its surface is OPTIONAL. When present
  the surface is still validated (it must be admitted), but a broad predicate
  never fails on coverage.
* A hook behind a NARROW predicate (``*git commit*`` / ``*git push*``) MUST
  declare ``HOOK_GIT_SUBCOMMANDS``, and every subcommand in that surface must be
  admitted by the predicate. This is what reproduces and blocks the PR #2120
  bug: re-narrowing a previously broad hook's predicate (or widening a narrow
  hook's surface without widening its predicate) forces a declaration that the
  predicate cannot admit, and the gate fails loudly with the fix.

Admission is decided by :func:`fnmatch.fnmatchcase` against a representative
``git <subcommand>`` probe, the same shell-glob semantics the agent harness uses
to evaluate ``Bash(...)`` ``if:`` predicates, so the check matches how the hook
is actually gated rather than re-deriving it.

Comparison model
----------------
The rendered Claude config ``.claude/settings.json`` is read (the ``if:``
predicate is a Claude-side pre-filter; ``gen_agent_hooks.py --check`` keeps it
in sync with the ``scripts/agent_hooks_source.json`` source of truth). For every
``PreToolUse`` ``Bash`` hook whose ``if:`` predicate references git, the gate
resolves the script it invokes, imports that module, reads
``HOOK_GIT_SUBCOMMANDS``, and verifies admission. The ``cd ... &&`` working-dir
wrapper the generator prepends does not hide the ``scripts/<name>.py`` token.

Exit codes:
* ``0``; every git hook's predicate admits its declared surface.
* ``1``; at least one narrow-predicate hook is missing a declaration, or a
  declared surface is not admitted by the hook's predicate.

Contract:
- Inputs: the ``verify`` subcommand; ``--settings`` (default
  ``.claude/settings.json``). Reads that rendered config and imports each
  git-hook script it references to read ``HOOK_GIT_SUBCOMMANDS``.
- Outputs: ``::error file=...::`` annotations on stderr, one per drifted hook
  (missing declaration on a narrow predicate, or a declared subcommand the
  predicate does not admit); exit 0 when every git hook is sound, exit 1
  otherwise.
- Failure policy: fail-loud. Malformed config sections are skipped defensively,
  but a missing declaration or an unadmitted surface is reported and exits 1; a
  hook module that cannot be imported is reported (not swallowed) and exits 1.

Tested by ``tests/test_scan_hook_predicate_surface_drift.py`` and
``tests/test_workflow_cli_contracts.py``. Refs #2133, #2120.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# The constant each git-hook script exposes to declare its command surface.
SURFACE_ATTR = "HOOK_GIT_SUBCOMMANDS"

# Sentinel surface: the script acts on arbitrary git commands, so only the
# broad ``Bash(*git *)`` predicate can pre-filter it without dropping a command.
ANY_GIT = "*"

# The single broad git predicate inner-glob that admits every git command.
BROAD_INNER = "*git *"

# Only ``PreToolUse`` ``Bash`` hooks are pre-filtered by a Bash ``if:``
# predicate; that is the surface this gate governs.
HOOK_EVENT = "PreToolUse"

# Extract the inner glob from a ``Bash(<inner>)`` predicate.
_BASH_PREDICATE_RE = re.compile(r"^Bash\((?P<inner>.*)\)$")
# Resolve ``python3 scripts/<name>.py`` to the importable module name.
_SCRIPT_REF = re.compile(r"\bscripts/([a-zA-Z][\w]*)\.py\b")


@dataclass(frozen=True)
class GitHook:
    """One git-predicated PreToolUse Bash hook from the source config."""

    script: str  # importable module name, e.g. "check_commit_signing_ready"
    command: str  # the raw command string (for error messages)
    predicate: str  # the raw ``if:`` predicate, e.g. "Bash(*git commit*)"
    inner: str  # the predicate inner glob, e.g. "*git commit*"


def _predicate_inner(predicate: str) -> str | None:
    """Return the inner glob of a ``Bash(...)`` predicate, or None if not one."""
    match = _BASH_PREDICATE_RE.match(predicate.strip())
    return match.group("inner") if match else None


def _is_git_predicate(inner: str) -> bool:
    """True when a predicate inner-glob targets git commands."""
    return "git" in inner


def iter_git_hooks(source: dict[str, object]) -> Iterator[GitHook]:
    """Yield every git-predicated PreToolUse Bash hook declared in *source*.

    Defensive ``isinstance`` guards skip malformed config rather than raising,
    matching the posture of ``scan_hook_coverage_drift.py``. A handler is a git
    hook when it carries a ``Bash(*...git...*)`` ``if:`` predicate and invokes a
    ``scripts/<name>.py`` script.
    """
    raw_hooks = source.get("hooks")
    if not isinstance(raw_hooks, dict):
        return
    raw_groups = raw_hooks.get(HOOK_EVENT)
    if not isinstance(raw_groups, list):
        return
    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            continue
        for handler in handlers:
            if not isinstance(handler, dict):
                continue
            predicate = handler.get("if")
            command = handler.get("command")
            if not isinstance(predicate, str) or not isinstance(command, str):
                continue
            inner = _predicate_inner(predicate)
            if inner is None or not _is_git_predicate(inner):
                continue
            scripts = _SCRIPT_REF.findall(command)
            if not scripts:
                continue
            # A single command invokes a single script; the first match is it.
            yield GitHook(
                script=scripts[0],
                command=command,
                predicate=predicate,
                inner=inner,
            )


def _load_surface(script: str) -> object:
    """Import *script* and return its ``HOOK_GIT_SUBCOMMANDS`` (or None).

    Importing is how the sibling gates resolve a script's source of truth
    (e.g. ``gate_retro_close_keyword_commit.py`` imports ``auto_retro``); the
    hook modules have no import-time side effects. A missing attribute yields
    ``None`` so the caller can apply the declaration policy.
    """
    module = importlib.import_module(script)
    return getattr(module, SURFACE_ATTR, None)


def _admits(inner: str, subcommand: str) -> bool:
    """True when predicate inner-glob *inner* admits ``git <subcommand>``.

    Uses the same shell-glob semantics (:func:`fnmatch.fnmatchcase`) the agent
    harness applies to ``Bash(...)`` ``if:`` predicates, probed with a
    representative invocation so a trailing argument cannot change the verdict.
    """
    probe = f"git {subcommand} -m x"
    return fnmatch.fnmatchcase(probe, inner)


def check_hook(hook: GitHook, surface: object) -> list[str]:
    """Return human-readable problems for one hook, or [] when it is sound.

    Policy (see module docstring): a narrow predicate MUST declare a surface
    that it fully admits; a broad ``Bash(*git *)`` predicate admits everything,
    so its declaration is optional but, when present, still validated.
    """
    is_broad = hook.inner == BROAD_INNER

    if surface is None:
        if is_broad:
            return []  # broad predicate admits all git commands; declaration optional
        return [
            f"hook scripts/{hook.script}.py is gated by a narrow predicate "
            f"{hook.predicate!r} but does not declare {SURFACE_ATTR}. Add "
            f"{SURFACE_ATTR} (a frozenset of git subcommands, or "
            f"scan_hook_predicate_surface_drift.ANY_GIT) so the predicate can "
            "be verified to admit it."
        ]

    if surface == ANY_GIT:
        if not is_broad:
            return [
                f"hook scripts/{hook.script}.py declares {SURFACE_ATTR} = "
                f"ANY_GIT (acts on arbitrary git commands) but its predicate "
                f"{hook.predicate!r} is narrower than {BROAD_INNER!r}; only the "
                "broad Bash(*git *) predicate can pre-filter it without dropping "
                "a command. Broaden the if: predicate in "
                "scripts/agent_hooks_source.json."
            ]
        return []

    if not isinstance(surface, set | frozenset) or not all(
        isinstance(s, str) for s in surface
    ):
        return [
            f"hook scripts/{hook.script}.py: {SURFACE_ATTR} must be a frozenset "
            f"of git-subcommand strings or ANY_GIT, got {type(surface).__name__}."
        ]
    if not surface:
        return [
            f"hook scripts/{hook.script}.py: {SURFACE_ATTR} is empty; declare the "
            "git subcommands the script acts on (or ANY_GIT)."
        ]

    unadmitted = sorted(sub for sub in surface if not _admits(hook.inner, sub))
    if unadmitted:
        return [
            f"hook scripts/{hook.script}.py predicate {hook.predicate!r} does NOT "
            f"admit declared subcommand(s) {unadmitted}; the hook would never fire "
            f"for them (the PR #2120 silent-inert-matcher class). Broaden the if: "
            "predicate in scripts/agent_hooks_source.json to cover the full "
            f"{SURFACE_ATTR} surface (e.g. {BROAD_INNER!r})."
        ]
    return []


def find_drift(source: dict[str, object]) -> list[str]:
    """Return every predicate-vs-surface problem across all git hooks."""
    problems: list[str] = []
    for hook in iter_git_hooks(source):
        try:
            surface = _load_surface(hook.script)
        except Exception as exc:  # report, do not crash the gate
            problems.append(
                f"hook scripts/{hook.script}.py could not be imported to read "
                f"{SURFACE_ATTR}: {exc}"
            )
            continue
        problems.extend(check_hook(hook, surface))
    return problems


def cmd_verify(args: argparse.Namespace) -> int:
    settings = json.loads(Path(args.settings).read_text(encoding="utf-8"))
    # Ensure scripts/ is importable so the hook modules resolve both when run as
    # ``python scripts/x.py`` (sys.path[0] is already scripts/) and under pytest.
    scripts_dir = str(SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    problems = find_drift(settings)
    for message in problems:
        # The fix lives in the source of truth where the if: predicate is
        # authored, not the generated settings file.
        print(f"::error file=scripts/agent_hooks_source.json::{message}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect drift between a git hook's if: predicate and its command surface.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser("verify", help="Run the drift check.")
    verify.add_argument(
        "--settings",
        default=str(CLAUDE_SETTINGS),
        help="Path to the rendered .claude/settings.json.",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
