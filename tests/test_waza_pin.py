"""Tests for scripts/waza_pin.py; reading the pinned waza coordinates.

flake.nix is the single source of truth for the waza version, release asset,
and SHA256 (#1150). These tests pin the parsing + SRI->hex conversion against
both a synthetic flake fragment and the real repository flake.nix, so a layout
change that breaks the reader is caught here rather than at CI download time.
"""

from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "waza_pin", REPO_ROOT / "scripts" / "waza_pin.py"
)
assert _SPEC and _SPEC.loader
waza_pin = importlib.util.module_from_spec(_SPEC)
sys.modules["waza_pin"] = waza_pin
_SPEC.loader.exec_module(waza_pin)


_SYNTHETIC_FLAKE = """
{
  outputs = { ... }:
    let
      wazaVersion = "1.2.3";
      uvNative = {
        x86_64-linux = { target = "x"; hash = "sha256-AAAA"; };
      }.${system};
      wazaNative = {
        aarch64-linux = {
          asset = "waza-linux-arm64";
          hash = "sha256-VSuk9F5fc+PpwMk0KeLFniHxpN6LmJX5j1Te6n8D36g=";
        };
        x86_64-linux = {
          asset = "waza-linux-amd64";
          hash = "sha256-waMaFdlZ0s1Tb+tBz3sg+UsENKjoaUnT3j0hweP7b/M=";
        };
      }.${system};
    in { };
}
"""


def test_waza_version_synthetic() -> None:
    assert waza_pin.waza_version(_SYNTHETIC_FLAKE) == "1.2.3"


def test_resolve_amd64_synthetic() -> None:
    version, asset, sha = waza_pin.resolve(_SYNTHETIC_FLAKE, "x86_64-linux")
    assert version == "1.2.3"
    assert asset == "waza-linux-amd64"
    # 64 lowercase hex chars == 32-byte sha256 digest.
    assert len(sha) == 64
    assert sha == bytes.fromhex(sha).hex()


def test_resolve_picks_waza_native_not_uv_native() -> None:
    """The uvNative block shares the x86_64-linux key; resolve must not read it."""
    _, asset, _ = waza_pin.resolve(_SYNTHETIC_FLAKE, "x86_64-linux")
    assert asset == "waza-linux-amd64"


def test_sri_to_hex_known_vector() -> None:
    raw = bytes(range(32))
    sri = "sha256-" + base64.b64encode(raw).decode()
    assert waza_pin.sri_to_hex(sri) == raw.hex()


@pytest.mark.parametrize("bad", ["md5-abc", "sha256-not!base64!", "sha256-AAAA"])
def test_sri_to_hex_rejects_bad(bad: str) -> None:
    with pytest.raises(waza_pin.WazaPinError):
        waza_pin.sri_to_hex(bad)


def test_resolve_unknown_system_fails_loud() -> None:
    with pytest.raises(waza_pin.WazaPinError):
        waza_pin.resolve(_SYNTHETIC_FLAKE, "windows")


def test_missing_version_fails_loud() -> None:
    with pytest.raises(waza_pin.WazaPinError):
        waza_pin.waza_version("{ no version here }")


def test_real_flake_resolves_both_systems() -> None:
    text = waza_pin.read_flake_text()
    for system in waza_pin.KNOWN_SYSTEMS:
        version, asset, sha = waza_pin.resolve(text, system)
        assert version  # non-empty
        assert asset.startswith("waza-linux-")
        assert len(sha) == 64
        int(sha, 16)  # valid hex


def test_real_flake_amd64_matches_known_digest() -> None:
    """Guards the SRI->hex path against the actual pinned amd64 asset."""
    _, asset, sha = waza_pin.resolve(waza_pin.read_flake_text(), "x86_64-linux")
    assert asset == "waza-linux-amd64"
    assert sha == (
        "c1a31a15d959d2cd536feb41cf7b20f94b0434a8e86949d3de3d21c1e3fb6ff3"
    )


def test_cli_resolve(capsys: pytest.CaptureFixture[str]) -> None:
    rc = waza_pin.main(["resolve", "--system", "x86_64-linux"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 3
    assert out[1] == "waza-linux-amd64"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    rc = waza_pin.main(["version"])
    assert rc == 0
    assert capsys.readouterr().out.strip()


def test_cli_resolve_bad_system_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    rc = waza_pin.main(["resolve", "--system", "nope"])
    assert rc == 1
    assert "::error::" in capsys.readouterr().err
