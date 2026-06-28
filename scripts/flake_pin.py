#!/usr/bin/env python3
"""Read and bump the GitHub-Releases-sourced fetchurl pins in ``flake.nix``.

``flake.nix`` is the single source of truth for the version + per-system SHA256
of every ``fetchurl``-pinned external tool. Several of those tools share the
same pin shape and release source (GitHub Releases):

* ``waza`` (microsoft/waza): ``wazaVersion`` + ``wazaNative.<sys>.{asset,hash}``
* ``apm``  (microsoft/apm):  ``apmVersion``  + ``apmNative.<sys>.{archive,hash}``
* ``rtk``  (rtk-ai/rtk):     ``rtkVersion``  + ``rtkNative.<sys>.{asset,hash}``
* ``actionlint`` (rhysd/actionlint): ``actionlintVersion`` +
  ``actionlintNative.<sys>.{asset,hash}`` (excluded from the refresh matrix --
  its asset filenames embed the version; see ``TOOLS`` and flake-pin-refresh.yml)

Dependabot has no Nix ecosystem, so these pins do not auto-follow upstream.
This module is the deterministic writer half of the auto-follow loop
(``flake_pin_latest.py`` decides *whether* to bump; the refresh workflow
recomputes the hashes): given a target version and the per-system SRI hashes,
it rewrites ``wazaVersion``/``apmVersion`` and the matching per-system ``hash``
entries in place.

The existing ``scripts/waza_pin.py`` runtime *reader* (used by
``install_waza.sh``) is intentionally left untouched; this module is the
update-path tool and never changes the asset/archive names, only the version
and checksums.

CLI::

    python3 scripts/flake_pin.py version --tool waza
        # -> the bare pinned version, e.g. "0.33.0"
    python3 scripts/flake_pin.py repo --tool apm
        # -> the "owner/name" GitHub repo
    python3 scripts/flake_pin.py asset-url --tool waza --system x86_64-linux \
            --version 0.34.0
        # -> the release download URL for that system + version
    python3 scripts/flake_pin.py resolve --tool rtk --system x86_64-linux
        # -> three lines: version, asset, sha256-hex (runtime reader for
        #    install_*.sh; the SRI base64 hash is converted to hex)
    python3 scripts/flake_pin.py bump --tool waza --version 0.34.0 \
            --hash x86_64-linux=sha256-... --hash aarch64-linux=sha256-...
        # -> rewrites flake.nix in place (version + both per-system hashes)

Fails loud (exit != 0) when the flake is missing, a field cannot be parsed, or
a bump would not land exactly one substitution; never a partial or guessed
write (CLAUDE.md section 4).

Tested by ``tests/test_flake_pin.py``. Refs #1171, #1150, #1153.

Contract:
    Inputs: a subcommand (``version`` / ``repo`` / ``asset-url`` / ``bump``);
        ``flake.nix`` at the repo root (the version + per-system hash source of
        truth); for ``bump``, ``--tool``, ``--version``, and one
        ``--hash SYSTEM=SRI`` per system in the flake's native block. No stdin.
    Outputs: ``version`` / ``repo`` / ``asset-url`` print one line to stdout;
        ``bump`` rewrites ``flake.nix`` in place and prints a one-line summary.
        Exit 0 on success.
    Failure policy: fails loud per CLAUDE.md section 4; a missing flake, an
        unparseable field, a non-SRI hash, a system-set mismatch, or a
        substitution that would not land exactly once exits non-zero rather
        than writing a partial or guessed result.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLAKE_PATH = REPO_ROOT / "flake.nix"

KNOWN_SYSTEMS = ("x86_64-linux", "aarch64-linux")
_SRI_RE = re.compile(r"^sha256-[A-Za-z0-9+/]+=*$")


@dataclass(frozen=True)
class ToolSpec:
    """How a single tool is pinned in ``flake.nix`` and where it is released."""

    version_var: str  # e.g. "wazaVersion"
    native_var: str  # e.g. "wazaNative"
    github_repo: str  # "owner/name"
    asset_field: str  # per-system field naming the release artifact
    # Build the release download URL from (version, asset_value).
    url_template: str  # uses {version} and {asset}

    def asset_url(self, version: str, asset_value: str) -> str:
        return self.url_template.format(version=version, asset=asset_value)


TOOLS: dict[str, ToolSpec] = {
    "waza": ToolSpec(
        version_var="wazaVersion",
        native_var="wazaNative",
        github_repo="microsoft/waza",
        asset_field="asset",
        url_template=(
            "https://github.com/microsoft/waza/releases/download/"
            "v{version}/{asset}"
        ),
    ),
    "apm": ToolSpec(
        version_var="apmVersion",
        native_var="apmNative",
        github_repo="microsoft/apm",
        asset_field="archive",
        url_template=(
            "https://github.com/microsoft/apm/releases/download/"
            "v{version}/{asset}.tar.gz"
        ),
    ),
    # rtk's per-system asset names differ in target (musl vs gnu), so the
    # ``asset`` field stores the full ``.tar.gz`` filename and the template
    # appends no extension; mirroring the waza shape, not apm's.
    "rtk": ToolSpec(
        version_var="rtkVersion",
        native_var="rtkNative",
        github_repo="rtk-ai/rtk",
        asset_field="asset",
        url_template=(
            "https://github.com/rtk-ai/rtk/releases/download/v{version}/{asset}"
        ),
    ),
    # actionlint's release assets embed the version in the filename
    # (actionlint_<ver>_linux_<arch>.tar.gz), so the ``asset`` field stores the
    # full ``.tar.gz`` filename and the template appends no extension; the
    # waza/rtk shape. NOTE: flake.nix keeps those filenames as static strings
    # (no ``${actionlintVersion}`` interpolation) because _native_block parses
    # with a brace-naive regex; a ``}`` inside an interpolation truncates the
    # match. A version bump must rewrite the embedded filenames too, which is
    # also why actionlint is excluded from the flake-pin-refresh matrix.
    "actionlint": ToolSpec(
        version_var="actionlintVersion",
        native_var="actionlintNative",
        github_repo="rhysd/actionlint",
        asset_field="asset",
        url_template=(
            "https://github.com/rhysd/actionlint/releases/download/"
            "v{version}/{asset}"
        ),
    ),
    # zizmor (zizmorcore/zizmor): tag is ``v{version}``; asset embeds no
    # version, so the rtk/waza shape (full filename in ``asset``). Consumed only
    # by scripts/install-zizmor.sh; web-only provisioning, not wired into nix.
    "zizmor": ToolSpec(
        version_var="zizmorVersion",
        native_var="zizmorNative",
        github_repo="zizmorcore/zizmor",
        asset_field="asset",
        url_template=(
            "https://github.com/zizmorcore/zizmor/releases/download/"
            "v{version}/{asset}"
        ),
    ),
    # lychee (lycheeverse/lychee): the release tag is ``lychee-v{version}`` (NOT
    # ``v{version}``), so the template carries that prefix. Asset embeds no
    # version. Consumed only by scripts/install-lychee.sh.
    "lychee": ToolSpec(
        version_var="lycheeVersion",
        native_var="lycheeNative",
        github_repo="lycheeverse/lychee",
        asset_field="asset",
        url_template=(
            "https://github.com/lycheeverse/lychee/releases/download/"
            "lychee-v{version}/{asset}"
        ),
    ),
    # betterleaks (betterleaks/betterleaks): tag is ``v{version}``; asset
    # filenames EMBED the version and are kept STATIC in flake.nix (actionlint
    # precedent; see flake.nix betterleaksNative). Consumed only by
    # scripts/install-betterleaks.sh.
    "betterleaks": ToolSpec(
        version_var="betterleaksVersion",
        native_var="betterleaksNative",
        github_repo="betterleaks/betterleaks",
        asset_field="asset",
        url_template=(
            "https://github.com/betterleaks/betterleaks/releases/download/"
            "v{version}/{asset}"
        ),
    ),
}


class FlakePinError(RuntimeError):
    """Raised when a required value cannot be read or written."""


def tool_spec(tool: str) -> ToolSpec:
    try:
        return TOOLS[tool]
    except KeyError:
        known = ", ".join(sorted(TOOLS))
        raise FlakePinError(f"unknown tool {tool!r}; known: {known}") from None


def _quoted_setter(value: str) -> Callable[[re.Match[str]], str]:
    """Return a re.sub replacer that keeps groups 1 and 2 and inserts *value*.

    Using a typed replacement function (rather than a backreference template)
    avoids backslash-escaping pitfalls in the inserted value and keeps mypy from
    widening the match to ``bytes``.
    """

    def _set(match: re.Match[str]) -> str:
        return f"{match.group(1)}{value}{match.group(2)}"

    return _set


def read_flake_text(flake_path: Path = FLAKE_PATH) -> str:
    try:
        return flake_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FlakePinError(f"cannot read {flake_path}: {exc}") from exc


def current_version(text: str, tool: str) -> str:
    """Return the bare pinned version for *tool* (e.g. ``0.33.0``)."""
    spec = tool_spec(tool)
    match = re.search(re.escape(spec.version_var) + r'\s*=\s*"([^"]+)"', text)
    if match is None:
        raise FlakePinError(f"{spec.version_var} not found in flake.nix")
    return match.group(1)


def _native_block(text: str, spec: ToolSpec) -> re.Match[str]:
    """Match the ``<native_var> = { ... }.${system}`` attrset; group(1)=body."""
    match = re.search(
        re.escape(spec.native_var) + r"\s*=\s*\{(.*?)\}\s*\.\s*\$\{\s*system\s*\}",
        text,
        re.DOTALL,
    )
    if match is None:
        raise FlakePinError(f"{spec.native_var} attrset not found in flake.nix")
    return match


def _system_entry(block_body: str, system: str, native_var: str) -> str:
    entry = re.search(
        re.escape(system) + r"\s*=\s*\{(.*?)\}", block_body, re.DOTALL
    )
    if entry is None:
        raise FlakePinError(
            f"{native_var} has no entry for system '{system}' in flake.nix"
        )
    return entry.group(1)


def asset_value(text: str, tool: str, system: str) -> str:
    """Return the release artifact name (asset/archive) for *system*."""
    spec = tool_spec(tool)
    body = _native_block(text, spec).group(1)
    entry = _system_entry(body, system, spec.native_var)
    match = re.search(re.escape(spec.asset_field) + r'\s*=\s*"([^"]+)"', entry)
    if match is None:
        raise FlakePinError(
            f"{spec.asset_field} not found for system '{system}' in flake.nix"
        )
    return match.group(1)


def asset_url(text: str, tool: str, system: str, version: str) -> str:
    spec = tool_spec(tool)
    return spec.asset_url(version, asset_value(text, tool, system))


def hash_value(text: str, tool: str, system: str) -> str:
    """Return the pinned ``sha256-<base64>`` SRI hash for *system*."""
    spec = tool_spec(tool)
    body = _native_block(text, spec).group(1)
    entry = _system_entry(body, system, spec.native_var)
    match = re.search(r'hash\s*=\s*"([^"]+)"', entry)
    if match is None:
        raise FlakePinError(
            f"hash not found for system '{system}' in flake.nix"
        )
    return match.group(1)


def sri_to_hex(sri: str) -> str:
    """Convert an ``sha256-<base64>`` SRI hash to a lowercase hex digest.

    ``install_*.sh`` verify downloads with ``sha256sum -c``, which expects a
    lowercase hex digest, while ``flake.nix`` pins the SRI base64 form. Fails
    loud on any non-sha256 or malformed input rather than returning a guessed
    value (CLAUDE.md section 4).
    """
    if not sri.startswith("sha256-"):
        raise FlakePinError(f"unsupported hash format (expected sha256-...): {sri!r}")
    b64 = sri[len("sha256-") :]
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FlakePinError(f"invalid base64 in SRI hash {sri!r}: {exc}") from exc
    if len(raw) != 32:
        raise FlakePinError(
            f"SRI hash {sri!r} decodes to {len(raw)} bytes, expected 32 (sha256)"
        )
    return raw.hex()


def resolve(text: str, tool: str, system: str) -> tuple[str, str, str]:
    """Return ``(version, asset, sha256_hex)`` for *tool* on *system*.

    The runtime reader half consumed by the ``install_*.sh`` provisioners:
    one call yields the three coordinates needed to download and checksum the
    pinned release artifact, all sourced from ``flake.nix``.
    """
    version = current_version(text, tool)
    asset = asset_value(text, tool, system)
    sha = sri_to_hex(hash_value(text, tool, system))
    return version, asset, sha


def _replace_hash_in_entry(block_body: str, system: str, new_sri: str) -> str:
    """Return *block_body* with the ``hash`` of *system*'s entry set to SRI."""
    entry_re = re.compile(
        r"(" + re.escape(system) + r"\s*=\s*\{)(.*?)(\})", re.DOTALL
    )

    def repl(match: re.Match[str]) -> str:
        head, entry_body, tail = match.group(1), match.group(2), match.group(3)
        new_body, n = re.subn(
            r'(hash\s*=\s*")[^"]+(")',
            _quoted_setter(new_sri),
            entry_body,
        )
        if n != 1:
            raise FlakePinError(
                f"expected exactly one hash in entry for '{system}', found {n}"
            )
        return head + new_body + tail

    new_block, count = entry_re.subn(repl, block_body)
    if count != 1:
        raise FlakePinError(
            f"expected exactly one entry for system '{system}', found {count}"
        )
    return new_block


