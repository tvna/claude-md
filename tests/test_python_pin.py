"""Tests for ``scripts/python_pin.py``.

The `scripts/` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import python_pin

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_pyproject(
    root: Path,
    *,
    requires: str = ">=3.12",
    ruff: str | None = "py312",
    mypy: str | None = "3.12",
) -> None:
    body = f'[project]\nrequires-python = "{requires}"\n'
    if ruff is not None:
        body += f'\n[tool.ruff]\ntarget-version = "{ruff}"\n'
    if mypy is not None:
        body += f'\n[tool.mypy]\npython_version = "{mypy}"\n'
    (root / "pyproject.toml").write_text(body)


# ---------------------------------------------------------------------------
# read_pin
# ---------------------------------------------------------------------------


class TestReadPin:
    def test_happy_path(self, tmp_path: Path) -> None:
        p = tmp_path / ".python-version"
        p.write_text("3.12.13\n")
        assert python_pin.read_pin(p) == "3.12.13"

    def test_strips_surrounding_whitespace(self, tmp_path: Path) -> None:
        p = tmp_path / ".python-version"
        p.write_text("  3.12.13  \n")
        assert python_pin.read_pin(p) == "3.12.13"

    def test_rejects_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cannot read"):
            python_pin.read_pin(tmp_path / ".python-version")

    def test_rejects_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / ".python-version"
        p.write_text("\n\n")
        with pytest.raises(ValueError, match="empty"):
            python_pin.read_pin(p)

    def test_rejects_multiple_lines(self, tmp_path: Path) -> None:
        p = tmp_path / ".python-version"
        p.write_text("3.12.13\n3.11.9\n")
        with pytest.raises(ValueError, match="single interpreter"):
            python_pin.read_pin(p)

    def test_rejects_bare_minor(self, tmp_path: Path) -> None:
        p = tmp_path / ".python-version"
        p.write_text("3.12\n")
        with pytest.raises(ValueError, match="exact patch"):
            python_pin.read_pin(p)

    def test_rejects_prerelease(self, tmp_path: Path) -> None:
        p = tmp_path / ".python-version"
        p.write_text("3.13.0rc1\n")
        with pytest.raises(ValueError, match="exact patch"):
            python_pin.read_pin(p)


# ---------------------------------------------------------------------------
# requires_python_floor
# ---------------------------------------------------------------------------


class TestRequiresPythonFloor:
    def test_parses_floor(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, requires=">=3.12")
        assert python_pin.requires_python_floor(tmp_path / "pyproject.toml") == (3, 12)

    def test_parses_floor_with_spaces(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, requires=">= 3.13")
        assert python_pin.requires_python_floor(tmp_path / "pyproject.toml") == (3, 13)

    def test_rejects_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cannot read"):
            python_pin.requires_python_floor(tmp_path / "pyproject.toml")

    def test_rejects_malformed_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project\n")
        with pytest.raises(ValueError, match="malformed TOML"):
            python_pin.requires_python_floor(tmp_path / "pyproject.toml")

    def test_rejects_missing_key(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        with pytest.raises(ValueError, match="missing"):
            python_pin.requires_python_floor(tmp_path / "pyproject.toml")

    def test_rejects_unparseable_floor(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, requires="==3.12.*")
        with pytest.raises(ValueError, match="floor"):
            python_pin.requires_python_floor(tmp_path / "pyproject.toml")


# ---------------------------------------------------------------------------
# find_inconsistencies
# ---------------------------------------------------------------------------


class TestFindInconsistencies:
    def _make_repo(self, root: Path, *, flake: str | None = "python312\n", **kw: str | None) -> None:
        _write_pyproject(root, **kw)  # type: ignore[arg-type]
        if flake is not None:
            (root / "flake.nix").write_text(flake)

    def test_clean(self, tmp_path: Path) -> None:
        self._make_repo(tmp_path)
        assert python_pin.find_inconsistencies(tmp_path, "3.12.13") == []

    def test_clean_without_flake(self, tmp_path: Path) -> None:
        self._make_repo(tmp_path, flake=None)
        assert python_pin.find_inconsistencies(tmp_path, "3.12.13") == []

    def test_pin_minor_mismatch(self, tmp_path: Path) -> None:
        self._make_repo(tmp_path)
        errors = python_pin.find_inconsistencies(tmp_path, "3.11.9")
        assert any("pin minor must match" in e for e in errors)

    def test_ruff_mismatch(self, tmp_path: Path) -> None:
        self._make_repo(tmp_path, ruff="py311")
        errors = python_pin.find_inconsistencies(tmp_path, "3.12.13")
        assert any("target-version" in e for e in errors)

    def test_ruff_absent_is_ok(self, tmp_path: Path) -> None:
        self._make_repo(tmp_path, ruff=None)
        assert python_pin.find_inconsistencies(tmp_path, "3.12.13") == []

    def test_mypy_mismatch(self, tmp_path: Path) -> None:
        self._make_repo(tmp_path, mypy="3.11")
        errors = python_pin.find_inconsistencies(tmp_path, "3.12.13")
        assert any("python_version" in e for e in errors)

    def test_mypy_absent_is_ok(self, tmp_path: Path) -> None:
        self._make_repo(tmp_path, mypy=None)
        assert python_pin.find_inconsistencies(tmp_path, "3.12.13") == []

    def test_flake_mismatch(self, tmp_path: Path) -> None:
        self._make_repo(tmp_path, flake="python311\npython311Packages.x\n")
        errors = python_pin.find_inconsistencies(tmp_path, "3.12.13")
        assert any("flake.nix references python311" in e for e in errors)

    def test_real_repo_is_consistent(self) -> None:
        # The checked-in tree must pass its own gate.
        pin = python_pin.read_pin(REPO_ROOT / ".python-version")
        assert python_pin.find_inconsistencies(REPO_ROOT, pin) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_read_prints_pin(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / ".python-version").write_text("3.12.13\n")
        rc = python_pin.main(["read", str(tmp_path / ".python-version")])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "3.12.13"

    def test_read_default_path(self) -> None:
        # Default argument resolves the repo-root pin without raising.
        assert python_pin.main(["read", str(REPO_ROOT / ".python-version")]) == 0

    def test_verify_clean(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path)
        (tmp_path / ".python-version").write_text("3.12.13\n")
        (tmp_path / "flake.nix").write_text("python312\n")
        assert python_pin.main(["verify", "--repo-root", str(tmp_path)]) == 0

    def test_verify_reports_drift(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_pyproject(tmp_path, ruff="py311")
        (tmp_path / ".python-version").write_text("3.12.13\n")
        rc = python_pin.main(["verify", "--repo-root", str(tmp_path)])
        assert rc == 1
        assert "::error::" in capsys.readouterr().out

    def test_verify_surfaces_value_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # No .python-version file -> read_pin raises -> exit 1 with a message.
        _write_pyproject(tmp_path)
        rc = python_pin.main(["verify", "--repo-root", str(tmp_path)])
        assert rc == 1
        assert "error:" in capsys.readouterr().err

    def test_requires_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            python_pin.main([])
