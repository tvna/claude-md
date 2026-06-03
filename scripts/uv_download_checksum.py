#!/usr/bin/env python3
"""Verify a downloaded uv tarball against the SHA-256 pinned in flake.nix.

``flake.nix`` is the single source of truth for the version + SHA-256 of the
uv binary (see scripts/scan_flake_pin_drift.py and #1153). The CI uv install
(`.github/actions/setup-uv`) downloads the uv release tarball over the network;
without a checksum that download is an unverified supply-chain input. This gate
closes the gap by re-using the hash nix already enforces -- no second hardcoded
copy, so a uv bump that updates flake.nix updates this check automatically.

It reads the ``uvNative`` entry in flake.nix whose ``target`` matches, converts
its ``sha256-<base64>`` SRI hash to hex, computes the SHA-256 of the downloaded
file, and fails loudly on mismatch.

Tested by ``tests/test_uv_download_checksum.py``.

Contract:
- Inputs: the ``verify`` subcommand; ``--file`` (path to the downloaded
  tarball, required); ``--target`` (release triple, e.g.
  ``x86_64-unknown-linux-gnu``, required); ``--flake`` (defaults to
  ``flake.nix``). No stdin, no env-var fallbacks.
- Outputs: an ``OK:`` line on stdout on match; a ``::error::`` annotation on
  stderr on mismatch or malformed input; exit 0 on match, 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate, so any
  mismatch, missing file, or absent/malformed flake hash exits non-zero).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
from pathlib import Path


def flake_uv_sha256_hex(flake_path: Path, target: str) -> str:
    """Return the hex SHA-256 of the pinned uv tarball for *target*.

    Reads the ``uvNative`` entry in *flake_path* whose ``target`` equals
    *target* and converts its ``sha256-<base64>`` SRI hash to a lowercase hex
    digest. Raises :class:`ValueError` (loud) when the file is unreadable or
    the target/hash is absent or malformed.
    """
    try:
        text = flake_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {flake_path}: {exc}") from exc

    pattern = re.compile(
        r'target\s*=\s*"' + re.escape(target) + r'"\s*;\s*'
        r'hash\s*=\s*"sha256-([A-Za-z0-9+/]+=*)"'
    )
    match = pattern.search(text)
    if match is None:
        raise ValueError(
            f"no uvNative sha256 hash for target {target!r} in {flake_path}"
        )
    try:
        # binascii.Error (raised on invalid base64) subclasses ValueError.
        raw = base64.b64decode(match.group(1), validate=True)
    except ValueError as exc:
        raise ValueError(
            f"malformed base64 in flake uv hash for {target!r}: {exc}"
        ) from exc
    if len(raw) != 32:
        raise ValueError(f"flake uv hash for {target!r} is not a 32-byte sha256")
    return raw.hex()


def file_sha256_hex(file_path: Path) -> str:
    """Return the lowercase hex SHA-256 of *file_path*, streamed in chunks."""
    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ValueError(f"cannot read {file_path}: {exc}") from exc
    return digest.hexdigest()


def _cmd_verify(args: argparse.Namespace) -> int:
    expected = flake_uv_sha256_hex(Path(args.flake), args.target)
    actual = file_sha256_hex(Path(args.file))
    if actual != expected:
        print(
            f"::error::uv download checksum mismatch for {args.target}: "
            f"expected {expected}, got {actual}",
            file=sys.stderr,
        )
        return 1
    print(f"OK: uv download matches flake.nix pin for {args.target} ({expected}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Fail unless --file matches the flake.nix uv pin for --target.",
    )
    p_verify.add_argument("--file", required=True)
    p_verify.add_argument("--target", required=True)
    p_verify.add_argument("--flake", default="flake.nix")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