def bump(text: str, tool: str, version: str, hashes: dict[str, str]) -> str:
    """Return *text* with *tool*'s version and per-system hashes replaced.

    *hashes* maps each system double to its new ``sha256-<base64>`` SRI. Every
    system present in the flake's native block MUST be supplied, and no extras;
    a mismatch fails loud rather than leaving a stale hash behind.
    """
    spec = tool_spec(tool)

    for system, sri in hashes.items():
        if not _SRI_RE.fullmatch(sri):
            raise FlakePinError(
                f"hash for '{system}' is not a sha256 SRI literal: {sri!r}"
            )

    # Replace the version (exactly one occurrence).
    new_text, vcount = re.subn(
        r"(" + re.escape(spec.version_var) + r'\s*=\s*")[^"]+(")',
        _quoted_setter(version),
        text,
        count=1,
    )
    if vcount != 1:
        raise FlakePinError(
            f"expected exactly one {spec.version_var} to bump, found {vcount}"
        )

    block_match = _native_block(new_text, spec)
    body = block_match.group(1)

    present = set(re.findall(r"([0-9a-z_]+-linux)\s*=\s*\{", body))
    if set(hashes) != present:
        raise FlakePinError(
            f"hash systems {sorted(hashes)} do not match flake systems "
            f"{sorted(present)} for {spec.native_var}"
        )

    new_body = body
    for system, sri in hashes.items():
        new_body = _replace_hash_in_entry(new_body, system, sri)

    return new_text[: block_match.start(1)] + new_body + new_text[block_match.end(1) :]


