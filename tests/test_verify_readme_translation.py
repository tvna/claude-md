"""Tests for ``scripts/verify_readme_translation.py``.

Mirrors the table-driven style of ``tests/test_preflight_pr_single_commit.py``:
pure functions get parametrize cases, the subprocess boundary is
exercised via a fake ``runner`` injected through the kwarg the
production code already exposes.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import verify_readme_translation as gate


def _fake_runner(stdout: str = "", returncode: int = 0):
    """Return a callable mimicking ``subprocess.run(..., check=True)``.

    The production ``_run`` calls ``runner(cmd, capture_output=True,
    text=True, timeout=..., check=True)``. ``check=True`` makes the real
    subprocess raise on non-zero exit; we mirror that so the fail-loud
    path in ``main()`` is reachable from tests.
    """

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if kwargs.get("check") and returncode != 0:
            raise subprocess.CalledProcessError(
                returncode, cmd, output=stdout, stderr=""
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=returncode, stdout=stdout, stderr=""
        )

    return runner


# ---------------------------------------------------------------------------
# resolve_base
# ---------------------------------------------------------------------------


class TestResolveBase:
    def test_explicit_base_ref_wins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/feature")
        monkeypatch.setenv("GITHUB_BASE_REF", "main")
        assert gate.resolve_base() == "origin/feature"

    def test_github_base_ref_used_when_explicit_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.setenv("GITHUB_BASE_REF", "main")
        assert gate.resolve_base() == "origin/main"

    def test_fallback_to_origin_main(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
        assert gate.resolve_base() == "origin/main"

    def test_empty_env_strings_treated_as_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BASE_REF", "")
        monkeypatch.setenv("GITHUB_BASE_REF", "")
        assert gate.resolve_base() == "origin/main"


# ---------------------------------------------------------------------------
# changed_readmes
# ---------------------------------------------------------------------------


class TestChangedReadmes:
    def test_returns_empty_when_no_readme_touched(self) -> None:
        runner = _fake_runner("docs/INDEX.md\nscripts/foo.py\n")
        assert gate.changed_readmes("origin/main", runner=runner) == frozenset()

    def test_detects_english_only(self) -> None:
        runner = _fake_runner("README.md\nscripts/foo.py\n")
        assert gate.changed_readmes("origin/main", runner=runner) == frozenset(
            {"README.md"}
        )

    def test_detects_all_three(self) -> None:
        runner = _fake_runner(
            "README.md\nREADME.ja.md\nREADME.zh.md\nunrelated.md\n"
        )
        assert gate.changed_readmes("origin/main", runner=runner) == frozenset(
            {"README.md", "README.ja.md", "README.zh.md"}
        )

    def test_other_files_filtered_out(self) -> None:
        runner = _fake_runner(
            "README.markdown\nREADME.md.bak\nsub/README.md\nREADME.md\n"
        )
        # Only the exact top-level paths in README_PATHS qualify.
        assert gate.changed_readmes("origin/main", runner=runner) == frozenset(
            {"README.md"}
        )

    def test_strips_whitespace_and_skips_blank_lines(self) -> None:
        runner = _fake_runner("  README.md  \n\n   \nREADME.ja.md\n")
        assert gate.changed_readmes("origin/main", runner=runner) == frozenset(
            {"README.md", "README.ja.md"}
        )

    def test_subprocess_failure_propagates(self) -> None:
        runner = _fake_runner(returncode=128)
        with pytest.raises(subprocess.CalledProcessError):
            gate.changed_readmes("origin/nonexistent", runner=runner)


# ---------------------------------------------------------------------------
# body_has_skip_marker
# ---------------------------------------------------------------------------


class TestBodyHasSkipMarker:
    def test_none_returns_false(self) -> None:
        assert gate.body_has_skip_marker(None) is False

    def test_empty_returns_false(self) -> None:
        assert gate.body_has_skip_marker("") is False

    def test_exact_marker_returns_true(self) -> None:
        assert (
            gate.body_has_skip_marker(
                "Some text\n<!-- readme-translation-ack -->\nmore"
            )
            is True
        )

    def test_marker_without_inner_spaces(self) -> None:
        assert (
            gate.body_has_skip_marker("<!--readme-translation-ack-->")
            is True
        )

    def test_marker_with_extra_whitespace(self) -> None:
        assert (
            gate.body_has_skip_marker(
                "<!--   readme-translation-ack    -->"
            )
            is True
        )

    def test_marker_case_insensitive(self) -> None:
        assert (
            gate.body_has_skip_marker("<!-- Readme-Translation-ACK -->")
            is True
        )

    def test_similar_string_outside_comment_returns_false(self) -> None:
        # Without the comment delimiters the marker does not apply.
        assert (
            gate.body_has_skip_marker("readme-translation-ack on its own")
            is False
        )

    def test_partial_marker_returns_false(self) -> None:
        assert (
            gate.body_has_skip_marker("<!-- readme-translation -->") is False
        )


# ---------------------------------------------------------------------------
# evaluate_drift
# ---------------------------------------------------------------------------


class TestEvaluateDrift:
    def test_no_readme_changed(self) -> None:
        assert gate.evaluate_drift(frozenset(), skip=False) == (0, [])

    def test_all_three_changed(self) -> None:
        changed = frozenset(
            {"README.md", "README.ja.md", "README.zh.md"}
        )
        assert gate.evaluate_drift(changed, skip=False) == (0, [])

    def test_ja_only_changed_passes(self) -> None:
        # Translation-only PRs are intentionally not blocked.
        assert gate.evaluate_drift(
            frozenset({"README.ja.md"}), skip=False
        ) == (0, [])

    def test_zh_only_changed_passes(self) -> None:
        assert gate.evaluate_drift(
            frozenset({"README.zh.md"}), skip=False
        ) == (0, [])

    def test_english_only_no_skip_fails(self) -> None:
        code, errors = gate.evaluate_drift(
            frozenset({"README.md"}), skip=False
        )
        assert code == 1
        assert len(errors) == 1
        assert "README.ja.md" in errors[0]
        assert "README.zh.md" in errors[0]
        assert errors[0].startswith("::error::")

    def test_english_plus_ja_only_no_skip_fails_listing_zh(self) -> None:
        code, errors = gate.evaluate_drift(
            frozenset({"README.md", "README.ja.md"}), skip=False
        )
        assert code == 1
        assert "README.zh.md" in errors[0]
        assert "README.ja.md" not in errors[0]

    def test_english_only_with_skip_passes(self) -> None:
        assert gate.evaluate_drift(
            frozenset({"README.md"}), skip=True
        ) == (0, [])


# ---------------------------------------------------------------------------
# main (CLI exit codes)
# ---------------------------------------------------------------------------


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch, stdout: str, returncode: int = 0
) -> None:
    monkeypatch.setattr(
        gate, "_run", lambda cmd, *, runner=None: _fake_runner(stdout, returncode)(cmd, check=True)
    )


class TestMainExitCode:
    def test_happy_path_all_three_changed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_runner(
            monkeypatch, "README.md\nREADME.ja.md\nREADME.zh.md\n"
        )
        body_file = tmp_path / "body.md"
        body_file.write_text("nothing special", encoding="utf-8")
        code = gate.main(
            [
                "verify",
                "--base-ref",
                "origin/main",
                "--body-file",
                str(body_file),
            ]
        )
        assert code == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out

    def test_drift_detected_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_runner(monkeypatch, "README.md\n")
        body_file = tmp_path / "body.md"
        body_file.write_text("no marker here", encoding="utf-8")
        code = gate.main(
            [
                "verify",
                "--base-ref",
                "origin/main",
                "--body-file",
                str(body_file),
            ]
        )
        assert code == 1
        captured = capsys.readouterr()
        assert "::error::" in captured.err
        assert "README.ja.md" in captured.err

    def test_skip_marker_short_circuits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_runner(monkeypatch, "README.md\n")
        body_file = tmp_path / "body.md"
        body_file.write_text(
            "Reason: translation pending.\n"
            "<!-- readme-translation-ack -->\n",
            encoding="utf-8",
        )
        code = gate.main(
            [
                "verify",
                "--base-ref",
                "origin/main",
                "--body-file",
                str(body_file),
            ]
        )
        assert code == 0
        captured = capsys.readouterr()
        assert "opt-out marker present" in captured.out

    def test_no_readme_changed_passes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_runner(monkeypatch, "scripts/foo.py\n")
        body_file = tmp_path / "body.md"
        body_file.write_text("", encoding="utf-8")
        code = gate.main(
            [
                "verify",
                "--base-ref",
                "origin/main",
                "--body-file",
                str(body_file),
            ]
        )
        assert code == 0
        captured = capsys.readouterr()
        assert "no README files modified" in captured.out

    def test_translation_only_change_passes_with_distinct_message(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_runner(monkeypatch, "README.ja.md\nREADME.zh.md\n")
        body_file = tmp_path / "body.md"
        body_file.write_text("", encoding="utf-8")
        code = gate.main(
            [
                "verify",
                "--base-ref",
                "origin/main",
                "--body-file",
                str(body_file),
            ]
        )
        assert code == 0
        captured = capsys.readouterr()
        assert "translation-only change" in captured.out
        assert "README.ja.md" in captured.out
        assert "README.zh.md" in captured.out

    def test_missing_body_file_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_runner(monkeypatch, "README.md\nREADME.ja.md\nREADME.zh.md\n")
        missing = tmp_path / "does-not-exist.md"
        code = gate.main(
            [
                "verify",
                "--base-ref",
                "origin/main",
                "--body-file",
                str(missing),
            ]
        )
        assert code == 1
        captured = capsys.readouterr()
        assert "body file not found" in captured.err

    def test_env_var_PR_BODY_fallback_works(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_runner(monkeypatch, "README.md\n")
        monkeypatch.setenv("PR_BODY", "<!-- readme-translation-ack -->")
        code = gate.main(["verify", "--base-ref", "origin/main"])
        assert code == 0
        captured = capsys.readouterr()
        assert "opt-out marker present" in captured.out

    def test_env_var_BASE_REF_fallback_works(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _patch_runner(
            monkeypatch, "README.md\nREADME.ja.md\nREADME.zh.md\n"
        )
        monkeypatch.setenv("BASE_REF", "origin/main")
        body_file = tmp_path / "body.md"
        body_file.write_text("", encoding="utf-8")
        code = gate.main(
            ["verify", "--body-file", str(body_file)]
        )
        assert code == 0

    def test_git_failure_returns_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_runner(monkeypatch, "", returncode=128)
        body_file = tmp_path / "body.md"
        body_file.write_text("", encoding="utf-8")
        code = gate.main(
            [
                "verify",
                "--base-ref",
                "origin/nonexistent",
                "--body-file",
                str(body_file),
            ]
        )
        assert code == 1
        captured = capsys.readouterr()
        assert "git invocation failed" in captured.err
