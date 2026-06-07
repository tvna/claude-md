"""Tests for scripts/uv_download_checksum.py.

Covers the flake-hash extraction, file hashing, and the ``verify`` CLI
(match, mismatch, malformed flake) plus a real-flake.nix smoke check.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest
import uv_download_checksum

pytestmark = pytest.mark.shard_ci_ops

# The x86_64-unknown-linux-gnu uv pin currently in flake.nix and its hex digest.
_REAL_SRI = "sha256-p2eEglQ5GFXJbfJx6cqLf3LdFy0xBGBEeFPSXZB7muA="
_REAL_HEX = "a767848254391855c96df271e9ca8b7f72dd172d310460447853d25d907b9ae0"


def _flake(target: str, sri: str) -> str:
    """Return a minimal flake.nix snippet with one uvNative target/hash pair."""
    return (
        "          uvNative = {\n"
        "            x86_64-linux = {\n"
        f'              target = "{target}";\n'
        f'              hash = "{sri}";\n'
        "            };\n"
        "          }.${system};\n"
    )


class TestFlakeUvSha256Hex:
    def test_known_sri_to_hex(self, tmp_path: Path) -> None:
        flake = tmp_path / "flake.nix"
        flake.write_text(_flake("x86_64-unknown-linux-gnu", _REAL_SRI))
        result = uv_download_checksum.flake_uv_sha256_hex(
            flake, "x86_64-unknown-linux-gnu"
        )
        assert result == _REAL_HEX

    def test_tolerates_extra_whitespace_and_newlines(self, tmp_path: Path) -> None:
        flake = tmp_path / "flake.nix"
        flake.write_text(
            f'target = "x86_64-unknown-linux-gnu"  ;\n\n   hash = "{_REAL_SRI}";'
        )
        assert (
            uv_download_checksum.flake_uv_sha256_hex(
                flake, "x86_64-unknown-linux-gnu"
            )
            == _REAL_HEX
        )

    def test_missing_target_fails_loud(self, tmp_path: Path) -> None:
        flake = tmp_path / "flake.nix"
        flake.write_text(_flake("x86_64-unknown-linux-gnu", _REAL_SRI))
        with pytest.raises(ValueError, match="no uvNative sha256 hash"):
            uv_download_checksum.flake_uv_sha256_hex(flake, "aarch64-apple-darwin")

    def test_missing_file_fails_loud(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cannot read"):
            uv_download_checksum.flake_uv_sha256_hex(
                tmp_path / "absent.nix", "x86_64-unknown-linux-gnu"
            )

    def test_non_32_byte_hash_fails_loud(self, tmp_path: Path) -> None:
        short = base64.b64encode(b"too-short").decode()
        flake = tmp_path / "flake.nix"
        flake.write_text(_flake("x86_64-unknown-linux-gnu", f"sha256-{short}"))
        with pytest.raises(ValueError, match="not a 32-byte sha256"):
            uv_download_checksum.flake_uv_sha256_hex(
                flake, "x86_64-unknown-linux-gnu"
            )

    def test_real_repo_flake(self) -> None:
        repo_flake = Path(__file__).resolve().parent.parent / "flake.nix"
        result = uv_download_checksum.flake_uv_sha256_hex(
            repo_flake, "x86_64-unknown-linux-gnu"
        )
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestFileSha256Hex:
    def test_matches_hashlib(self, tmp_path: Path) -> None:
        blob = tmp_path / "blob.bin"
        payload = b"uv-tarball-bytes" * 100
        blob.write_bytes(payload)
        assert (
            uv_download_checksum.file_sha256_hex(blob)
            == hashlib.sha256(payload).hexdigest()
        )


def _sri_for(payload: bytes) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(payload).digest()).decode()


class TestVerifyCli:
    def test_match_exits_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        payload = b"the-real-uv-tarball"
        tarball = tmp_path / "uv.tar.gz"
        tarball.write_bytes(payload)
        flake = tmp_path / "flake.nix"
        flake.write_text(_flake("x86_64-unknown-linux-gnu", _sri_for(payload)))

        rc = uv_download_checksum.main(
            [
                "verify",
                "--file", str(tarball),
                "--target", "x86_64-unknown-linux-gnu",
                "--flake", str(flake),
            ]
        )
        assert rc == 0
        assert "OK:" in capsys.readouterr().out

    def test_mismatch_exits_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        tarball = tmp_path / "uv.tar.gz"
        tarball.write_bytes(b"tampered-bytes")
        flake = tmp_path / "flake.nix"
        flake.write_text(_flake("x86_64-unknown-linux-gnu", _sri_for(b"original")))

        rc = uv_download_checksum.main(
            [
                "verify",
                "--file", str(tarball),
                "--target", "x86_64-unknown-linux-gnu",
                "--flake", str(flake),
            ]
        )
        assert rc == 1
        assert "checksum mismatch" in capsys.readouterr().err

    def test_malformed_flake_exits_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        tarball = tmp_path / "uv.tar.gz"
        tarball.write_bytes(b"anything")
        flake = tmp_path / "flake.nix"
        flake.write_text("no uv pin here")

        rc = uv_download_checksum.main(
            [
                "verify",
                "--file", str(tarball),
                "--target", "x86_64-unknown-linux-gnu",
                "--flake", str(flake),
            ]
        )
        assert rc == 1
        assert "::error::" in capsys.readouterr().err
