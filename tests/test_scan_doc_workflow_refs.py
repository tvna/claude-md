"""Tests for scripts/scan_doc_workflow_refs.py.

The gate scans every tracked Markdown file outside docs/archive/ for the path
form ``.github/workflows/<name>.yml`` and fails when the referenced workflow
file does not exist (#1325). These tests pin the regex (path form only, no
bare names, no ``*`` globs), the existence oracle, the archive exclusion, the
ack escape hatch, the relative-link basename resolution, and a real-repo
self-check.
"""

from __future__ import annotations

import pytest
import scan_doc_workflow_refs as gate

pytestmark = pytest.mark.shard_ci_ops


def _make_repo(tmp_path):
    """Create a minimal repo tree with one real workflow under .github/workflows."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "verify-pr.yml").write_text("name: x\n")
    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    return tmp_path


def test_regex_matches_path_form_only() -> None:
    assert gate._WORKFLOW_REF_RE.findall("see `.github/workflows/verify-pr.yml`") == [
        "verify-pr.yml"
    ]
    # Relative Markdown link: only the basename is captured.
    assert gate._WORKFLOW_REF_RE.findall("[x](../../.github/workflows/verify-pr.yml)") == [
        "verify-pr.yml"
    ]


def test_regex_ignores_bare_name_and_glob() -> None:
    # A bare filename without the directory prefix is not gated.
    assert gate._WORKFLOW_REF_RE.findall("`portable-pr-policy.yml` is gone") == []
    # A literal glob is not a concrete path.
    assert gate._WORKFLOW_REF_RE.findall(".github/workflows/*.yml") == []


def test_find_refs_collects_existing_and_stale(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "runbooks" / "x.md").write_text(
        "ok: `.github/workflows/verify-pr.yml`\n"
        "stale: `.github/workflows/portable-pr-policy.yml`\n"
    )
    names = {(r.name, r.line) for r in gate.find_refs(repo)}
    assert ("verify-pr.yml", 1) in names
    assert ("portable-pr-policy.yml", 2) in names


def test_stale_refs_flags_only_missing(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "runbooks" / "x.md").write_text(
        "`.github/workflows/verify-pr.yml` `.github/workflows/portable-pr-policy.yml`\n"
    )
    stale = gate.stale_refs(repo, gate.find_refs(repo))
    assert [r.name for r in stale] == ["portable-pr-policy.yml"]


def test_archive_is_excluded(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "archive" / "old.md").write_text(
        "historical: `.github/workflows/portable-pr-policy.yml`\n"
    )
    assert gate.find_refs(repo) == []
    assert gate.stale_refs(repo, gate.find_refs(repo)) == []


def test_ack_marker_bypasses_line(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "runbooks" / "x.md").write_text(
        "future: `.github/workflows/not-yet.yml` <!-- workflow-ref-ack -->\n"
    )
    assert gate.find_refs(repo) == []


def test_iter_markdown_skips_archive_and_finds_docs(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "runbooks" / "x.md").write_text("x\n")
    (repo / "docs" / "archive" / "old.md").write_text("x\n")
    rels = {p.relative_to(repo).as_posix() for p in gate.iter_markdown(repo)}
    assert "docs/runbooks/x.md" in rels
    assert "docs/archive/old.md" not in rels


def test_real_repo_is_clean() -> None:
    """The actual tree must not cite a nonexistent workflow path outside archive."""
    stale = gate.stale_refs(gate.REPO_ROOT, gate.find_refs(gate.REPO_ROOT))
    assert stale == [], f"stale workflow refs: {[(r.doc, r.line, r.name) for r in stale]}"


def test_cli_verify_clean_repo() -> None:
    assert gate.main(["verify"]) == 0


def test_cli_verify_detects_stale(tmp_path, monkeypatch, capsys) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "runbooks" / "x.md").write_text(
        "stale: `.github/workflows/portable-pr-policy.yml`\n"
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    assert gate.main(["verify"]) == 1
    assert "portable-pr-policy.yml" in capsys.readouterr().err


def test_cli_list_prints_refs(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["list"]) == 0
    assert ".github/workflows/" in capsys.readouterr().out
