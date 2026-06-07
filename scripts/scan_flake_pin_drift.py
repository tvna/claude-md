#!/usr/bin/env python3
"""Fail when a pinned binary's flake.nix SHA256 is hardcoded elsewhere.

``flake.nix`` is the single source of truth for the version + SHA256 of every
fetchurl-pinned external tool (uv, waza, claude, codex, apm, ...). PR #1151
moved the waza pin out of ``scripts/install_waza.sh`` and into a flake reader
(``scripts/waza_pin.py``) for exactly this reason: a hardcoded second copy of a
checksum silently diverges from the flake on the next bump, and an updater that
only touches ``flake.nix`` cannot keep the copy in step (#1150, retro #1152).

This gate makes that discipline deterministic and registry-free. It derives
the forbidden literal set FROM ``flake.nix`` (every ``sha256-<base64>`` SRI
hash and its hex digest), then fails if any of them appear under ``scripts/``
or ``.github/workflows/``. Because the set is computed from the flake, a NEW
fetchurl-pinned module is covered the moment its hash lands in ``flake.nix`` --
no per-tool registry to maintain.

Scope is deliberately narrow:

* Only SHA256 hashes (high-entropy, unambiguous). Version strings are short and
  appear legitimately in many places, so they are out of scope; the
  supply-chain risk lives in the checksum.
* Only ``scripts/`` and ``.github/workflows/`` -- the provisioning surface.
  ``flake.nix`` (the SoT) lives at the repo root and is not scanned. ``tests/``
  is not scanned: a test asserting a known digest is a legitimate regression
  guard, not provisioning drift.

Escape hatch: append ``# flake-pin-ack`` to a line that must legitimately carry
a hash literal (mirrors the ``scan_workflow_pip.py`` ACK precedent).

CLI::

    python3 scripts/scan_flake_pin_drift.py verify  # exit 1 on drift
    python3 scripts/scan_flake_pin_drift.py list     # print the derived hashes

Fails loud per CLAUDE.md section 4. Tested by
``tests/test_scan_flake_pin_drift.py``. Refs #1150, #1152, #1153.

Contract:
    Inputs: the ``verify`` or ``list`` subcommand; ``flake.nix`` at the repo
        root (the hash source of truth); the files under ``scripts/`` and
        ``.github/workflows/`` (the scanned provisioning surface). No stdin,
        no env input.
    Outputs: ``verify`` prints ``::error file=...::`` annotations on stderr per
        hardcoded hash and a one-line summary, exit 0 when clean and exit 1 on
        any drift; ``list`` prints the derived forbidden hash set on stdout.
    Failure policy: fails loud per CLAUDE.md section 4 (gate: a hardcoded flake
        hash exits non-zero; a missing flake.nix exits non-zero).
"""

from __future__ import annotations

import argparse
import base64
import binascii
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories whose files must not carry a hardcoded copy of a flake hash.
SCANNED_SUBDIRS: tuple[str, ...] = ("scripts", ".github/workflows")

# Lines carrying this marker bypass the scan. Mirrors scan_workflow_pip.py.
ACK_MARKER = "# flake-pin-ack"

# An SRI sha256 hash as written in flake.nix: ``sha256-<base64>``.
_SRI_RE = re.compile(r"sha256-[A-Za-z0-9+/]+=*")


def sri_to_hex(sri: str) -> str | None:
    """Return the lowercase hex digest for an ``sha256-<base64>`` SRI, or None."""
    b64 = sri[len("sha256-") :]
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) != 32:
        return None
    return raw.hex()


def flake_hashes(flake_text: str) -> set[str]:
    """Return every forbidden literal: each SRI hash plus its hex digest."""
    forbidden: set[str] = set()
    for sri in _SRI_RE.findall(flake_text):
        hexd = sri_to_hex(sri)
        if hexd is None:
            continue  # not a 32-byte sha256 (defensive; SRI sha256 always is)
        forbidden.add(sri)
        forbidden.add(hexd)
    return forbidden


def _iter_files(repo_root: Path) -> Iterator[Path]:
    for subdir in SCANNED_SUBDIRS:
        base = repo_root / subdir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                yield path


def find_drift(repo_root: Path, forbidden: set[str]) -> list[str]:
    """Return ``::error::`` strings for every hardcoded flake hash found."""
    if not forbidden:
        return []
    errors: list[str] = []
    for path in _iter_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # unreadable or binary file: nothing to match
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ACK_MARKER in line:
                continue
            for literal in forbidden:
                if literal in line:
                    rel = path.relative_to(repo_root)
                    errors.append(
                        f"::error file={rel},line={lineno}::hardcoded flake.nix "
                        f"hash '{literal}' -- flake.nix is the single source of "
                        f"truth; read it at runtime (see scripts/waza_pin.py) "
                        f"instead of copying the digest (#1153)."
                    )
                    break  # one error per line is enough
    return errors


def _read_flake(repo_root: Path) -> str:
    flake = repo_root / "flake.nix"
    if not flake.is_file():
        raise SystemExit(f"::error::flake.nix not found at {flake}")
    return flake.read_text(encoding="utf-8")


def _cmd_verify(_args: argparse.Namespace) -> int:
    forbidden = flake_hashes(_read_flake(REPO_ROOT))
    errors = find_drift(REPO_ROOT, forbidden)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(
            f"FAIL: {len(errors)} hardcoded flake.nix hash(es) found under "
            f"{', '.join(SCANNED_SUBDIRS)}.",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: no flake.nix hash is hardcoded under {', '.join(SCANNED_SUBDIRS)} "
        f"({len(forbidden) // 2} pinned hash(es) checked)."
    )
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    for literal in sorted(flake_hashes(_read_flake(REPO_ROOT))):
        print(literal)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify", help="fail on any hardcoded flake hash").set_defaults(
        func=_cmd_verify
    )
    sub.add_parser("list", help="print the derived forbidden hash set").set_defaults(
        func=_cmd_list
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
