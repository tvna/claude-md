"""Tests for ``scripts/scan_workflow_injection.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_workflow_injection

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# scan_run_text
# ---------------------------------------------------------------------------


class TestScanRunText:
    @pytest.mark.parametrize(
        "run_text",
        [
            'echo "${{ github.event.issue.title }}"',
            'echo "${{ github.event.pull_request.body }}"',
            'NAME=${{ github.event.comment.body }}',
            'git checkout ${{ github.head_ref }}',
            'echo ${{ github.head_commit.message }}',
            "echo ${{   github.event.issue.title   }}",
        ],
    )
    def test_detects_untrusted_context(self, run_text: str) -> None:
        hits = scan_workflow_injection.scan_run_text(run_text)
        assert len(hits) == 1
        assert hits[0][0] == 1

    @pytest.mark.parametrize(
        "run_text",
        [
            # env-name enum, not free text (no trailing dot after event)
            'echo "${{ github.event_name }}"',
            # safe contexts
            'echo "${{ github.ref }}"',
            'echo "${{ github.sha }}"',
            'echo "${{ github.repository }}"',
            'echo "${{ github.actor }}"',
            'echo "${{ github.run_id }}"',
            # dispatch inputs are out of scope by design
            'echo "${{ inputs.measure_issue_number }}"',
            'echo "${{ inputs.ruleset }}"',
            # plain shell referencing an env var (the safe pattern)
            'echo "$TITLE"',
            "",
            "set -euo pipefail",
        ],
    )
    def test_allows_safe_and_out_of_scope(self, run_text: str) -> None:
        assert scan_workflow_injection.scan_run_text(run_text) == []

    def test_reports_1_based_line_numbers(self) -> None:
        run_text = (
            "set -euo pipefail\n"
            'echo "$SAFE"\n'
            'echo "${{ github.event.issue.title }}"\n'
        )
        hits = scan_workflow_injection.scan_run_text(run_text)
        assert [lineno for lineno, _ in hits] == [3]

    def test_multiple_hits_same_block(self) -> None:
        run_text = (
            'echo "${{ github.event.issue.title }}"\n'
            'echo "${{ github.head_ref }}"\n'
        )
        hits = scan_workflow_injection.scan_run_text(run_text)
        assert [lineno for lineno, _ in hits] == [1, 2]

    def test_ack_marker_skips_line(self) -> None:
        run_text = (
            'echo "${{ github.event.issue.title }}"  # inject-ack reviewed\n'
            'echo "${{ github.head_ref }}"\n'
        )
        hits = scan_workflow_injection.scan_run_text(run_text)
        assert [lineno for lineno, _ in hits] == [2]

    def test_fragment_is_trimmed(self) -> None:
        run_text = '    echo "${{ github.event.issue.title }}" rest'
        hits = scan_workflow_injection.scan_run_text(run_text)
        assert hits[0][1].startswith("${{ github.event.issue.title")


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
            "      - name: echo\n"
            "        env:\n"
            "          TITLE: ${{ github.event.issue.title }}\n"
            "        run: |\n"
            '          echo "$TITLE"\n'
        )
        assert scan_workflow_injection.find_violations(wf_dir) == []

    def test_detects_inline_event_interpolation(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "ci.yml").write_text(
            "name: ci\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: bad\n"
            "        run: |\n"
            '          echo "${{ github.event.issue.title }}"\n'
        )
        violations = scan_workflow_injection.find_violations(wf_dir)
        assert len(violations) == 1
        v = violations[0]
        assert v.workflow == "ci.yml"
        assert v.job == "build"
        assert v.step == "bad"

    def test_unnamed_step_has_empty_step_name(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "ci.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - run: echo ${{ github.head_ref }}\n"
        )
        violations = scan_workflow_injection.find_violations(wf_dir)
        assert violations[0].step == ""

    def test_malformed_yaml_is_skipped(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "broken.yml").write_text("name: [unterminated\n")
        assert scan_workflow_injection.find_violations(wf_dir) == []

    def test_non_dict_top_level_skipped(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "list.yml").write_text("- just\n- a\n- list\n")
        assert scan_workflow_injection.find_violations(wf_dir) == []

    def test_non_dict_jobs_and_steps_skipped(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "a.yml").write_text("jobs: not-a-dict\n")
        (wf_dir / "b.yml").write_text(
            "jobs:\n  build:\n    steps: not-a-list\n"
        )
        (wf_dir / "c.yml").write_text(
            "jobs:\n  build:\n    steps:\n      - just-a-string\n"
        )
        (wf_dir / "d.yml").write_text(
            "jobs:\n  build: not-a-dict\n"
        )
        assert scan_workflow_injection.find_violations(wf_dir) == []

    def test_non_string_run_skipped(self, tmp_path: Path) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "a.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
        )
        assert scan_workflow_injection.find_violations(wf_dir) == []

    def test_real_repo_has_no_violations(self) -> None:
        """The checked-in repo must pass the gate end-to-end."""
        violations = scan_workflow_injection.find_violations(
            REPO_ROOT / ".github" / "workflows"
        )
        assert violations == [], "\n".join(
            f"{v.workflow}:{v.line} {v.fragment!r}" for v in violations
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_verify_clean_real_repo(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = scan_workflow_injection.main(["verify"])
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    def test_verify_dirty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "ci.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: bad\n"
            "        run: echo ${{ github.event.issue.title }}\n"
        )
        monkeypatch.setattr(scan_workflow_injection, "WORKFLOW_DIR", wf_dir)
        exit_code = scan_workflow_injection.main(["verify"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "::error file=.github/workflows/ci.yml" in captured.err
        assert "FAIL" in captured.err

    def test_list_prints_matches(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        wf_dir = _make_workflow_dir(tmp_path)
        (wf_dir / "ci.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - run: echo ${{ github.head_ref }}\n"
        )
        monkeypatch.setattr(scan_workflow_injection, "WORKFLOW_DIR", wf_dir)
        exit_code = scan_workflow_injection.main(["list"])
        assert exit_code == 0
        assert "github.head_ref" in capsys.readouterr().out

    def test_no_subcommand_exits_nonzero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            scan_workflow_injection.main([])
        assert exc.value.code == 2
