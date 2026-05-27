from __future__ import annotations

from pathlib import Path

import pytest
import verify_apm_checksums as vac

pytestmark = pytest.mark.shard_ci_ops

def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(tmp_path: Path) -> Path:
    _write(tmp_path, ".apm/instructions/master.instructions.md", "one\n")
    return tmp_path


def test_update_writes_lockfile(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)

    vac.update(root)

    lockfile = root / ".apm/CHECKSUMS"
    assert lockfile.exists()
    assert ".apm/instructions/master.instructions.md" in lockfile.read_text(encoding="utf-8")
    assert vac.verify(root) == []


def test_verify_clean_checksums(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    vac.update(root)

    assert vac.verify(root) == []


def test_verify_reports_changed_file_content(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    vac.update(root)
    _write(root, ".apm/instructions/master.instructions.md", "changed\n")

    assert vac.verify(root) == ["checksum mismatch: .apm/instructions/master.instructions.md"]


def test_verify_reports_missing_file(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    vac.update(root)
    (root / ".apm/instructions/master.instructions.md").unlink()

    assert vac.verify(root) == ["missing file listed in lockfile: .apm/instructions/master.instructions.md"]


def test_verify_reports_added_file(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    vac.update(root)
    _write(root, ".apm/instructions/extra.instructions.md", "two\n")

    assert vac.verify(root) == ["new file missing from lockfile: .apm/instructions/extra.instructions.md"]


@pytest.mark.parametrize(
    "row,expected",
    [
        ("not-a-row\n", "line 1: expected '<sha256>  <path>'"),
        ("0  .apm/instructions/master.instructions.md\n", "line 1: invalid sha256 digest"),
        ("a" * 64 + "  ../outside\n", "line 1: path must be a relative .apm/ path"),
        ("a" * 64 + "  .apm/CHECKSUMS\n", "line 1: lockfile must not checksum itself"),
    ],
)
def test_verify_reports_malformed_lockfile_rows(tmp_path: Path, row: str, expected: str) -> None:
    root = _make_repo(tmp_path)
    _write(root, ".apm/CHECKSUMS", row)

    assert expected in vac.verify(root)


def test_cli_verify_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_repo(tmp_path)
    vac.update(root)

    rc = vac.main(["--root", str(root), "verify"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "OK: .apm/CHECKSUMS matches APM source files." in captured.out


def test_cli_verify_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_repo(tmp_path)
    vac.update(root)
    _write(root, ".apm/instructions/master.instructions.md", "changed\n")

    rc = vac.main(["--root", str(root), "verify"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "::error::checksum mismatch: .apm/instructions/master.instructions.md" in captured.err


def test_cli_update_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _make_repo(tmp_path)

    rc = vac.main(["--root", str(root), "update"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Updated .apm/CHECKSUMS." in captured.out
    assert (root / ".apm/CHECKSUMS").exists()
