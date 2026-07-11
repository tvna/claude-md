#!/usr/bin/env python3
"""Deterministic gate: forbid hand edits to post-merge-owned generated artifacts.

Content under ``docs/generated/`` (both ``scripts/`` and ``workflows/``) is
owned by the post-merge automation (refs #1540, #1545): the ``decision-tree``
job in ``.github/workflows/post-merge.yml`` regenerates the per-script AST docs
and the workflow if-branch diagrams after a merge to ``main`` and opens the bot
branch ``chore/update-generated-docs`` to publish them. The same job also writes
the ``.gitapex/snapshots/module-size-distribution.toml`` size snapshot, which joined
the single-producer model in #2013 and is published through that same bot PR.
Neither the pre-push gate nor any pre-merge drift gate regenerates or
drift-checks those paths, so this gate is the inverse control: a non-bot branch
whose diff touches ``docs/generated/scripts/**``, ``docs/generated/workflows/**``,
``docs/generated/graph/**``, or the size snapshot is rejected, keeping each a
single-producer surface instead of a hand-editable one. Refs #2013.

The post-merge bot branches (``chore/update-generated-docs`` for the AST docs
and diagrams, ``chore/refresh-auto-retro-triage-report`` for the triage-report
snapshot) are exempt: they are the legitimate producers, and their diffs are
exactly the regenerated content.

A byte-identical (100%-similarity) rename INTO one of the exact-file entries
of :data:`PROTECTED_PREFIXES` (currently only the module-size snapshot) from
a path that was not itself protected is also let through: it is a one-time
infrastructure relocation of the artifact's tracked path (e.g. #2342 moving
the module-size snapshot to ``.gitapex/``), not an edit of its content, so it
is not the drift class this gate exists to prevent. The exemption is scoped
to exact-file entries only, never to the folder-prefix entries
(``docs/generated/scripts/`` etc.): a folder prefix accepts any filename
underneath it, so exempting renames into it would let a hand-authored
``git mv docs/foo.md docs/generated/scripts/foo.md`` bypass the single-producer
gate entirely, which is not a relocation this gate should ever wave through.
Any content change during the move (git then reports it as a plain add, not a
rename), or a rename between two already-protected paths, still fails loud.

Architecture: pure functions on top (:func:`resolve_base`,
:func:`changed_generated_docs`, :func:`evaluate`), a single subprocess
boundary at the bottom (:func:`_run`).

Contract:
- Inputs: the ``verify`` subcommand; optional ``--base-ref`` (falls back to the
  ``BASE_REF`` env var, then ``origin/$GITHUB_BASE_REF``, then ``origin/main``)
  and ``--branch`` (falls back to ``GITHUB_HEAD_REF``, then the current
  ``git`` branch).
- Outputs: a single ``OK``/``::error::`` line; exit 0 when no protected path is
  touched or the branch is the exempt bot branch, exit 1 when a non-exempt
  branch edits a protected folder or the module-size snapshot.
- Failure policy: fails loud per CLAUDE.md section 4; a forbidden edit and a
  failed git invocation both exit non-zero rather than passing silently.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# Paths owned by the post-merge automation; hand edits are forbidden here.
# docs/generated/graph/ holds the Mermaid doc-dependency diagram produced by
# scripts/doc_graph_viz.py (wired into post-merge.yml). Refs #1754.
# The module-size snapshot is a single file, not a folder; it matches by exact
# path under the same ``startswith`` filter, joining the single-producer model
# the post-merge decision-tree job already owns. Refs #2013, #2342.
PROTECTED_PREFIXES = (
    "docs/generated/scripts/",
    "docs/generated/workflows/",
    "docs/generated/graph/",
    ".gitapex/snapshots/module-size-distribution.toml",
)

# The exact-file (non-folder-prefix) subset of PROTECTED_PREFIXES: entries
# that name one specific tracked path rather than a whole folder. Only these
# are eligible for the pure-rename-in exemption below (refs #2342, Codex
# review on PR #2347): a folder prefix accepts any filename placed under it,
# so exempting a rename INTO one would let an arbitrary hand-authored file
# bypass the single-producer gate, not just the one artifact this exemption
# exists to relocate.
_PROTECTED_EXACT_FILES = frozenset(p for p in PROTECTED_PREFIXES if not p.endswith("/"))

# The folder-prefix (non-exact-file) subset of PROTECTED_PREFIXES, for use with
# str.startswith(). Kept separate from _PROTECTED_EXACT_FILES so exact files are
# matched by equality (``in``), not by prefix: plain startswith() has no path
# boundary, so ``.gitapex/module-size-distribution.toml.bak`` would otherwise
# also satisfy startswith(".gitapex/module-size-distribution.toml") and be
# misclassified as a hand-edit of the protected snapshot.
_PROTECTED_FOLDER_PREFIXES = tuple(p for p in PROTECTED_PREFIXES if p.endswith("/"))


def _is_protected(path: str) -> bool:
    """Return True when *path* is a protected folder member or exact file."""
    return path.startswith(_PROTECTED_FOLDER_PREFIXES) or path in _PROTECTED_EXACT_FILES


# The post-merge bot branches that legitimately regenerate the folder, each a
# fixed PR_BRANCH used by a post-merge job:
# - chore/update-generated-docs: the ``decision-tree`` job (AST docs + diagrams).
# - chore/refresh-auto-retro-triage-report: the ``triage-report`` job, which
#   writes docs/generated/scripts/auto-retro-triage-report.md via
#   createCommitOnBranch (auto_retro._TRIAGE_REPORT_PR_BRANCH). Refs #1553.
# - chore/refresh-repair-free-merge-ledger: the ``open-retro`` job's ledger
#   recording, which writes docs/generated/scripts/repair-free-merge-ledger.md
#   via createCommitOnBranch (auto_retro._LEDGER_PR_BRANCH). Refs #2415.
EXEMPT_BRANCHES = frozenset(
    {
        "chore/update-generated-docs",
        "chore/refresh-auto-retro-triage-report",
        "chore/refresh-repair-free-merge-ledger",
    }
)


def resolve_base() -> str:
    """Return the base ref the gate diffs HEAD against.

    Resolution order: ``BASE_REF`` -> ``origin/$GITHUB_BASE_REF`` ->
    ``origin/main``. Empty environment values are treated as unset so a blank
    ``GITHUB_BASE_REF`` on push events does not silently win.
    """
    explicit = os.environ.get("BASE_REF")
    if explicit:
        return explicit
    actions_base = os.environ.get("GITHUB_BASE_REF")
    if actions_base:
        return f"origin/{actions_base}"
    return "origin/main"


def resolve_branch(explicit: str | None = None, *, runner=subprocess.run) -> str:
    """Return the branch under test.

    Resolution order: an explicit ``--branch`` value -> ``GITHUB_HEAD_REF``
    (the PR source branch on ``pull_request`` events) -> the current local
    branch (``git rev-parse --abbrev-ref HEAD``). Returns ``""`` when the
    branch cannot be determined; callers treat that as non-exempt.
    """
    if explicit:
        return explicit
    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if head_ref:
        return head_ref
    try:
        result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], runner=runner)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    return result.stdout.strip()


def changed_generated_docs(
    base_ref: str, head: str = "HEAD", *, runner=subprocess.run
) -> frozenset[str]:
    """Return paths under any :data:`PROTECTED_PREFIXES` the branch changed.

    Uses the three-dot ``{base_ref}...{head}`` (merge-base) diff so the gate
    reports only what the branch introduced relative to the common ancestor,
    not whatever the base accumulated after the branch was cut. The two-dot
    ``{base_ref}..{head}`` form compares the two tips directly, so once ``main``
    advances while the PR is open; e.g. a post-merge ``docs/generated``
    regeneration lands on ``main``; two-dot surfaces that base-only churn as
    if this branch had touched the folder, the false positive recorded in retro
    #1703 (repair 4). Three-dot is anchored at the merge-base, so base-only
    commits never appear; a genuine hand-edit on the branch still does.

    Uses ``git diff --name-status -M100%`` (not ``--name-only``) so a
    byte-identical rename is distinguishable from an add/modify/delete: at the
    ``100%`` similarity threshold, git reports a rename only when the content
    is unchanged, so a rename from a not-yet-protected path into one of
    :data:`_PROTECTED_EXACT_FILES` is excluded (a one-time relocation, refs
    #2342), while a rename with any content change falls back to a plain add
    at the new path and still surfaces here. A rename into a folder-prefix
    entry is never exempted, regardless of similarity (see module docstring).
    """
    result = _run(
        ["git", "diff", "--name-status", "-M100%", f"{base_ref}...{head}"],
        runner=runner,
    )
    touched: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) == 3:
            old_path, new_path = parts[1], parts[2]
            if not _is_protected(old_path) and new_path in _PROTECTED_EXACT_FILES:
                continue
            touched.update(p for p in (old_path, new_path) if _is_protected(p))
        elif len(parts) == 2:
            path = parts[1]
            if _is_protected(path):
                touched.add(path)
    return frozenset(touched)


def is_exempt(branch: str) -> bool:
    """Return True when *branch* is the post-merge bot branch."""
    return branch in EXEMPT_BRANCHES


def evaluate(changed: frozenset[str], branch: str) -> tuple[int, list[str]]:
    """Return ``(exit_code, error_lines)`` for the gate decision."""
    if not changed:
        return 0, []
    if is_exempt(branch):
        return 0, []
    pretty = ", ".join(sorted(changed))
    return 1, [
        "::error::Post-merge-owned generated artifacts (docs/generated/ and the "
        ".gitapex/snapshots/module-size-distribution.toml size snapshot; refs "
        "#1540, #1545, #2013) must not be edited by hand. The following files "
        f"were changed on branch {branch or '(unknown)'!r}: {pretty}. Revert "
        "them; the post-merge `decision-tree` job regenerates them and opens "
        "the `chore/update-generated-docs` PR after merge."
    ]


def _cmd_verify(args: argparse.Namespace) -> int:
    base = args.base_ref or resolve_base()
    branch = resolve_branch(args.branch)
    try:
        changed = changed_generated_docs(base)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as exc:
        print(
            "::error::gate_generated_scripts_manual_edit: git invocation failed "
            f"against base {base!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    code, errors = evaluate(changed, branch)
    if code == 0:
        if changed:
            pretty = ", ".join(sorted(changed))
            print(
                f"OK: exempt bot branch {branch!r} regenerated {pretty}."
            )
        else:
            print("OK: no docs/generated/ files modified.")
        return 0
    for line in errors:
        print(line, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Fail when a non-bot branch edits docs/generated/ (scripts/ or workflows/).",
    )
    p_verify.add_argument(
        "--base-ref",
        help=(
            "Base ref to diff HEAD against. Falls back to BASE_REF, then "
            "origin/$GITHUB_BASE_REF, then origin/main."
        ),
    )
    p_verify.add_argument(
        "--branch",
        help=(
            "Branch under test. Falls back to GITHUB_HEAD_REF, then the "
            "current git branch."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


def _run(cmd: list[str], *, runner=subprocess.run):
    """Thin subprocess boundary; the only impure surface in this module."""
    return runner(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
