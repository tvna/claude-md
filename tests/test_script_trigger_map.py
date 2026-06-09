"""Tests for scripts/script_trigger_map.py."""

from __future__ import annotations

from pathlib import Path

import pytest
import script_trigger_map as stm

pytestmark = pytest.mark.shard_ci_ops


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_workflow_refs_only_match_run_steps(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - name: run gate\n"
        "        run: python3 scripts/alpha.py verify\n"
        "      - name: unrelated\n"
        "        uses: scripts/not_a_run.py\n",
    )
    refs = stm._workflow_refs(tmp_path)
    # The ``uses:`` reference is ignored; only the ``run:`` step is mapped.
    assert refs == [stm.TriggerRef("alpha.py", "workflow", "ci.yml (build)")]


def test_precommit_refs_use_hook_id_as_location(tmp_path: Path) -> None:
    _write(
        tmp_path / ".pre-commit-config.yaml",
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: scan-beta\n"
        "        entry: uv run python scripts/beta.py verify\n",
    )
    assert stm._precommit_refs(tmp_path) == [
        stm.TriggerRef("beta.py", "pre-commit", "scan-beta")
    ]


def test_preflight_refs_map_step_name_to_argv_scripts(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/preflight_all.py",
        "STEPS = (\n"
        "    Step(\n"
        "        name='scan_gamma',\n"
        "        argv=('python3', 'scripts/gamma.py', 'verify'),\n"
        "    ),\n"
        ")\n",
    )
    assert stm._preflight_refs(tmp_path) == [
        stm.TriggerRef("gamma.py", "preflight", "scan_gamma")
    ]


def test_agent_hook_refs_use_agent_and_event_location(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/agent_hooks_source.json",
        '{"targets": [{"agent": "claude", "config": {"hooks": {'
        '"PreToolUse": [{"hooks": [{"type": "command", '
        '"command": "python3 scripts/delta.py"}]}]}}}]}',
    )
    assert stm._agent_hook_refs(tmp_path) == [
        stm.TriggerRef("delta.py", "agent-hook", "claude:PreToolUse")
    ]


def test_collect_refs_dedupes_and_sorts(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/workflows/ci.yml",
        "jobs:\n  b:\n    steps:\n      - run: python3 scripts/alpha.py x\n",
    )
    _write(
        tmp_path / ".pre-commit-config.yaml",
        "repos:\n  - repo: local\n    hooks:\n      - id: a\n        entry: python3 scripts/alpha.py\n",
    )
    refs = stm.collect_refs(tmp_path)
    # Two distinct sources reference alpha.py -> two sorted, deduped refs.
    assert refs == (
        stm.TriggerRef("alpha.py", "pre-commit", "a"),
        stm.TriggerRef("alpha.py", "workflow", "ci.yml (b)"),
    )


def test_unreferenced_scripts_excludes_referenced(tmp_path: Path) -> None:
    refs = (stm.TriggerRef("alpha.py", "workflow", "ci.yml (b)"),)
    scripts = frozenset({"alpha.py", "_helper.py", "lonely.py"})
    assert stm.unreferenced_scripts(refs, scripts) == ("_helper.py", "lonely.py")


def test_render_markdown_has_table_and_dead_candidates() -> None:
    refs = (
        stm.TriggerRef("alpha.py", "preflight", "scan_alpha"),
        stm.TriggerRef("alpha.py", "workflow", "ci.yml (build)"),
    )
    scripts = frozenset({"alpha.py", "_git.py"})
    markdown = stm.render_trigger_markdown(refs, scripts)

    assert markdown.startswith("# Script trigger reverse-map\n")
    # The fact/speculation detection caveat is present in the generated doc.
    assert "Fact: only literal `scripts/<name>.py`" in markdown
    assert "Speculation:" in markdown
    # The table renders one row per (script, kind, location) reference.
    assert "| `alpha.py` | preflight | `scan_alpha` |" in markdown
    assert "| `alpha.py` | workflow | `ci.yml (build)` |" in markdown
    # _git.py has no trigger -> listed as a dead-script candidate.
    dead = markdown.split("## Unreferenced scripts", 1)[1]
    assert "`_git.py`" in dead


def test_render_markdown_handles_empty_inputs() -> None:
    markdown = stm.render_trigger_markdown((), frozenset())
    assert "No scanned source references any script." in markdown
    assert "Every script is referenced by at least one scanned source." in markdown


def test_missing_sources_yield_no_refs(tmp_path: Path) -> None:
    # An empty root has none of the four sources; collection is empty, not an error.
    assert stm.collect_refs(tmp_path) == ()
    assert stm.script_filenames(tmp_path) == frozenset()


def test_write_trigger_doc_writes_expected_path(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/alpha.py",
        "x = 1\n",
    )
    _write(
        tmp_path / ".github/workflows/ci.yml",
        "jobs:\n  b:\n    steps:\n      - run: python3 scripts/alpha.py x\n",
    )
    target = stm.write_trigger_doc(tmp_path)
    assert target == tmp_path / "docs/generated/scripts/trigger-map.md"
    assert target.read_text(encoding="utf-8") == stm.build_document(tmp_path)
    assert "| `alpha.py` | workflow | `ci.yml (b)` |" in target.read_text(encoding="utf-8")


def test_all_doc_cli_writes_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "scripts/alpha.py", "x = 1\n")
    monkeypatch.chdir(tmp_path)
    assert stm.main(["all-doc"]) == 0
    assert Path("docs/generated/scripts/trigger-map.md").is_file()


def test_preview_cli_writes_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / "scripts/alpha.py", "x = 1\n")
    monkeypatch.chdir(tmp_path)
    assert stm.main(["preview"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Script trigger reverse-map\n")
    assert not Path("docs/generated/scripts/trigger-map.md").exists()
