"""Tests for ``scripts/scan_runbook_template_drift.py``.

Covers :func:`extract_h2_headings`, :func:`check_conformance`,
:func:`parse_waivers`, :func:`run_gate`, and :func:`main`. All tests are
hermetic: ``get_changed_runbooks`` is patched; no real ``git diff`` subprocess
is called and no runbook is read from disk.

Refs #2065.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import scan_runbook_template_drift as gate

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONFORMING = "# Example Runbook\n\n" + "".join(f"## {section}\n\nbody\n\n" for section in gate.REQUIRED_SECTIONS)
_NON_CONFORMING = "# Example Runbook\n\n## Overview\n\nbody\n\n## Steps\n\nbody\n"


def _reader(mapping: dict[str, str]):
    def read(path: str) -> str:
        return mapping[path]

    return read


# ---------------------------------------------------------------------------
# extract_h2_headings
# ---------------------------------------------------------------------------


def test_extract_h2_headings_only_h2() -> None:
    text = "# Title\n## Scope\nprose\n### Subsection\n## Why not\n"
    assert gate.extract_h2_headings(text) == ["Scope", "Why not"]


def test_extract_h2_headings_strips_trailing_space() -> None:
    assert gate.extract_h2_headings("##  Pause / Resume  \n") == ["Pause / Resume"]


def test_extract_h2_headings_ignores_indented_or_hashless() -> None:
    # A '##' that is not at line start (e.g. inside a fenced block) is ignored.
    text = "text ## not a heading\n   ## indented\n## Real\n"
    assert gate.extract_h2_headings(text) == ["Real"]


def test_extract_h2_headings_ignores_fenced_backtick_block() -> None:
    # H2-looking lines inside a ``` fence are code samples, not headings.
    text = "# Title\n\n## Scope\n\n```\n## Why\n## Procedure\n```\n\n## References\n"
    assert gate.extract_h2_headings(text) == ["Scope", "References"]


def test_extract_h2_headings_ignores_fenced_canonical_sections_in_order() -> None:
    # A full canonical skeleton rendered inside a fence must count as zero
    # headings; a doc that only illustrates the sections is not conforming.
    fenced = "```\n" + "".join(f"## {s}\n" for s in gate.REQUIRED_SECTIONS) + "```\n"
    assert gate.extract_h2_headings(fenced) == []


def test_extract_h2_headings_ignores_fenced_canonical_sections_reversed() -> None:
    # Same, reverse order and a tilde fence: still zero headings.
    fenced = "~~~\n" + "".join(f"## {s}\n" for s in reversed(gate.REQUIRED_SECTIONS)) + "~~~\n"
    assert gate.extract_h2_headings(fenced) == []


def test_extract_h2_headings_longer_outer_fence_not_closed_by_shorter_inner() -> None:
    # A 4-backtick outer fence wraps a 3-backtick inner sample (CommonMark: the
    # closing fence must be at least as long as the opener). The inner ``` must
    # NOT terminate the outer block, so '## Why' stays a code sample and is not
    # counted; only the real '## Scope' and '## References' headings remain.
    text = "# Title\n\n## Scope\n\n" "````\n" "```\n" "## Why\n" "```\n" "````\n\n" "## References\n"
    assert gate.extract_h2_headings(text) == ["Scope", "References"]


def test_extract_h2_headings_full_skeleton_inside_longer_outer_fence() -> None:
    # The whole canonical skeleton wrapped in a 4-tilde fence (with an inner
    # 3-tilde sample) counts as zero headings: a runbook that only illustrates
    # the sections inside a longer fence must not pass the gate.
    inner = "~~~\n" + "".join(f"## {s}\n" for s in gate.REQUIRED_SECTIONS) + "~~~\n"
    fenced = "~~~~\n" + inner + "~~~~\n"
    assert gate.extract_h2_headings(fenced) == []


# ---------------------------------------------------------------------------
# check_conformance
# ---------------------------------------------------------------------------


def test_conforming_when_all_sections_in_order() -> None:
    assert gate.check_conformance(list(gate.REQUIRED_SECTIONS)) == []


def test_extra_non_canonical_headings_are_allowed() -> None:
    headings = list(gate.REQUIRED_SECTIONS)
    headings.insert(2, "Background")  # non-canonical heading interleaved
    assert gate.check_conformance(headings) == []


def test_missing_section_reported() -> None:
    headings = [h for h in gate.REQUIRED_SECTIONS if h != "Why not"]
    problems = gate.check_conformance(headings)
    assert any("Why not" in p for p in problems)


def test_all_missing_lists_every_section() -> None:
    problems = gate.check_conformance(["Overview", "Steps"])
    assert sum("missing required section" in p for p in problems) == len(gate.REQUIRED_SECTIONS)


def test_out_of_order_reported() -> None:
    headings = list(gate.REQUIRED_SECTIONS)
    headings[0], headings[1] = headings[1], headings[0]  # Why before Scope
    problems = gate.check_conformance(headings)
    assert any("order" in p.lower() for p in problems)


# ---------------------------------------------------------------------------
# TEMPLATE.md <-> REQUIRED_SECTIONS co-change guard
# ---------------------------------------------------------------------------


def test_template_h2_sections_match_required_sections() -> None:
    """The TEMPLATE.md example body must list exactly REQUIRED_SECTIONS, in order.

    Deterministic co-change guard: editing the section skeleton in
    docs/runbooks/TEMPLATE.md without updating REQUIRED_SECTIONS (or vice
    versa) breaks here, so the gate and the template it enforces cannot drift
    apart. The example runbook starts at the '# [Runbook title]' line, after
    the explanatory '## Template' heading; the H2 group below that line is the
    canonical skeleton.
    """
    template = (Path(__file__).resolve().parents[1] / "docs/runbooks/TEMPLATE.md").read_text(encoding="utf-8")
    marker = "# [Runbook title]"
    assert marker in template, "TEMPLATE.md example title line changed; update this guard and the gate."
    example_body = template.split(marker, 1)[1]
    assert gate.extract_h2_headings(example_body) == list(gate.REQUIRED_SECTIONS)


# ---------------------------------------------------------------------------
# parse_waivers
# ---------------------------------------------------------------------------


def test_parse_waivers_extracts_path() -> None:
    body = "intro\nrunbook-template-waiver: docs/runbooks/foo.md; pure reference\n"
    assert gate.parse_waivers(body) == frozenset({"docs/runbooks/foo.md"})


def test_parse_waivers_case_insensitive_multiple() -> None:
    body = "Runbook-Template-Waiver: docs/runbooks/a.md; r1\n" "runbook-template-waiver: docs/runbooks/b.md\n"
    assert gate.parse_waivers(body) == frozenset({"docs/runbooks/a.md", "docs/runbooks/b.md"})


def test_parse_waivers_empty() -> None:
    assert gate.parse_waivers("no markers here") == frozenset()


# ---------------------------------------------------------------------------
# _is_runbook (diff-scope filter)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("docs/runbooks/new.md", True),
        ("docs/runbooks/README.md", False),
        ("docs/runbooks/TEMPLATE.md", False),
        ("docs/runbooks/sub/nested.md", False),
        ("docs/standards/x.md", False),
        ("docs/runbooks/notes.txt", False),
    ],
)
def test_is_runbook(path: str, expected: bool) -> None:
    assert gate._is_runbook(path) is expected


# ---------------------------------------------------------------------------
# run_gate
# ---------------------------------------------------------------------------


def test_run_gate_passes_for_conforming_changed_runbook() -> None:
    ok = gate.run_gate(
        ["docs/runbooks/new.md"],
        _reader({"docs/runbooks/new.md": _CONFORMING}),
        frozenset(),
    )
    assert ok is True


def test_run_gate_fails_for_nonconforming() -> None:
    ok = gate.run_gate(
        ["docs/runbooks/new.md"],
        _reader({"docs/runbooks/new.md": _NON_CONFORMING}),
        frozenset(),
    )
    assert ok is False


def test_run_gate_waived_passes() -> None:
    ok = gate.run_gate(
        ["docs/runbooks/new.md"],
        _reader({"docs/runbooks/new.md": _NON_CONFORMING}),
        frozenset({"docs/runbooks/new.md"}),
    )
    assert ok is True


def test_run_gate_no_changed_runbooks_passes() -> None:
    assert gate.run_gate([], _reader({}), frozenset()) is True


def test_run_gate_unreadable_file_is_skipped_not_failed() -> None:
    def boom(_path: str) -> str:
        raise OSError("nope")

    assert gate.run_gate(["docs/runbooks/new.md"], boom, frozenset()) is True


# ---------------------------------------------------------------------------
# get_changed_runbooks (subprocess boundary)
# ---------------------------------------------------------------------------


def _mock_run(committed_stdout: str, cached_stdout: str = "", committed_rc: int = 0):
    from unittest.mock import MagicMock

    committed = MagicMock(returncode=committed_rc, stdout=committed_stdout)
    cached = MagicMock(returncode=0, stdout=cached_stdout)
    return [committed, cached]


def test_get_changed_runbooks_filters_and_unions() -> None:
    from unittest.mock import patch

    committed = "docs/runbooks/a.md\ndocs/runbooks/README.md\nsrc/x.py\n"
    cached = "docs/runbooks/b.md\ndocs/runbooks/a.md\n"
    with patch("subprocess.run", side_effect=_mock_run(committed, cached)):
        result = gate.get_changed_runbooks("origin/main")
    assert result == ["docs/runbooks/a.md", "docs/runbooks/b.md"]


def test_get_changed_runbooks_none_on_git_failure() -> None:
    from unittest.mock import patch

    with patch("subprocess.run", side_effect=_mock_run("", committed_rc=128)):
        assert gate.get_changed_runbooks("origin/main") is None


def test_get_changed_runbooks_ignores_cached_failure() -> None:
    from unittest.mock import MagicMock, patch

    committed = MagicMock(returncode=0, stdout="docs/runbooks/a.md\n")
    cached = MagicMock(returncode=1, stdout="")
    with patch("subprocess.run", side_effect=[committed, cached]):
        assert gate.get_changed_runbooks("origin/main") == ["docs/runbooks/a.md"]


# ---------------------------------------------------------------------------
# _audit_all / --all
# ---------------------------------------------------------------------------


def test_audit_all_reports_nonconforming(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    (tmp_path / "bad.md").write_text(_NON_CONFORMING, encoding="utf-8")
    (tmp_path / "good.md").write_text(_CONFORMING, encoding="utf-8")
    monkeypatch.setattr(gate, "_RUNBOOK_PARENT", tmp_path)
    assert gate.main(["verify", "--all"]) == 0
    err = capsys.readouterr().err
    assert "bad.md" in err
    assert "good.md" not in err


def test_audit_all_all_conforming(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    (tmp_path / "good.md").write_text(_CONFORMING, encoding="utf-8")
    monkeypatch.setattr(gate, "_RUNBOOK_PARENT", tmp_path)
    assert gate.main(["verify", "--all"]) == 0
    assert "all runbooks conform" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_fail_open_when_diff_unavailable() -> None:
    with patch.object(gate, "get_changed_runbooks", return_value=None):
        assert gate.main(["verify"]) == 0


def test_main_unknown_subcommand_returns_64() -> None:
    assert gate.main(["bogus"]) == 64


def test_main_no_subcommand_returns_64() -> None:
    assert gate.main([]) == 64


def test_main_pass_for_conforming(tmp_path) -> None:
    with (
        patch.object(gate, "get_changed_runbooks", return_value=["docs/runbooks/new.md"]),
        patch.object(gate, "_read_text", return_value=_CONFORMING),
    ):
        assert gate.main(["verify"]) == 0


def test_main_fail_for_nonconforming() -> None:
    with (
        patch.object(gate, "get_changed_runbooks", return_value=["docs/runbooks/new.md"]),
        patch.object(gate, "_read_text", return_value=_NON_CONFORMING),
    ):
        assert gate.main(["verify"]) == 1


def test_main_waiver_from_body_file_passes(tmp_path) -> None:
    body = tmp_path / "body.txt"
    body.write_text("runbook-template-waiver: docs/runbooks/new.md; reason\n")
    with (
        patch.object(gate, "get_changed_runbooks", return_value=["docs/runbooks/new.md"]),
        patch.object(gate, "_read_text", return_value=_NON_CONFORMING),
    ):
        assert gate.main(["verify", "--body-file", str(body)]) == 0


def test_main_waiver_from_pr_body_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PR_BODY", "runbook-template-waiver: docs/runbooks/new.md; reason\n")
    with (
        patch.object(gate, "get_changed_runbooks", return_value=["docs/runbooks/new.md"]),
        patch.object(gate, "_read_text", return_value=_NON_CONFORMING),
    ):
        assert gate.main(["verify"]) == 0


def test_main_unreadable_body_file_warns_but_proceeds(tmp_path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PR_BODY", raising=False)
    # A directory path is not readable as a file: triggers the OSError branch.
    with patch.object(gate, "get_changed_runbooks", return_value=[]):
        assert gate.main(["verify", "--body-file", str(tmp_path)]) == 0
    assert "cannot read PR body file" in capsys.readouterr().err
