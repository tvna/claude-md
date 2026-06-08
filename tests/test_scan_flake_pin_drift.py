"""Tests for scripts/scan_flake_pin_drift.py.

The gate derives the forbidden literal set from flake.nix and fails when any
pinned SHA256 is hardcoded under scripts/ or .github/workflows/ (#1153). These
tests pin the extraction, the drift detection, the ack escape hatch, the
scoping (tests/ is not scanned), and a real-repo self-check.
"""

from __future__ import annotations

import base64

import pytest
import scan_flake_pin_drift as gate

pytestmark = pytest.mark.shard_ci_ops

# A synthetic SHA256 SRI not present in the real flake.nix.
_RAW = bytes(range(32))
_SRI = "sha256-" + base64.b64encode(_RAW).decode()
_HEX = _RAW.hex()
_SYNTHETIC_FLAKE = f'  hash = "{_SRI}";\n'


def test_flake_hashes_extracts_sri_and_hex() -> None:
    forbidden = gate.flake_hashes(_SYNTHETIC_FLAKE)
    assert _SRI in forbidden
    assert _HEX in forbidden


def test_sri_to_hex_roundtrip() -> None:
    assert gate.sri_to_hex(_SRI) == _HEX


@pytest.mark.parametrize("bad", ["sha256-not!base64", "sha256-AAAA"])
def test_sri_to_hex_rejects_non_sha256(bad: str) -> None:
    assert gate.sri_to_hex(bad) is None


def _make_repo(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    return tmp_path


def test_find_drift_flags_hardcoded_hex(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "scripts" / "install.sh").write_text(f'SHA="{_HEX}"\n')
    errors = gate.find_drift(repo, {_SRI, _HEX})
    assert len(errors) == 1
    assert "install.sh" in errors[0]


def test_find_drift_flags_hardcoded_sri_in_workflow(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".github" / "workflows" / "x.yml").write_text(f"hash: {_SRI}\n")
    assert len(gate.find_drift(repo, {_SRI, _HEX})) == 1


def test_find_drift_respects_ack(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "scripts" / "install.sh").write_text(
        f'SHA="{_HEX}"  {gate.ACK_MARKER}\n'
    )
    assert gate.find_drift(repo, {_SRI, _HEX}) == []


def test_find_drift_ignores_tests_dir(tmp_path) -> None:
    """A digest asserted in tests/ is a regression guard, not provisioning drift."""
    repo = _make_repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(f'assert sha == "{_HEX}"\n')
    assert gate.find_drift(repo, {_SRI, _HEX}) == []


def test_find_drift_empty_forbidden_is_noop(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "scripts" / "install.sh").write_text(f'SHA="{_HEX}"\n')
    assert gate.find_drift(repo, set()) == []


def test_real_repo_is_clean() -> None:
    """The actual tree must keep flake.nix as the sole home of its hashes."""
    text = (gate.REPO_ROOT / "flake.nix").read_text(encoding="utf-8")
    forbidden = gate.flake_hashes(text)
    assert forbidden, "expected at least one sha256 pin in flake.nix"
    assert gate.find_drift(gate.REPO_ROOT, forbidden) == []


def test_cli_verify_clean_repo() -> None:
    assert gate.main(["verify"]) == 0


def test_cli_list_prints_hashes(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["list"]) == 0
    assert capsys.readouterr().out.strip()
