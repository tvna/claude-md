#!/usr/bin/env python3
"""Publish compiled agent instructions as tagged GitHub release assets.

Creates a GitHub release for a tag and uploads the compiled ``CLAUDE.md`` /
``AGENTS.md`` / ``GEMINI.md`` plus a ``SHA256SUMS`` manifest as downloadable
assets, so a downstream consumer can pin a version and verify the sha256
digest before landing the instructions as a committed real file (no
submodule, no symlink).

Usage::

    python3 scripts/publish_instruction_release.py publish \\
        --tag vX.Y.Z \\
        --asset CLAUDE.md --asset AGENTS.md --asset GEMINI.md --asset SHA256SUMS

Environment variables:
    GH_TOKEN / GITHUB_TOKEN  GitHub token with contents:write scope.
    REPO                     Repository in ``owner/repo`` format.

Contract:
- Inputs: the ``publish`` subcommand; ``--tag`` (required release tag); one or
  more ``--asset PATH`` files to attach; ``REPO`` and
  ``GH_TOKEN``/``GITHUB_TOKEN`` from the environment.
- Outputs: a created GitHub release for ``--tag`` with each asset uploaded; the
  release HTML URL on stdout; exit 0 on success, 1 on any error.
- Failure policy: fails loud per CLAUDE.md section 4; a missing env var, a
  missing asset file, or any non-2xx API response exits non-zero rather than
  publishing a partial or empty release.

Exit codes:
    0  Success.
    1  Missing env var, missing asset, or API error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

from _git import Runner, make_runner
from _github_api import apply_call as _github_apply_call
from _github_api import upload_release_asset as _github_upload_asset

_API_ROOT = "https://api.github.com"

# Map an asset's extension to its upload Content-Type. The compiled
# instructions are Markdown; SHA256SUMS and anything else default to a plain
# downloadable stream.
_CONTENT_TYPES = {".md": "text/markdown"}

_RELEASE_BODY = (
    "Compiled agent instructions for downstream consumers.\n\n"
    "Assets: CLAUDE.md, AGENTS.md, GEMINI.md, and SHA256SUMS. Pin this tag and "
    "verify the sha256 of each file against SHA256SUMS before committing it as "
    "a real file (do not use a submodule or symlink). See docs/runbooks/"
    "consumer-instruction-sync.md in the source repository.\n"
)

# A published release tag is a three-part semver tag: ``v<MAJOR>.<MINOR>.<PATCH>``.
# The post-merge auto-tag job (.github/workflows/post-merge.yml) mints exactly
# this shape from apm.yml: version, so previous-tag selection compares these three
# integers numerically rather than lexically (v0.10.0 > v0.9.0). A tag that does
# not match is ignored for range selection. Refs #2193.
_SEMVER_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

_RELEASE_NOTES_HEADER = "## Release notes"

# Shown when there is no previous v* semver tag to diff against, so an initial
# release still produces a well-formed body per the #2193 acceptance criteria.
_INITIAL_RELEASE_NOTE = "Initial release."


def _semver_key(tag: str) -> tuple[int, int, int] | None:
    """Return ``(major, minor, patch)`` for a semver tag, or None when it is not one."""
    match = _SEMVER_TAG_RE.match(tag)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _list_semver_tags(run: Runner) -> list[str]:
    """Return every ``v*`` semver tag in the repository.

    Uses ``git tag --list 'v*'`` and drops any listed tag that is not a strict
    three-part semver tag, so a stray ``v1`` or ``vfoo`` cannot poison
    previous-tag selection. A non-zero git exit fails loud per CLAUDE.md
    section 4 rather than silently treating the release as initial.
    """
    result = run(["tag", "--list", "v*"])
    if result.returncode != 0:
        raise RuntimeError(f"git tag --list failed: {result.stderr.strip()[:200]}")
    return [tag for line in result.stdout.splitlines() if (tag := line.strip()) and _semver_key(tag) is not None]


def _previous_tag(tag: str, tags: list[str]) -> str | None:
    """Return the highest ``v*`` semver tag strictly below *tag*, or None.

    Comparison is numeric on the parsed ``(major, minor, patch)`` tuple, so
    v0.10.0 correctly ranks above v0.9.0. When *tag* itself is not a semver tag,
    or no listed tag is lower, None signals "no previous tag" and the caller
    emits an initial-release body.
    """
    current = _semver_key(tag)
    if current is None:
        return None
    lesser = [(key, candidate) for candidate in tags if (key := _semver_key(candidate)) is not None and key < current]
    if not lesser:
        return None
    return max(lesser)[1]


def _log_subjects(previous_tag: str, tag: str, run: Runner) -> list[str]:
    """Return the commit subjects in ``previous_tag..tag`` (newest first).

    ``--no-merges`` keeps merge-commit noise out of the notes; the repository
    lands changes as squash commits whose subject is the PR title, which is the
    line consumers want to read. A non-zero git exit fails loud.
    """
    result = run(["log", "--no-merges", "--format=%s", f"{previous_tag}..{tag}"])
    if result.returncode != 0:
        raise RuntimeError(f"git log {previous_tag}..{tag} failed: {result.stderr.strip()[:200]}")
    return [subject for line in result.stdout.splitlines() if (subject := line.strip())]


def _release_notes(previous_tag: str | None, subjects: list[str]) -> str:
    """Render the release-notes fragment for the release body.

    No previous tag -> ``Initial release.``. A previous tag with commits ->
    a bullet per subject. A previous tag with no intervening commits (a retag of
    the same commit) -> an explicit "no changes" line rather than a blank
    section, so the empty case is visible instead of silently dropped.
    """
    if previous_tag is None:
        return _INITIAL_RELEASE_NOTE
    if not subjects:
        return f"No changes since {previous_tag}."
    return "\n".join(f"- {subject}" for subject in subjects)


def build_release_body(*, tag: str, run: Runner | None = None) -> str:
    """Return the full release body: asset instructions plus git-log release notes.

    Preserves the downstream asset-verification instructions verbatim and appends
    a ``## Release notes`` section listing the commit subjects from the previous
    ``v*`` semver tag up to *tag*. *run* is a git runner seam (defaulting to the
    production one) so tests can supply a canned git without touching a real
    repository. Refs #2193.
    """
    run = run or make_runner()
    previous_tag = _previous_tag(tag, _list_semver_tags(run))
    subjects = _log_subjects(previous_tag, tag, run) if previous_tag is not None else []
    notes = _release_notes(previous_tag, subjects)
    return f"{_RELEASE_BODY}\n{_RELEASE_NOTES_HEADER}\n\n{notes}\n"


def _content_type(name: str) -> str:
    """Return the upload Content-Type for an asset file name."""
    return _CONTENT_TYPES.get(Path(name).suffix, "application/octet-stream")


def _create_release(
    *,
    repo: str,
    tag: str,
    token: str,
    body: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> tuple[int, str]:
    """Create a GitHub release for *tag* with *body*. Returns ``(release_id, html_url)``."""
    url = f"{_API_ROOT}/repos/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": tag,
        "body": body,
        "draft": False,
        "prerelease": False,
    }
    code, resp = apply_call(method="POST", url=url, payload=payload, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Create release failed: HTTP {code or '000'}: {resp[:200]}")
    try:
        data = json.loads(resp)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Create release returned non-JSON: {exc}") from exc
    if not isinstance(data, dict) or "id" not in data:
        raise RuntimeError(f"Create release returned no release id: {resp[:200]}")
    return int(data["id"]), str(data.get("html_url", ""))


def publish(
    *,
    repo: str,
    tag: str,
    asset_paths: list[str],
    token: str,
    apply_call: Callable[..., tuple[int, str]] | None = None,
    upload_asset: Callable[..., tuple[int, str]] | None = None,
    run: Runner | None = None,
) -> str:
    """Create the release and upload every asset. Returns the release HTML URL.

    Validates every asset exists before creating the release so a missing file
    fails loud without leaving an empty release behind. The release body is
    generated from the git log (see :func:`build_release_body`); *run* is the git
    runner seam so tests can inject a canned git.
    """
    # Resolve the boundary callables at call time (not as captured defaults) so
    # a test can patch the module-level wrappers, mirroring _github_api's
    # call-time sleeper idiom.
    apply_call = apply_call or _github_apply_call
    upload_asset = upload_asset or _github_upload_asset
    if not asset_paths:
        raise RuntimeError("at least one --asset is required")
    for path in asset_paths:
        if not Path(path).is_file():
            raise RuntimeError(f"Asset not found: {path}")

    body = build_release_body(tag=tag, run=run)
    release_id, html_url = _create_release(repo=repo, tag=tag, token=token, body=body, apply_call=apply_call)

    for path in asset_paths:
        name = Path(path).name
        content = Path(path).read_bytes()
        code, resp = upload_asset(
            repo=repo,
            release_id=release_id,
            name=name,
            content=content,
            content_type=_content_type(name),
            token=token,
        )
        if not (200 <= code < 300):
            raise RuntimeError(f"Upload asset {name} failed: HTTP {code or '000'}: {resp[:200]}")

    return html_url


def _cmd_publish(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        print("Error: GH_TOKEN or GITHUB_TOKEN environment variable is required", file=sys.stderr)
        return 1
    repo = os.environ.get("REPO", "")
    if not repo:
        print("Error: REPO environment variable is required", file=sys.stderr)
        return 1

    try:
        html_url = publish(repo=repo, tag=args.tag, asset_paths=list(args.asset), token=token)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(html_url)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish agent instructions as release assets.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    publish_p = sub.add_parser("publish", help="Create a release and upload instruction assets")
    publish_p.add_argument("--tag", required=True, help="Release tag, e.g. vX.Y.Z")
    publish_p.add_argument(
        "--asset",
        action="append",
        default=[],
        help="Path to an asset file to attach (repeatable)",
    )

    args = parser.parse_args(argv)

    if args.cmd == "publish":
        return _cmd_publish(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
