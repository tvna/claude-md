"""Tests for ``scripts/dependabot_labels.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.

Mirrors the structure of ``tests/test_issue_link.py``: pure
functions get focused unit tests; the CLI/file boundary is exercised
via tmp_path. See #138 (deterministic harness for dependabot label
drift).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dependabot_labels as dl


# ---------------------------------------------------------------------------
# parse_dependabot_labels
# ---------------------------------------------------------------------------


class TestParseDependabotLabels:
    def test_empty(self) -> None:
        assert dl.parse_dependabot_labels("") == []

    def test_no_labels_block(self) -> None:
        src = "version: 2\nupdates:\n  - package-ecosystem: 'uv'\n"
        assert dl.parse_dependabot_labels(src) == []

    def test_single_block_double_quoted(self) -> None:
        src = (
            "version: 2\n"
            "updates:\n"
            "  - package-ecosystem: \"uv\"\n"
            "    labels:\n"
            "      - \"dependencies\"\n"
        )
        assert dl.parse_dependabot_labels(src) == ["dependencies"]

    def test_single_block_single_quoted(self) -> None:
        src = "    labels:\n      - 'dependencies'\n"
        assert dl.parse_dependabot_labels(src) == ["dependencies"]

    def test_single_block_unquoted(self) -> None:
        src = "    labels:\n      - dependencies\n"
        assert dl.parse_dependabot_labels(src) == ["dependencies"]

    def test_multiple_items(self) -> None:
        src = (
            "    labels:\n"
            "      - \"dependencies\"\n"
            "      - \"chore\"\n"
            "      - \"security\"\n"
        )
        assert dl.parse_dependabot_labels(src) == [
            "dependencies",
            "chore",
            "security",
        ]

    def test_multiple_blocks_both_contribute(self) -> None:
        src = (
            "updates:\n"
            "  - package-ecosystem: \"github-actions\"\n"
            "    labels:\n"
            "      - \"dependencies\"\n"
            "    commit-message:\n"
            "      prefix: \"chore\"\n"
            "\n"
            "  - package-ecosystem: \"uv\"\n"
            "    labels:\n"
            "      - \"dependencies\"\n"
            "      - \"deps:python\"\n"
        )
        assert dl.parse_dependabot_labels(src) == [
            "dependencies",
            "dependencies",
            "deps:python",
        ]

    def test_block_ends_at_sibling_key(self) -> None:
        src = (
            "    labels:\n"
            "      - \"a\"\n"
            "      - \"b\"\n"
            "    commit-message:\n"
            "      prefix: \"chore\"\n"
        )
        assert dl.parse_dependabot_labels(src) == ["a", "b"]

    def test_blank_lines_inside_block_do_not_terminate(self) -> None:
        src = (
            "    labels:\n"
            "      - \"a\"\n"
            "\n"
            "      - \"b\"\n"
        )
        assert dl.parse_dependabot_labels(src) == ["a", "b"]

    def test_full_line_comments_ignored(self) -> None:
        src = (
            "# top-level comment\n"
            "    labels:\n"
            "      # inline-list comment\n"
            "      - \"dependencies\"\n"
        )
        assert dl.parse_dependabot_labels(src) == ["dependencies"]

    def test_labels_substring_key_not_matched(self) -> None:
        # Keys like ``extra-labels:`` must not trigger the parser.
        src = (
            "    extra-labels:\n"
            "      - \"never\"\n"
            "    labels:\n"
            "      - \"yes\"\n"
        )
        assert dl.parse_dependabot_labels(src) == ["yes"]


# ---------------------------------------------------------------------------
# load_sot_label_names
# ---------------------------------------------------------------------------


class TestLoadSotLabelNames:
    def test_empty_array(self) -> None:
        assert dl.load_sot_label_names("[]") == set()

    def test_single_entry(self) -> None:
        src = json.dumps([{"name": "dependencies", "color": "0366d6", "description": "x"}])
        assert dl.load_sot_label_names(src) == {"dependencies"}

    def test_multiple_entries(self) -> None:
        src = json.dumps(
            [
                {"name": "a", "color": "000000", "description": ""},
                {"name": "b", "color": "ffffff", "description": ""},
            ]
        )
        assert dl.load_sot_label_names(src) == {"a", "b"}

    def test_not_a_list_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON array"):
            dl.load_sot_label_names('{"name": "x"}')

    def test_entry_missing_name_raises(self) -> None:
        with pytest.raises(ValueError, match="missing non-empty 'name'"):
            dl.load_sot_label_names('[{"color": "000000"}]')

    def test_entry_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="missing non-empty 'name'"):
            dl.load_sot_label_names('[{"name": ""}]')

    def test_entry_not_object_raises(self) -> None:
        with pytest.raises(ValueError, match="must be objects"):
            dl.load_sot_label_names('["just-a-string"]')


# ---------------------------------------------------------------------------
# find_drift
# ---------------------------------------------------------------------------


class TestFindDrift:
    def test_no_drift(self) -> None:
        assert dl.find_drift(["a", "b"], {"a", "b", "c"}) == []

    def test_one_missing(self) -> None:
        assert dl.find_drift(["a", "ghost"], {"a"}) == ["ghost"]

    def test_duplicates_collapsed(self) -> None:
        assert dl.find_drift(["x", "x", "y"], set()) == ["x", "y"]

    def test_sorted(self) -> None:
        assert dl.find_drift(["z", "a", "m"], set()) == ["a", "m", "z"]


# ---------------------------------------------------------------------------
# CLI: verify against the real repo files (regression guard)
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestVerifyRepoFiles:
    def test_repo_dependabot_labels_resolve_in_sot(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The actual files in this repo must not drift -- this is the gate.

        If this test fails, either add the missing label to
        .github/labels.json or remove it from .github/dependabot.yml.
        """
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(REPO_ROOT / ".github" / "dependabot.yml"),
                "--labels",
                str(REPO_ROOT / ".github" / "labels.json"),
            ]
        )
        captured = capsys.readouterr()
        assert rc == 0, captured.out + captured.err


