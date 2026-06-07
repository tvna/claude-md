#!/usr/bin/env python3
"""Read the pinned ccusage release coordinates from ``flake.nix`` (the SoT).

``flake.nix`` pins ccusage for the devcontainer: ``ccusageVersion`` plus a
per-system ``ccusageNative.<system>`` entry carrying the npm scoped-package
basename (``pkg``, e.g. ``ccusage-linux-x64``) and its SRI ``hash``
(``sha256-<base64>``). ``scripts/install-ccusage.sh`` needs the same version +
pkg + checksum to download the prebuilt native binary in the Claude Code on the
Web environment.

Hardcoding those values a second time in ``install-ccusage.sh`` would create a
drift surface: a ccusage bump would update ``flake.nix`` but silently leave the
shell copy stale. This module makes ``flake.nix`` the single source of truth --
``install-ccusage.sh`` resolves the coordinates from it at runtime, so there is
exactly one place to update (mirrors ``scripts/waza_pin.py``). Refs #1404.

ccusage is npm-distributed (not GitHub Releases) and its per-system URL is a
scoped-package path, which is why it has its own reader rather than an entry in
``scripts/flake_pin.py`` (that module's url_template is GitHub-Releases-shaped).
The registry URL is built by the caller from ``pkg`` + ``version``:
``https://registry.npmjs.org/@ccusage/<pkg>/-/<pkg>-<version>.tgz``.

CLI::

    python3 scripts/ccusage_pin.py version
        # -> the bare ccusageVersion, e.g. "20.0.6"
    python3 scripts/ccusage_pin.py resolve --system x86_64-linux
        # -> three lines: version, pkg, sha256-hex

The SRI ``sha256-<base64>`` from the flake is converted to the lowercase hex
digest that ``sha256sum -c`` expects.

Fails loud (exit != 0) when the flake is missing or a requested field cannot be
parsed -- never returns a partial or guessed value (CLAUDE.md section 4).

Tested by ``tests/test_ccusage_pin.py``.
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

# nix system doubles that flake.nix's ccusageNative block enumerates.
KNOWN_SYSTEMS = ("x86_64-linux", "aarch64-linux")

_VERSION_RE = re.compile(r'ccusageVersion\s*=\s*"([^"]+)"')
# The ccusageNative attrset, up to its closing ``}.${system};`` selector.
_CCUSAGE_NATIVE_RE = re.compile(
    r"ccusageNative\s*=\s*\{(.*?)\}\s*\.\s*\$\{\s*system\s*\}", re.DOTALL
)


class CcusagePinError(RuntimeError):
    """Raised when a required value cannot be read from the flake."""


def read_flake_text(flake_path: Path = FLAKE_PATH) -> str:
    """Return the text of ``flake.nix``; raise CcusagePinError if it is missing."""
    try:
        return flake_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CcusagePinError(f"cannot read {flake_path}: {exc}") from exc


def ccusage_version(text: str) -> str:
    """Return the bare ``ccusageVersion`` (e.g. ``20.0.6``)."""
    match = _VERSION_RE.search(text)
    if match is None:
        raise CcusagePinError("ccusageVersion not found in flake.nix")
    return match.group(1)


def _ccusage_native_block(text: str) -> str:
    """Return the body of the ``ccusageNative = { ... }`` attrset."""
    match = _CCUSAGE_NATIVE_RE.search(text)
    if match is None:
        raise CcusagePinError("ccusageNative attrset not found in flake.nix")
    return match.group(1)


def _system_entry(block: str, system: str) -> str:
    """Return the body of the ``<system> = { ... }`` entry within *block*."""
    entry_re = re.compile(re.escape(system) + r"\s*=\s*\{(.*?)\}", re.DOTALL)
    match = entry_re.search(block)
    if match is None:
        raise CcusagePinError(
            f"ccusageNative has no entry for system '{system}' in flake.nix"
        )
    return match.group(1)


def sri_to_hex(sri: str) -> str:
    """Convert an ``sha256-<base64>`` SRI hash to a lowercase hex digest."""
    if not sri.startswith("sha256-"):
        raise CcusagePinError(
            f"unsupported hash format (expected sha256-...): {sri!r}"
        )
    b64 = sri[len("sha256-") :]
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CcusagePinError(f"invalid base64 in SRI hash {sri!r}: {exc}") from exc
    if len(raw) != 32:
        raise CcusagePinError(
            f"SRI hash {sri!r} decodes to {len(raw)} bytes, expected 32 (sha256)"
        )
    return raw.hex()


def resolve(text: str, system: str) -> tuple[str, str, str]:
    """Return ``(version, pkg, sha256_hex)`` for *system*."""
    entry = _system_entry(_ccusage_native_block(text), system)
    pkg_match = re.search(r'pkg\s*=\s*"([^"]+)"', entry)
    hash_match = re.search(r'hash\s*=\s*"([^"]+)"', entry)
    if pkg_match is None:
        raise CcusagePinError(f"pkg not found for system '{system}' in flake.nix")
    if hash_match is None:
        raise CcusagePinError(f"hash not found for system '{system}' in flake.nix")
    return ccusage_version(text), pkg_match.group(1), sri_to_hex(hash_match.group(1))


def _cmd_version(_args: argparse.Namespace) -> int:
    print(ccusage_version(read_flake_text()))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    version, pkg, sha = resolve(read_flake_text(), args.system)
    print(version)
    print(pkg)
    print(sha)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_version = sub.add_parser("version", help="print the bare ccusageVersion")
    p_version.set_defaults(func=_cmd_version)

    p_resolve = sub.add_parser(
        "resolve", help="print version, pkg, and sha256-hex for a system"
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
    except CcusagePinError as exc:
        print(f"::error::ccusage_pin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
