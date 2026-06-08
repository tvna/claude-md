#!/usr/bin/env python3
"""Prune old GHCR devcontainer agent image versions.

The ``Publish devcontainer images`` workflow pushes a new commit-SHA-tagged
version of each ``ghcr.io/<owner>/claude-md-devcontainer-<agent>`` package on
every ``main`` change to a devcontainer image input, plus per-arch
``<sha>-amd64`` / ``<sha>-arm64`` tags. Those versions accumulate without
bound. ``monthly-maintenance.yml`` invokes this script to delete the old ones
on a monthly cadence (issue #1400, child of #696).

Retention policy (count + age). For each package, a version is **protected**
-- never deleted -- when any of its tags is:

* ``main`` (the moving convenience alias),
* a ``buildcache-*`` BuildKit cache tag, or
* the currently pinned SHA (read from
  ``.devcontainer/<agent>/devcontainer.json``) or its ``-amd64`` / ``-arm64``
  variant.

Among the remaining tagged versions, the newest ``--keep-recent`` are kept
unconditionally; of the rest, only versions older than ``--min-age-days`` are
deleted. Untagged versions are skipped entirely: they may be the child
manifests of a retained multi-platform manifest list, and deleting one would
break a tag we keep.

Deletion of a user-owned container package version is not possible with the
Actions ``GITHUB_TOKEN`` (there is no ``packages: delete`` permission and the
token is an app installation token, so the delete endpoint returns 403). The
caller must supply a PAT with ``read:packages`` + ``delete:packages`` via
``GH_TOKEN``; see ``docs/runbooks/devcontainers.md``.

Usage::

    python3 scripts/prune_devcontainer_images.py prune \\
        --owner OWNER \\
        --package PACKAGE [--package PACKAGE ...] \\
        --pinned-sha-from PATH [--pinned-sha-from PATH ...] \\
        --keep-recent N --min-age-days DAYS \\
        --dry-run true|false [--summary-file PATH]

Environment variables:
    GH_TOKEN  PAT with read:packages + delete:packages on the container.

Exit codes:
    0  Success (dry-run preview, or every selected version deleted).
    1  Missing token, bad argument, list failure, or a delete that failed.

Contract:
- Inputs: the ``prune`` subcommand; ``--owner``, repeatable ``--package`` and
  ``--pinned-sha-from``, ``--keep-recent`` (int), ``--min-age-days`` (int),
  ``--dry-run`` (true/false string), optional ``--summary-file``; ``GH_TOKEN``
  env var (GitHub REST API auth, required).
- Outputs: a per-package deletion plan/result to stdout and, when
  ``--summary-file`` is given, an appended Markdown report; exit 0 on success
  or 1 on any failure.
- Failure policy: fails loud per CLAUDE.md section 4 -- a missing token, an
  API list error, or any failed delete exits non-zero; nothing is swallowed.

Tested by ``tests/test_prune_devcontainer_images.py``. Refs #1400, #696.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _github_api import apply_call

API_ROOT = "https://api.github.com"
_PER_PAGE = 100
# A defensive cap so a pathological response (or an opener that never returns a
# short page) cannot loop forever (CWE-835).
_MAX_PAGES = 100
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_ARCH_SUFFIXES = ("-amd64", "-arm64")

Opener = Callable[[Any], Any]


def parse_bool(value: str) -> bool:
    """Return the boolean for *value*, raising on anything ambiguous.

    Accepts ``true``/``false`` (case-insensitive). A workflow that passes an
    unexpected token (e.g. an unrendered ``${{ }}`` expression) fails loud
    rather than defaulting to a destructive real delete.
    """
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"expected 'true' or 'false' for --dry-run, got: {value!r}")


def parse_pinned_shas(paths: list[str]) -> set[str]:
    """Return the set of 40-char image SHAs pinned by the given config files.

    Each ``.devcontainer/<agent>/devcontainer.json`` pins one image as
    ``ghcr.io/.../<package>:<sha>``. The SHA after the final ``:`` is the
    protected tag. A config whose image tag is not a 40-hex SHA (e.g. a stray
    ``:main``) contributes nothing -- ``main`` is protected by name anyway.
    """
    shas: set[str] = set()
    for raw in paths:
        path = Path(raw)
        data = json.loads(path.read_text(encoding="utf-8"))
        image = data.get("image")
        if not isinstance(image, str) or ":" not in image:
            raise ValueError(f"{path}: 'image' must be a 'ghcr.io/...:<tag>' string")
        tag = image.rsplit(":", 1)[1]
        if _SHA_RE.fullmatch(tag):
            shas.add(tag)
    return shas


def is_protected_tag(tag: str, pinned_shas: set[str]) -> bool:
    """Return True when *tag* must never be deleted.

    Protected tags are ``main``, any ``buildcache-*`` cache tag, and a pinned
    SHA (or its ``-amd64`` / ``-arm64`` per-arch variant).
    """
    if tag == "main":
        return True
    if tag.startswith("buildcache-"):
        return True
    base = tag
    for suffix in _ARCH_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base in pinned_shas


def version_tags(version: dict[str, Any]) -> list[str]:
    """Return the container tags of *version* (empty list when untagged)."""
    tags = version.get("metadata", {}).get("container", {}).get("tags", [])
    return [t for t in tags if isinstance(t, str)]


def _parse_created_at(version: dict[str, Any]) -> datetime:
    """Return the timezone-aware creation time of *version*.

    GHCR stamps ``created_at`` as RFC 3339 with a trailing ``Z``. A version
    missing the field sorts as epoch (oldest) so it is never mistaken for a
    recent keep -- but, lacking a tag, such a version is filtered out earlier.
    """
    raw = version.get("created_at")
    if not isinstance(raw, str) or not raw:
        return datetime.fromtimestamp(0, tz=UTC)
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _deletion_order_key(version: dict[str, Any]) -> int:
    """Order manifest-list (non-arch) tags before per-arch children.

    A multi-platform manifest list (``<sha>`` / ``main``) references the
    per-arch child manifests (``<sha>-amd64`` / ``<sha>-arm64``). Deleting the
    parent first frees the children, avoiding a "referenced by a manifest list"
    rejection. Returns 0 for a version carrying at least one non-arch tag, 1
    for an arch-only version.
    """
    for tag in version_tags(version):
        if not any(tag.endswith(suffix) for suffix in _ARCH_SUFFIXES):
            return 0
    return 1


def select_versions_to_delete(
    versions: list[dict[str, Any]],
    pinned_shas: set[str],
    keep_recent: int,
    min_age_days: int,
    now: datetime,
) -> list[dict[str, Any]]:
    """Return the versions to delete under the count+age retention policy.

    Candidates are tagged versions with no protected tag. The newest
    *keep_recent* candidates are kept unconditionally; of the remainder, those
    created more than *min_age_days* before *now* are returned, ordered so a
    manifest list is deleted before its per-arch children.
    """
    if keep_recent < 0 or min_age_days < 0:
        raise ValueError("--keep-recent and --min-age-days must be non-negative")

    candidates = [
        v
        for v in versions
        if version_tags(v)
        and not any(is_protected_tag(t, pinned_shas) for t in version_tags(v))
    ]
    candidates.sort(key=_parse_created_at, reverse=True)

    aged_out = candidates[keep_recent:]
    cutoff = now - timedelta(days=min_age_days)
    to_delete = [v for v in aged_out if _parse_created_at(v) < cutoff]
    to_delete.sort(key=_deletion_order_key)
    return to_delete


def _list_versions(
    owner: str,
    package: str,
    token: str,
    *,
    opener: Opener | None = None,
) -> list[dict[str, Any]]:
    """Return every active version of a user-owned container package.

    Pages through the REST list endpoint until a short page is returned.
    Raises ``RuntimeError`` on any non-2xx response so a list failure fails
    loud instead of silently pruning against an empty set.
    """
    results: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        url = (
            f"{API_ROOT}/users/{owner}/packages/container/{package}/versions"
            f"?per_page={_PER_PAGE}&page={page}&state=active"
        )
        code, body = _call(method="GET", url=url, token=token, opener=opener)
        if not (200 <= code < 300):
            raise RuntimeError(
                f"listing {package} versions failed: HTTP {code}: {body[:200]}"
            )
        try:
            chunk = json.loads(body) if body else []
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"unexpected response for {package}: {body[:200]}") from exc
        if not isinstance(chunk, list):
            raise RuntimeError(f"expected a list for {package}, got: {body[:200]}")
        results.extend(chunk)
        if len(chunk) < _PER_PAGE:
            break
    return results


def _delete_version(
    owner: str,
    package: str,
    version_id: int,
    token: str,
    *,
    opener: Opener | None = None,
) -> tuple[int, str]:
    """Delete one package version. Returns the (status, body) of the call."""
    url = f"{API_ROOT}/users/{owner}/packages/container/{package}/versions/{version_id}"
    return _call(method="DELETE", url=url, token=token, opener=opener)


def _call(*, method: str, url: str, token: str, opener: Opener | None) -> tuple[int, str]:
    """Thin seam over ``_github_api.apply_call`` so tests can inject an opener."""
    if opener is None:
        return apply_call(method=method, url=url, payload=None, token=token)
    return apply_call(method=method, url=url, payload=None, token=token, opener=opener)


def _format_plan(package: str, to_delete: list[dict[str, Any]]) -> list[str]:
    """Return Markdown report lines for one package's deletion plan."""
    lines = [f"### {package}", ""]
    if not to_delete:
        lines.append("- nothing to prune")
        lines.append("")
        return lines
    for version in to_delete:
        tags = ", ".join(version_tags(version)) or "(untagged)"
        created = version.get("created_at", "?")
        lines.append(f"- id `{version.get('id')}` created {created} tags: {tags}")
    lines.append("")
    return lines


