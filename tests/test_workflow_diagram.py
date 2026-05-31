"""Unit tests for scripts/workflow_diagram.py."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import workflow_diagram as wd
import yaml

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_yaml(text: str) -> dict[Any, Any]:
    return yaml.safe_load(textwrap.dedent(text)) or {}


def _write_workflow(tmp_path: Path, content: str, name: str = "test.yml") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _get_on_section
# ---------------------------------------------------------------------------

class TestGetOnSection:
    def test_pyaml_boolean_key(self) -> None:
        data = _make_yaml("on: push\nname: x\n")
        # PyYAML parses 'on' as True
        assert wd._get_on_section(data) == "push"

    def test_explicit_on_string_key(self) -> None:
        data: dict[Any, Any] = {"on": "push"}
        assert wd._get_on_section(data) == "push"

    def test_missing_returns_empty_dict(self) -> None:
        assert wd._get_on_section({}) == {}


# ---------------------------------------------------------------------------
# _parse_triggers
# ---------------------------------------------------------------------------

class TestParseTriggers:
    def test_string_on(self) -> None:
        triggers = wd._parse_triggers("push")
        assert len(triggers) == 1
        assert triggers[0].event == "push"
        assert triggers[0].filters == {}

    def test_list_on(self) -> None:
        triggers = wd._parse_triggers(["push", "pull_request"])
        assert [t.event for t in triggers] == ["push", "pull_request"]

    def test_dict_on_with_filters(self) -> None:
        on_val = {"push": {"branches": ["main"]}, "workflow_dispatch": None}
        triggers = wd._parse_triggers(on_val)
        events = {t.event for t in triggers}
        assert "push" in events
        assert "workflow_dispatch" in events
        push = next(t for t in triggers if t.event == "push")
        assert "branches" in push.filters

    def test_none_returns_empty(self) -> None:
        assert wd._parse_triggers(None) == []

    def test_unknown_type_returns_empty(self) -> None:
        assert wd._parse_triggers(42) == []


# ---------------------------------------------------------------------------
# _parse_jobs
# ---------------------------------------------------------------------------

class TestParseJobs:
    def test_job_without_if(self) -> None:
        jobs = wd._parse_jobs({"build": {"runs-on": "ubuntu-latest", "steps": []}})
        assert len(jobs) == 1
        assert jobs[0].job_id == "build"
        assert jobs[0].if_condition is None
        assert jobs[0].needs == []

    def test_job_with_if(self) -> None:
        jobs = wd._parse_jobs({
            "deploy": {
                "if": "github.event_name == 'push'",
                "runs-on": "ubuntu-latest",
                "steps": [],
            }
        })
        assert jobs[0].if_condition == "github.event_name == 'push'"

    def test_job_with_needs_string(self) -> None:
        jobs = wd._parse_jobs({
            "b": {"needs": "a", "runs-on": "ubuntu-latest", "steps": []}
        })
        assert jobs[0].needs == ["a"]

    def test_job_with_needs_list(self) -> None:
        jobs = wd._parse_jobs({
            "c": {"needs": ["a", "b"], "runs-on": "ubuntu-latest", "steps": []}
        })
        assert jobs[0].needs == ["a", "b"]

    def test_steps_with_if(self) -> None:
        jobs = wd._parse_jobs({
            "test": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {"name": "Run", "run": "pytest"},
                    {"name": "Upload", "if": "always()", "uses": "codecov/..."},
                ],
            }
        })
        assert len(jobs[0].steps_with_if) == 1
        assert jobs[0].steps_with_if[0].name == "Upload"
        assert jobs[0].steps_with_if[0].if_condition == "always()"

    def test_steps_without_if_ignored(self) -> None:
        jobs = wd._parse_jobs({
            "test": {
                "runs-on": "ubuntu-latest",
                "steps": [{"name": "A", "run": "echo hi"}],
            }
        })
        assert jobs[0].steps_with_if == []

    def test_non_dict_value_skipped(self) -> None:
        jobs = wd._parse_jobs({"bad": "not-a-dict"})
        assert jobs == []

    def test_non_dict_input_returns_empty(self) -> None:
        assert wd._parse_jobs(None) == []


# ---------------------------------------------------------------------------
# Trigger helpers
# ---------------------------------------------------------------------------

class TestTriggerHelpers:
    def test_node_id_replaces_non_alnum(self) -> None:
        t = wd.Trigger(event="pull_request_target")
        assert t.node_id() == "T_pull_request_target"

    def test_label_no_filters(self) -> None:
        t = wd.Trigger(event="push")
        assert t.label() == "push"

    def test_label_with_filters(self) -> None:
        t = wd.Trigger(event="push", filters={"branches": "['main']"})
        lbl = t.label()
        assert "push" in lbl
        assert "branches" in lbl

    def test_label_truncates_long_filter_value(self) -> None:
        long_val = "x" * 100
        t = wd.Trigger(event="workflow_dispatch", filters={"inputs": long_val})
        lbl = t.label()
        assert "..." in lbl
        assert len(lbl.split("\\n")[1]) <= 48  # "inputs: " (8) + 37 chars + "..."


# ---------------------------------------------------------------------------
# render_mermaid
# ---------------------------------------------------------------------------

class TestRenderMermaid:
    def _simple_diagram(self) -> wd.WorkflowDiagram:
        return wd.WorkflowDiagram(
            workflow_name="Test",
            source_path=Path(".github/workflows/test.yml"),
            triggers=[wd.Trigger(event="push")],
            jobs=[
                wd.Job(
                    job_id="build",
                    if_condition=None,
                    needs=[],
                    steps_with_if=[],
                )
            ],
        )

    def test_starts_with_flowchart(self) -> None:
        mermaid = wd.render_mermaid(self._simple_diagram())
        assert mermaid.startswith("flowchart TD\n")

    def test_trigger_node_present(self) -> None:
        mermaid = wd.render_mermaid(self._simple_diagram())
        assert "T_push" in mermaid

    def test_job_node_present(self) -> None:
        mermaid = wd.render_mermaid(self._simple_diagram())
        assert "J_build" in mermaid

    def test_edge_trigger_to_job_no_condition(self) -> None:
        mermaid = wd.render_mermaid(self._simple_diagram())
        assert "T_push --> J_build" in mermaid

    def test_edge_with_if_condition(self) -> None:
        diagram = wd.WorkflowDiagram(
            workflow_name="T",
            source_path=Path(".github/workflows/t.yml"),
            triggers=[wd.Trigger(event="push")],
            jobs=[
                wd.Job(
                    job_id="deploy",
                    if_condition="github.event_name == 'push'",
                    needs=[],
                )
            ],
        )
        mermaid = wd.render_mermaid(diagram)
        assert "T_push" in mermaid
        assert "J_deploy" in mermaid
        assert '-->|"' in mermaid

    def test_needs_edge_from_parent_job(self) -> None:
        diagram = wd.WorkflowDiagram(
            workflow_name="T",
            source_path=Path(".github/workflows/t.yml"),
            triggers=[wd.Trigger(event="push")],
            jobs=[
                wd.Job(job_id="build", if_condition=None, needs=[]),
                wd.Job(
                    job_id="deploy",
                    if_condition=None,
                    needs=["build"],
                ),
            ],
        )
        mermaid = wd.render_mermaid(diagram)
        assert "J_build --> J_deploy" in mermaid

    def test_step_branch_node_and_edge(self) -> None:
        diagram = wd.WorkflowDiagram(
            workflow_name="T",
            source_path=Path(".github/workflows/t.yml"),
            triggers=[wd.Trigger(event="push")],
            jobs=[
                wd.Job(
                    job_id="test",
                    if_condition=None,
                    needs=[],
                    steps_with_if=[
                        wd.StepBranch(name="Upload", if_condition="always()")
                    ],
                )
            ],
        )
        mermaid = wd.render_mermaid(diagram)
        assert "S_J_test_0" in mermaid
        assert "J_test" in mermaid
        assert "always()" in mermaid

    def test_event_name_filter_skips_unmatched_trigger(self) -> None:
        diagram = wd.WorkflowDiagram(
            workflow_name="T",
            source_path=Path(".github/workflows/t.yml"),
            triggers=[
                wd.Trigger(event="push"),
                wd.Trigger(event="pull_request"),
            ],
            jobs=[
                wd.Job(
                    job_id="only_push",
                    if_condition="github.event_name == 'push'",
                    needs=[],
                )
            ],
        )
        mermaid = wd.render_mermaid(diagram)
        assert "T_push" in mermaid
        # pull_request trigger should NOT connect to only_push job
        assert "T_pull_request --> J_only_push" not in mermaid
        assert "T_pull_request -->|" not in mermaid

    def test_ends_with_newline(self) -> None:
        mermaid = wd.render_mermaid(self._simple_diagram())
        assert mermaid.endswith("\n")


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_contains_preamble(self) -> None:
        diagram = wd.WorkflowDiagram(
            workflow_name="My Workflow",
            source_path=Path(".github/workflows/my.yml"),
            triggers=[],
            jobs=[],
        )
        md = wd.render_markdown(diagram)
        assert "# Workflow if-branches: My Workflow" in md
        assert "Do not edit it by hand" in md
        assert "```mermaid" in md
        assert "```\n" in md

    def test_source_path_in_preamble(self) -> None:
        diagram = wd.WorkflowDiagram(
            workflow_name="X",
            source_path=Path(".github/workflows/x.yml"),
            triggers=[],
            jobs=[],
        )
        md = wd.render_markdown(diagram)
        assert ".github/workflows/x.yml" in md


# ---------------------------------------------------------------------------
# parse_workflow (integration)
# ---------------------------------------------------------------------------

class TestParseWorkflow:
    def test_parses_name_and_triggers(self, tmp_path: Path) -> None:
        wf = _write_workflow(
            tmp_path,
            """\
            name: My CI
            on:
              push:
                branches: [main]
            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        diagram = wd.parse_workflow(wf)
        assert diagram.workflow_name == "My CI"
        assert any(t.event == "push" for t in diagram.triggers)

    def test_parses_job_if_and_needs(self, tmp_path: Path) -> None:
        wf = _write_workflow(
            tmp_path,
            """\
            name: T
            on: push
            jobs:
              build:
                runs-on: ubuntu-latest
                steps: []
              deploy:
                needs: build
                if: "github.event_name == 'push'"
                runs-on: ubuntu-latest
                steps: []
            """,
        )
        diagram = wd.parse_workflow(wf)
        deploy = next(j for j in diagram.jobs if j.job_id == "deploy")
        assert deploy.needs == ["build"]
        assert deploy.if_condition is not None

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            wd.parse_workflow(tmp_path / "nonexistent.yml")

    def test_uses_stem_as_name_when_no_name_field(self, tmp_path: Path) -> None:
        wf = _write_workflow(
            tmp_path,
            """\
            on: push
            jobs:
              j:
                runs-on: ubuntu-latest
                steps: []
            """,
            name="my-workflow.yml",
        )
        diagram = wd.parse_workflow(wf)
        assert diagram.workflow_name == "my-workflow"


