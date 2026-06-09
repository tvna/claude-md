#!/usr/bin/env python3
"""Deterministic gate: forbid hand edits to ``docs/generated/scripts/``.

Content under ``docs/generated/scripts/`` is owned by the post-merge
automation (refs #1540): the ``decision-tree`` job in
``.github/workflows/post-merge.yml`` regenerates the per-script AST docs after a
merge to ``main`` and opens the bot branch ``chore/update-generated-docs`` to
publish them. Neither the pre-push gate nor any pre-merge drift gate regenerates
or drift-checks that folder, so this gate is the inverse
control: a non-bot branch whose diff touches ``docs/generated/scripts/**`` is
rejected, keeping the folder a single-producer surface instead of a
hand-editable one.

The post-merge bot branch (``chore/update-generated-docs``) is exempt: it is the
legitimate producer, and its diff is exactly the regenerated content.

Architecture: pure functions on top (:func:`resolve_base`,
:func:`changed_generated_scripts`, :func:`evaluate`), a single subprocess
boundary at the bottom (:func:`_run`).

Contract:
- Inputs: the ``verify`` subcommand; optional ``--base-ref`` (falls back to the
  ``BASE_REF`` env var, then ``origin/$GITHUB_BASE_REF``, then ``origin/main``)
  and ``--branch`` (falls back to ``GITHUB_HEAD_REF``, then the current
  ``git`` branch).
- Outputs: a single ``OK``/``::error::`` line; exit 0 when no protected path is
  touched or the branch is the exempt bot branch, exit 1 when a non-exempt
  branch edits the protected folder.
- Failure policy: fails loud per CLAUDE.md section 4 -- a forbidden edit and a
  failed git invocation both exit non-zero rather than passing silently.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# Folder owned by the post-merge automation; hand edits are forbidden here.
PROTECTED_PREFIX = "docs/generated/scripts/"

# The post-merge bot branch that legitimately regenerates the folder. It is the
# fixed PR_BRANCH used by the post-merge ``decision-tree`` job.
EXEMPT_BRANCHES = frozenset({"chore/update-generated-docs"})


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


def changed_generated_scripts(
    base_ref: str, head: str = "HEAD", *, runner=subprocess.run
) -> frozenset[str]:
    """Return paths under :data:`PROTECTED_PREFIX` changed in ``{base}..{head}``.

    Uses ``git diff --name-only`` so renames and deletes also surface.
    """
    result = _run(
        ["git", "diff", "--name-only", f"{base_ref}..{head}"], runner=runner
    )
    touched = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return frozenset(path for path in touched if path.startswith(PROTECTED_PREFIX))


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
        f"::error::{PROTECTED_PREFIX} is owned by the post-merge automation "
        "(refs #1540) and must not be edited by hand. The following files "
        f"were changed on branch {branch or '(unknown)'!r}: {pretty}. Revert "
        "them; the post-merge `decision-tree` job regenerates per-script AST "
        "docs and opens the `chore/update-generated-docs` PR after merge."
    ]


def _cmd_verify(args: argparse.Namespace) -> int:
    base = args.base_ref or resolve_base()
    branch = resolve_branch(args.branch)
    try:
        changed = changed_generated_scripts(base)
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
            print(f"OK: no {PROTECTED_PREFIX} files modified.")
        return 0
    for line in errors:
        print(line, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Fail when a non-bot branch edits docs/generated/scripts/.",
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
    """Thin subprocess boundary -- the only impure surface in this module."""
    return runner(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
