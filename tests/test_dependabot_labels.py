"""Tests for ``scripts/dependabot_labels.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.

Mirrors the structure of ``tests/test_issue_link.py``: pure
functions get focused unit tests; the CLI/file boundary is exercised
via tmp_path. See #138 (deterministic harness for dependabot label
drift) and #2499 (label-policy.toml is the single label SoT).
"""

from __future__ import annotations

from pathlib import Path

import dependabot_labels as dl
import pytest

pytestmark = pytest.mark.shard_ci_ops
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
# load_sot_label_names_from_policy
# ---------------------------------------------------------------------------


class TestLoadSotLabelNamesFromPolicy:
    def test_matches_synthetic_fixture(self, tmp_path: Path) -> None:
        policy_path = tmp_path / "label-policy.toml"
        policy_path.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "ops:dependencies"',
                    'status = "keep"',
                    'description = "Dependency update workflow state."',
                    'color = "0366d6"',
                ]
            ),
            encoding="utf-8",
        )
        names = dl.load_sot_label_names_from_policy(policy_path)

        assert names == {"ops:dependencies"}

    def test_status_add_excluded(self, tmp_path: Path) -> None:
        policy_path = tmp_path / "label-policy.toml"
        policy_path.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "ops:dependencies"',
                    'status = "keep"',
                    'description = "x"',
                    'color = "0366d6"',
                    "",
                    "[[labels]]",
                    'name = "area:apm"',
                    'status = "add"',
                    'description = "Design-only, not live yet."',
                    'color = "5319e7"',
                ]
            ),
            encoding="utf-8",
        )
        names = dl.load_sot_label_names_from_policy(policy_path)

        assert names == {"ops:dependencies"}


# ---------------------------------------------------------------------------
# CLI: verify against the real repo files (regression guard)
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestVerifyRepoFiles:
    def test_repo_dependabot_labels_resolve_in_sot(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The actual files in this repo must not drift; this is the gate.

        If this test fails, either add the missing label to
        .github/label-policy.toml or remove it from .github/dependabot.yml.
        """
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(REPO_ROOT / ".github" / "dependabot.yml"),
                "--label-policy",
                str(REPO_ROOT / ".github" / "label-policy.toml"),
            ]
        )
        captured = capsys.readouterr()
        assert rc == 0, captured.out + captured.err


class TestVerifyCli:
    @staticmethod
    def _write_policy(path: Path, names: list[str]) -> None:
        blocks = []
        for name in names:
            blocks.append(
                "\n".join(
                    [
                        "[[labels]]",
                        f'name = "{name}"',
                        'status = "keep"',
                        'description = "x"',
                        'color = "0366d6"',
                    ]
                )
            )
        path.write_text("\n\n".join(blocks) or "", encoding="utf-8")

    def test_missing_dependabot_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        policy = tmp_path / "label-policy.toml"
        self._write_policy(policy, ["dependencies"])
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(tmp_path / "missing.yml"),
                "--label-policy",
                str(policy),
            ]
        )
        assert rc == 1
        assert "dependabot file not found" in capsys.readouterr().out

    def test_missing_policy_returns_1(
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
                "--label-policy",
                str(tmp_path / "missing.toml"),
            ]
        )
        assert rc == 1
        assert "label policy not found" in capsys.readouterr().out

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
        policy = tmp_path / "label-policy.toml"
        self._write_policy(policy, ["dependencies"])
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(dep),
                "--label-policy",
                str(policy),
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
        policy = tmp_path / "label-policy.toml"
        self._write_policy(policy, ["dependencies"])
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(dep),
                "--label-policy",
                str(policy),
            ]
        )
        assert rc == 0
        assert "all resolve" in capsys.readouterr().out

    def test_malformed_policy_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        dep = tmp_path / "dependabot.yml"
        dep.write_text("", encoding="utf-8")
        policy = tmp_path / "label-policy.toml"
        policy.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "dependencies"',
                    'status = "bogus"',
                    'description = "x"',
                    'color = "0366d6"',
                ]
            ),
            encoding="utf-8",
        )
        rc = dl.main(
            [
                "verify",
                "--dependabot",
                str(dep),
                "--label-policy",
                str(policy),
            ]
        )
        assert rc == 1
        assert "::error::" in capsys.readouterr().out


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["dependabot_labels", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("dependabot_labels", run_name="__main__")
    assert exc_info.value.code == 0
