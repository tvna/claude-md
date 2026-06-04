"""Tests for scripts/flake_pin.py -- reading and bumping flake.nix tool pins.

flake.nix is the single source of truth for the version + per-system SHA256 of
the GitHub-Releases-sourced tools (waza, apm, rtk). These tests pin the parsing and
the in-place bump (version + per-system hash) against both a synthetic flake
fragment and the real repository flake.nix, so a layout change that breaks the
updater is caught here rather than at CI bump time. Refs #1171.
"""

from __future__ import annotations

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
