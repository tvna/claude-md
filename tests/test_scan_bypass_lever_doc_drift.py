"""Tests for ``scripts/scan_bypass_lever_doc_drift.py``.

Refs #2152 (retrospective for PR #2134 / issue #2133). Verifies that the gate
flags a pre-push bypass lever that the runbook does not name (the PR #2134
stale-escape-hatch class) and the reverse (a runbook lever the hook dropped),
passes when the two name sets are equal, and that the gate holds on the real
repository tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_bypass_lever_doc_drift as g

pytestmark = pytest.mark.shard_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# lever extraction
# ---------------------------------------------------------------------------
def test_extract_levers_finds_each_family_member() -> None:
    text = 'if [ "${PREFLIGHT_SKIP_ALL:-0}" = "1" ]; export PREFLIGHT_SKIP_STEPS\nPREFLIGHT_SKIP=1'
    assert g.extract_levers(text) == frozenset(
        {"PREFLIGHT_SKIP", "PREFLIGHT_SKIP_ALL", "PREFLIGHT_SKIP_STEPS"}
    )


def test_extract_levers_does_not_split_longer_token() -> None:
    # The bare-prefix lever must not be reported when only the longer token is
    # present (word-boundary discipline).
    assert g.extract_levers("PREFLIGHT_SKIP_ALL only") == frozenset({"PREFLIGHT_SKIP_ALL"})


def test_extract_levers_empty_when_absent() -> None:
    assert g.extract_levers("no levers here") == frozenset()


def test_extract_levers_captures_digit_suffixed_token() -> None:
    # Regression for the Codex P2 review on #2155: a future digit-suffixed lever
    # must be captured as its own token, not collapsed onto the bare prefix the
    # runbook already documents (which would report false parity).
    assert g.extract_levers("PREFLIGHT_SKIP2") == frozenset({"PREFLIGHT_SKIP2"})
    assert g.extract_levers("PREFLIGHT_SKIP_STEPS2") == frozenset({"PREFLIGHT_SKIP_STEPS2"})


def test_digit_suffixed_lever_in_hook_is_drift_against_prefix_only_runbook() -> None:
    # The hook gains PREFLIGHT_SKIP2; the runbook documents only PREFLIGHT_SKIP.
    # Parity must NOT hold.
    hook = g.extract_levers("PREFLIGHT_SKIP\nPREFLIGHT_SKIP2\n")
    doc = g.extract_levers("`PREFLIGHT_SKIP`\n")
    problems = g.find_drift(hook, doc)
    assert len(problems) == 1
    assert "PREFLIGHT_SKIP2" in problems[0]


# ---------------------------------------------------------------------------
# drift detection
# ---------------------------------------------------------------------------
def test_lever_in_hook_missing_from_runbook_is_drift() -> None:
    # Reproduces the PR #2134 drift: hook gained PREFLIGHT_SKIP_ALL, runbook
    # never named it.
    hook = frozenset({"PREFLIGHT_SKIP", "PREFLIGHT_SKIP_ALL", "PREFLIGHT_SKIP_STEPS"})
    doc = frozenset({"PREFLIGHT_SKIP", "PREFLIGHT_SKIP_STEPS"})
    problems = g.find_drift(hook, doc)
    assert len(problems) == 1
    assert "PREFLIGHT_SKIP_ALL" in problems[0]
    assert "does not name it" in problems[0]


def test_lever_in_runbook_missing_from_hook_is_drift() -> None:
    hook = frozenset({"PREFLIGHT_SKIP"})
    doc = frozenset({"PREFLIGHT_SKIP", "PREFLIGHT_SKIP_OLD"})
    problems = g.find_drift(hook, doc)
    assert len(problems) == 1
    assert "PREFLIGHT_SKIP_OLD" in problems[0]
    assert "no longer references it" in problems[0]


def test_parity_yields_no_drift() -> None:
    levers = frozenset({"PREFLIGHT_SKIP", "PREFLIGHT_SKIP_ALL", "PREFLIGHT_SKIP_STEPS"})
    assert g.find_drift(levers, levers) == []


# ---------------------------------------------------------------------------
# verify subcommand (end to end against synthetic files)
# ---------------------------------------------------------------------------
def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_verify_green_on_matching_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    hook = _write(tmp_path, "pre-push", "PREFLIGHT_SKIP_ALL\nPREFLIGHT_SKIP\n")
    runbook = _write(tmp_path, "preflight.md", "`PREFLIGHT_SKIP` and `PREFLIGHT_SKIP_ALL`\n")
    rc = g.main(["verify", "--hook", str(hook), "--runbook", str(runbook)])
    assert rc == 0
    assert "OK:" in capsys.readouterr().out


def test_verify_red_on_stale_runbook(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    hook = _write(tmp_path, "pre-push", "PREFLIGHT_SKIP_ALL\nPREFLIGHT_SKIP\n")
    runbook = _write(tmp_path, "preflight.md", "`PREFLIGHT_SKIP` only\n")
    rc = g.main(["verify", "--hook", str(hook), "--runbook", str(runbook)])
    assert rc == 1
    assert "PREFLIGHT_SKIP_ALL" in capsys.readouterr().err


def test_verify_missing_hook_fails_loud(tmp_path: Path) -> None:
    runbook = _write(tmp_path, "preflight.md", "`PREFLIGHT_SKIP`\n")
    rc = g.main(["verify", "--hook", str(tmp_path / "absent"), "--runbook", str(runbook)])
    assert rc == 1


# ---------------------------------------------------------------------------
# real-tree invariant
# ---------------------------------------------------------------------------
def test_repository_tree_is_in_parity() -> None:
    rc = g.main(["verify"])
    assert rc == 0