def _parse_hash_args(pairs: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise FlakePinError(f"--hash expects SYSTEM=SRI, got: {pair!r}")
        system, sri = pair.split("=", 1)
        system = system.strip()
        if system in result:
            raise FlakePinError(f"duplicate --hash for system '{system}'")
        result[system] = sri.strip()
    if not result:
        raise FlakePinError("bump requires at least one --hash SYSTEM=SRI")
    return result


def _cmd_version(args: argparse.Namespace) -> int:
    print(current_version(read_flake_text(), args.tool))
    return 0


def _cmd_repo(args: argparse.Namespace) -> int:
    print(tool_spec(args.tool).github_repo)
    return 0


def _cmd_asset_url(args: argparse.Namespace) -> int:
    print(asset_url(read_flake_text(), args.tool, args.system, args.version))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    version, asset, sha = resolve(read_flake_text(), args.tool, args.system)
    print(version)
    print(asset)
    print(sha)
    return 0


def _cmd_bump(args: argparse.Namespace) -> int:
    hashes = _parse_hash_args(args.hash)
    text = read_flake_text()
    new_text = bump(text, args.tool, args.version, hashes)
    if new_text == text:
        print("flake.nix already at target; nothing to write", file=sys.stderr)
        return 0
    FLAKE_PATH.write_text(new_text, encoding="utf-8")
    print(f"bumped {args.tool} to {args.version} in flake.nix")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_version = sub.add_parser("version", help="print the bare pinned version")
    p_version.add_argument("--tool", required=True, choices=sorted(TOOLS))
    p_version.set_defaults(func=_cmd_version)

    p_repo = sub.add_parser("repo", help="print the owner/name GitHub repo")
    p_repo.add_argument("--tool", required=True, choices=sorted(TOOLS))
    p_repo.set_defaults(func=_cmd_repo)

    p_url = sub.add_parser("asset-url", help="print the release download URL")
    p_url.add_argument("--tool", required=True, choices=sorted(TOOLS))
    p_url.add_argument("--system", required=True, choices=KNOWN_SYSTEMS)
    p_url.add_argument("--version", required=True)
    p_url.set_defaults(func=_cmd_asset_url)

    p_resolve = sub.add_parser(
        "resolve", help="print version, asset, and sha256-hex for a system"
    )
    p_resolve.add_argument("--tool", required=True, choices=sorted(TOOLS))
    p_resolve.add_argument("--system", required=True, choices=KNOWN_SYSTEMS)
    p_resolve.set_defaults(func=_cmd_resolve)

    p_bump = sub.add_parser("bump", help="rewrite version + per-system hashes")
    p_bump.add_argument("--tool", required=True, choices=sorted(TOOLS))
    p_bump.add_argument("--version", required=True)
    p_bump.add_argument(
        "--hash",
        action="append",
        default=[],
        metavar="SYSTEM=SRI",
        help="per-system sha256 SRI (repeatable, one per system)",
    )
    p_bump.set_defaults(func=_cmd_bump)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FlakePinError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
