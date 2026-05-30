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


def test_parse_lockfile_ignores_blank_lines() -> None:
    digest = "a" * 64
    text = f"\n{digest}  .apm/instructions/file.md\n\n"
    rows, errors = vac.parse_lockfile(text)
    assert not errors
    from pathlib import Path as _Path
    assert _Path(".apm/instructions/file.md") in rows


def test_parse_lockfile_reports_duplicate_path() -> None:
    digest = "a" * 64
    path = ".apm/instructions/file.md"
    text = f"{digest}  {path}\n{digest}  {path}\n"
    _rows, errors = vac.parse_lockfile(text)
    assert any("duplicate path" in e for e in errors)


def test_cli_verify_handles_file_not_found_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raises(root: object) -> object:
        raise FileNotFoundError("missing APM directory: .apm")

    monkeypatch.setattr(vac, "verify", _raises)
    rc = vac.main(["--root", str(tmp_path), "verify"])
    assert rc == 1
    assert "missing APM directory" in capsys.readouterr().err


def test_cli_update_handles_file_not_found_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raises(root: object) -> None:
        raise FileNotFoundError("missing APM directory: .apm")

    monkeypatch.setattr(vac, "update", _raises)
    rc = vac.main(["--root", str(tmp_path), "update"])
    assert rc == 1
    assert "missing APM directory" in capsys.readouterr().err


def test_build_checksums_raises_when_apm_dir_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing APM directory"):
        vac.build_checksums(tmp_path)


def test_verify_reports_missing_lockfile(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    # .apm/instructions/ exists but CHECKSUMS was never written.
    errors = vac.verify(root)
    assert any("missing lockfile" in e for e in errors)


def test_main_block_exits_via_runpy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import runpy
    import sys

    root = _make_repo(tmp_path)
    vac.update(root)
    monkeypatch.setattr(sys, "argv", ["verify_apm_checksums", "--root", str(root), "verify"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("verify_apm_checksums", run_name="__main__")
    assert exc_info.value.code == 0
