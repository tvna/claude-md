#!/usr/bin/env python3
"""Deterministic gate: forbid hand edits to post-merge-owned generated artifacts.

Content under ``docs/generated/`` (both ``scripts/`` and ``workflows/``) is
owned by the post-merge automation (refs #1540, #1545): the ``decision-tree``
job in ``.github/workflows/post-merge.yml`` regenerates the per-script AST docs
and the workflow if-branch diagrams after a merge to ``main`` and opens the bot
branch ``chore/update-generated-docs`` to publish them. The same job also writes
the ``.gitapex/module-size-distribution.toml`` size snapshot, which joined
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
    ".gitapex/module-size-distribution.toml",
)

# The post-merge bot branches that legitimately regenerate the folder, each a
# fixed PR_BRANCH used by a post-merge job:
# - chore/update-generated-docs: the ``decision-tree`` job (AST docs + diagrams).
# - chore/refresh-auto-retro-triage-report: the ``triage-report`` job, which
#   writes docs/generated/scripts/auto-retro-triage-report.md via
#   createCommitOnBranch (auto_retro._TRIAGE_REPORT_PR_BRANCH). Refs #1553.
EXEMPT_BRANCHES = frozenset(
    {"chore/update-generated-docs", "chore/refresh-auto-retro-triage-report"}
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

    Uses ``git diff --name-only`` so renames and deletes also surface.
    """
    result = _run(
        ["git", "diff", "--name-only", f"{base_ref}...{head}"], runner=runner
    )
    touched = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return frozenset(path for path in touched if path.startswith(PROTECTED_PREFIXES))


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
        ".gitapex/module-size-distribution.toml size snapshot; refs "
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
