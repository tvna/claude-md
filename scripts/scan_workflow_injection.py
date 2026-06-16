#!/usr/bin/env python3
"""Flag untrusted GitHub context interpolated directly into workflow ``run:`` blocks.

Refs #1129. GitHub's security-hardening guidance warns that expressions
like ``${{ github.event.issue.title }}`` expanded inside a ``run:`` shell
script enable command injection: the attacker-controlled value is pasted
into the script body *before* the shell parses it, so a crafted issue
title can break out and run arbitrary commands. The safe pattern is to
route the value through an ``env:`` variable and reference ``"$VAR"`` in
the script, so the value reaches the shell as data, never as script text.

This gate is the deterministic sibling of ``scan_workflow_pip.py`` and
``scan_workflow_gh_calls.py``. The repository is currently clean -- every
untrusted context is already routed through ``env:`` -- so this gate is a
regression guard that keeps that discipline from drifting, not a fix for
an existing hole.

Untrusted contexts flagged (only inside ``run:`` values):

* ``github.event.*`` -- issue / PR / comment / review / commit payload
* ``github.head_ref`` -- the PR source branch name (attacker-named)
* ``github.head_commit`` -- head commit message / author fields

These are the contexts any *external* user can populate (open an issue,
a PR, a comment) without repository access, so they are the realistic
command-injection vector this gate targets.

Out of scope by design: ``workflow_dispatch`` / ``workflow_call``
``inputs.*``. Dispatching a workflow requires repository write access, so
inputs are not externally controllable; and GitHub-typed inputs
(``type: choice``/``boolean``/``number``) cannot carry shell payloads at
all. Flagging them would be false-positive churn against intentionally
inlined, typed inputs. ``env:``-indirection remains the recommended
pattern there too, but it is not enforced by this gate.

Interpolations elsewhere (``env:``, ``if:``, ``with:``,
``concurrency.group``) are intentionally NOT scanned: env-indirection is
the mitigation, so a value referenced there is safe.

Escape hatch: append ``# inject-ack`` to the offending line inside the run
block when an interpolation is genuinely safe and has been reviewed.

CLI::

    python3 scripts/scan_workflow_injection.py verify  # exit 1 on violations
    python3 scripts/scan_workflow_injection.py list     # print all matches

Exit codes:
    0  verify passed (no violations) or list completed
    1  verify found untrusted interpolation in a run block
    2  usage error

Tested by ``tests/test_scan_workflow_injection.py``.

Contract:
    Inputs: the ``.github/workflows/*.yml`` tree (no stdin, no env input).
    Outputs: ``::error file=...::`` annotations on stderr and a one-line
        summary; exit code as documented above.
    Failure policy: loud -- a workflow that cannot be parsed as YAML is
        skipped, but any detected untrusted interpolation fails the gate
        with a non-zero exit rather than passing silently.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import yaml

WORKFLOW_DIR = Path(".github/workflows")

# Lines carrying this marker bypass the scan. Mirrors the ACK escape-hatch
# precedent of ``scripts/scan_workflow_pip.py``.
ACK_MARKER = "# inject-ack"

# Externally attacker-controllable contexts whose direct interpolation
# into a shell ``run:`` body is a command-injection sink.
# ``github.event_name`` (no trailing dot) is deliberately NOT matched --
# it is a fixed enum, not free text. ``inputs.*`` is out of scope (see the
# module docstring: write-access-gated and typed). ``env:``-routed
# references never reach this scanner because only ``run:`` values are
# inspected.
_UNTRUSTED_CONTEXT = re.compile(
    r"\$\{\{[^}]*?\b(?:"
    r"github\.event\."
    r"|github\.head_ref\b"
    r"|github\.head_commit\b"
    r")[^}]*?\}\}"
)

_FRAGMENT_LEN = 80


class Violation(NamedTuple):
    workflow: str  # file basename
    job: str       # job key
    step: str      # step name, or "" if unnamed
    line: int      # 1-based line number within the run block
    fragment: str  # trimmed fragment starting at the match


def _load_yaml(wf_path: Path) -> dict[str, Any] | None:
    """Return parsed YAML dict, or None if the file is missing or not a dict."""
    try:
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _iter_run_steps(
    workflow_dir: Path,
) -> Iterator[tuple[str, str, str, str]]:
    """Yield ``(workflow_basename, job_id, step_name, run_text)`` for run steps.

    Skips workflow files that cannot be parsed as YAML dicts and steps that
    lack a string ``run:`` value.
    """
    for wf_path in sorted(workflow_dir.glob("*.yml")):
        data = _load_yaml(wf_path)
        if data is None:
            continue
        jobs = data.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps") or []
            if not isinstance(steps, list):
                continue
            for step in steps:
                if not isinstance(step, dict):
                    continue
                run_text = step.get("run")
                if not isinstance(run_text, str):
                    continue
                step_name = str(step.get("name") or "")
                yield wf_path.name, str(job_id), step_name, run_text


def scan_run_text(run_text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, fragment)`` for each untrusted interpolation.

    Line numbers are 1-based within *run_text*. Lines carrying
    :data:`ACK_MARKER` are treated as reviewed exceptions and skipped.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(run_text.splitlines(), start=1):
        if ACK_MARKER in line:
            continue
        match = _UNTRUSTED_CONTEXT.search(line)
        if match is not None:
            fragment = line[match.start() : match.start() + _FRAGMENT_LEN].strip()
            hits.append((lineno, fragment))
    return hits


def _iter_matches(workflow_dir: Path) -> Iterator[Violation]:
    for wf_name, job_id, step_name, run_text in _iter_run_steps(workflow_dir):
        for lineno, fragment in scan_run_text(run_text):
            yield Violation(
                workflow=wf_name,
                job=job_id,
                step=step_name,
                line=lineno,
                fragment=fragment,
            )


def find_violations(workflow_dir: Path = WORKFLOW_DIR) -> list[Violation]:
    """Return a Violation for every untrusted interpolation in a run block."""
    return list(_iter_matches(workflow_dir))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan workflow run: blocks for untrusted context interpolation.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="Exit 1 if any untrusted interpolation is found")
    sub.add_parser("list", help="Print every untrusted interpolation found")
    args = parser.parse_args(argv)

    wf_dir = WORKFLOW_DIR

    if args.cmd == "list":
        for v in _iter_matches(wf_dir):
            print(
                f"{v.workflow} / {v.job} / {v.step!r} line {v.line}: {v.fragment!r}"
            )
        return 0

    violations = find_violations(wf_dir)
    if not violations:
        print("OK: no untrusted context interpolated into run: blocks.")
        return 0

    for v in violations:
        print(
            f"::error file=.github/workflows/{v.workflow}::"
            f"Untrusted GitHub context interpolated directly into a run: block "
            f"in step {v.step!r} (job: {v.job}): {v.fragment!r}. "
            f"Route the value through an env: variable and reference \"$VAR\" in "
            f"the script, or append '{ACK_MARKER}' to the line if reviewed safe.",
            file=sys.stderr,
        )
    print(
        f"FAIL: {len(violations)} untrusted interpolation(s) in workflow run blocks.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