# ---------------------------------------------------------------------------
# output_path_for
# ---------------------------------------------------------------------------

class TestOutputPathFor:
    def test_stem_plus_suffix(self) -> None:
        out = wd.output_path_for(
            Path(".github/workflows/post-merge.yml"),
            Path("docs/generated/workflows"),
        )
        assert out == Path("docs/generated/workflows/post-merge-if-branches.md")


# ---------------------------------------------------------------------------
# CLI: main()
# ---------------------------------------------------------------------------

class TestCLIDiagram:
    def test_diagram_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        wf = _write_workflow(
            tmp_path,
            """\
            name: T
            on: push
            jobs:
              build:
                runs-on: ubuntu-latest
                steps: []
            """,
        )
        rc = wd.main(["diagram", str(wf)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "flowchart TD" in out

    def test_diagram_missing_file(self, tmp_path: Path) -> None:
        rc = wd.main(["diagram", str(tmp_path / "missing.yml")])
        assert rc == 1


class TestCLIDiagramDoc:
    def test_writes_output_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps: []\n",
            encoding="utf-8",
        )
        out_dir = tmp_path / "docs" / "generated" / "workflows"

        rc = wd.main(["diagram-doc", "--output-dir", str(out_dir)])
        assert rc == 0
        out_file = out_dir / "ci-if-branches.md"
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "flowchart TD" in content

    def test_explicit_workflow_path(self, tmp_path: Path) -> None:
        wf = _write_workflow(
            tmp_path,
            "name: X\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps: []\n",
        )
        out_dir = tmp_path / "out"
        rc = wd.main(["diagram-doc", str(wf), "--output-dir", str(out_dir)])
        assert rc == 0
        assert (out_dir / "test-if-branches.md").exists()

    def test_missing_explicit_workflow_returns_error(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "out"
        rc = wd.main([
            "diagram-doc",
            str(tmp_path / "nonexistent.yml"),
            "--output-dir",
            str(out_dir),
        ])
        assert rc == 1

    def test_no_workflows_found_warns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        # No .github/workflows directory → glob returns nothing
        out_dir = tmp_path / "out"
        rc = wd.main(["diagram-doc", "--output-dir", str(out_dir)])
        assert rc == 0
        assert "no workflow files found" in capsys.readouterr().err

    def test_checked_in_diagrams_are_current(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mirror what generate-docs.yml verifies: no drift in docs/generated/workflows/."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            rc = wd.main(["diagram-doc", "--output-dir", str(out_dir)])
            assert rc == 0

            checked_in = Path("docs/generated/workflows")
            for generated in out_dir.glob("*.md"):
                committed = checked_in / generated.name
                assert committed.exists(), f"missing committed file: {committed}"
                assert generated.read_text() == committed.read_text(), (
                    f"{committed} is out of date. "
                    "Run 'python3 scripts/workflow_diagram.py diagram-doc' and commit."
                )
