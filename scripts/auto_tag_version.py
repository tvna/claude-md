#!/usr/bin/env python3
"""Post-merge auto-tag: push a ``v{version}`` tag when apm.yml version changes.

Issue #89; design record ``docs/prd/semantic-versioning-universal-text.md``
(requirement R5). After a merge to the default branch, this reads
``apm.yml: version`` at the merge commit and at its first parent. If the
version changed, it creates and pushes a lightweight tag ``v{version}`` (for
example ``v1.1.0``). Because the R4 drift gate
(``scripts/verify_source_version_bump.py``) guarantees the version changes
only when the universal text changes, the tag is created only on a
universal-text update - satisfying "assign a tag automatically only when the
universal text is updated". The new tag triggers the existing
``publish-instructions-release.yml`` release flow (migrated to the ``v*``
trigger).

Idempotency: an existing tag is a no-op. The tag is never moved, never
force-pushed, never overwritten - a re-run or a re-merge that lands the same
version simply finds the tag present and exits 0.

Architecture mirrors ``scripts/verify_source_version_bump.py``: pure decision
functions on top, one thin :func:`_run` subprocess boundary at the bottom that
tests monkeypatch via the ``runner`` kwarg. Version parsing is single-sourced
from :mod:`verify_source_version_bump`.

Contract:
    Inputs: the ``run`` subcommand; ``--merge-sha`` (falls back to the
        ``MERGE_SHA`` env var, then ``HEAD``); ``--remote`` (default
        ``origin``); ``--dry-run`` (decide and print, push nothing). No stdin.
    Outputs: a human-readable line on stdout describing the action (tag
        created, tag already present, or no version change); exit 0 on
        success or a clean no-op, exit 1 on a git failure.
    Failure policy: fails loud per CLAUDE.md section 4 (a git error reading
        the versions or pushing the tag exits non-zero with an ``::error::``).

Tested by ``tests/test_auto_tag_version.py`` per
``docs/standards/workflow-script-quality.md``. Refs #89.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from verify_source_version_bump import Version, format_version, parse_version

_GIT_TIMEOUT_SECONDS: int = 15
_APM_FILE = "apm.yml"


def tag_name(version: Version) -> str:
    """Return the release tag for a parsed version, for example ``v1.1.0``."""
    return f"v{format_version(version)}"


def tag_for_change(base_version: Version, head_version: Version) -> str | None:
    """Return the tag to create, or ``None`` when the version is unchanged.

    R5 tags on any version change. The R4 PR gate has already guaranteed the
    change is a clean single-component bump tied to a universal-text edit, so
    this function only decides "did the version move?" and names the tag for
    the head version.
    """
    if head_version == base_version:
        return None
    return tag_name(head_version)


def read_version_at(ref: str, *, runner=subprocess.run) -> Version:
    """Return the parsed apm.yml version at *ref* via ``git show``."""
    result = _run(["git", "show", f"{ref}:{_APM_FILE}"], runner=runner)
    return parse_version(result.stdout)


def tag_exists(tag: str, *, runner=subprocess.run) -> bool:
    """Return True when *tag* already exists locally."""
    result = _run(["git", "tag", "--list", tag], runner=runner)
    return any(line.strip() == tag for line in result.stdout.splitlines())


def create_and_push_tag(
    tag: str, sha: str, remote: str, *, runner=subprocess.run
) -> None:
    """Create a lightweight tag at *sha* and push it to *remote*.

    Lightweight (no ``-a``) so no tagger identity is required in the runner.
    The caller guarantees the tag does not already exist (idempotency is
    enforced in :func:`_cmd_run`), so this never force-pushes or moves a tag.
    """
    _run(["git", "tag", tag, sha], runner=runner)
    _run(["git", "push", remote, tag], runner=runner)


def _resolve_merge_sha(args: argparse.Namespace) -> str:
    if args.merge_sha:
        return args.merge_sha
    return os.environ.get("MERGE_SHA") or "HEAD"


def _cmd_run(args: argparse.Namespace) -> int:
    sha = _resolve_merge_sha(args)
    remote = args.remote
    try:
        head_version = read_version_at(sha)
        base_version = read_version_at(f"{sha}^")
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(
            "::error::auto_tag_version: could not read apm.yml version at "
            f"{sha} or its first parent: {exc}",
            file=sys.stderr,
        )
        return 1

    tag = tag_for_change(base_version, head_version)
    if tag is None:
        print(
            "OK: apm.yml version unchanged "
            f"({format_version(head_version)}); no tag created."
        )
        return 0

    try:
        if tag_exists(tag):
            print(f"OK: tag {tag} already exists; nothing to do (idempotent).")
            return 0
        if args.dry_run:
            print(f"DRY-RUN: would create and push tag {tag} at {sha}.")
            return 0
        create_and_push_tag(tag, sha, remote)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        RuntimeError,
    ) as exc:
        print(
            f"::error::auto_tag_version: failed to create or push tag {tag}: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: created and pushed tag {tag} "
        f"({format_version(base_version)} -> {format_version(head_version)})."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser(
        "run",
        help=(
            "Tag v{version} when apm.yml version changed across the merge "
            "commit and its first parent; idempotent."
        ),
    )
    p_run.add_argument(
        "--merge-sha",
        help=(
            "Merge commit to inspect. Falls back to the MERGE_SHA env var, "
            "then HEAD."
        ),
    )
    p_run.add_argument(
        "--remote",
        default="origin",
        help="Remote to push the tag to (default origin).",
    )
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Decide and print the action without creating or pushing a tag.",
    )
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


def _run(cmd: list[str], *, runner=subprocess.run):
    """Thin subprocess boundary; the only impure surface in this module.

    ``check=True`` raises ``CalledProcessError`` on non-zero exit; the
    caller translates that into the fail-loud ``::error::`` path. Tests
    monkeypatch ``runner`` to inject fake completed-process objects.
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
