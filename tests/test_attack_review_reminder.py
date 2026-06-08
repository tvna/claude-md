"""Tests for ``scripts/attack_review_reminder.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import attack_review_reminder as arr
import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "attack-coverage-review-cadence.md"

_TEMPLATE = (
    f"{arr.BEGIN_MARKER}\n"
    "\n"
    "### One\n"
    "body one\n"
    "\n"
    "### Two\n"
    "body two\n"
    f"{arr.END_MARKER}\n"
)


def _runbook(template: str = _TEMPLATE) -> str:
    return f"# Heading\n\nprose before\n\n{template}\nprose after\n"


# ---------------------------------------------------------------------------
# extract_template_block
# ---------------------------------------------------------------------------


class TestExtractTemplateBlock:
    def test_returns_block_including_both_markers(self) -> None:
        block = arr.extract_template_block(_runbook())
        assert block.startswith(arr.BEGIN_MARKER)
        assert arr.END_MARKER in block
        assert "### One" in block
        assert "prose before" not in block
        assert "prose after" not in block

    def test_missing_begin_marker_raises(self) -> None:
        text = "# Heading\n\n### One\n\n" + arr.END_MARKER + "\n"
        with pytest.raises(ValueError, match="begin marker"):
            arr.extract_template_block(text)

    def test_missing_end_marker_raises(self) -> None:
        text = "# Heading\n\n" + arr.BEGIN_MARKER + "\n### One\nno closing marker\n"
        with pytest.raises(ValueError, match="end marker"):
            arr.extract_template_block(text)

    def test_marker_only_block_is_returned(self) -> None:
        text = arr.BEGIN_MARKER + "\n" + arr.END_MARKER + "\n"
        block = arr.extract_template_block(text)
        assert arr.BEGIN_MARKER in block
        assert arr.END_MARKER in block

    def test_first_end_marker_closes_range(self) -> None:
        text = (
            arr.BEGIN_MARKER
            + "\n### One\n"
            + arr.END_MARKER
            + "\n### Two\n"
            + arr.END_MARKER
            + "\n"
        )
        block = arr.extract_template_block(text)
        assert "### One" in block
        assert "### Two" not in block


# ---------------------------------------------------------------------------
# count_h3
# ---------------------------------------------------------------------------


class TestCountH3:
    def test_counts_line_start_h3_only(self) -> None:
        text = "### A\nnot ### inline\n#### B is h4\n### C\n"
        assert arr.count_h3(text) == 2

    def test_real_runbook_template_has_seven_h3(self) -> None:
        block = arr.extract_template_block(REAL_RUNBOOK.read_text(encoding="utf-8"))
        assert arr.count_h3(block) == arr.EXPECTED_H3


# ---------------------------------------------------------------------------
# build_comment
# ---------------------------------------------------------------------------


class TestBuildComment:
    def test_contains_header_date_links_and_template(self) -> None:
        comment = arr.build_comment(
            template_text="### Body\n",
            run_date="2026-06-02",
            repo="tvna/claude-md",
            runbook_path="docs/runbooks/attack-coverage-review-cadence.md",
            run_url="https://example/run/1",
        )
        assert "## ATT&CK coverage review reminder -- 2026-06-02" in comment
        assert "https://github.com/tvna/claude-md/blob/main/docs/runbooks/attack-coverage-review-cadence.md" in comment
        assert "Workflow run: https://example/run/1." in comment
        assert "Refs #184." in comment
        assert comment.rstrip().endswith("### Body")


# ---------------------------------------------------------------------------
# _cmd_assemble / main
# ---------------------------------------------------------------------------


class TestCmdAssemble:
    def test_writes_out_and_summary(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        runbook = tmp_path / "rb.md"
        runbook.write_text(_runbook(), encoding="utf-8")
        out = tmp_path / "comment.md"
        summary = tmp_path / "summary.md"
        rc = arr.main(
            [
                "assemble",
                "--runbook",
                str(runbook),
                "--out",
                str(out),
                "--summary-file",
                str(summary),
                "--repo",
                "tvna/claude-md",
                "--run-url",
                "https://example/run/2",
                "--run-date",
                "2026-06-02",
                "--expected-h3",
                "2",
            ]
        )
        assert rc == 0
        comment = out.read_text(encoding="utf-8")
        assert "ATT&CK coverage review reminder -- 2026-06-02" in comment
        assert "### One" in comment
        summary_text = summary.read_text(encoding="utf-8")
        assert "Assembled review reminder comment" in summary_text
        assert "```markdown" in summary_text
        assert "Assembled review reminder comment ->" in capsys.readouterr().out

    def test_default_run_date_used_when_omitted(self, tmp_path: Path) -> None:
        runbook = tmp_path / "rb.md"
        runbook.write_text(_runbook(), encoding="utf-8")
        out = tmp_path / "comment.md"
        rc = arr.main(
            [
                "assemble",
                "--runbook",
                str(runbook),
                "--out",
                str(out),
                "--repo",
                "r/r",
                "--run-url",
                "u",
                "--expected-h3",
                "2",
            ]
        )
        assert rc == 0
        # Header date is YYYY-MM-DD shaped.
        first_line = out.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("## ATT&CK coverage review reminder -- ")
        date_token = first_line.rsplit("-- ", 1)[1]
        assert len(date_token) == 10 and date_token[4] == "-" and date_token[7] == "-"

    def test_exits_1_when_h3_count_mismatch(self, tmp_path: Path) -> None:
        runbook = tmp_path / "rb.md"
        runbook.write_text(_runbook(), encoding="utf-8")  # template has 2 H3 sections
        out = tmp_path / "comment.md"
        rc = arr.main(
            [
                "assemble",
                "--runbook",
                str(runbook),
                "--out",
                str(out),
                "--repo",
                "r/r",
                "--run-url",
                "u",
                "--expected-h3",
                "7",
            ]
        )
        assert rc == 1
        assert not out.exists()

    def test_exits_1_when_markers_missing(self, tmp_path: Path) -> None:
        runbook = tmp_path / "rb.md"
        runbook.write_text("# No markers here\n\n### One\n", encoding="utf-8")
        out = tmp_path / "comment.md"
        rc = arr.main(
            [
                "assemble",
                "--runbook",
                str(runbook),
                "--out",
                str(out),
                "--repo",
                "r/r",
                "--run-url",
                "u",
            ]
        )
        assert rc == 1
        assert not out.exists()

    def test_exits_1_when_runbook_unreadable(self, tmp_path: Path) -> None:
        rc = arr.main(
            [
                "assemble",
                "--runbook",
                str(tmp_path / "does-not-exist.md"),
                "--out",
                str(tmp_path / "comment.md"),
                "--repo",
                "r/r",
                "--run-url",
                "u",
            ]
        )
        assert rc == 1
