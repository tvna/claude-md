"""Tests for ``scripts/scan_issue_anchor_drift.py`` (issue #1640).

Exercises each violation class against a synthetic repo tree (fixture
directories under ``tmp_path``), the comment/provenance carve-outs, and the
live repository tree, which must stay clean so the gate can hold the #1640
invariant going forward.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_issue_anchor_drift

pytestmark = pytest.mark.shard_default


CLEAN_CONFIG = """\
schema_version = 1

[[anchors]]
key = "alpha"
issue = 11
writes = "comment"
consumers = [".github/workflows/clean.yml"]
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal clean repo tree the individual tests then make dirty."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "pr-body-templates").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".github" / "tracking-issues.toml").write_text(
        CLEAN_CONFIG, encoding="utf-8"
    )
    (tmp_path / ".github" / "workflows" / "clean.yml").write_text(
        "jobs:\n  a:\n    steps:\n"
        "      # comment provenance: Refs #123 stays legal\n"
        '      - run: echo "$(python3 scripts/issue_anchors.py get alpha)"\n',
        encoding="utf-8",
    )
    return tmp_path


def _run(repo_root: Path) -> int:
    return scan_issue_anchor_drift.main(["verify", "--repo-root", str(repo_root)])


def test_clean_tree_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(repo) == 0
    assert "clean" in capsys.readouterr().out


@pytest.mark.parametrize(
    "line",
    [
        '            --issue 178 \\',
        '            --issue-number "197" \\',
        '            --commit-trailer "Refs #696" \\',
        '            --commit-body "Refs #960" \\',
        "          Closes #960",
        "          Refs #18",
        '  TRACKING_ISSUE: "178"',
    ],
)
def test_functional_hardcode_in_workflow_fails(
    repo: Path, line: str, capsys: pytest.CaptureFixture[str]
) -> None:
    workflow = repo / ".github" / "workflows" / "dirty.yml"
    workflow.write_text(f"jobs:\n  a:\n    steps:\n{line}\n", encoding="utf-8")
    assert _run(repo) == 1
    err = capsys.readouterr().err
    assert "::error file=.github/workflows/dirty.yml,line=4::" in err
    assert "hardcoded tracking-issue number" in err


@pytest.mark.parametrize(
    "line",
    [
        "      # Refs #1437, #1466: provenance comment",
        "          # --issue 178 commented-out flag",
        '          --issue "${TRACKING_ISSUE}" \\',
        '          --issue-number "${{ inputs.measure_issue_number }}" \\',
        "          - [x] Issue number recorded on the `Closes #` line above",
        "          Refs #__ISSUE_ANCHOR:alpha__",
    ],
)
def test_non_functional_lines_pass(repo: Path, line: str) -> None:
    workflow = repo / ".github" / "workflows" / "ok.yml"
    workflow.write_text(f"jobs:\n  a:\n    steps:\n{line}\n", encoding="utf-8")
    assert _run(repo) == 0


def test_template_literal_ref_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    template = repo / ".github" / "pr-body-templates" / "t.md"
    template.write_text("## Related Issue\n\nRefs #1171\n", encoding="utf-8")
    assert _run(repo) == 1
    assert (
        "::error file=.github/pr-body-templates/t.md,line=3::"
        in capsys.readouterr().err
    )


def test_template_token_passes(repo: Path) -> None:
    template = repo / ".github" / "pr-body-templates" / "t.md"
    template.write_text("Refs #__ISSUE_ANCHOR:alpha__\n", encoding="utf-8")
    assert _run(repo) == 0


def test_script_integer_issue_constant_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = repo / "scripts" / "bad.py"
    script.write_text("TARGET_ISSUE = 197\n", encoding="utf-8")
    assert _run(repo) == 1
    err = capsys.readouterr().err
    assert "::error file=scripts/bad.py,line=1::" in err
    assert "TARGET_ISSUE" in err


def test_script_annotated_issue_constant_fails(repo: Path) -> None:
    script = repo / "scripts" / "bad.py"
    script.write_text("PARENT_ISSUE: int = 1156\n", encoding="utf-8")
    assert _run(repo) == 1


@pytest.mark.parametrize(
    "source",
    [
        "import issue_anchors\nTARGET_ISSUE = issue_anchors.resolve('alpha')\n",
        "TIMEOUT = 30\n",
        "ISSUE_MARKER = '<!-- marker -->'\n",
        "DEBUG_ISSUE = True\n",
        "issue_number = 7\n",  # lowercase: a local, not a pinned constant
    ],
)
def test_script_non_literal_or_non_issue_constants_pass(
    repo: Path, source: str
) -> None:
    (repo / "scripts" / "ok.py").write_text(source, encoding="utf-8")
    assert _run(repo) == 0


def test_missing_consumer_path_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / ".github" / "tracking-issues.toml").write_text(
        CLEAN_CONFIG.replace("clean.yml", "renamed-away.yml"), encoding="utf-8"
    )
    assert _run(repo) == 1
    err = capsys.readouterr().err
    assert "renamed-away.yml" in err
    assert "does not exist" in err


def test_malformed_config_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / ".github" / "tracking-issues.toml").write_text(
        "schema_version = 2\n", encoding="utf-8"
    )
    assert _run(repo) == 1
    assert "schema_version" in capsys.readouterr().err


def test_unreadable_tree_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo root without the expected layout fails loud, not silently."""
    assert _run(tmp_path / "absent") == 1
    assert "::error" in capsys.readouterr().err


def test_live_repository_tree_is_clean() -> None:
    """The migrated tree carries no functional hardcoded issue numbers."""
    assert scan_issue_anchor_drift.main(["verify"]) == 0
