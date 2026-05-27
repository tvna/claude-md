#!/usr/bin/env python3
"""Deterministic gate: a PR carries no merge-from-main commits.

Issue #491: 22 of 23 open retrospective issues record a
``merge from main`` repair signal because branches behind ``main``
are brought back in sync via ``git merge`` rather than ``git rebase``.
The squash merge method on the protected branch ultimately absorbs
the merge commit, so the ruleset never trips, but the PR diff and
review history carry noise that pollutes auto-retro and inflates the
repair-history table tracked by ``scripts/auto_retro.py``.

Architecture mirrors :mod:`preflight_pr_single_commit`: pure functions
on top, one thin :func:`_run` subprocess boundary at the bottom that
tests monkeypatch via the ``runner`` kwarg. The two preflights are
complementary -- ``preflight_pr_single_commit`` uses
``git rev-list --no-merges`` and therefore lets merge commits through;
this script catches what that one allows.

Detection rules (both fire the gate):

1. Subject prefix match against :data:`_MERGE_FROM_MAIN_PREFIXES`,
   kept in lockstep with ``scripts/auto_retro.py``'s
   ``_MERGE_FROM_MAIN_PREFIXES`` so the detector and the retro
   reporter agree on what counts as a merge-from-main commit.
2. Parent count > 1 (any merge commit), which catches merge subjects
   we did not anticipate (e.g. ``Merge pull request ...`` or a
   non-default remote name).

Wiring:

* Pre-push: ``.pre-commit-config.yaml`` local hook with
  ``stages: [pre-push]``. Requires ``pre-commit install --hook-type
  pre-push`` once per checkout.
* CI: an extra step inside the ``gate`` job of
  ``.github/workflows/verify-github-content.yml``. The job's existing
  required-status-check context (``Verify GitHub content / gate``,
  pinned in ``.github/rulesets/main.json``) covers this step too --
  no ruleset change needed.

Recovery when the gate fires on an existing PR is documented in
``docs/runbooks/rebase-debt-recovery.md``; :func:`format_failure`
points operators at that runbook.

Exit codes:

* 0 -- no merge commits in ``{base}..HEAD``.
* 1 -- one or more merge commits detected, OR git invocation failed.
  Fail-loud per CLAUDE.md section 4: every failure path prints a
  ``::error::`` line so CI annotations surface the cause.
"""

from __future__ import annotations

import os
import subprocess
import sys

_GIT_TIMEOUT_SECONDS: int = 15

# Subject-line prefixes that identify a ``git merge`` of main into the
# feature branch. Kept in lockstep with
# ``scripts/auto_retro.py:_MERGE_FROM_MAIN_PREFIXES`` so the detector
# and the retro reporter agree on what counts as a merge-from-main
# commit. If you extend one, extend the other in the same PR.
_MERGE_FROM_MAIN_PREFIXES: tuple[str, ...] = (
    "Merge branch 'main'",
    "Merge remote-tracking branch 'origin/main'",
    "Merge branch 'master'",
    "Merge remote-tracking branch 'origin/master'",
)

# Runbook path referenced from the failure annotation so operators
# can find the canonical recovery procedure (rebase + force-with-lease)
# without scrolling through the PR template.
_RECOVERY_RUNBOOK: str = "docs/runbooks/rebase-debt-recovery.md"


def resolve_base() -> str:
    """Return the base ref the gate compares HEAD against.

    Resolution order matches :mod:`preflight_pr_single_commit` so the
    two preflights agree on the base under every invocation context
    (pre-push hook, GitHub Actions pull_request event, local manual
    run):

    1. ``BASE_REF`` (explicit override).
    2. ``GITHUB_BASE_REF`` (set by GitHub Actions on ``pull_request``
       events; bare branch name like ``main``, so we prefix
       ``origin/``).
    3. Hard-coded fallback ``origin/main`` for local invocations.
    """
    explicit = os.environ.get("BASE_REF")
    if explicit:
        return explicit
    actions_base = os.environ.get("GITHUB_BASE_REF")
    if actions_base:
        return f"origin/{actions_base}"
    return "origin/main"


