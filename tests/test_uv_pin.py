"""Tests for ``scripts/uv_pin.py``.

The `scripts/` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import uv_pin

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# read_pin
# ---------------------------------------------------------------------------


class TestReadPin:
    def test_happy_path(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text('[tool.uv]\nrequired-version = "==1.2.3"\n')
        assert uv_pin.read_pin(p) == "1.2.3"

    def test_strips_only_leading_double_equals(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text('[tool.uv]\nrequired-version = "==1.2.3rc1"\n')
        assert uv_pin.read_pin(p) == "1.2.3rc1"

    def test_rejects_lower_bound_spec(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text('[tool.uv]\nrequired-version = ">=1.2.3"\n')
        with pytest.raises(ValueError, match="exact pin"):
            uv_pin.read_pin(p)

    def test_rejects_caret_spec(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text('[tool.uv]\nrequired-version = "^1.2.3"\n')
        with pytest.raises(ValueError, match="exact pin"):
            uv_pin.read_pin(p)

    def test_rejects_bare_version(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text('[tool.uv]\nrequired-version = "1.2.3"\n')
        with pytest.raises(ValueError, match="exact pin"):
            uv_pin.read_pin(p)

    def test_rejects_non_string(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text("[tool.uv]\nrequired-version = 123\n")
        with pytest.raises(ValueError, match="exact pin"):
            uv_pin.read_pin(p)

    def test_missing_section(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text('[project]\nname = "x"\n')
        with pytest.raises(ValueError, match="missing"):
            uv_pin.read_pin(p)

    def test_missing_key(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text("[tool.uv]\npackage = false\n")
        with pytest.raises(ValueError, match="missing"):
            uv_pin.read_pin(p)

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cannot read"):
            uv_pin.read_pin(tmp_path / "no-such-file.toml")

    def test_malformed_toml(self, tmp_path: Path) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text("[[[ not valid toml")
        with pytest.raises(ValueError, match="malformed TOML"):
            uv_pin.read_pin(p)

    def test_real_repo_pyproject(self) -> None:
        pin = uv_pin.read_pin(REPO_ROOT / "pyproject.toml")
        # Sanity: looks like a dotted version, no `==` prefix left.
        assert "." in pin
        assert not pin.startswith("=")


# ---------------------------------------------------------------------------
# find_drift
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path, *, pin: str = "1.2.3") -> Path:
    """Build a minimal mock repo tree at *tmp_path* and return the root."""
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.uv]\nrequired-version = "=={pin}"\n'
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()
    return tmp_path


class TestFindDrift:
    def test_clean_tree(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / ".github/workflows/test.yml").write_text("name: test\n")
        (repo / "scripts/x.sh").write_text("#!/bin/bash\n")
        (repo / "docs/x.md").write_text("# Doc\n")
        assert uv_pin.find_drift(repo, "1.2.3") == []

    def test_literal_in_workflow_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / ".github/workflows/test.yml").write_text(
            'env:\n  X: "1.2.3"\n'
        )
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert any("1.2.3" in e and "test.yml" in e for e in errors)

    def test_literal_in_script_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "scripts/x.sh").write_text('UV="1.2.3"\n')
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert any("scripts/x.sh" in e for e in errors)

    def test_literal_in_docs_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "docs/x.md").write_text("Version 1.2.3 is current.\n")
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert any("docs/x.md" in e for e in errors)

    def test_uv_version_literal_assignment_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, pin="1.2.3")
        # Use a non-pin value so it does not also trip check (1).
        (repo / ".github/workflows/test.yml").write_text(
            'env:\n  UV_VERSION: "9.9.9"\n'
        )
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert any("UV_VERSION" in e and "literal" in e for e in errors)

    def test_uv_version_single_quoted_literal_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, pin="1.2.3")
        (repo / ".github/workflows/test.yml").write_text(
            "env:\n  UV_VERSION: '9.9.9'\n"
        )
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert any("UV_VERSION" in e and "literal" in e for e in errors)

    def test_uv_version_bare_literal_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, pin="1.2.3")
        (repo / ".github/workflows/test.yml").write_text(
            "env:\n  UV_VERSION: 9.9.9\n"
        )
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert any("UV_VERSION" in e and "literal" in e for e in errors)

    def test_uv_version_from_step_outputs_is_allowed(self, tmp_path: Path) -> None:
        """Step env sourced from ``${{ ... }}`` is the supported pattern."""
        repo = _make_repo(tmp_path, pin="1.2.3")
        (repo / ".github/workflows/test.yml").write_text(
            "        env:\n"
            "          UV_VERSION: ${{ steps.uvpin.outputs.version }}\n"
        )
        assert uv_pin.find_drift(repo, "1.2.3") == []

    def test_uv_version_symbol_in_docs_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "docs/x.md").write_text("See UV_VERSION below.\n")
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert any("docs/x.md" in e and "UV_VERSION" in e for e in errors)

    def test_apm_cli_version_is_not_a_false_positive(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, pin="1.2.3")
        (repo / ".github/workflows/test.yml").write_text(
            'env:\n  APM_CLI_VERSION: "0.12.1"\n'
        )
        assert uv_pin.find_drift(repo, "1.2.3") == []

    def test_action_sha_pin_comment_is_not_a_false_positive(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, pin="1.2.3")
        (repo / ".github/workflows/test.yml").write_text(
            "uses: actions/checkout@deadbeef # v5.0.1\n"
        )
        assert uv_pin.find_drift(repo, "1.2.3") == []

    def test_pyproject_itself_is_not_flagged(self, tmp_path: Path) -> None:
        """The SoT pyproject.toml file may legally contain the pin literal."""
        repo = _make_repo(tmp_path, pin="1.2.3")
        # The make_repo helper already wrote `==1.2.3` to pyproject.toml.
        # If the iterator accidentally walked into pyproject.toml, the literal
        # would appear in the errors. Confirm it does not.
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert not any("pyproject.toml" in e for e in errors)

    def test_translations_json_is_excluded(self, tmp_path: Path) -> None:
        """`scripts/translations.json` is a historical snapshot of issue/PR
        bodies that legitimately quote past pin literals; the drift gate
        must skip it. Refs #102 P3.
        """
        repo = _make_repo(tmp_path, pin="1.2.3")
        (repo / "scripts/translations.json").write_text(
            '{"items": [{"original": "see uv 1.2.3"}]}\n'
        )
        # A sibling unrelated file with the literal MUST still fail, so
        # this exclusion is precisely scoped.
        (repo / "scripts/other.py").write_text('PIN = "1.2.3"\n')
        errors = uv_pin.find_drift(repo, "1.2.3")
        assert all("translations.json" not in e for e in errors)
        assert any("other.py" in e for e in errors)

    def test_real_repo_has_no_drift(self) -> None:
        """The checked-in repo must pass the drift gate end-to-end."""
        pin = uv_pin.read_pin(REPO_ROOT / "pyproject.toml")
        errors = uv_pin.find_drift(REPO_ROOT, pin)
        assert errors == [], "\n".join(errors)


# ---------------------------------------------------------------------------
# fetch_latest_uv_release
# ---------------------------------------------------------------------------


class TestFetchLatestUvRelease:
    def test_gh_missing_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_args, **_kwargs):
            raise FileNotFoundError("gh: command not found")

        monkeypatch.setattr(subprocess, "run", _raise)
        assert uv_pin.fetch_latest_uv_release() is None

    def test_gh_nonzero_exit_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_args, **_kwargs):
            raise subprocess.CalledProcessError(1, "gh", stderr="auth required")

        monkeypatch.setattr(subprocess, "run", _raise)
        assert uv_pin.fetch_latest_uv_release() is None

    def test_gh_timeout_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=30)

        monkeypatch.setattr(subprocess, "run", _raise)
        assert uv_pin.fetch_latest_uv_release() is None

    def test_gh_success_returns_tag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Result:
            stdout = "0.11.12\n"

        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Result())
        assert uv_pin.fetch_latest_uv_release() == "0.11.12"

    def test_gh_empty_output_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Result:
            stdout = "   \n"

        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Result())
        assert uv_pin.fetch_latest_uv_release() is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_read_cli(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text('[tool.uv]\nrequired-version = "==4.5.6"\n')
        exit_code = uv_pin.main(["read", str(p)])
        assert exit_code == 0
        assert capsys.readouterr().out.strip() == "4.5.6"

    def test_read_cli_bad_spec_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        p = tmp_path / "pyproject.toml"
        p.write_text('[tool.uv]\nrequired-version = ">=4.5.6"\n')
        exit_code = uv_pin.main(["read", str(p)])
        assert exit_code == 1
        assert "exact pin" in capsys.readouterr().err

    def test_drift_cli_clean(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        _make_repo(tmp_path, pin="7.8.9")
        exit_code = uv_pin.main(["drift", "--repo-root", str(tmp_path)])
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    def test_drift_cli_dirty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        repo = _make_repo(tmp_path, pin="7.8.9")
        (repo / "scripts/x.sh").write_text('UV="7.8.9"\n')
        exit_code = uv_pin.main(["drift", "--repo-root", str(repo)])
        assert exit_code == 1
        assert "::error::" in capsys.readouterr().out

    def test_stale_cli_skips_when_gh_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        _make_repo(tmp_path, pin="1.2.3")
        monkeypatch.setattr(
            uv_pin, "fetch_latest_uv_release", lambda: None
        )
        exit_code = uv_pin.main(["stale", "--repo-root", str(tmp_path)])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "::warning::" in out
        assert "skipped" in out

    def test_stale_cli_warns_when_pin_trails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        _make_repo(tmp_path, pin="1.2.3")
        monkeypatch.setattr(
            uv_pin, "fetch_latest_uv_release", lambda: "9.9.9"
        )
        exit_code = uv_pin.main(["stale", "--repo-root", str(tmp_path)])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "::warning::" in out
        assert "trails upstream" in out

    def test_stale_cli_silent_when_pin_matches(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        _make_repo(tmp_path, pin="1.2.3")
        monkeypatch.setattr(
            uv_pin, "fetch_latest_uv_release", lambda: "1.2.3"
        )
        exit_code = uv_pin.main(["stale", "--repo-root", str(tmp_path)])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "::warning::" not in out
        assert "matches upstream" in out
