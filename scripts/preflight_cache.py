#!/usr/bin/env python3
"""Content-addressed skip cache for preflight's heavy (pytest) step.

Refs #985. The pre-push gate runs the full pytest suite (~290s) on every push
via ``scripts/preflight_all.py``. Issue #985 records the dominant real-world
waste: a single PR cycle re-runs the whole suite 2-3 times (rebase, stale
``--force-with-lease``, new-branch push) against a byte-identical working tree.
PR #983 alone burned ~14.5 minutes this way, none of it exercising a source
change after the first green run.

This module preserves *strict* coverage parity with CI -- the same full suite
runs, never a subset -- while skipping a re-run only when the inputs that can
affect the suite outcome are byte-for-byte unchanged since the last recorded
green run. The fingerprint covers the working-tree contents (not the index) of
the test-relevant path set (``scripts/``, ``tests/``, ``pyproject.toml``,
``uv.lock``) plus an opaque ``extra`` token list (the pytest argv). Any edit,
dependency bump, or command change busts the cache and forces a full run, so a
stale skip is impossible short of a SHA-256 collision.

The cache lives at ``<git-dir>/preflight_heavy_cache.json`` -- per-clone,
untracked, and naturally absent on a fresh clone, so the first run in any
checkout is always a full run. Export ``PREFLIGHT_NO_CACHE=1`` to force a full
run and refresh the fingerprint regardless of cache state.

Exit codes (CLI ``status``):
* ``0`` -- always; ``status`` is read-only and never gates a push on its own.

Tested by ``tests/test_preflight_cache.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Tracked path globs whose working-tree contents determine the pytest outcome.
# Kept deliberately narrow: a docs-only change cannot change a script test, so
# excluding docs/ avoids needless cache busts while staying provably sufficient
# (the suite imports only from ``scripts/`` and reads only these config files).
INPUT_PATHSPECS: tuple[str, ...] = (
    "scripts",
    "tests",
    "pyproject.toml",
    "uv.lock",
)

_ENV_DISABLE = "PREFLIGHT_NO_CACHE"
_CACHE_BASENAME = "preflight_heavy_cache.json"


def _git_dir(repo_root: Path) -> Path:
    """Return the resolved ``.git`` directory for *repo_root*.

    Uses ``git rev-parse --git-dir`` so worktrees (where ``.git`` is a file
    pointing elsewhere) and submodules resolve correctly. The path is made
    absolute against *repo_root* when git returns a relative answer.
    """
    out = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ["git", "rev-parse", "--git-dir"],  # noqa: S607 -- git resolved from PATH, repo convention
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    git_dir = Path(out)
    if not git_dir.is_absolute():
        git_dir = (repo_root / git_dir).resolve()
    return git_dir


def cache_path(repo_root: Path = REPO_ROOT) -> Path:
    """Return the absolute path to the per-clone cache file."""
    return _git_dir(repo_root) / _CACHE_BASENAME


def _tracked_input_files(repo_root: Path) -> list[Path]:
    """Return tracked files under :data:`INPUT_PATHSPECS`, sorted by path.

    Uses ``git ls-files`` so untracked scratch files never enter the
    fingerprint (they cannot affect a committed test run) and the set is
    deterministic across machines.
    """
    out = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ["git", "ls-files", "-z", "--", *INPUT_PATHSPECS],  # noqa: S607 -- git resolved from PATH, repo convention
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rels = [chunk for chunk in out.split("\0") if chunk]
    files = [repo_root / rel for rel in rels]
    # ``git ls-files`` can list a path whose blob was removed from the working
    # tree (e.g. mid-rebase); skip non-files so hashing never raises.
    return sorted((p for p in files if p.is_file()), key=lambda p: p.as_posix())


def compute_fingerprint(
    repo_root: Path = REPO_ROOT,
    *,
    extra: Sequence[str] = (),
) -> str:
    """Return a SHA-256 hex digest over the test-relevant working-tree state.

    The digest folds in, in a fixed order:

    * each tracked input file's repo-relative POSIX path and the SHA-256 of its
      on-disk bytes (working-tree state, so uncommitted edits bust the cache);
    * each token in *extra* (the pytest argv), so changing the command -- e.g.
      adding ``-n auto`` -- forces a fresh run rather than reusing a digest
      recorded under the old command.

    Raises ``subprocess.CalledProcessError`` / ``OSError`` when git or a file is
    unavailable; callers treat that as "no cache" and run the full suite.
    """
    digest = hashlib.sha256()
    for path in _tracked_input_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    digest.update(b"\0extra\0")
    for token in extra:
        digest.update(token.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def load(path: Path) -> dict[str, object] | None:
    """Return the parsed cache record, or ``None`` when absent / unreadable.

    A malformed or unreadable cache is treated as a miss (return ``None``)
    rather than an error: the worst case is one extra full run, never a stale
    skip.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def is_fresh(cache: dict[str, object] | None, fingerprint: str) -> bool:
    """Return ``True`` only when *cache* records a passing run at *fingerprint*.

    Both the fingerprint match and the ``status == "pass"`` marker are
    required, so a cache written for a failed/aborted run never authorises a
    skip.
    """
    if cache is None:
        return False
    return cache.get("fingerprint") == fingerprint and cache.get("status") == "pass"


def record(path: Path, fingerprint: str) -> None:
    """Persist a passing-run record for *fingerprint* to *path*.

    Best-effort: a write failure is swallowed (the next run simply recomputes
    and re-runs the suite). The directory is the git dir, which always exists.
    """
    payload = {
        "fingerprint": fingerprint,
        "status": "pass",
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"::warning::preflight_cache: could not write cache: {exc}", file=sys.stderr)


def cache_disabled(environ: dict[str, str]) -> bool:
    """Return ``True`` when ``PREFLIGHT_NO_CACHE=1`` forces a full run."""
    return environ.get(_ENV_DISABLE, "0") == "1"


def _format_status(cache: dict[str, object] | None, fingerprint: str) -> str:
    if cache is None:
        return "miss: no cache recorded yet (first run is always a full run)"
    if is_fresh(cache, fingerprint):
        ts = cache.get("recorded_at", "?")
        return f"fresh: tree unchanged since last green run at {ts}"
    return "stale: tracked test inputs changed since the last green run"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the preflight heavy-step skip cache (read-only).",
    )
    parser.add_argument(
        "command",
        choices=("status",),
        help="status: print whether the current tree matches the last green run.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "status":
        try:
            fingerprint = compute_fingerprint()
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"unavailable: {exc}")
            return 0
        cache = load(cache_path())
        print(_format_status(cache, fingerprint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
