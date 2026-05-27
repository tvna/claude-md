"""Tests for ``scripts/scan_apm_portability.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_apm_portability as sap

pytestmark = pytest.mark.shard_default
REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# scan_line
# ---------------------------------------------------------------------------


class TestScanLine:
    @pytest.mark.parametrize(
        "line,expected",
        [
            ("see scripts/foo.py for details", ["scripts/"]),
            ("path .github/workflows/x.yml", [".github/"]),
            ("read CODEOWNERS for owners", ["CODEOWNERS"]),
            ("use mcp__github__issue_read", ["mcp__github__"]),
            (
                "ref plan_language_context.py for plan-mode language",
                ["plan_language_context.py"],
            ),
            (
                "see preflight_non_ascii.py for hook details",
                ["preflight_non_ascii.py"],
            ),
            ("update owners.yaml mapping", ["owners.yaml"]),
        ],
    )
    def test_token_detected(
        self, line: str, expected: list[str]
    ) -> None:
        assert sap.scan_line(line) == expected

    @pytest.mark.parametrize(
        "line",
        [
            # bare "scripts" without trailing slash must not match
            "running scripted workflows and APIs end-to-end",
            # github.com URLs include ".github" without the slash
            "see https://github.com/tvna/claude-md/issues/230",
            # legitimate APM ecosystem reference
            "manage modules declaratively (nix, uv, microsoft/apm)",
            # generic English
            "the apm compile output is regenerated",
            # empty / whitespace
            "",
            "   ",
            # markdown heading
            "## 3. Use Git Ecosystem Effectively",
            # the documented escape hatch with no token present
            "<!-- portability-ack -->",
        ],
    )
    def test_no_false_positive(self, line: str) -> None:
        assert sap.scan_line(line) == []

    def test_multiple_tokens_in_one_line(self) -> None:
        line = "see scripts/foo and CODEOWNERS for routing"
        assert sorted(sap.scan_line(line)) == sorted(
            ["scripts/", "CODEOWNERS"]
        )

    def test_ack_marker_skips_line_even_with_token(self) -> None:
        line = "see scripts/foo.py <!-- portability-ack -->"
        assert sap.scan_line(line) == []


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------


class TestScanText:
    def test_empty(self) -> None:
        assert sap.scan_text("") == []

    def test_clean_text(self) -> None:
        text = "line one\nline two\nthird line\n"
        assert sap.scan_text(text) == []

    def test_reports_line_numbers_1_based(self) -> None:
        text = "clean line\nbad scripts/x.py here\nclean again\n"
        assert sap.scan_text(text) == [(2, "scripts/")]

    def test_multiple_violations_across_lines(self) -> None:
        text = "first scripts/a\nsecond .github/wf\n"
        hits = sap.scan_text(text)
        assert (1, "scripts/") in hits
        assert (2, ".github/") in hits
        assert len(hits) == 2

    def test_ack_marker_excludes_only_marked_line(self) -> None:
        text = (
            "bad scripts/a here\n"
            "ack scripts/b <!-- portability-ack -->\n"
            "bad scripts/c here\n"
        )
        hits = sap.scan_text(text)
        line_nums = {n for n, _ in hits}
        assert line_nums == {1, 3}


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------


class TestScanFile:
    def test_clean_file(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.md"
        f.write_text("plain content\n", encoding="utf-8")
        assert sap.scan_file(f) == []

    def test_dirty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "dirty.md"
        f.write_text("see scripts/x.py\n", encoding="utf-8")
        assert sap.scan_file(f) == [(1, "scripts/")]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestMain:
    def test_verify_clean_file_returns_zero(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        f = tmp_path / "clean.md"
        f.write_text("plain content\n", encoding="utf-8")
        rc = sap.main(["verify", "--path", str(f)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "OK: no repo-local references" in captured.out

    def test_verify_dirty_file_returns_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        f = tmp_path / "dirty.md"
        f.write_text("see scripts/x.py here\n", encoding="utf-8")
        rc = sap.main(["verify", "--path", str(f)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "scripts/" in captured.err
        assert str(f) in captured.err

    def test_missing_path_reports_and_fails(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = sap.main(
            ["verify", "--path", str(tmp_path / "does-not-exist.md")]
        )
        captured = capsys.readouterr()
        assert rc == 1
        assert "missing scan target" in captured.err

    def test_no_path_returns_two(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = sap.main(["verify"])
        captured = capsys.readouterr()
        assert rc == 2
        assert "at least one --path is required" in captured.err

    def test_multiple_paths_both_clean(self, tmp_path: Path) -> None:
        a = tmp_path / "a.md"
        a.write_text("clean\n", encoding="utf-8")
        b = tmp_path / "b.md"
        b.write_text("also clean\n", encoding="utf-8")
        rc = sap.main(["verify", "--path", str(a), "--path", str(b)])
        assert rc == 0

    def test_multiple_paths_one_dirty(self, tmp_path: Path) -> None:
        a = tmp_path / "a.md"
        a.write_text("clean\n", encoding="utf-8")
        b = tmp_path / "b.md"
        b.write_text("see scripts/x.py\n", encoding="utf-8")
        rc = sap.main(["verify", "--path", str(a), "--path", str(b)])
        assert rc == 1


# ---------------------------------------------------------------------------
# Regression guard: real repo artifacts must pass
# ---------------------------------------------------------------------------


class TestRepoArtifacts:
    @pytest.mark.parametrize(
        "rel",
        [
            ".apm/instructions/master.instructions.md",
            "CLAUDE.md",
            "AGENTS.md",
        ],
    )
    def test_no_violations_in_repo_artifact(self, rel: str) -> None:
        path = REPO_ROOT / rel
        assert path.exists(), f"expected artifact missing: {path}"
        hits = sap.scan_file(path)
        assert hits == [], (
            f"unexpected portability violations in {rel}: {hits}"
        )
