#!/usr/bin/env python3
"""Read the pinned waza release coordinates from ``flake.nix`` (the SoT).

``flake.nix`` already pins waza for the devcontainer: ``wazaVersion`` plus a
per-system ``wazaNative.<system>`` entry carrying the release ``asset`` name
and its SRI ``hash`` (``sha256-<base64>``). ``scripts/install_waza.sh`` needs
the same version + asset + checksum to download the prebuilt binary in CI.

Hardcoding those values a second time in ``install_waza.sh`` created a drift
surface: a waza bump (manual or automated) would update ``flake.nix`` but
silently leave the shell copy stale. This module makes ``flake.nix`` the
single source of truth -- ``install_waza.sh`` resolves the coordinates from it
at runtime, so there is exactly one place to update (#1150).

CLI::

    python3 scripts/waza_pin.py version
        # -> the bare wazaVersion, e.g. "0.33.0"
    python3 scripts/waza_pin.py resolve --system x86_64-linux
        # -> three lines: version, asset, sha256-hex

The SRI ``sha256-<base64>`` from the flake is converted to the lowercase hex
digest that ``sha256sum -c`` expects.

Fails loud (exit != 0) when the flake is missing or a requested field cannot
be parsed -- never returns a partial or guessed value (CLAUDE.md section 4).

Tested by ``tests/test_waza_pin.py``. Refs #1150, #1103.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLAKE_PATH = REPO_ROOT / "flake.nix"

# nix system doubles that flake.nix's wazaNative block enumerates.
KNOWN_SYSTEMS = ("x86_64-linux", "aarch64-linux")

_VERSION_RE = re.compile(r'wazaVersion\s*=\s*"([^"]+)"')
# The wazaNative attrset, up to its closing ``}.${system};`` selector.
_WAZA_NATIVE_RE = re.compile(
    r"wazaNative\s*=\s*\{(.*?)\}\s*\.\s*\$\{\s*system\s*\}", re.DOTALL
)


class WazaPinError(RuntimeError):
    """Raised when a required value cannot be read from the flake."""


def read_flake_text(flake_path: Path = FLAKE_PATH) -> str:
    """Return the text of ``flake.nix``; raise WazaPinError if it is missing."""
    try:
        return flake_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WazaPinError(f"cannot read {flake_path}: {exc}") from exc


def waza_version(text: str) -> str:
    """Return the bare ``wazaVersion`` (e.g. ``0.33.0``)."""
    match = _VERSION_RE.search(text)
    if match is None:
        raise WazaPinError("wazaVersion not found in flake.nix")
    return match.group(1)


def _waza_native_block(text: str) -> str:
    """Return the body of the ``wazaNative = { ... }`` attrset."""
    match = _WAZA_NATIVE_RE.search(text)
    if match is None:
        raise WazaPinError("wazaNative attrset not found in flake.nix")
    return match.group(1)


def _system_entry(block: str, system: str) -> str:
    """Return the body of the ``<system> = { ... }`` entry within *block*."""
    entry_re = re.compile(
        re.escape(system) + r"\s*=\s*\{(.*?)\}", re.DOTALL
    )
    match = entry_re.search(block)
    if match is None:
        raise WazaPinError(
            f"wazaNative has no entry for system '{system}' in flake.nix"
        )
    return match.group(1)


def sri_to_hex(sri: str) -> str:
    """Convert an ``sha256-<base64>`` SRI hash to a lowercase hex digest."""
    if not sri.startswith("sha256-"):
        raise WazaPinError(f"unsupported hash format (expected sha256-...): {sri!r}")
    b64 = sri[len("sha256-") :]
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WazaPinError(f"invalid base64 in SRI hash {sri!r}: {exc}") from exc
    if len(raw) != 32:
        raise WazaPinError(
            f"SRI hash {sri!r} decodes to {len(raw)} bytes, expected 32 (sha256)"
        )
    return raw.hex()


def resolve(text: str, system: str) -> tuple[str, str, str]:
    """Return ``(version, asset, sha256_hex)`` for *system*."""
    entry = _system_entry(_waza_native_block(text), system)
    asset_match = re.search(r'asset\s*=\s*"([^"]+)"', entry)
    hash_match = re.search(r'hash\s*=\s*"([^"]+)"', entry)
    if asset_match is None:
        raise WazaPinError(f"asset not found for system '{system}' in flake.nix")
    if hash_match is None:
        raise WazaPinError(f"hash not found for system '{system}' in flake.nix")
    return waza_version(text), asset_match.group(1), sri_to_hex(hash_match.group(1))


def _cmd_version(_args: argparse.Namespace) -> int:
    print(waza_version(read_flake_text()))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    version, asset, sha = resolve(read_flake_text(), args.system)
    print(version)
    print(asset)
    print(sha)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_version = sub.add_parser("version", help="print the bare wazaVersion")
    p_version.set_defaults(func=_cmd_version)

    p_resolve = sub.add_parser(
        "resolve", help="print version, asset, and sha256-hex for a system"
    )
    p_resolve.add_argument(
        "--system",
        required=True,
        help=f"nix system double (one of: {', '.join(KNOWN_SYSTEMS)})",
    )
    p_resolve.set_defaults(func=_cmd_resolve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except WazaPinError as exc:
        print(f"::error::waza_pin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
