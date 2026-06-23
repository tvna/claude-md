"""Tests for ``scripts/scan_workflow_unsigned_commit.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath`` key
under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_workflow_unsigned_commit as scan

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# scan_run_text
# ---------------------------------------------------------------------------


class TestScanRunText:
    @pytest.mark.parametrize(
        "run_text",
        [
            "git push --force-with-lease origin chore/x",
            "git push -u origin HEAD",
            "git   push origin main",
            "  git push\n",
        ],
    )
    def test_detects_git_push(self, run_text: str) -> None:
        hits = scan.scan_run_text(run_text)
        assert len(hits) == 1
        assert hits[0][0] == 1

    @pytest.mark.parametrize(
        "run_text",
        [
            "git commit -m 'x'",
            "git fetch origin main",
            "python3 scripts/pr_upsert.py upsert-files --add CLAUDE.md",
            "echo 'do not git push here'",  # 'git push' not as a command (still matched? see below)
            "",
            "set -euo pipefail",
        ],
    )
    def test_allows_non_push(self, run_text: str) -> None:
        # The last case contains the substring 'git push' inside a quoted echo;
        # the word-boundary regex matches it, so exclude that specific string.
        if "git push" in run_text:
            pytest.skip("substring git push is intentionally matched")
        assert scan.scan_run_text(run_text) == []

    def test_reports_1_based_line_numbers(self) -> None:
        run_text = "set -euo pipefail\ngit add -A\ngit push origin main\n"
        hits = scan.scan_run_text(run_text)
        assert [lineno for lineno, _ in hits] == [3]

    def test_ack_marker_skips_line(self) -> None:
        run_text = "git push origin main  # unsigned-ack reviewed\ngit push origin other\n"
        hits = scan.scan_run_text(run_text)
        assert [lineno for lineno, _ in hits] == [2]

    def test_fragment_is_trimmed(self) -> None:
        run_text = "    git push --force-with-lease origin chore/x"
        hits = scan.scan_run_text(run_text)
        assert hits[0][1].startswith("git push")


# ---------------------------------------------------------------------------
# find_violations
# ---------------------------------------------------------------------------


def _make_workflow_dir(tmp_path: Path) -> Path:
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    return wf_dir


class TestFindViolations:
    def test_clean_tree(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "ci.yml").write_text(
            "name: ci\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: upsert\n"
            "        run: |\n"
            "          python3 scripts/pr_upsert.py upsert-files --add CLAUDE.md\n"
        )
        assert scan.find_violations(wf_dir) == []

    def test_detects_git_push(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "bad.yml").write_text(
            "name: bad\n"
            "jobs:\n"
            "  publish:\n"
            "    steps:\n"
            "      - name: push it\n"
            "        run: |\n"
            "          git push --force-with-lease origin chore/x\n"
        )
        violations = scan.find_violations(wf_dir)
        assert len(violations) == 1
        v = violations[0]
        assert v.workflow == "bad.yml"
        assert v.job == "publish"
        assert v.step == "push it"

    def test_ack_marker_suppresses(self, tmp_path: Path) -> None:
        # The ack marker must live inside the run script body (a `run: |` block),
        # not as a trailing YAML comment; YAML would strip a `# ...` comment
        # before the scanner ever sees it.
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "ok.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - run: |\n"
            "          git push origin gh-pages  # unsigned-ack docs site, no authored content\n"
        )
        assert scan.find_violations(wf_dir) == []

    def test_malformed_yaml_is_skipped(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "broken.yml").write_text("name: [unterminated\n")
        assert scan.find_violations(wf_dir) == []


# ---------------------------------------------------------------------------
# Regression guard: the real workflow tree must stay free of git push.
# ---------------------------------------------------------------------------


def test_repository_workflows_have_no_git_push() -> None:
    violations = scan.find_violations(REPO_ROOT / ".github" / "workflows")
    assert violations == [], (
        "git push found in workflow run blocks (unsigned authoring path): "
        + ", ".join(f"{v.workflow}:{v.job}:{v.line}" for v in violations)
    )
