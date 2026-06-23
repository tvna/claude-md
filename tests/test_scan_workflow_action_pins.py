"""Tests for ``scripts/scan_workflow_action_pins.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_workflow_action_pins

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]

GOOD_PIN = (
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5.0.1"
)


# ---------------------------------------------------------------------------
# scan_line
# ---------------------------------------------------------------------------


class TestScanLine:
    @pytest.mark.parametrize(
        "line",
        [
            f"      - uses: {GOOD_PIN}",
            f"        uses: {GOOD_PIN}",
            f"  uses: {GOOD_PIN}",
            (
                "      - uses: actions/setup-python@"
                "0b93645e9fea7318ecaed2b359559ac225c90a2b # v5.3.0"
            ),
            "      - uses: ./.github/workflows/generate-agents.yml",
            "      - uses: ../shared/reusable.yml",
            "      - uses: docker://alpine:3.20",
            "      # uses: actions/checkout@v4 ; doc only",
            "  # forbidden form documented inline",
            f"      - uses: actions/checkout@v4  {scan_workflow_action_pins.ACK_MARKER}",
            "",
            "name: ci",
            "      - run: echo 'uses: anything goes in shell strings'",
        ],
    )
    def test_acceptable_lines(self, line: str) -> None:
        assert scan_workflow_action_pins.scan_line(line) is None

    @pytest.mark.parametrize(
        "line",
        [
            "      - uses: actions/checkout@v4",
            "      - uses: actions/checkout@main",
            "      - uses: actions/checkout@master",
            "      - uses: actions/checkout@v4.2.2",
            "      - uses: actions/checkout@11bd7190",
            "      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af68",
            "      - uses: actions/checkout@11BD71901BBE5B1630CEEA73D27597364C9AF683",
            "      - uses: actions/checkout",
        ],
    )
    def test_invalid_pin_form(self, line: str) -> None:
        reason = scan_workflow_action_pins.scan_line(line)
        assert reason is not None

    def test_sha_pin_without_tag_comment(self) -> None:
        line = (
            "      - uses: actions/checkout@"
            "11bd71901bbe5b1630ceea73d27597364c9af683"
        )
        reason = scan_workflow_action_pins.scan_line(line)
        assert reason is not None
        assert "missing trailing" in reason

    def test_sha_pin_with_empty_tag_comment(self) -> None:
        line = (
            "      - uses: actions/checkout@"
            "11bd71901bbe5b1630ceea73d27597364c9af683 #"
        )
        reason = scan_workflow_action_pins.scan_line(line)
        assert reason is not None
        assert "missing trailing" in reason

    def test_sha_pin_with_whitespace_only_tag_comment(self) -> None:
        line = (
            "      - uses: actions/checkout@"
            "11bd71901bbe5b1630ceea73d27597364c9af683 #    "
        )
        reason = scan_workflow_action_pins.scan_line(line)
        assert reason is not None
        assert "missing trailing" in reason

    def test_short_sha_is_rejected(self) -> None:
        line = "      - uses: actions/checkout@11bd71901bbe # v4"
        reason = scan_workflow_action_pins.scan_line(line)
        assert reason is not None
        assert "40-char" in reason

    def test_uppercase_sha_is_rejected(self) -> None:
        line = (
            "      - uses: actions/checkout@"
            "11BD71901BBE5B1630CEEA73D27597364C9AF683 # v4"
        )
        reason = scan_workflow_action_pins.scan_line(line)
        assert reason is not None
        assert "40-char" in reason

    def test_missing_at_is_rejected(self) -> None:
        line = "      - uses: actions/checkout"
        reason = scan_workflow_action_pins.scan_line(line)
        assert reason is not None
        assert "no '@<sha>'" in reason


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------


class TestScanText:
    def test_returns_empty_when_clean(self) -> None:
        text = (
            "name: x\n"
            "jobs:\n"
            "  a:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            f"      - uses: {GOOD_PIN}\n"
        )
        assert scan_workflow_action_pins.scan_text(text) == []

    def test_returns_line_numbers_1_based(self) -> None:
        text = (
            "name: x\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            f"      - uses: {GOOD_PIN}\n"
            "      - uses: actions/setup-node@main\n"
        )
        hits = scan_workflow_action_pins.scan_text(text)
        assert [lineno for lineno, _ in hits] == [5, 7]

    def test_local_and_docker_refs_are_skipped(self) -> None:
        text = (
            "      - uses: ./.github/workflows/generate-agents.yml\n"
            "      - uses: docker://node:20\n"
        )
        assert scan_workflow_action_pins.scan_text(text) == []

    def test_ack_marker_skips_line(self) -> None:
        marker = scan_workflow_action_pins.ACK_MARKER
        text = (
            "      - uses: actions/checkout@v4\n"
            f"      - uses: actions/checkout@v4  {marker}\n"
            "      - uses: actions/checkout@main\n"
        )
        hits = scan_workflow_action_pins.scan_text(text)
        assert [lineno for lineno, _ in hits] == [1, 3]

    def test_uses_inside_shell_string_is_ignored(self) -> None:
        text = (
            "      - name: echo it\n"
            "        run: echo 'uses: actions/checkout@v4'\n"
        )
        assert scan_workflow_action_pins.scan_text(text) == []


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
            f"      - uses: {GOOD_PIN}\n"
        )
        assert scan_workflow_action_pins.find_violations(repo) == []

    def test_violation_in_workflow_yml(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "name: ci\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
        )
        violations = scan_workflow_action_pins.find_violations(repo)
        assert len(violations) == 1
        rel, lineno, _reason = violations[0]
        assert rel == Path(".github/workflows/ci.yml")
        assert lineno == 5

    def test_violation_in_workflow_yaml(self, tmp_path: Path) -> None:
        """The ``.yaml`` (long) extension is treated identically."""
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yaml").write_text(
            "      - uses: actions/setup-node@main\n"
        )
        violations = scan_workflow_action_pins.find_violations(repo)
        assert len(violations) == 1
        assert violations[0][0] == Path(".github/workflows/ci.yaml")
        assert violations[0][1] == 1

    def test_local_uses_is_allowed(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "      - uses: ./.github/workflows/generate-agents.yml\n"
        )
        assert scan_workflow_action_pins.find_violations(repo) == []

    def test_docker_uses_is_allowed(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "      - uses: docker://alpine:3.20\n"
        )
        assert scan_workflow_action_pins.find_violations(repo) == []

    def test_ack_marker_is_allowed(self, tmp_path: Path) -> None:
        repo = _make_workflow_repo(tmp_path)
        marker = scan_workflow_action_pins.ACK_MARKER
        (repo / ".github/workflows/ci.yml").write_text(
            f"      - uses: actions/checkout@v4  {marker}\n"
        )
        assert scan_workflow_action_pins.find_violations(repo) == []

    def test_violations_across_multiple_files_are_collected(
        self, tmp_path: Path
    ) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/a.yml").write_text(
            "      - uses: actions/checkout@v4\n"
        )
        (repo / ".github/workflows/b.yml").write_text(
            f"      - uses: {GOOD_PIN}\n"
            "      - uses: actions/setup-node@main\n"
        )
        violations = scan_workflow_action_pins.find_violations(repo)
        paths = {(rel, lineno) for rel, lineno, _ in violations}
        assert (Path(".github/workflows/a.yml"), 1) in paths
        assert (Path(".github/workflows/b.yml"), 2) in paths
        assert len(violations) == 2

    def test_non_yaml_files_in_workflows_dir_are_ignored(
        self, tmp_path: Path
    ) -> None:
        """A stray README or .json file in the workflow dir is not scanned."""
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/README.md").write_text(
            "Avoid `uses: actions/checkout@v4`; pin to a SHA.\n"
        )
        (repo / ".github/workflows/labels.json").write_text(
            '{"note": "uses: actions/checkout@v4"}\n'
        )
        assert scan_workflow_action_pins.find_violations(repo) == []

    def test_missing_workflow_dir_is_clean(self, tmp_path: Path) -> None:
        """A repo with no ``.github/workflows`` directory trivially passes."""
        assert scan_workflow_action_pins.find_violations(tmp_path) == []

    def test_real_repo_has_no_violations(self) -> None:
        """The checked-in repo must pass the gate end-to-end."""
        violations = scan_workflow_action_pins.find_violations(REPO_ROOT)
        assert violations == [], "\n".join(
            f"{rel}:{lineno}: {reason}"
            for rel, lineno, reason in violations
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_verify_cli_clean(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _make_workflow_repo(tmp_path)
        exit_code = scan_workflow_action_pins.main(
            ["verify", "--repo-root", str(tmp_path)]
        )
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    def test_verify_cli_dirty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_workflow_repo(tmp_path)
        (repo / ".github/workflows/ci.yml").write_text(
            "      - uses: actions/checkout@v4\n"
        )
        exit_code = scan_workflow_action_pins.main(
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
        exit_code = scan_workflow_action_pins.main(["verify"])
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    def test_no_subcommand_exits_nonzero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            scan_workflow_action_pins.main([])
        assert exc.value.code == 2
