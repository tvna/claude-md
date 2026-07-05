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

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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


# The pre-push ref lines and remote name, bridged from ``.githooks/pre-push``
# through the environment (a preflight ``verify`` step is dispatched with a
# fixed argv and no stdin routed to it, so the refs travel through the
# environment instead). ``PREFLIGHT_PUSH_REFS`` carries git's pre-push stdin
# verbatim (one line per updated ref: ``<local-ref> <local-oid> <remote-ref>
# <remote-oid>``); ``PREFLIGHT_PUSH_REMOTE`` carries the remote name git passes
# the hook as its first argument, needed to scope a new-branch range to that
# remote. Shared by every pre-push gate that must inspect the commits actually
# being pushed rather than a fixed ``origin/main..HEAD`` range (#2162, #2307).
_PUSH_REFS_ENV_VAR = "PREFLIGHT_PUSH_REFS"
_PUSH_REMOTE_ENV_VAR = "PREFLIGHT_PUSH_REMOTE"
_DEFAULT_REMOTE = "origin"


@dataclass(frozen=True)
class PushRef:
    """One updated ref from git's pre-push stdin (four space-separated fields)."""

    local_ref: str
    local_oid: str
    remote_ref: str
    remote_oid: str


def parse_push_refs(value: str) -> list[PushRef]:
    """Return the :class:`PushRef` rows parsed from a pre-push stdin payload.

    Git feeds the pre-push hook one line per updated ref, each ``<local-ref>
    <local-oid> <remote-ref> <remote-oid>``. A blank line or any line that does
    not split into exactly four fields is skipped (it cannot be a ref update), so
    a malformed or empty payload yields an empty list and the caller falls back
    to a fixed base-ref range.
    """
    refs: list[PushRef] = []
    for line in value.splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        refs.append(PushRef(*fields))
    return refs


def read_push_refs(env: Mapping[str, str] | None = None) -> tuple[list[PushRef], str]:
    """Return the parsed pushed refs and the remote name from the environment.

    Reads ``PREFLIGHT_PUSH_REFS`` / ``PREFLIGHT_PUSH_REMOTE`` (set by
    ``.githooks/pre-push``). The remote defaults to ``origin`` when unset, so a
    new-branch range can still be scoped. An empty/absent refs payload yields an
    empty list, the signal for a caller's fixed-range fallback.
    """
    source = os.environ if env is None else env
    refs = parse_push_refs(source.get(_PUSH_REFS_ENV_VAR, ""))
    remote = source.get(_PUSH_REMOTE_ENV_VAR, "") or _DEFAULT_REMOTE
    return refs, remote


def commits_in_range(runner: Runner, base_ref: str) -> list[str] | None:
    """Return the shas in ``<base_ref>..HEAD``, or None when undeterminable.

    Delegates to :func:`rev_list`: None signals the range could not be
    resolved (the base ref is missing, or a git error occurred) so a caller
    can fail open; an empty list means the range resolved with nothing to
    inspect (HEAD already contains the base). Shared by every pre-push gate
    that falls back to a fixed base-ref range when no pushed-ref payload is
    present (``preflight_coauthor_trailer.py``, ``preflight_signed_commits.py``).
    """
    return rev_list(runner, [f"{base_ref}..HEAD"])


def commits_for_pushed_refs(
    runner: Runner, refs: list[PushRef], remote: str
) -> tuple[list[str], bool]:
    """Return the deduplicated shas every pushed *refs* entry would ship.

    For each ref the range is computed by :func:`commits_to_push`
    (``remote-oid..local-oid`` for an existing branch, or the new-branch scan
    when ``remote-oid`` is the all-zeros sentinel); a delete refspec
    (``local-oid`` all-zeros) ships nothing and is skipped. Commits shared
    across refs are returned once, in first-seen order. The second element is
    True when at least one ref's range could not be resolved (fail-open for
    that ref, matching the #2138 union model); a caller treats an empty result
    with this flag set as "undeterminable" (skip), and an empty result with the
    flag clear as "nothing to inspect" (pass). Shared by every pre-push gate
    that inspects the commits actually being pushed (#2162, #2307).
    """
    seen: set[str] = set()
    commits: list[str] = []
    undeterminable = False
    for ref in refs:
        if is_all_zeros(ref.local_oid):
            continue  # deletion: ships no commit
        remote_oid = None if is_all_zeros(ref.remote_oid) else ref.remote_oid
        shas = commits_to_push(runner, local_sha=ref.local_oid, remote_sha=remote_oid, remote=remote)
        if shas is None:
            undeterminable = True
            continue
        for sha in shas:
            if sha not in seen:
                seen.add(sha)
                commits.append(sha)
    return commits, undeterminable
