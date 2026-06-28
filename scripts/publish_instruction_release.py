#!/usr/bin/env python3
"""Publish compiled agent instructions as tagged GitHub release assets.

Creates a GitHub release for a tag and uploads the compiled ``CLAUDE.md`` /
``AGENTS.md`` plus a ``SHA256SUMS`` manifest as downloadable assets, so a
downstream consumer can pin a version and verify the sha256 digest before
landing the instructions as a committed real file (no submodule, no symlink).

Usage::

    python3 scripts/publish_instruction_release.py publish \\
        --tag vX.Y.Z \\
        --asset CLAUDE.md --asset AGENTS.md --asset SHA256SUMS

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
import sys
from collections.abc import Callable
from pathlib import Path

from _github_api import apply_call as _github_apply_call
from _github_api import upload_release_asset as _github_upload_asset

_API_ROOT = "https://api.github.com"

# Map an asset's extension to its upload Content-Type. The compiled
# instructions are Markdown; SHA256SUMS and anything else default to a plain
# downloadable stream.
_CONTENT_TYPES = {".md": "text/markdown"}

_RELEASE_BODY = (
    "Compiled agent instructions for downstream consumers.\n\n"
    "Assets: CLAUDE.md, AGENTS.md, and SHA256SUMS. Pin this tag and verify the "
    "sha256 of each file against SHA256SUMS before committing it as a real file "
    "(do not use a submodule or symlink). See docs/runbooks/"
    "consumer-instruction-sync.md in the source repository.\n"
)


def _content_type(name: str) -> str:
    """Return the upload Content-Type for an asset file name."""
    return _CONTENT_TYPES.get(Path(name).suffix, "application/octet-stream")


def _create_release(
    *,
    repo: str,
    tag: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> tuple[int, str]:
    """Create a GitHub release for *tag*. Returns ``(release_id, html_url)``."""
    url = f"{_API_ROOT}/repos/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": tag,
        "body": _RELEASE_BODY,
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
) -> str:
    """Create the release and upload every asset. Returns the release HTML URL.

    Validates every asset exists before creating the release so a missing file
    fails loud without leaving an empty release behind.
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

    release_id, html_url = _create_release(repo=repo, tag=tag, token=token, apply_call=apply_call)

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
