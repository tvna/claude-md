"""Tests for ``scripts/scan_workflow_pip.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_workflow_pip

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# scan_line
# ---------------------------------------------------------------------------


class TestScanLine:
    @pytest.mark.parametrize(
        "line",
        [
            "          pip install pytest",
            "  pip3 install 'pytest>=8,<9'",
            "  python -m pip install pyyaml",
            "  python3 -m pip install --user pytest",
            "RUN pip install foo && bar",
            "\t\tpip   install   foo",
        ],
    )
    def test_detects_direct_pip_install(self, line: str) -> None:
        assert scan_line_true(line)

    @pytest.mark.parametrize(
        "line",
        [
            "  uv pip install 'pytest>=8,<9'",
            "  uv sync --locked",
            "  uv run python -m pytest -v",
            "  uv run --with 'apm-cli==0.12.1' apm compile",
            "  uv add pyyaml",
            "  echo 'pipeline'",
            "  echo 'zipinstall'",
            "  Pipfile.lock",
            "  curl -fLsS https://example.com/install.sh",
            "",
            "  # pip install pytest ; documentation of the forbidden form",
            "# python3 -m pip install foo  (this line is just a comment)",
            (
                "  pip install foo  "
                "<!-- pip-install-ack -->  legitimate one-off"
            ),
        ],
    )
    def test_allows_non_violations(self, line: str) -> None:
        assert not scan_workflow_pip.scan_line(line)


def scan_line_true(line: str) -> bool:
    """Wrapper that asserts the SUT returned True for clarity."""
    return scan_workflow_pip.scan_line(line) is True


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------


class TestScanText:
    def test_returns_empty_when_clean(self) -> None:
        text = "name: x\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        assert scan_workflow_pip.scan_text(text) == []

    def test_returns_line_numbers_1_based(self) -> None:
        text = (
            "name: x\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      - run: pip install pytest\n"
            "      - run: uv sync --locked\n"
            "      - run: python3 -m pip install pyyaml\n"
        )
        assert scan_workflow_pip.scan_text(text) == [5, 7]

    def test_multiple_violations_same_run_block(self) -> None:
        text = (
            "run: |\n"
            "  pip install foo\n"
            "  pip3 install bar\n"
            "  python -m pip install baz\n"
        )
        assert scan_workflow_pip.scan_text(text) == [2, 3, 4]

    def test_ack_marker_skips_line(self) -> None:
        text = (
            "  pip install one\n"
            "  pip install two  <!-- pip-install-ack -->\n"
            "  pip install three\n"
        )
        assert scan_workflow_pip.scan_text(text) == [1, 3]


# ---------------------------------------------------------------------------
# find_violations
# ---------------------------------------------------------------------------


def _make_workflow_repo(tmp_path: Path) -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    return tmp_path


class TestFindViolations:
    def test_clean_tree(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "name: ci\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: uv sync --locked\n"
            "      - run: uv run python -m pytest -v\n"
        )
        assert scan_workflow_pip.find_violations(repo) == []

    def test_violation_in_workflow_yml(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "name: ci\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - run: pip install pytest\n"
        )
        violations = scan_workflow_pip.find_violations(repo)
        assert violations == [(Path(".github/workflows/ci.yml"), 5)]

    def test_violation_in_workflow_yaml(self, tmp_path: Path) -> None:
        """The ``.yaml`` (long) extension is treated identically."""
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yaml").write_text(
            "      - run: python -m pip install foo\n"
        )
        violations = scan_workflow_pip.find_violations(repo)
        assert violations == [(Path(".github/workflows/ci.yaml"), 1)]

    def test_uv_pip_install_is_allowed(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "      - run: uv pip install pytest\n"
        )
        assert scan_workflow_pip.find_violations(repo) == []

    def test_comment_line_is_allowed(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "  # do not use 'pip install' here; prefer uv\n"
        )
        assert scan_workflow_pip.find_violations(repo) == []

    def test_ack_marker_is_allowed(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "      - run: pip install foo  <!-- pip-install-ack -->\n"
        )
        assert scan_workflow_pip.find_violations(repo) == []

    def test_violations_across_multiple_files_are_collected(
        self, tmp_path: Path
    ) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/a.yml").write_text(
            "      - run: pip install one\n"
        )
        (repo / ".github/workflows/b.yml").write_text(
            "uv sync --locked\n"
            "      - run: pip3 install two\n"
        )
        violations = scan_workflow_pip.find_violations(repo)
        assert (Path(".github/workflows/a.yml"), 1) in violations
        assert (Path(".github/workflows/b.yml"), 2) in violations
        assert len(violations) == 2

    def test_non_yaml_files_in_workflows_dir_are_ignored(
        self, tmp_path: Path
    ) -> None:
        """A stray README or .json file in the workflow dir is not scanned."""
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/README.md").write_text(
            "Do NOT do `pip install`; use uv.\n"
        )
        (repo / ".github/workflows/labels.json").write_text(
            '{"note": "pip install foo"}\n'
        )
        assert scan_workflow_pip.find_violations(repo) == []

    def test_missing_workflow_dir_is_clean(self, tmp_path: Path) -> None:
        """A repo with no ``.github/workflows`` directory trivially passes."""
        assert scan_workflow_pip.find_violations(tmp_path) == []

    def test_real_repo_has_no_violations(self) -> None:
        """The checked-in repo must pass the gate end-to-end."""
        violations = scan_workflow_pip.find_violations(REPO_ROOT)
        assert violations == [], "\n".join(
            f"{rel}:{lineno}" for rel, lineno in violations
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_verify_cli_clean(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _make_workflow_repo(tmp_path)
        exit_code = scan_workflow_pip.main(
            ["verify", "--repo-root", str(tmp_path)]
        )
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    def test_verify_cli_dirty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "      - run: pip install pytest\n"
        )
        exit_code = scan_workflow_pip.main(
            ["verify", "--repo-root", str(repo)]
        )
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "::error file=" in captured.err
        assert "ci.yml" in captured.err
        assert "FAIL" in captured.err

    def test_verify_cli_defaults_to_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_workflow_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        exit_code = scan_workflow_pip.main(["verify"])
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    def test_no_subcommand_exits_nonzero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            scan_workflow_pip.main([])
        assert exc.value.code == 2
