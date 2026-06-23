"""Generate Mermaid if-branch diagrams for GitHub Actions workflow YAML files.

Each output file is named ``<workflow-stem>-if-branches.md`` and placed in
``docs/generated/workflows/`` (configurable with ``--output-dir``).

CLI
---
  # Write Markdown diagrams; omit paths to process all .github/workflows/*.yml
  python3 scripts/workflow_diagram.py diagram-doc \\
      [<workflow.yml> ...] [--output-dir docs/generated/workflows]

  # Render Mermaid only to stdout (preview / debug)
  python3 scripts/workflow_diagram.py diagram <workflow.yml>
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_WORKFLOWS_DIR = Path(".github/workflows")
_OUTPUT_DIR = Path("docs/generated/workflows")

_PREAMBLE_TEMPLATE = (
    "# {title}\n\n"
    "This file is generated from `{source}` by "
    "`python3 scripts/workflow_diagram.py diagram-doc`. "
    "Do not edit it by hand; update the workflow YAML and regenerate instead.\n\n"
    "```mermaid\n"
    "{mermaid}"
    "```\n"
)

# Extracts event names from GitHub Actions expression syntax:
#   github.event_name == 'push'  →  "push"
_EVENT_NAME_RE = re.compile(r"github\.event_name\s*==\s*['\"](\w[\w-]*)['\"]")

# Strips characters that are invalid in a Mermaid node identifier.
_MERMAID_ID_STRIP = re.compile(r"[^A-Za-z0-9_]")


@dataclass
class Trigger:
    event: str
    filters: dict[str, str] = field(default_factory=dict)

    def node_id(self) -> str:
        return "T_" + _MERMAID_ID_STRIP.sub("_", self.event)

    def label(self) -> str:
        # Mermaid literal \n creates a newline inside a node label.
        parts = [self.event]
        for k, v in self.filters.items():
            v_str = str(v)
            # Complex nested values (e.g. workflow_dispatch inputs dict) are
            # truncated to keep node labels readable.
            if len(v_str) > 40:
                v_str = v_str[:37] + "..."
            parts.append(f"{k}: {v_str}")
        return "\\n".join(parts)


@dataclass
class StepBranch:
    name: str
    if_condition: str


@dataclass
class Job:
    job_id: str
    if_condition: str | None
    needs: list[str] = field(default_factory=list)
    steps_with_if: list[StepBranch] = field(default_factory=list)

    def node_id(self) -> str:
        return "J_" + _MERMAID_ID_STRIP.sub("_", self.job_id)


@dataclass
class WorkflowDiagram:
    workflow_name: str
    source_path: Path
    triggers: list[Trigger]
    jobs: list[Job]


def _get_on_section(data: dict[Any, Any]) -> Any:
    # PyYAML 1.1 parses the bare key 'on' as boolean True.  GitHub Actions
    # files use 'on' as the trigger key, so check both forms.
    return data.get(True, data.get("on", {}))


def _parse_triggers(on_val: Any) -> list[Trigger]:
    if isinstance(on_val, str):
        return [Trigger(event=on_val)]
    if isinstance(on_val, list):
        return [Trigger(event=str(e)) for e in on_val]
    if isinstance(on_val, dict):
        result: list[Trigger] = []
        for event, config in on_val.items():
            filters: dict[str, str] = {}
            if isinstance(config, dict):
                for k, v in config.items():
                    filters[str(k)] = str(v)
            result.append(Trigger(event=str(event), filters=filters))
        return result
    return []


def _parse_jobs(jobs_val: Any) -> list[Job]:
    if not isinstance(jobs_val, dict):
        return []
    result: list[Job] = []
    for job_id, job_data in jobs_val.items():
        if not isinstance(job_data, dict):
            continue
        raw_if = job_data.get("if")
        if_cond = str(raw_if) if raw_if is not None else None

        needs_raw = job_data.get("needs", [])
        if isinstance(needs_raw, str):
            needs: list[str] = [needs_raw]
        elif isinstance(needs_raw, list):
            needs = [str(n) for n in needs_raw]
        else:
            needs = []

        steps_with_if: list[StepBranch] = []
        for step in job_data.get("steps") or []:
            if not isinstance(step, dict):
                continue
            step_if = step.get("if")
            if step_if is None:
                continue
            name = str(step.get("name") or step.get("id") or "(unnamed)")
            steps_with_if.append(StepBranch(name=name, if_condition=str(step_if)))

        result.append(Job(
            job_id=str(job_id),
            if_condition=if_cond,
            needs=needs,
            steps_with_if=steps_with_if,
        ))
    return result


def parse_workflow(path: Path) -> WorkflowDiagram:
    """Parse a workflow YAML file into a :class:`WorkflowDiagram`."""
    data: dict[Any, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    name = str(data.get("name", path.stem))
    triggers = _parse_triggers(_get_on_section(data))
    jobs = _parse_jobs(data.get("jobs"))
    return WorkflowDiagram(
        workflow_name=name,
        source_path=path,
        triggers=triggers,
        jobs=jobs,
    )


def _mermaid_escape(text: str) -> str:
    """Escape characters that would break a Mermaid quoted label."""
    return text.replace('"', "'").replace("\n", " ")


def _shorten(text: str, max_len: int = 72) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "~"


def render_mermaid(diagram: WorkflowDiagram) -> str:
    """Render *diagram* as a Mermaid ``flowchart TD`` string."""
    lines: list[str] = ["flowchart TD"]

    # Trigger nodes
    if diagram.triggers:
        lines.append("")
        for t in diagram.triggers:
            lbl = _mermaid_escape(t.label())
            lines.append(f'    {t.node_id()}(["on: {lbl}"])')

    # Job nodes and their step-branch child nodes
    lines.append("")
    for j in diagram.jobs:
        lines.append(f'    {j.node_id()}["{_mermaid_escape(j.job_id)}"]')
        for idx, step in enumerate(j.steps_with_if):
            step_node = f"S_{j.node_id()}_{idx}"
            lbl = _mermaid_escape(step.name)
            lines.append(f'    {step_node}(("{lbl}"))')

    # Edges
    lines.append("")
    job_by_id = {j.job_id: j for j in diagram.jobs}

    for j in diagram.jobs:
        if j.needs:
            # Connect from parent job(s) via needs: dependency
            for parent_id in j.needs:
                parent_job = job_by_id.get(parent_id)
                if parent_job is None:
                    continue
                if j.if_condition:
                    lbl = _mermaid_escape(_shorten(j.if_condition))
                    lines.append(f'    {parent_job.node_id()} -->|"{lbl}"| {j.node_id()}')
                else:
                    lines.append(f"    {parent_job.node_id()} --> {j.node_id()}")
        else:
            # Connect from matching trigger(s)
            event_names = _EVENT_NAME_RE.findall(j.if_condition or "")
            for t in diagram.triggers:
                if event_names and t.event not in event_names:
                    continue  # if: condition names specific events; skip unmatched
                if j.if_condition:
                    lbl = _mermaid_escape(_shorten(j.if_condition))
                    lines.append(f'    {t.node_id()} -->|"{lbl}"| {j.node_id()}')
                else:
                    lines.append(f"    {t.node_id()} --> {j.node_id()}")

        # Step-branch edges within the job
        for idx, step in enumerate(j.steps_with_if):
            step_node = f"S_{j.node_id()}_{idx}"
            lbl = _mermaid_escape(_shorten(step.if_condition))
            lines.append(f'    {j.node_id()} -->|"{lbl}"| {step_node}')

    return "\n".join(lines) + "\n"


def render_markdown(diagram: WorkflowDiagram) -> str:
    """Render *diagram* as a Markdown document with a Mermaid code block."""
    source = str(diagram.source_path).replace("\\", "/")
    title = f"Workflow if-branches: {diagram.workflow_name}"
    return _PREAMBLE_TEMPLATE.format(
        title=title,
        source=source,
        mermaid=render_mermaid(diagram),
    )


def output_path_for(workflow_path: Path, output_dir: Path) -> Path:
    """Return the canonical output path for *workflow_path* under *output_dir*."""
    return output_dir / f"{workflow_path.stem}-if-branches.md"


def _cmd_diagram(args: argparse.Namespace) -> int:
    path = Path(args.workflow)
    if not path.exists():
        print(f"::error::file not found: {path}", file=sys.stderr)
        return 1
    diagram = parse_workflow(path)
    print(render_mermaid(diagram), end="")
    return 0


def _cmd_diagram_doc(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)

    if args.workflows:
        workflow_paths = [Path(w) for w in args.workflows]
    else:
        workflow_paths = sorted(_WORKFLOWS_DIR.glob("*.yml"))

    if not workflow_paths:
        print("::warning::no workflow files found", file=sys.stderr)
        return 0

    errors = 0
    written: set[Path] = set()
    for wf_path in workflow_paths:
        if not wf_path.exists():
            print(f"::error::file not found: {wf_path}", file=sys.stderr)
            errors += 1
            continue
        diagram = parse_workflow(wf_path)
        out = output_path_for(wf_path, output_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_markdown(diagram), encoding="utf-8")
        written.add(out.resolve())

    # On a full regeneration (no explicit workflow list), prune orphaned
    # diagrams: ``*-if-branches.md`` files whose source workflow no longer
    # exists. This keeps docs/generated/workflows/ a faithful mirror of the
    # current workflow set so the post-merge automation owns deletions too, not
    # just additions. A scoped run (explicit workflows) never prunes.
    if not args.workflows and output_dir.exists():
        for stale in sorted(output_dir.glob("*-if-branches.md")):
            if stale.resolve() not in written:
                stale.unlink()
                print(f"pruned orphaned diagram: {stale}")

    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diagram = sub.add_parser("diagram", help="Render Mermaid to stdout.")
    p_diagram.add_argument("workflow", help="Path to workflow YAML file.")
    p_diagram.set_defaults(func=_cmd_diagram)

    p_doc = sub.add_parser(
        "diagram-doc",
        help="Write Markdown if-branch diagrams to the output directory.",
    )
    p_doc.add_argument(
        "workflows",
        nargs="*",
        metavar="workflow.yml",
        help="Workflow file paths. Default: all .github/workflows/*.yml.",
    )
    p_doc.add_argument(
        "--output-dir",
        default=str(_OUTPUT_DIR),
        help=f"Output directory (default: {_OUTPUT_DIR}).",
    )
    p_doc.set_defaults(func=_cmd_diagram_doc)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
