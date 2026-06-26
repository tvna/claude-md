"""Tests for ``scripts/scan_install_curl_retry_drift.py`` (Refs #2038).

Verifies the drift gate that bans a bare ``curl`` download in any
``scripts/install-*.sh``: every installer must fetch through the shared
``retry_download`` helper instead. The live ``scripts/`` tree must pass; a
synthetic installer carrying a bare ``curl`` must fail; a ``curl`` mention in a
comment line must not false-positive.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_install_curl_retry_drift as gate

pytestmark = pytest.mark.shard_preflight

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_live_installers_have_no_bare_curl() -> None:
    """The real installer tree downloads only via retry_download."""
    paths = gate.installer_paths(_REPO_ROOT)
    assert paths, "expected install-*.sh installers under scripts/"
    assert gate.find_violations(paths) == []


def test_bare_curl_download_is_flagged(tmp_path: Path) -> None:
    """A synthetic installer with a bare curl download is reported."""
    bad = tmp_path / "install-bad.sh"
    bad.write_text(
        '#!/usr/bin/env bash\ncurl -fsSL "${url}" -o "${tarball}"\n',
        encoding="utf-8",
    )
    violations = gate.find_violations([bad])
    assert len(violations) == 1
    path, line_no, _ = violations[0]
    assert path == bad
    assert line_no == 2


def test_retry_download_call_is_not_flagged(tmp_path: Path) -> None:
    """An installer that uses retry_download (no curl) passes."""
    good = tmp_path / "install-good.sh"
    good.write_text(
        '#!/usr/bin/env bash\n'
        '. "${SCRIPT_DIR}/_retry.sh"\n'
        'retry_download "${url}" "${tarball}" "good" "scripts/install-good.sh" || exit 0\n',
        encoding="utf-8",
    )
    assert gate.find_violations([good]) == []


def test_curl_in_comment_is_ignored(tmp_path: Path) -> None:
    """A comment that mentions curl does not trip the gate."""
    commented = tmp_path / "install-doc.sh"
    commented.write_text(
        '#!/usr/bin/env bash\n'
        '# historically this used curl directly; now via retry_download\n'
        'retry_download "${url}" "${dest}" "doc" "scripts/install-doc.sh" || exit 0\n',
        encoding="utf-8",
    )
    assert gate.find_violations([commented]) == []


def test_verify_cli_passes_on_clean_tree(capsys: pytest.CaptureFixture[str]) -> None:
    """``verify`` against the live repo root exits 0."""
    assert gate.main(["verify"]) == 0


def test_verify_cli_fails_on_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``verify`` exits 1 and emits an ::error:: line when a bare curl exists."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "install-bad.sh").write_text(
        '#!/usr/bin/env bash\ncurl -fsSL "${url}" -o "${out}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "_REPO_ROOT", tmp_path)
    assert gate.main(["verify"]) == 1


def test_unreadable_file_is_skipped(tmp_path: Path) -> None:
    """A path that cannot be read is skipped (fail-open), not a violation."""
    missing = tmp_path / "install-missing.sh"
    assert gate.find_violations([missing]) == []


def test_verify_warns_and_passes_when_no_installers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty installer set exits 0 with a warning (gate bug never wedges CI)."""
    (tmp_path / "scripts").mkdir()
    monkeypatch.setattr(gate, "_REPO_ROOT", tmp_path)
    assert gate.main(["verify"]) == 0
    assert "no install-*.sh" in capsys.readouterr().err
