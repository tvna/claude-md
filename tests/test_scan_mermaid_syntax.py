"""Tests for ``scripts/scan_mermaid_syntax.py``.

The pure extraction/diagnostic logic and the bun I/O boundary (with a mocked
``subprocess.run``) are covered without bun. A final integration block runs the
real parser end-to-end and is skipped when bun or the pinned node_modules tree
is unavailable, so CI without bun still proves the deterministic logic. Refs
#1597.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import scan_mermaid_syntax

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
_BUN = shutil.which("bun")
_HAS_DEPS = (REPO_ROOT / "node_modules" / "mermaid").is_dir()
_INTEGRATION = pytest.mark.skipif(
    not (_BUN and _HAS_DEPS),
    reason="bun and node_modules/mermaid required for the live Mermaid parser",
)

GOOD_SEQUENCE = "sequenceDiagram\n    actor H\n    H->>A: submit prompt"
GOOD_FLOWCHART = "flowchart TD\n    A --> B"
# The #1595 class: a ';' in a sequence message body is a statement separator.
BAD_SEQUENCE = "sequenceDiagram\n    actor H\n    H->>A: do A; then B"


def _md(*blocks: str) -> str:
    """Wrap each block in a ```mermaid fence inside a Markdown document."""
    parts = ["# Doc", ""]
    for block in blocks:
        parts += ["```mermaid", block, "```", ""]
    return "\n".join(parts)


# --- pure extraction ------------------------------------------------------


def test_extract_blocks_records_fence_line_numbers() -> None:
    text = _md(GOOD_SEQUENCE, GOOD_FLOWCHART)
    blocks = scan_mermaid_syntax.extract_blocks(Path("docs/x.md"), text)

    assert [b.line for b in blocks] == [3, 9]
    assert blocks[0].text == GOOD_SEQUENCE
    assert blocks[1].text == GOOD_FLOWCHART


def test_extract_blocks_ignores_non_mermaid_fences() -> None:
    text = "```python\nprint('hi')\n```\n\n```\nplain\n```\n\n```mermaidjs\nx\n```\n"
    assert scan_mermaid_syntax.extract_blocks(Path("d.md"), text) == []


def test_extract_blocks_handles_indented_fence() -> None:
    text = "- item\n    ```mermaid\n    flowchart TD\n        A --> B\n    ```\n"
    blocks = scan_mermaid_syntax.extract_blocks(Path("d.md"), text)

    assert len(blocks) == 1
    # The opening fence indentation is stripped from each body line.
    assert blocks[0].text == "flowchart TD\n    A --> B"


def test_extract_blocks_handles_tilde_fence() -> None:
    text = "~~~mermaid\nflowchart TD\n  A --> B\n~~~\n"
    blocks = scan_mermaid_syntax.extract_blocks(Path("d.md"), text)

    assert len(blocks) == 1
    assert blocks[0].text == "flowchart TD\n  A --> B"


def test_extract_blocks_emits_unclosed_block() -> None:
    text = "```mermaid\nflowchart TD\n  A --> B\n"
    blocks = scan_mermaid_syntax.extract_blocks(Path("d.md"), text)

    assert len(blocks) == 1
    assert blocks[0].text == "flowchart TD\n  A --> B"


# --- file discovery + exemption -------------------------------------------


def test_is_exempt_excludes_no_path() -> None:
    # The gate is permanent: the ast prefix is no longer exempt (#1598).
    assert not scan_mermaid_syntax.is_exempt("docs/generated/scripts/ast/x.md")
    assert not scan_mermaid_syntax.is_exempt("docs/uml/x.md")


def test_iter_docs_markdown_includes_ast_and_skips_non_md(tmp_path: Path) -> None:
    (tmp_path / "docs" / "uml").mkdir(parents=True)
    (tmp_path / "docs" / "generated" / "scripts" / "ast").mkdir(parents=True)
    (tmp_path / "docs" / "uml" / "a.md").write_text(_md(GOOD_FLOWCHART), encoding="utf-8")
    (tmp_path / "docs" / "uml" / "note.txt").write_text("not markdown", encoding="utf-8")
    (tmp_path / "docs" / "generated" / "scripts" / "ast" / "g.md").write_text(_md(GOOD_FLOWCHART), encoding="utf-8")

    found = {scan_mermaid_syntax.rel(p, tmp_path) for p in scan_mermaid_syntax.iter_docs_markdown(tmp_path)}
    # The ast directory is now in scope; only the non-Markdown note is skipped.
    assert found == {"docs/uml/a.md", "docs/generated/scripts/ast/g.md"}


def test_iter_docs_markdown_no_docs_dir(tmp_path: Path) -> None:
    assert scan_mermaid_syntax.iter_docs_markdown(tmp_path) == []