class TestVerifyCli:
    def test_missing_dependabot_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        labels = tmp_path / "labels.json"
        labels.write_text("[]", encoding="utf-8")
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(tmp_path / "missing.yml"),
                "--labels",
                str(labels),
            ]
        )
        assert rc == 1
        assert "dependabot file not found" in capsys.readouterr().out

    def test_missing_labels_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        dep = tmp_path / "dependabot.yml"
        dep.write_text("", encoding="utf-8")
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(dep),
                "--labels",
                str(tmp_path / "missing.json"),
            ]
        )
        assert rc == 1
        assert "labels SoT not found" in capsys.readouterr().out

    def test_drift_detected_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        dep = tmp_path / "dependabot.yml"
        dep.write_text(
            "    labels:\n      - \"ghost\"\n",
            encoding="utf-8",
        )
        labels = tmp_path / "labels.json"
        labels.write_text("[]", encoding="utf-8")
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(dep),
                "--labels",
                str(labels),
            ]
        )
        assert rc == 1
        out = capsys.readouterr().out
        assert "ghost" in out
        assert "drift" in out

    def test_no_drift_returns_0(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        dep = tmp_path / "dependabot.yml"
        dep.write_text(
            "    labels:\n      - \"dependencies\"\n",
            encoding="utf-8",
        )
        labels = tmp_path / "labels.json"
        labels.write_text(
            json.dumps(
                [{"name": "dependencies", "color": "0366d6", "description": "x"}]
            ),
            encoding="utf-8",
        )
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(dep),
                "--labels",
                str(labels),
            ]
        )
        assert rc == 0
        assert "all resolve" in capsys.readouterr().out

    def test_malformed_labels_json_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        dep = tmp_path / "dependabot.yml"
        dep.write_text("", encoding="utf-8")
        labels = tmp_path / "labels.json"
        labels.write_text("{not json", encoding="utf-8")
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(dep),
                "--labels",
                str(labels),
            ]
        )
        assert rc == 1
        assert "::error::" in capsys.readouterr().out
