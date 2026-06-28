"""Shared git subprocess runner.

Many ``scripts/`` tools shell out to git with the same boilerplate: resolve the
git executable from ``PATH`` and then call ``subprocess.run([git, *args], ...)``
with captured text output. This module owns that once as :func:`run_git`,
replacing the direct ``subprocess.run`` git calls and the two ad-hoc per-file
wrappers (``preflight_branch_base.run_git`` and
``scan_area_path_coverage._run_git``).

No git command logic moves here: which subcommands run, how their output is
parsed, and how a non-zero exit is surfaced all stay in the callers. Only the
"find the git binary and run it with captured output" plumbing moves in, so
behaviour is unchanged; each caller keeps deciding whether to pass
``check=True``, how to read ``stdout``/``stderr``, and how to react to failure.

Refs #1005.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

# A runner takes a git argv (WITHOUT the leading ``git``) and returns the
# completed process, mirroring :func:`run_git`'s signature. Gates that shell out
# to git through an injectable seam (so tests can supply a canned git) type that
# seam as ``Runner``; :func:`make_runner` builds the production one.
Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def run_git(
    args: list[str],
    *,
    cwd: Path | str | None = None,
    check: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` with captured text output and return the result.

    Resolves the git executable from ``PATH`` (raising :class:`RuntimeError`
    when it is absent, matching the two wrappers this replaces), then runs it
    under *cwd* with ``capture_output=True`` and ``text=True``. The
    :class:`subprocess.CompletedProcess` is returned unchanged: callers decide
    how to read ``stdout``/``stderr`` and how to react to ``returncode``. Pass
    ``check=True`` to raise :class:`subprocess.CalledProcessError` on a non-zero
    exit, or ``timeout`` to bound the call.
    """
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable not found on PATH")
    return subprocess.run(  # noqa: S603 -- git argv is caller-built, never a shell string
        [git, *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def make_runner(*, cwd: Path | str | None = None, timeout: float | None = None) -> Runner:
    """Return a :data:`Runner` that runs ``git <args>`` under *cwd* with *timeout*.

    The production runner several gates build by hand (a closure binding
    :func:`run_git`'s ``cwd``/``timeout``); centralised here so the timeout/cwd
    policy lives in one place instead of one private copy per gate.
    """

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        return run_git(args, cwd=cwd, timeout=timeout)

    return runner


def rev_list(runner: Runner, args: list[str]) -> list[str] | None:
    """Return the shas ``git rev-list <args>`` prints, or None when undeterminable.

    Runs ``rev-list`` through *runner*, strips and drops blank lines, and returns
    the resulting shas. None signals "could not determine" (a subprocess error or
    a non-zero exit, e.g. an unresolvable ref) so a caller can fail open; an empty
    list means the range resolved with nothing to ship. Shared by the unsigned-
    commit gates so both compute a push range the same way.
    """
    try:
        result = runner(["rev-list", *args])
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