def cmd_prune(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("Error: GH_TOKEN environment variable is required", file=sys.stderr)
        return 1

    try:
        dry_run = parse_bool(args.dry_run)
        pinned_shas = parse_pinned_shas(args.pinned_sha_from)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    now = datetime.now(UTC)
    mode = "dry-run" if dry_run else "delete"
    report: list[str] = [f"## Devcontainer image prune ({mode})", ""]
    deleted = 0
    failures: list[str] = []

    for package in args.package:
        try:
            versions = _list_versions(args.owner, package, token)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        to_delete = select_versions_to_delete(
            versions, pinned_shas, args.keep_recent, args.min_age_days, now
        )
        report.extend(_format_plan(package, to_delete))
        print(f"{package}: {len(versions)} versions, {len(to_delete)} to prune ({mode})")

        if dry_run:
            continue

        for version in to_delete:
            raw_id = version.get("id")
            if raw_id is None:
                failures.append(f"{package}: version missing an id, skipped")
                continue
            version_id = int(raw_id)
            code, body = _delete_version(args.owner, package, version_id, token)
            if 200 <= code < 300:
                deleted += 1
                print(f"  deleted {package} version {version_id}")
            else:
                failures.append(f"{package} version {version_id}: HTTP {code}: {body[:120]}")

    if not dry_run:
        report.append(f"Deleted {deleted} version(s); {len(failures)} failure(s).")
        report.append("")

    if args.summary_file:
        with Path(args.summary_file).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(report) + "\n")

    for failure in failures:
        print(f"::error::failed to delete {failure}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune old GHCR devcontainer image versions.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    prune = sub.add_parser("prune", help="Delete old image versions per the retention policy.")
    prune.add_argument("--owner", required=True, help="GHCR package owner (user login).")
    prune.add_argument(
        "--package",
        action="append",
        required=True,
        help="Container package name (repeatable).",
    )
    prune.add_argument(
        "--pinned-sha-from",
        action="append",
        default=[],
        help="devcontainer.json whose pinned image SHA is protected (repeatable).",
    )
    prune.add_argument("--keep-recent", type=int, required=True, help="Newest N to always keep.")
    prune.add_argument("--min-age-days", type=int, required=True, help="Delete only versions older than this.")
    prune.add_argument("--dry-run", required=True, help="'true' to preview, 'false' to delete.")
    prune.add_argument("--summary-file", default=None, help="Append a Markdown report to this file.")
    prune.set_defaults(func=cmd_prune)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
