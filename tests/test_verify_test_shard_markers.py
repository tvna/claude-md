"""Tests for ``scripts/verify_test_shard_markers.py``.

Refs #545. Exercises the static checker that gates the pytest matrix
on every test file declaring exactly one module-scope shard marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import verify_test_shard_markers as vtsm

pytestmark = pytest.mark.shard_default


class TestExtractShardMarkers:
    def test_single_marker(self) -> None:
        source = "import pytest\npytestmark = pytest.mark.shard_default\n"
        assert vtsm.extract_shard_markers(source) == ["shard_default"]

    def test_list_marker(self) -> None:
        source = (
            "import pytest\n"
            "pytestmark = [pytest.mark.shard_policy, pytest.mark.usefixtures('x')]\n"
        )
        assert vtsm.extract_shard_markers(source) == ["shard_policy"]

    def test_tuple_marker(self) -> None:
        source = (
            "import pytest\n"
            "pytestmark = (pytest.mark.shard_ci_ops,)\n"
        )
        assert vtsm.extract_shard_markers(source) == ["shard_ci_ops"]

    def test_no_marker(self) -> None:
        source = "import pytest\n\ndef test_x():\n    assert True\n"
        assert vtsm.extract_shard_markers(source) == []

    def test_multiple_shard_markers(self) -> None:
        source = (
            "import pytest\n"
            "pytestmark = [pytest.mark.shard_preflight, pytest.mark.shard_policy]\n"
        )
        assert vtsm.extract_shard_markers(source) == ["shard_preflight", "shard_policy"]

    def test_unknown_attr_not_counted(self) -> None:
        # ``pytest.mark.usefixtures`` is not a shard marker; ignored.
        source = (
            "import pytest\n"
            "pytestmark = [pytest.mark.usefixtures('x'), pytest.mark.shard_default]\n"
        )
        assert vtsm.extract_shard_markers(source) == ["shard_default"]

    def test_inner_function_pytestmark_ignored(self) -> None:
        # Only module-scope ``pytestmark`` counts; in-function assignments
        # should not be picked up.
        source = (
            "import pytest\n"
            "def helper():\n"
            "    pytestmark = pytest.mark.shard_default\n"
        )
        assert vtsm.extract_shard_markers(source) == []


class TestVerifyFile:
    def test_conformant(self, tmp_path: Path) -> None:
        p = tmp_path / "test_x.py"
        p.write_text("import pytest\npytestmark = pytest.mark.shard_default\n")
        assert vtsm.verify_file(p) == []

    def test_missing_marker(self, tmp_path: Path) -> None:
        p = tmp_path / "test_x.py"
        p.write_text("def test_x():\n    assert True\n")
        errors = vtsm.verify_file(p)
        assert len(errors) == 1
        assert "missing module-scope shard marker" in errors[0]

    def test_multiple_markers(self, tmp_path: Path) -> None:
        p = tmp_path / "test_x.py"
        p.write_text(
            "import pytest\n"
            "pytestmark = [pytest.mark.shard_preflight, pytest.mark.shard_policy]\n"
        )
        errors = vtsm.verify_file(p)
        assert any("multiple shard markers" in e for e in errors)

    def test_unknown_bucket(self, tmp_path: Path) -> None:
        p = tmp_path / "test_x.py"
        p.write_text("import pytest\npytestmark = pytest.mark.shard_nonsense\n")
        errors = vtsm.verify_file(p)
        assert any("unknown shard bucket" in e for e in errors)

    def test_syntax_error(self, tmp_path: Path) -> None:
        p = tmp_path / "test_x.py"
        p.write_text("def broken(:\n")
        errors = vtsm.verify_file(p)
        assert len(errors) == 1
        assert "cannot parse" in errors[0]


class TestVerify:
    def test_all_conformant_exit_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / "test_a.py").write_text(
            "import pytest\npytestmark = pytest.mark.shard_default\n"
        )
        (tmp_path / "test_b.py").write_text(
            "import pytest\npytestmark = pytest.mark.shard_policy\n"
        )
        assert vtsm.verify(tmp_path) == 0
        out = capsys.readouterr().out
        assert "2 test files" in out

    def test_one_missing_exit_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "test_a.py").write_text(
            "import pytest\npytestmark = pytest.mark.shard_default\n"
        )
        (tmp_path / "test_b.py").write_text("def test_x():\n    assert True\n")
        assert vtsm.verify(tmp_path) == 1
        err = capsys.readouterr().err
        assert "missing module-scope shard marker" in err

    def test_empty_tests_dir(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert vtsm.verify(tmp_path) == 1
        err = capsys.readouterr().err
        assert "no test files found" in err


class TestRealRepo:
    def test_repo_passes_self_check(self) -> None:
        # The production tests directory must conform once the migration is done.
        # This test ensures regressions are caught immediately by the local suite.
        assert vtsm.verify(vtsm.REPO_ROOT / "tests") == 0


class TestMain:
    def test_main_passes_argv_through(self, tmp_path: Path) -> None:
        (tmp_path / "test_a.py").write_text(
            "import pytest\npytestmark = pytest.mark.shard_default\n"
        )
        assert vtsm.main(["--tests-dir", str(tmp_path)]) == 0
