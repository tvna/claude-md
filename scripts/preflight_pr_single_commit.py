#!/usr/bin/env python3
"""Deterministic gate: a PR carries exactly one commit ahead of its base.

Issue #492: 15 of 23 open retrospective issues record a
``multi-commit PR squash-collapsed`` repair signal because the repo
relies on the `squash` merge method to flatten whatever commit count
the PR happens to carry. The repair is silent, the source-branch
history is lost on merge, and the agent instructions never said
"open the PR with exactly one commit". This script makes the
single-commit contract deterministic.

Architecture mirrors :mod:`branch_cleanup`: pure functions on top,
one thin :func:`_run` subprocess boundary at the bottom that tests
monkeypatch via the ``runner`` kwarg. The shape stays consistent
with the rest of ``scripts/`` so a single review pass covers it.

Wiring:

* Pre-push: ``.pre-commit-config.yaml`` local hook with
  ``stages: [pre-push]``. Requires ``pre-commit install --hook-type
  pre-push`` once per checkout.
* CI: an extra step inside the ``gate`` job of
  ``.github/workflows/verify-github-content.yml``. The job's existing
  required-status-check context (``Verify GitHub content / gate``,
  pinned in ``.github/rulesets/main.json``) covers this step too --
  no ruleset change needed.

D1 (Issue #492 unresolved point, decided 2026-05-27): ``fixup!`` /
``squash!`` prefixed commits are rejected outright rather than
auto-squashed by the hook. The deterministic gate carries no side
effects on the working tree; the agent runs ``git commit --amend`` or
``git rebase -i --autosquash`` itself.

Exit codes:

* 0 -- ``git rev-list --no-merges {base}..HEAD --count`` returns 1.
* 1 -- count != 1, OR git invocation failed, OR base ref cannot be
  resolved. Fail-loud per CLAUDE.md section 4: every failure path
  prints a ``::error::`` line so CI annotations surface the cause.
"""

from __future__ import annotations

import os
import subprocess
import sys

_GIT_TIMEOUT_SECONDS: int = 15

# Subject-line prefixes that indicate the commit is a fixup/squash
# placeholder. ``git commit --fixup=<ref>`` writes ``fixup! <subject>``
# and ``--squash=<ref>`` writes ``squash! <subject>``. We surface a
# distinct hint when any such commit is present so the operator knows
# to run ``git rebase -i --autosquash`` rather than just amending.
_FIXUP_PREFIXES: tuple[str, ...] = ("fixup!", "squash!", "amend!")


def resolve_base() -> str:
    """Return the base ref the gate compares HEAD against.

    Resolution order:

    1. ``BASE_REF`` (explicit override the workflow / pre-commit hook
       can pass).
    2. ``GITHUB_BASE_REF`` (set by GitHub Actions on ``pull_request``
       events; bare branch name like ``main``, so we prefix
       ``origin/``).
    3. Hard-coded fallback ``origin/main`` for local invocations
       where no env var is set.

    Returning a string rather than raising keeps the boundary simple;
    a missing base manifests as ``git rev-list`` failure, which
    :func:`main` surfaces with the same ``::error::`` path.
    """
    explicit = os.environ.get("BASE_REF")
    if explicit:
        return explicit
    actions_base = os.environ.get("GITHUB_BASE_REF")
    if actions_base:
        return f"origin/{actions_base}"
    return "origin/main"


def count_commits(base: str, head: str = "HEAD", *, runner=subprocess.run) -> int:
    """Return the number of non-merge commits in ``{base}..{head}``.

    ``--no-merges`` excludes ``Merge branch 'main'`` style commits so
    transient rebase debt does not fire the gate. This mirrors
    ``scripts/auto_retro.py``'s ``_count_merge_from_main`` policy:
    merge-from-main commits are a structural artifact of the
    squash-only + linear-history ruleset, not repair history.
    """
    result = _run(["git", "rev-list", "--no-merges", f"{base}..{head}", "--count"], runner=runner)
    raw = result.stdout.strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"git rev-list returned non-integer count: {raw!r}") from exc


def list_subjects(base: str, head: str = "HEAD", *, runner=subprocess.run) -> list[str]:
    """Return the subject line of each non-merge commit in ``{base}..{head}``.

    Used to render the deny message so the operator can see what the
    branch actually carries without running ``git log`` themselves.
    """
    result = _run(
        ["git", "log", "--no-merges", "--format=%h %s", f"{base}..{head}"],
        runner=runner,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def has_fixup_commits(subjects: list[str]) -> bool:
    """Return True when any subject starts with a fixup/squash prefix."""
    for line in subjects:
        # Subject format from ``--format=%h %s`` is ``<sha> <subject>``;
        # split once on whitespace to isolate the subject head.
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        subject = parts[1].lstrip()
        if any(subject.startswith(prefix) for prefix in _FIXUP_PREFIXES):
            return True
    return False


def format_failure(count: int, base: str, subjects: list[str], *, fixup_present: bool) -> str:
    """Return the multi-line ``::error::`` block printed on rejection.

    Shape:

    * First line is the canonical ``::error::PR has N commits, expected
      1`` annotation so GitHub surfaces it on the CI step summary. The
      Issue #492 acceptance criterion pins this wording.
    * Optional second annotation flags fixup/squash prefixes so the
      operator picks ``--autosquash`` over a plain amend.
    * Following lines list each commit subject so the operator does
      not need to run ``git log`` to see what to squash.
    * Closing line points at the remediation command (amend vs
      autosquash) and the documenting issue.
    """
    lines = [f"::error::PR has {count} commits, expected 1 (base: {base})"]
    if fixup_present:
        lines.append(
            "::error::fixup!/squash!/amend! commit detected; "
            "run `git rebase -i --autosquash` to collapse before push."
        )
    if subjects:
        lines.append("Commits ahead of base:")
        lines.extend(f"  - {subject}" for subject in subjects)
    remediation = (
        f"git rebase -i --autosquash {base}" if fixup_present else f"git rebase -i {base}"
    )
    lines.append(f"Squash to one commit before push: `{remediation}`.")
    lines.append("See Issue #492 for the single-commit contract.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry. No arguments accepted; configuration is via env vars."""
    del argv  # configuration is env-driven; argparse would over-engineer this
    base = resolve_base()

    try:
        subjects = list_subjects(base)
        count = count_commits(base)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
        # Fail loudly per CLAUDE.md section 4 -- the gate failing closed is
        # the right call: a silent skip would let multi-commit PRs through.
        print(
            f"::error::preflight_pr_single_commit: git invocation failed against base "
            f"{base!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    fixup_present = has_fixup_commits(subjects)
    if count == 1 and not fixup_present:
        print(f"OK: 1 commit ahead of {base}")
        return 0

    print(
        format_failure(count, base, subjects, fixup_present=fixup_present),
        file=sys.stderr,
    )
    return 1


def _run(cmd: list[str], *, runner=subprocess.run):
    """Thin subprocess boundary -- the only impure surface in this module.

    ``check=True`` raises ``CalledProcessError`` on non-zero exit; the
    caller in :func:`main` translates that into the fail-loud
    ``::error::`` path. Tests monkeypatch ``runner`` to inject fake
    completed-process objects.
    """
    return runner(
        cmd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
