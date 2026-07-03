#!/usr/bin/env python3
"""Ownership registry and retirement sweep for ``docs/generated/`` artifacts.

Refs #2226. ``docs/generated/`` is a single-producer surface owned by the
post-merge automation (``docs/standards/docs-generated-ownership.md``), but
until this module the retirement half of that lifecycle was ad hoc: two
generators pruned their own orphans (``script_ast_graph.py`` inside
``docs/generated/scripts/ast/``, ``workflow_diagram.py`` inside
``docs/generated/workflows/``), one carried a hard-coded legacy deletion list
(#1540), and the remaining single-file surfaces had no retirement path at all.
Retiring a generator therefore meant a per-case negotiation about who deletes
the stale outputs and on which branch, because
``gate_generated_scripts_manual_edit.py`` forbids non-bot branches from
touching ``docs/generated/``.

This module is the single source of truth closing that gap: :data:`OWNERSHIP`
maps every ``docs/generated/`` path pattern to the producer script that owns
it, and the subcommands split read and write lanes:

* ``verify`` (read-only; preflight and the ``lint-scripts-static`` CI job):
  fails when a registered producer script no longer exists or a pattern is
  malformed. A PR that retires a generator must drop its registry entry in
  the same change, which is exactly what feeds the sweep below.
* ``retire`` (write; post-merge ``decision-tree`` job only): deletes every
  file under ``docs/generated/`` that no registry pattern owns and prunes
  emptied subdirectories. The job's existing drift detection then publishes
  the deletions through the ``chore/update-generated-docs`` bot PR, so a
  retired generator's outputs decommission themselves one post-merge run
  after the retiring PR lands; no hand-authored deletion, no discussion.
* ``list`` (read-only): prints every generated file with its owning producer
  or ``ORPHAN``, so a human can inspect coverage without running the sweep.

The registry deliberately does NOT gate orphan files pre-merge: between a
retiring PR's merge and the next post-merge run the tree legitimately holds
outputs whose owner is gone, and the manual-edit gate stops the retiring PR
from deleting them itself. Coverage converges within one decision-tree run.
Registration is mandatory for new generators: an unregistered output is
deleted by the sweep, loudly, on the next post-merge run.

CLI::

    python3 scripts/verify_generated_docs_ownership.py verify [--root PATH]
    python3 scripts/verify_generated_docs_ownership.py list   [--root PATH]
    python3 scripts/verify_generated_docs_ownership.py retire [--root PATH]

Contract:
    Inputs: one subcommand plus an optional ``--root`` (defaults to the
        repository root); the scanned surface is every file under
        ``docs/generated/`` on the filesystem and the producer paths in
        :data:`OWNERSHIP`. No stdin, no env input, no network, no git.
    Outputs: ``verify`` prints ``::error::`` lines on stderr per registry
        inconsistency and exits 1, or prints one ``OK`` line and exits 0;
        ``list`` prints ``<path>\\t<producer|ORPHAN>`` per file on stdout,
        exit 0; ``retire`` prints one ``retired orphaned doc:`` line per
        deletion plus a summary, exit 0 (a clean tree is a successful no-op).
    Failure policy: fails loud per CLAUDE.md section 4; ``verify`` treats a
        missing producer as an error rather than silently skipping the entry,
        and ``retire`` never deletes a file matched by any registry pattern.

Tested by ``tests/test_verify_generated_docs_ownership.py``. Refs #2226,
#1540, #1771, #2013.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directory owned by the post-merge automation; the only tree the retire
# subcommand may ever delete from.
GENERATED_ROOT = PurePosixPath("docs/generated")


@dataclass(frozen=True)
class OwnedSurface:
    """One producer's claim on a ``docs/generated/`` path pattern.

    ``pattern`` is a glob relative to ``docs/generated/`` whose ``*`` does not
    cross ``/`` (matching is segment-wise); ``producer`` is the repo-relative
    script whose regeneration writes the matched files.
    """

    pattern: str
    producer: str


# Single source of truth: every artifact under docs/generated/ must be matched
# by exactly these claims. Adding a generator REQUIRES a new entry here in the
# same PR (an unregistered output is deleted by the post-merge sweep);
# retiring a generator REQUIRES dropping its entry in the same PR (``verify``
# fails on a registered producer that no longer exists), after which the sweep
# decommissions its outputs automatically. Refs #2226.
OWNERSHIP: tuple[OwnedSurface, ...] = (
    # One AST doc per scripts/*.py; the producer prunes inside ast/ itself
    # (#1540), this registry covers the surface as a whole.
    OwnedSurface(pattern="scripts/ast/*.md", producer="scripts/script_ast_graph.py"),
    OwnedSurface(pattern="scripts/dependency-graph.md", producer="scripts/script_dependency_graph.py"),
    OwnedSurface(pattern="scripts/trigger-map.md", producer="scripts/script_trigger_map.py"),
    # Written by the triage-report job (post-merge.yml) via its own bot branch
    # chore/refresh-auto-retro-triage-report; registered so the decision-tree
    # sweep never touches the sibling job's artifact.
    OwnedSurface(pattern="scripts/auto-retro-triage-report.md", producer="scripts/auto_retro.py"),
    # One if-branch diagram per workflow; the producer prunes inside
    # workflows/ itself on a full regeneration (#1771).
    OwnedSurface(pattern="workflows/*-if-branches.md", producer="scripts/workflow_diagram.py"),
    OwnedSurface(pattern="graph/doc-dependency-graph.md", producer="scripts/doc_graph_viz.py"),
)


def pattern_matches(pattern: str, rel_path: PurePosixPath) -> bool:
    """Segment-wise glob match where ``*`` never crosses a ``/`` boundary.

    ``fnmatch`` alone would let ``scripts/*.md`` claim ``scripts/ast/x.md``;
    per-segment matching keeps each claim anchored to its directory depth.
    """
    pattern_parts = PurePosixPath(pattern).parts
    path_parts = rel_path.parts
    if len(pattern_parts) != len(path_parts):
        return False
    return all(
        fnmatchcase(part, pattern_part)
        for part, pattern_part in zip(path_parts, pattern_parts, strict=True)
    )


def owner_for(rel_path: PurePosixPath) -> OwnedSurface | None:
    """Return the first registry claim matching ``rel_path``, or ``None``."""
    for surface in OWNERSHIP:
        if pattern_matches(surface.pattern, rel_path):
            return surface
    return None


def iter_generated_files(root: Path) -> Iterator[Path]:
    """Yield every file under ``<root>/docs/generated/`` in sorted order."""
    base = root / Path(GENERATED_ROOT)
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file():
            yield path


def registry_errors(root: Path) -> list[str]:
    """Pure check: registry entries must be well-formed with live producers."""
    errors: list[str] = []
    for surface in OWNERSHIP:
        pattern = PurePosixPath(surface.pattern)
        if pattern.is_absolute() or ".." in pattern.parts or not surface.pattern:
            errors.append(
                f"malformed OWNERSHIP pattern {surface.pattern!r}: patterns "
                f"must be relative to {GENERATED_ROOT}/ and contain no '..'"
            )
        if not (root / surface.producer).is_file():
            errors.append(
                f"OWNERSHIP producer {surface.producer!r} (pattern "
                f"{surface.pattern!r}) does not exist; a retired generator "
                "must drop its registry entry in the same change so the "
                "post-merge retire sweep decommissions its outputs"
            )
    return errors


def orphaned_files(root: Path) -> list[Path]:
    """Return generated files no registry pattern owns, in sorted order."""
    base = root / Path(GENERATED_ROOT)
    return [
        path
        for path in iter_generated_files(root)
        if owner_for(PurePosixPath(path.relative_to(base).as_posix())) is None
    ]


def retire_orphans(root: Path) -> list[Path]:
    """Delete orphaned generated files and prune emptied subdirectories.

    Never touches a file matched by a registry pattern, never leaves
    ``docs/generated/``, and keeps the root directory itself even when the
    sweep empties it. Returns the deleted paths in sorted order.
    """
    base = root / Path(GENERATED_ROOT)
    orphans = orphaned_files(root)
    for path in orphans:
        path.unlink()
    if base.is_dir():
        # Bottom-up so a directory emptied by its children's removal is seen
        # after them; sorting descending by path length gives that order.
        for directory in sorted(base.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
    return orphans


def _cmd_verify(args: argparse.Namespace) -> int:
    errors = registry_errors(Path(args.root))
    for error in errors:
        print(f"::error::{error}", file=sys.stderr)
    if errors:
        return 1
    print(f"OK: all {len(OWNERSHIP)} registered docs/generated/ producers exist.")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    root = Path(args.root)
    base = root / Path(GENERATED_ROOT)
    for path in iter_generated_files(root):
        rel = PurePosixPath(path.relative_to(base).as_posix())
        surface = owner_for(rel)
        owner = surface.producer if surface is not None else "ORPHAN"
        print(f"{GENERATED_ROOT / rel}\t{owner}")
    return 0


def _cmd_retire(args: argparse.Namespace) -> int:
    root = Path(args.root)
    retired = retire_orphans(root)
    for path in retired:
        print(f"retired orphaned doc: {path.relative_to(root)}")
    print(f"retired {len(retired)} orphaned file(s) under {GENERATED_ROOT}/.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_verify = subparsers.add_parser(
        "verify",
        help="Fail when a registered docs/generated/ producer no longer exists.",
    )
    p_verify.set_defaults(func=_cmd_verify)

    p_list = subparsers.add_parser(
        "list",
        help="Print every docs/generated/ file with its owning producer or ORPHAN.",
    )
    p_list.set_defaults(func=_cmd_list)

    p_retire = subparsers.add_parser(
        "retire",
        help="Delete docs/generated/ files no registered producer owns (post-merge lane).",
    )
    p_retire.set_defaults(func=_cmd_retire)

    for sub in (p_verify, p_list, p_retire):
        sub.add_argument("--root", default=str(REPO_ROOT), help="Repository root to operate on.")

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
