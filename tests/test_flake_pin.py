"""Tests for scripts/flake_pin.py -- reading and bumping flake.nix tool pins.

flake.nix is the single source of truth for the version + per-system SHA256 of
the GitHub-Releases-sourced tools (waza, apm, rtk). These tests pin the parsing and
the in-place bump (version + per-system hash) against both a synthetic flake
fragment and the real repository flake.nix, so a layout change that breaks the
updater is caught here rather than at CI bump time. Refs #1171.
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
    "flake_pin", REPO_ROOT / "scripts" / "flake_pin.py"
)
assert _SPEC and _SPEC.loader
flake_pin = importlib.util.module_from_spec(_SPEC)
sys.modules["flake_pin"] = flake_pin
_SPEC.loader.exec_module(flake_pin)

_HASH_A = "sha256-VSuk9F5fc+PpwMk0KeLFniHxpN6LmJX5j1Te6n8D36g="
_HASH_B = "sha256-waMaFdlZ0s1Tb+tBz3sg+UsENKjoaUnT3j0hweP7b/M="
_NEW_A = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
_NEW_B = "sha256-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="

_SYNTHETIC_FLAKE = f"""
{{
  outputs = {{ ... }}:
    let
      apmVersion = "0.12.1";
      wazaVersion = "0.33.0";
      apmNative = {{
        aarch64-linux = {{
          archive = "apm-linux-arm64";
          hash = "sha256-NkplG444MzHPCumW09V7fxZLON40VjSuCP5xFMT546c=";
        }};
        x86_64-linux = {{
          archive = "apm-linux-x86_64";
          hash = "sha256-oLiW6MvdEEQRJemJqhnRgMYgUu2nyKqFD+s2eAXRJW8=";
        }};
      }}.${{system}};
      wazaNative = {{
        aarch64-linux = {{
          asset = "waza-linux-arm64";
          hash = "{_HASH_A}";
        }};
        x86_64-linux = {{
          asset = "waza-linux-amd64";
          hash = "{_HASH_B}";
        }};
      }}.${{system}};
    in {{ }};
}}
"""


def _real_flake() -> str:
    return (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")


# ---- reading -------------------------------------------------------------


def test_version_synthetic() -> None:
    assert flake_pin.current_version(_SYNTHETIC_FLAKE, "waza") == "0.33.0"
    assert flake_pin.current_version(_SYNTHETIC_FLAKE, "apm") == "0.12.1"


def test_version_real_flake() -> None:
    text = _real_flake()
    # Non-empty dotted versions for both tools.
    assert flake_pin.current_version(text, "waza").count(".") >= 1
    assert flake_pin.current_version(text, "apm").count(".") >= 1


def test_repo() -> None:
    assert flake_pin.tool_spec("waza").github_repo == "microsoft/waza"
    assert flake_pin.tool_spec("apm").github_repo == "microsoft/apm"
    assert flake_pin.tool_spec("rtk").github_repo == "rtk-ai/rtk"


def test_version_rtk_real_flake() -> None:
    assert flake_pin.current_version(_real_flake(), "rtk").count(".") >= 1


def test_asset_url_rtk_keeps_full_archive_name() -> None:
    text = _real_flake()
    rtk_url = flake_pin.asset_url(text, "rtk", "x86_64-linux", "9.9.9")
    assert rtk_url.startswith(
        "https://github.com/rtk-ai/rtk/releases/download/v9.9.9/"
    )
    # rtk stores the full archive filename in the asset field (musl/gnu differ),
    # so the URL ends with .tar.gz without the template adding an extension.
    assert rtk_url.endswith(".tar.gz")


def test_asset_url_waza_and_apm() -> None:
    text = _real_flake()
    waza_url = flake_pin.asset_url(text, "waza", "x86_64-linux", "9.9.9")
    assert waza_url.startswith(
        "https://github.com/microsoft/waza/releases/download/v9.9.9/"
    )
    assert not waza_url.endswith(".tar.gz")  # waza ships a bare binary

    apm_url = flake_pin.asset_url(text, "apm", "x86_64-linux", "9.9.9")
    assert apm_url.startswith(
        "https://github.com/microsoft/apm/releases/download/v9.9.9/"
    )
    assert apm_url.endswith(".tar.gz")


def test_unknown_tool_fails_loud() -> None:
    with pytest.raises(flake_pin.FlakePinError):
        flake_pin.tool_spec("nope")


# ---- runtime reader (resolve / sri_to_hex) -------------------------------
# These back scripts/install-rtk.sh, which downloads the pinned rtk release
# and verifies it with `sha256sum -c`. flake.nix stays the single source of
# truth; the reader converts the SRI base64 hash to the hex digest sha256sum
# expects. Refs #1218.


def test_sri_to_hex_known_vector() -> None:
    raw = bytes(range(32))
    sri = "sha256-" + base64.b64encode(raw).decode()
    assert flake_pin.sri_to_hex(sri) == raw.hex()


@pytest.mark.parametrize("bad", ["md5-abc", "sha256-not!base64!", "sha256-AAAA"])
def test_sri_to_hex_rejects_bad(bad: str) -> None:
    with pytest.raises(flake_pin.FlakePinError):
        flake_pin.sri_to_hex(bad)


def test_resolve_rtk_real_flake() -> None:
    version, asset, sha = flake_pin.resolve(_real_flake(), "rtk", "x86_64-linux")
    assert version.count(".") >= 1
    assert asset == "rtk-x86_64-unknown-linux-musl.tar.gz"
    # 64 lowercase hex chars == 32-byte sha256 digest.
    assert len(sha) == 64
    int(sha, 16)  # valid hex


def test_resolve_rtk_amd64_matches_known_digest() -> None:
    """Guards the SRI->hex path against the actual pinned rtk x86_64 asset."""
    _, asset, sha = flake_pin.resolve(_real_flake(), "rtk", "x86_64-linux")
    assert asset == "rtk-x86_64-unknown-linux-musl.tar.gz"
    assert sha == (
        "a37ca300a42510a964453f2bc2e217769ef0872780af802db8a7d698f1da2465"
    )


def test_resolve_isolates_tool_from_waza() -> None:
    """rtk and waza share the x86_64-linux key; resolve must not cross them."""
    text = _real_flake()
    _, rtk_asset, _ = flake_pin.resolve(text, "rtk", "x86_64-linux")
    _, waza_asset, _ = flake_pin.resolve(text, "waza", "x86_64-linux")
    assert rtk_asset.startswith("rtk-")
    assert waza_asset.startswith("waza-")


def test_resolve_unknown_tool_fails_loud() -> None:
    with pytest.raises(flake_pin.FlakePinError):
        flake_pin.resolve(_real_flake(), "nope", "x86_64-linux")


def test_cli_resolve_rtk(capsys: pytest.CaptureFixture[str]) -> None:
    rc = flake_pin.main(["resolve", "--tool", "rtk", "--system", "x86_64-linux"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 3
    assert out[1] == "rtk-x86_64-unknown-linux-musl.tar.gz"
    assert len(out[2]) == 64


# ---- bumping -------------------------------------------------------------


def test_bump_round_trip_synthetic() -> None:
    new_text = flake_pin.bump(
        _SYNTHETIC_FLAKE,
        "waza",
        "0.34.0",
        {"x86_64-linux": _NEW_B, "aarch64-linux": _NEW_A},
    )
    assert flake_pin.current_version(new_text, "waza") == "0.34.0"
    # Old waza hashes gone, new ones present.
    assert _HASH_A not in new_text and _HASH_B not in new_text
    assert _NEW_A in new_text and _NEW_B in new_text
    # apm block untouched.
    assert flake_pin.current_version(new_text, "apm") == "0.12.1"
    assert "apm-linux-x86_64" in new_text


def test_bump_preserves_asset_names() -> None:
    new_text = flake_pin.bump(
        _SYNTHETIC_FLAKE,
        "waza",
        "0.34.0",
        {"x86_64-linux": _NEW_B, "aarch64-linux": _NEW_A},
    )
    # The asset/archive names must not be rewritten by a version bump.
    assert "waza-linux-amd64" in new_text
    assert "waza-linux-arm64" in new_text


def test_bump_real_flake_text_isolates_tool() -> None:
    text = _real_flake()
    apm_before = flake_pin.current_version(text, "apm")
    new_text = flake_pin.bump(
        text,
        "waza",
        "0.99.0",
        {"x86_64-linux": _NEW_B, "aarch64-linux": _NEW_A},
    )
    assert flake_pin.current_version(new_text, "waza") == "0.99.0"
    # apm version is not collaterally changed.
    assert flake_pin.current_version(new_text, "apm") == apm_before


def test_bump_rejects_mismatched_systems() -> None:
    with pytest.raises(flake_pin.FlakePinError):
        flake_pin.bump(
            _SYNTHETIC_FLAKE, "waza", "0.34.0", {"x86_64-linux": _NEW_B}
        )


def test_bump_rejects_non_sri_hash() -> None:
    with pytest.raises(flake_pin.FlakePinError):
        flake_pin.bump(
            _SYNTHETIC_FLAKE,
            "waza",
            "0.34.0",
            {"x86_64-linux": "deadbeef", "aarch64-linux": _NEW_A},
        )


def test_parse_hash_args_rejects_duplicate_and_empty() -> None:
    with pytest.raises(flake_pin.FlakePinError):
        flake_pin._parse_hash_args([])
    with pytest.raises(flake_pin.FlakePinError):
        flake_pin._parse_hash_args(["x86_64-linux=a", "x86_64-linux=b"])
    with pytest.raises(flake_pin.FlakePinError):
        flake_pin._parse_hash_args(["no-equals-sign"])
