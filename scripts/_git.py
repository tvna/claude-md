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

import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

# A git object name is the all-zeros sentinel in two places this matters: git's
# pre-push protocol reports it for the remote side of a new branch (and the local
# side of a deletion), and a remote-tracking ref that does not resolve is treated
# the same way by the unsigned-commit gates. Either 40-hex (sha-1) or 64-hex
# (sha-256) all-zeros. Refs #2138, #2162.
ALL_ZEROS_RE = re.compile(r"^0{40}(?:0{24})?$")

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


def is_all_zeros(oid: str) -> bool:
    """Return True when *oid* is git's all-zeros object-name sentinel.

    Matches both the sha-1 (40-hex) and sha-256 (64-hex) spellings, so a new
    branch's remote side or a deletion's local side is recognised regardless of
    the repository's object format.
    """
    return ALL_ZEROS_RE.match(oid) is not None


def resolve_remote_name(runner: Runner, remote: str | None) -> str | None:
    """Return a configured remote NAME for *remote*, or None when unscopable.

    git names the remote by its configured NAME for a named push but by a
    repository URL for a direct-URL push (``git push https://... ref``; the
    pre-push hook then receives the URL as its remote argument). A URL cannot
    scope ``git rev-list --remotes=<x>``: it matches no remote-tracking ref, so
    the new-branch scan below would exclude nothing and fall back to the entire
    history, falsely rejecting a valid new-branch push whose history carries any
    unsigned commit. When *remote* is already a configured remote name it is
    returned unchanged; when it is a URL matching a configured remote's URL the
    matching name is returned; otherwise None, so the caller scopes the exclusion
    to all remote-tracking refs rather than a bogus single-remote glob. A git
    error returns None (fail to the all-remotes scope). Refs #2162.
    """
    if not remote:
        return None
    try:
        result = runner(["remote", "-v"])
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    names: set[str] = set()
    url_to_name: dict[str, str] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        name, url = fields[0], fields[1]
        names.add(name)
        url_to_name.setdefault(url, name)
    if remote in names:
        return remote
    return url_to_name.get(remote)


def commits_to_push(
    runner: Runner, *, local_sha: str, remote_sha: str | None, remote: str | None
) -> list[str] | None:
    """Return the shas a push of *local_sha* would ship, or None when undeterminable.

    When *remote_sha* resolves to a real commit (the target ref already exists on
    the remote) the range is ``<remote_sha>..<local_sha>``. When *remote_sha* is
    None or git's all-zeros sentinel (a new branch) the range is every commit
    reachable from *local_sha* but not from the remote's refs. *remote* is
    resolved to a configured remote NAME by :func:`resolve_remote_name`: a name
    scopes to that TARGET remote (``--not --remotes=<name>``), which keeps a
    commit that exists on a different remote but is new to this push from being
    silently skipped; a URL or unresolvable value falls back to all
    remote-tracking refs (``--not --remotes``) rather than a bogus
    ``--remotes=<url>`` glob that would scan the whole history (the #2162 URL-push
    false-reject). None propagates :func:`rev_list`'s undeterminable signal so a
    caller can fail open. Shared by the unsigned-commit gates (#2138 Bash hook,
    #2162 pre-push step) so both compute a push range identically.
    Refs #2138, #2162.
    """
    if remote_sha is not None and is_all_zeros(remote_sha):
        remote_sha = None
    if remote_sha is not None:
        rev_args = [f"{remote_sha}..{local_sha}"]
    else:
        scoped = resolve_remote_name(runner, remote)
        if scoped:
            rev_args = [local_sha, "--not", f"--remotes={scoped}"]
        else:
            rev_args = [local_sha, "--not", "--remotes"]
    return rev_list(runner, rev_args)