def resolve_head() -> str:
    """Return the head ref the gate walks back from.

    On ``pull_request`` events GitHub Actions checks out ``refs/pull/
    <N>/merge`` -- a synthetic merge of the PR head into the base.
    Walking ``{base}..HEAD`` from that ref always finds the synthetic
    merge commit, which would false-positive this gate. The workflow
    passes the actual PR head SHA via ``HEAD_REF`` so the comparison
    sees only commits the author authored.

    Locally and in the pre-push hook ``HEAD_REF`` is unset, so the
    function returns ``HEAD`` which is the branch tip the contributor
    is about to push -- the desired comparison endpoint.
    """
    explicit = os.environ.get("HEAD_REF")
    if explicit:
        return explicit
    return "HEAD"


def find_merge_commits(base: str, head: str = "HEAD", *, runner=subprocess.run) -> list[tuple[str, str]]:
    """Return ``[(sha, subject), ...]`` for every merge commit in ``{base}..{head}``.

    ``--merges`` selects only commits with parent count > 1, which is
    the structural definition of a merge commit. The subject is then
    inspected to provide a useful annotation in the failure message,
    but the structural rule (parent count > 1) is what fires the gate;
    a merge commit with an unrecognized subject still counts.

    ``--format=%H %s`` gives ``<full-sha> <subject>``. Full SHA (rather
    than abbreviated) keeps the annotation copy-paste friendly for the
    operator running ``git rebase -i``.
    """
    result = _run(
        ["git", "log", "--merges", "--format=%H %s", f"{base}..{head}"],
        runner=runner,
    )
    commits: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 1)
        sha = parts[0]
        subject = parts[1] if len(parts) > 1 else ""
        commits.append((sha, subject))
    return commits


def subject_matches_merge_from_main(subject: str) -> bool:
    """Return True when *subject* starts with a known merge-from-main prefix.

    Surfaced as a separate predicate so the failure annotation can
    distinguish "known merge-from-main pattern" from "unknown merge
    commit" -- both fire the gate, but the operator hint differs.
    """
    stripped = subject.lstrip()
    return any(stripped.startswith(prefix) for prefix in _MERGE_FROM_MAIN_PREFIXES)


def format_failure(commits: list[tuple[str, str]], base: str) -> str:
    """Return the multi-line ``::error::`` block printed on rejection.

    Shape:

    * First line is the canonical ``::error::PR has N merge commit(s),
      expected 0`` annotation so GitHub surfaces it on the CI step
      summary. The Issue #491 verification example pins this wording.
    * Following lines list each offending commit (full sha + subject)
      so the operator does not need to run ``git log`` to know what
      to drop in the interactive rebase.
    * Closing lines point at the canonical recovery procedure (rebase
      + force-with-lease) documented in
      ``docs/runbooks/rebase-debt-recovery.md`` and reference the
      tracking issue.
    """
    count = len(commits)
    noun = "commit" if count == 1 else "commits"
    lines = [f"::error::PR has {count} merge {noun}, expected 0 (base: {base})"]
    if commits:
        lines.append("Merge commits ahead of base:")
        for sha, subject in commits:
            tag = "[merge-from-main]" if subject_matches_merge_from_main(subject) else "[merge]"
            lines.append(f"  - {sha} {tag} {subject}")
    lines.append(f"Recovery: rebase onto {base} and force-with-lease. " f"See {_RECOVERY_RUNBOOK}.")
    lines.append("See Issue #491 for the no-merge-commits contract.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry. No arguments accepted; configuration is via env vars."""
    del argv  # configuration is env-driven; argparse would over-engineer this
    base = resolve_base()
    head = resolve_head()

    try:
        commits = find_merge_commits(base, head)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        # Fail loudly per CLAUDE.md section 4 -- the gate failing closed
        # is the right call: a silent skip would let merge commits through.
        print(
            f"::error::preflight_pr_no_merge_commits: git invocation failed against base " f"{base!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    if not commits:
        print(f"OK: 0 merge commits ahead of {base}")
        return 0

    print(format_failure(commits, base), file=sys.stderr)
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