def test_collect_blocks_aggregates(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(_md(GOOD_FLOWCHART), encoding="utf-8")
    (tmp_path / "docs" / "b.md").write_text(_md(GOOD_SEQUENCE, GOOD_FLOWCHART), encoding="utf-8")

    blocks = scan_mermaid_syntax.collect_blocks(tmp_path)
    assert len(blocks) == 3


def test_rel_handles_path_outside_root(tmp_path: Path) -> None:
    other = Path("/somewhere/else/x.md")
    assert scan_mermaid_syntax.rel(other, tmp_path) == other.as_posix()


# --- diagnostics + parser boundary (mocked) -------------------------------


def test_format_error_is_github_annotation(tmp_path: Path) -> None:
    block = scan_mermaid_syntax.MermaidBlock(source=tmp_path / "docs" / "x.md", line=4, text="")
    msg = scan_mermaid_syntax.format_error(block, "Parse error on line 3", tmp_path)
    assert msg == "::error file=docs/x.md,line=4::Mermaid parse error: Parse error on line 3"


def test_diagnostics_maps_failures_and_skips_ok(tmp_path: Path) -> None:
    blocks = [
        scan_mermaid_syntax.MermaidBlock(source=tmp_path / "docs" / "a.md", line=1, text=""),
        scan_mermaid_syntax.MermaidBlock(source=tmp_path / "docs" / "b.md", line=2, text=""),
    ]
    results = [
        {"id": f"{tmp_path / 'docs' / 'a.md'}:1", "ok": True, "error": None},
        {"id": f"{tmp_path / 'docs' / 'b.md'}:2", "ok": False, "error": "boom"},
        {"id": "unknown:99", "ok": False, "error": "orphan"},
    ]
    errors = scan_mermaid_syntax.diagnostics(blocks, results, tmp_path)
    assert errors == ["::error file=docs/b.md,line=2::Mermaid parse error: boom"]


def test_diagnostics_defaults_missing_error_message(tmp_path: Path) -> None:
    blocks = [scan_mermaid_syntax.MermaidBlock(source=tmp_path / "docs" / "a.md", line=1, text="")]
    results = [{"id": f"{tmp_path / 'docs' / 'a.md'}:1", "ok": False}]
    errors = scan_mermaid_syntax.diagnostics(blocks, results, tmp_path)
    assert "unknown parse error" in errors[0]


def _fake_run(stdout: str = "", returncode: int = 0, stderr: str = "", record: list[str] | None = None):
    def _run(cmd, input, capture_output, text, check):  # noqa: A002 - mirror subprocess.run kwargs
        if record is not None:
            record.append(input)
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return _run


def test_run_parser_returns_results(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    block = scan_mermaid_syntax.MermaidBlock(source=tmp_path / "docs" / "a.md", line=1, text="flowchart TD")
    payload_id = f"{tmp_path / 'docs' / 'a.md'}:1"
    sent: list[str] = []
    runner = _fake_run(stdout=json.dumps([{"id": payload_id, "ok": True, "error": None}]), record=sent)
    monkeypatch.setattr(scan_mermaid_syntax.subprocess, "run", runner)

    results = scan_mermaid_syntax.run_parser([block], "bun")
    assert results == [{"id": payload_id, "ok": True, "error": None}]
    # The block text is forwarded to the worker as JSON.
    assert "flowchart TD" in sent[0]


def test_run_parser_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    block = scan_mermaid_syntax.MermaidBlock(source=tmp_path / "a.md", line=1, text="")
    monkeypatch.setattr(scan_mermaid_syntax.subprocess, "run", _fake_run(returncode=2, stderr="missing module"))
    with pytest.raises(RuntimeError, match="missing module"):
        scan_mermaid_syntax.run_parser([block], "bun")


def test_run_parser_raises_on_bad_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    block = scan_mermaid_syntax.MermaidBlock(source=tmp_path / "a.md", line=1, text="")
    monkeypatch.setattr(scan_mermaid_syntax.subprocess, "run", _fake_run(stdout="not json"))
    with pytest.raises(RuntimeError, match="non-JSON"):
        scan_mermaid_syntax.run_parser([block], "bun")


def test_verify_short_circuits_without_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _boom(*_a, **_k):
        nonlocal called
        called = True
        raise AssertionError("run_parser must not run when there are no blocks")

    monkeypatch.setattr(scan_mermaid_syntax, "run_parser", _boom)
    assert scan_mermaid_syntax.verify(tmp_path, "bun") == []
    assert called is False


def test_verify_uses_run_parser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(_md(GOOD_FLOWCHART), encoding="utf-8")
    block_id = f"{tmp_path / 'docs' / 'a.md'}:3"
    monkeypatch.setattr(
        scan_mermaid_syntax,
        "run_parser",
        lambda blocks, bun: [{"id": block_id, "ok": False, "error": "nope"}],
    )
    errors = scan_mermaid_syntax.verify(tmp_path, "bun")
    assert errors == ["::error file=docs/a.md,line=3::Mermaid parse error: nope"]


# --- CLI boundary ---------------------------------------------------------


def test_resolve_bun_delegates_to_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_mermaid_syntax.shutil, "which", lambda name: "/x/bun" if name == "bun" else None)
    assert scan_mermaid_syntax.resolve_bun() == "/x/bun"


def test_cmd_verify_fails_when_bun_missing(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(scan_mermaid_syntax, "resolve_bun", lambda: None)
    args = argparse.Namespace(root=str(REPO_ROOT), bun=None)
    assert scan_mermaid_syntax.cmd_verify(args) == 1
    assert "bun is required" in capsys.readouterr().err


def test_cmd_verify_reports_runtime_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(scan_mermaid_syntax, "verify", lambda root, bun: (_ for _ in ()).throw(RuntimeError("worker died")))
    args = argparse.Namespace(root=str(REPO_ROOT), bun="/x/bun")
    assert scan_mermaid_syntax.cmd_verify(args) == 1
    assert "worker died" in capsys.readouterr().err


def test_cmd_verify_prints_errors_and_fails(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(scan_mermaid_syntax, "verify", lambda root, bun: ["::error file=docs/x.md,line=1::Mermaid parse error: x"])
    args = argparse.Namespace(root=str(REPO_ROOT), bun="/x/bun")
    assert scan_mermaid_syntax.cmd_verify(args) == 1
    err = capsys.readouterr().err
    assert "1 Mermaid block(s) failed" in err


def test_cmd_verify_passes_when_clean(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(scan_mermaid_syntax, "verify", lambda root, bun: [])
    args = argparse.Namespace(root=str(REPO_ROOT), bun="/x/bun")
    assert scan_mermaid_syntax.cmd_verify(args) == 0
    assert "all Mermaid blocks under docs/ parse" in capsys.readouterr().out


def test_main_dispatches_to_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_mermaid_syntax, "verify", lambda root, bun: [])
    assert scan_mermaid_syntax.main(["--bun", "/x/bun", "verify"]) == 0


def test_build_parser_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        scan_mermaid_syntax.main([])


# --- live integration (real Mermaid parser via bun) -----------------------


@_INTEGRATION
def test_live_gate_flags_semicolon_regression(tmp_path: Path) -> None:
    (tmp_path / "docs" / "uml").mkdir(parents=True)
    (tmp_path / "docs" / "uml" / "bad.md").write_text(_md(BAD_SEQUENCE), encoding="utf-8")
    (tmp_path / "docs" / "uml" / "good.md").write_text(_md(GOOD_SEQUENCE, GOOD_FLOWCHART), encoding="utf-8")

    assert _BUN is not None  # guaranteed by @_INTEGRATION
    errors = scan_mermaid_syntax.verify(tmp_path, _BUN)
    assert len(errors) == 1
    assert "docs/uml/bad.md" in errors[0]


@_INTEGRATION
def test_live_gate_flags_broken_ast_block(tmp_path: Path) -> None:
    # The ast directory is no longer exempt (#1598): a broken generated block
    # must be flagged. The #1598 bug class is a backslash-quote (\") inside a
    # node label, which the Mermaid parser rejects.
    ast = tmp_path / "docs" / "generated" / "scripts" / "ast"
    ast.mkdir(parents=True)
    (ast / "x.md").write_text('```mermaid\nflowchart TD\n  N1["a\\"b"]\n```\n', encoding="utf-8")

    assert _BUN is not None  # guaranteed by @_INTEGRATION
    errors = scan_mermaid_syntax.verify(tmp_path, _BUN)
    assert len(errors) == 1
    assert "docs/generated/scripts/ast/x.md" in errors[0]


@_INTEGRATION
def test_live_gate_passes_real_uml_sequences() -> None:
    blocks = []
    for name in ("branch-local-remote.state.md", "branch-local-remote.state.ja.md"):
        path = REPO_ROOT / "docs" / "uml" / name
        blocks += scan_mermaid_syntax.extract_blocks(path, path.read_text(encoding="utf-8"))
    assert blocks, "expected the committed UML sequence blocks to exist"

    assert _BUN is not None  # guaranteed by @_INTEGRATION
    results = scan_mermaid_syntax.run_parser(blocks, _BUN)
    assert all(r["ok"] for r in results), [r for r in results if not r["ok"]]
