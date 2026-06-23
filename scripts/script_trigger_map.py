#!/usr/bin/env python3
"""Generate a reverse-map of where each ``scripts/*.py`` is launched from.

The dependency graph (#1543) shows how scripts import one another; it does not
show how the harness *invokes* them. This generator answers the inverse
question; "where is ``scripts/X.py`` triggered from?"; by scanning the four
launch surfaces of the repository for literal ``scripts/<name>.py`` references:

* ``.github/workflows/*.yml``; ``run:`` steps (location: ``<file> (<job>)``).
* ``.pre-commit-config.yaml``; hook ``entry`` strings (location: hook ``id``).
* ``scripts/preflight_all.py``; the ``Step(argv=...)`` definitions, read via
  :mod:`ast` so a step name maps to the scripts its argv invokes.
* agent hooks (``scripts/agent_hooks_source.json``); hook ``command`` strings
  (location: ``<agent>:<event>``).

``all-doc`` writes ``docs/generated/scripts/trigger-map.md`` with a
script -> (trigger kind, location) table and an unreferenced-scripts list
(dead-script candidates). Content under ``docs/generated/scripts/`` is owned by
the post-merge automation; the pre-push and pre-merge gates do not regenerate
it; the same single-producer model as the dependency graph (refs #1540,
#1543).

Detection is string-match based, so its coverage is bounded:

* fact: only literal ``scripts/<name>.py`` substrings in the four sources above
  are matched.
* speculation: a script invoked through a dynamically computed command (a
  variable or assembled path) is not matched and may surface as a dead-script
  candidate even though it is reachable.
* speculation: a helper module imported by another script (e.g. ``_git.py``)
  is reachable via import, not via these launch sources, so it is expected in
  the unreferenced list; cross-reference the dependency graph (#1543).

Architecture: pure functions on top (the four ``_*_refs`` collectors,
:func:`collect_refs`, :func:`render_trigger_markdown`), a single filesystem
write at the bottom (:func:`write_trigger_doc`).

Contract:
- Inputs: subcommands ``all-doc`` (writes the doc) and ``preview`` (stdout
  preview); optional ``--root`` path (defaults to the current directory).
- Outputs: ``docs/generated/scripts/trigger-map.md`` for ``all-doc``, the same
  Markdown on stdout for ``preview``; exit 0 when generation succeeds. The
  generated doc and this Contract both record that string-match detection can
  miss dynamic invocations (fact vs speculation separated above).
- Failure policy: fails loud per CLAUDE.md section 4 when a scanned source
  exists but cannot be parsed, or the output file cannot be written. A source
  file that is simply absent contributes no references (a plausible state, not
  an error).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

SCRIPTS_DIR = Path("scripts")
DOC_PATH = Path("docs/generated/scripts/trigger-map.md")

WORKFLOWS_DIR = Path(".github/workflows")
PRECOMMIT_CONFIG = Path(".pre-commit-config.yaml")
PREFLIGHT_SCRIPT = Path("scripts/preflight_all.py")
AGENT_HOOKS_SOURCE = Path("scripts/agent_hooks_source.json")

# Matches a literal ``scripts/<name>.py`` reference and captures ``<name>.py``.
# Mirrors the invocation-name shape used by the workflow CLI-contract inventory.
_SCRIPT_REF = re.compile(r"scripts/([A-Za-z_][\w-]*\.py)")


@dataclass(frozen=True, order=True)
class TriggerRef:
    """One ``script <- trigger`` reference found in a launch source."""

    script: str
    kind: str
    location: str


def script_filenames(root: Path = Path()) -> frozenset[str]:
    """Return the ``<name>.py`` file names under ``scripts/`` at *root*."""
    scripts_dir = root / SCRIPTS_DIR
    if not scripts_dir.is_dir():
        return frozenset()
    return frozenset(path.name for path in scripts_dir.glob("*.py") if path.is_file())


def _workflow_refs(root: Path) -> list[TriggerRef]:
    """Collect ``scripts/X.py`` references from workflow ``run:`` steps.

    Each workflow YAML is walked structurally (``jobs.<job>.steps[*].run``).
    A workflow whose GitHub Actions extensions defeat ``yaml.safe_load`` falls
    back to a raw-text scan so it still contributes; the same robustness
    posture as the workflow CLI-contract inventory.
    """
    wf_dir = root / WORKFLOWS_DIR
    if not wf_dir.is_dir():
        return []
    refs: list[TriggerRef] = []
    for path in sorted(wf_dir.glob("*.yml")):
        raw = path.read_text(encoding="utf-8")
        try:
            document: object = yaml.safe_load(raw)
        except yaml.YAMLError:
            document = None
        jobs = document.get("jobs") if isinstance(document, dict) else None
        if not isinstance(jobs, dict):
            for match in _SCRIPT_REF.finditer(raw):
                refs.append(TriggerRef(match.group(1), "workflow", f"{path.name} (<unparsed>)"))
            continue
        for job_name, job in jobs.items():
            steps = job.get("steps") if isinstance(job, dict) else None
            if not isinstance(steps, list):
                continue
            for step in steps:
                run = step.get("run") if isinstance(step, dict) else None
                if not isinstance(run, str):
                    continue
                for match in _SCRIPT_REF.finditer(run):
                    refs.append(
                        TriggerRef(match.group(1), "workflow", f"{path.name} ({job_name})")
                    )
    return refs


def _precommit_refs(root: Path) -> list[TriggerRef]:
    """Collect references from ``.pre-commit-config.yaml`` hook entries."""
    path = root / PRECOMMIT_CONFIG
    if not path.is_file():
        return []
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    repos = document.get("repos") if isinstance(document, dict) else None
    if not isinstance(repos, list):
        return []
    refs: list[TriggerRef] = []
    for repo in repos:
        hooks = repo.get("hooks") if isinstance(repo, dict) else None
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            entry = hook.get("entry") if isinstance(hook, dict) else None
            if not isinstance(entry, str):
                continue
            hook_id = str(hook.get("id", "?"))
            for match in _SCRIPT_REF.finditer(entry):
                refs.append(TriggerRef(match.group(1), "pre-commit", hook_id))
    return refs


def _str_constants(node: ast.AST) -> list[str]:
    """Return every string constant nested under *node*."""
    return [
        sub.value
        for sub in ast.walk(node)
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
    ]


def _step_name(call: ast.Call) -> str:
    """Return the ``name=`` string argument of a ``Step(...)`` call, or ``?``."""
    for keyword in call.keywords:
        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            if isinstance(value, str):
                return value
    return "?"


def _preflight_refs(root: Path) -> list[TriggerRef]:
    """Collect references from ``scripts/preflight_all.py`` ``Step`` argv.

    The file is parsed with :mod:`ast` (never imported) so each ``Step`` call's
    ``name=`` maps to the ``scripts/X.py`` tokens in its ``argv=`` tuple.
    """
    path = root / PREFLIGHT_SCRIPT
    if not path.is_file():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    refs: list[TriggerRef] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "Step":
            continue
        name = _step_name(node)
        argv = next((kw.value for kw in node.keywords if kw.arg == "argv"), None)
        if argv is None:
            continue
        for literal in _str_constants(argv):
            for match in _SCRIPT_REF.finditer(literal):
                refs.append(TriggerRef(match.group(1), "preflight", name))
    return refs


def _agent_hook_refs(root: Path) -> list[TriggerRef]:
    """Collect references from agent hook ``command`` strings.

    Walks ``targets[*].config.hooks.<event>[*].hooks[*].command`` in
    ``scripts/agent_hooks_source.json``; the location is ``<agent>:<event>``.
    """
    path = root / AGENT_HOOKS_SOURCE
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = data.get("targets") if isinstance(data, dict) else None
    if not isinstance(targets, list):
        return []
    refs: list[TriggerRef] = []
    for target in targets:
        config = target.get("config") if isinstance(target, dict) else None
        hooks = config.get("hooks") if isinstance(config, dict) else None
        if not isinstance(hooks, dict):
            continue
        agent = str(target.get("agent", "?"))
        for event, entries in hooks.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                inner = entry.get("hooks") if isinstance(entry, dict) else None
                if not isinstance(inner, list):
                    continue
                for hook in inner:
                    command = hook.get("command") if isinstance(hook, dict) else None
                    if not isinstance(command, str):
                        continue
                    for match in _SCRIPT_REF.finditer(command):
                        refs.append(
                            TriggerRef(match.group(1), "agent-hook", f"{agent}:{event}")
                        )
    return refs


def collect_refs(root: Path = Path()) -> tuple[TriggerRef, ...]:
    """Return the deduplicated, sorted trigger references across all sources."""
    refs: set[TriggerRef] = set()
    refs.update(_workflow_refs(root))
    refs.update(_precommit_refs(root))
    refs.update(_preflight_refs(root))
    refs.update(_agent_hook_refs(root))
    return tuple(sorted(refs))


def unreferenced_scripts(
    refs: tuple[TriggerRef, ...], scripts: frozenset[str]
) -> tuple[str, ...]:
    """Return the sorted script names that no scanned source references."""
    referenced = frozenset(ref.script for ref in refs)
    return tuple(sorted(scripts - referenced))


def render_trigger_markdown(
    refs: tuple[TriggerRef, ...], scripts: frozenset[str]
) -> str:
    """Render the trigger reverse-map as a Markdown document."""
    lines = [
        "# Script trigger reverse-map",
        "",
        "This file is generated from the repository launch surfaces by "
        "`python3 scripts/script_trigger_map.py all-doc`. Do not edit it by "
        "hand: content under `docs/generated/scripts/` is owned by the "
        "post-merge automation (refs #1540, #1543); update the source "
        "instead.",
        "",
        "Detection is string-match based:",
        "",
        "- Fact: only literal `scripts/<name>.py` references in "
        "`.github/workflows/*.yml` `run:` steps, `.pre-commit-config.yaml` "
        "hook entries, `scripts/preflight_all.py` `Step` argv, and "
        "`scripts/agent_hooks_source.json` commands are matched.",
        "- Speculation: a script launched through a dynamically computed "
        "command is not matched and may appear as a dead-script candidate "
        "even though it is reachable.",
        "- Speculation: a helper module imported by another script (e.g. "
        "`_git.py`) is reachable via import, not via these launch sources, so "
        "it is expected in the unreferenced list; cross-reference the "
        "dependency graph (#1543).",
        "",
    ]

    lines.extend(["## Trigger map", ""])
    if not refs:
        lines.extend(["No scanned source references any script.", ""])
    else:
        lines.extend(["| Script | Trigger kind | Location |", "| --- | --- | --- |"])
        for ref in refs:
            lines.append(f"| `{ref.script}` | {ref.kind} | `{ref.location}` |")
        lines.append("")

    unreferenced = unreferenced_scripts(refs, scripts)
    lines.extend(["## Unreferenced scripts (dead script candidates)", ""])
    if not unreferenced:
        lines.extend(["Every script is referenced by at least one scanned source.", ""])
    else:
        lines.append(
            f"{len(unreferenced)} script(s) are referenced by no scanned launch "
            "source (see the detection caveats above before treating one as dead):"
        )
        lines.append("")
        lines.append(", ".join(f"`{name}`" for name in unreferenced))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_document(root: Path = Path()) -> str:
    """Build the trigger reverse-map Markdown for the repository at *root*."""
    return render_trigger_markdown(collect_refs(root), script_filenames(root))


def write_trigger_doc(root: Path = Path()) -> Path:
    """Write the trigger reverse-map doc under ``docs/generated/scripts/``."""
    target = root / DOC_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_document(root), encoding="utf-8")
    return target


def _cmd_all_doc(args: argparse.Namespace) -> int:
    write_trigger_doc(Path(args.root))
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    sys.stdout.write(build_document(Path(args.root)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_all_doc = sub.add_parser(
        "all-doc",
        help="Write docs/generated/scripts/trigger-map.md.",
    )
    p_all_doc.add_argument("--root", default=".", help="Repository root (default current directory).")
    p_all_doc.set_defaults(func=_cmd_all_doc)

    p_preview = sub.add_parser(
        "preview",
        help="Print the trigger reverse-map Markdown to stdout (no write).",
    )
    p_preview.add_argument("--root", default=".", help="Repository root (default current directory).")
    p_preview.set_defaults(func=_cmd_preview)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
