"""Tests for scripts/ccusage_pin.py -- reading the pinned ccusage coordinates.

flake.nix is the single source of truth for the ccusage version, npm
scoped-package basename, and SHA256 (#1404). These tests pin the parsing +
SRI->hex conversion against both a synthetic flake fragment and the real
repository flake.nix, so a layout change that breaks the reader is caught here
rather than at CI download time. Mirrors tests/test_waza_pin.py.
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
    "ccusage_pin", REPO_ROOT / "scripts" / "ccusage_pin.py"
)
assert _SPEC and _SPEC.loader
ccusage_pin = importlib.util.module_from_spec(_SPEC)
sys.modules["ccusage_pin"] = ccusage_pin
_SPEC.loader.exec_module(ccusage_pin)


_SYNTHETIC_FLAKE = """
{
  outputs = { ... }:
    let
      ccusageVersion = "9.8.7";
      uvNative = {
        x86_64-linux = { target = "x"; hash = "sha256-AAAA"; };
      }.${system};
      ccusageNative = {
        aarch64-linux = {
          pkg = "ccusage-linux-arm64";
          hash = "sha256-vcXhHYK2+CkKcq/u5WQZhAUs5FNXq36HSgJ8fKWZ2zE=";
        };
        x86_64-linux = {
          pkg = "ccusage-linux-x64";
          hash = "sha256-Wl94vPpOZ4A74sG3AFDz64grUmUxPTF/PIWze7yO/xw=";
        };
      }.${system};
    in { };
}
"""


def test_ccusage_version_synthetic() -> None:
    assert ccusage_pin.ccusage_version(_SYNTHETIC_FLAKE) == "9.8.7"


def test_resolve_x64_synthetic() -> None:
    version, pkg, sha = ccusage_pin.resolve(_SYNTHETIC_FLAKE, "x86_64-linux")
    assert version == "9.8.7"
    assert pkg == "ccusage-linux-x64"
    # 64 lowercase hex chars == 32-byte sha256 digest.
    assert len(sha) == 64
    assert sha == bytes.fromhex(sha).hex()


def test_resolve_picks_ccusage_native_not_uv_native() -> None:
    """The uvNative block shares the x86_64-linux key; resolve must not read it."""
    _, pkg, _ = ccusage_pin.resolve(_SYNTHETIC_FLAKE, "x86_64-linux")
    assert pkg == "ccusage-linux-x64"


def test_sri_to_hex_known_vector() -> None:
    raw = bytes(range(32))
    sri = "sha256-" + base64.b64encode(raw).decode()
    assert ccusage_pin.sri_to_hex(sri) == raw.hex()


@pytest.mark.parametrize("bad", ["md5-abc", "sha256-not!base64!", "sha256-AAAA"])
def test_sri_to_hex_rejects_bad(bad: str) -> None:
    with pytest.raises(ccusage_pin.CcusagePinError):
        ccusage_pin.sri_to_hex(bad)


def test_resolve_unknown_system_fails_loud() -> None:
    with pytest.raises(ccusage_pin.CcusagePinError):
        ccusage_pin.resolve(_SYNTHETIC_FLAKE, "windows")


def test_missing_version_fails_loud() -> None:
    with pytest.raises(ccusage_pin.CcusagePinError):
        ccusage_pin.ccusage_version("{ no version here }")


def test_real_flake_resolves_both_systems() -> None:
    text = ccusage_pin.read_flake_text()
    for system in ccusage_pin.KNOWN_SYSTEMS:
        version, pkg, sha = ccusage_pin.resolve(text, system)
        assert version  # non-empty
        assert pkg.startswith("ccusage-linux-")
        assert len(sha) == 64
        int(sha, 16)  # valid hex


def test_real_flake_x64_matches_known_digest() -> None:
    """Guards the SRI->hex path against the actual pinned x64 package."""
    _, pkg, sha = ccusage_pin.resolve(ccusage_pin.read_flake_text(), "x86_64-linux")
    assert pkg == "ccusage-linux-x64"
    assert sha == (
        "5a5f78bcfa4e67803be2c1b70050f3eb882b5265313d317f3c85b37bbc8eff1c"
    )


def test_cli_resolve(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ccusage_pin.main(["resolve", "--system", "x86_64-linux"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 3
    assert out[1] == "ccusage-linux-x64"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ccusage_pin.main(["version"])
    assert rc == 0
    assert capsys.readouterr().out.strip()


def test_cli_resolve_bad_system_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ccusage_pin.main(["resolve", "--system", "nope"])
    assert rc == 1
    assert "::error::" in capsys.readouterr().err
