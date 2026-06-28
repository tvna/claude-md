#!/usr/bin/env python3
"""Fail when a Markdown doc cites a `.github/workflows/<name>.yml` that is gone.

Refs #1325. When #1319 consolidated CI workflows by trigger class
(``portable-pr-policy.yml`` / ``verify-design-philosophy.yml`` /
``verify-dependabot-labels.yml`` / ``verify-ruleset-sync.yml`` ->
``verify-pr.yml``; the ``auto-retro-*`` / ``retro-followup-drift.yml`` set ->
``daily-maintenance.yml``; ``flake-pin-refresh.yml`` /
``auto-retro-triage-report.yml`` -> ``weekly-maintenance.yml``;
``attack-coverage-review-reminder.yml`` -> ``monthly-maintenance.yml``), the
deleted filenames lived on as inline-code references across PRD / standards /
runbook docs. ``scan_markdown_links.py`` did not catch them because they are
not Markdown links, and ``scan_docs_inventory.py`` only validates the docs
index; so the drift class was invisible to every deterministic gate.

This gate closes that gap. It scans every tracked Markdown file (outside
``docs/archive/``, which is a historical record of past state) for the literal
path form ``.github/workflows/<name>.yml`` and fails when the referenced file
does not exist under ``.github/workflows/``. The path form is unambiguous: a
referenced workflow path either resolves to a real file or it does not, so the
gate carries no false-positive risk and needs no per-file registry.

Scope is deliberately the *path* form only (``.github/workflows/<name>.yml``),
matching the #1325 acceptance criterion. A bare filename such as
``portable-pr-policy.yml`` written without the directory prefix is not gated:
bare ``*.yml`` tokens (``dependabot.yml``, example snippets) cannot be told
apart from a workflow reference without a name registry that would itself drift.
Those bare references are repaired by hand in the same change set; this gate
locks in the path-form subset so the drift cannot silently return.

Escape hatch: put ``workflow-ref-ack`` on the same line as a path that must
legitimately name a workflow file that does not exist (e.g. a migration sketch
proposing a future rename). Mirrors the ``# flake-pin-ack`` precedent in
``scan_flake_pin_drift.py``. Prefer moving genuinely historical docs into
``docs/archive/`` instead, which is excluded wholesale.

CLI::

    python3 scripts/scan_doc_workflow_refs.py verify  # exit 1 on a stale ref
    python3 scripts/scan_doc_workflow_refs.py list     # print every (file, ref)

Fails loud per CLAUDE.md section 4. Tested by
``tests/test_scan_doc_workflow_refs.py``. Refs #1319, #1325.

Contract:
    Inputs: the ``verify`` or ``list`` subcommand. The scanned surface is every
        ``*.md`` file tracked under the repository root except those under
        ``docs/archive/``; the existence oracle is the set of files under
        ``.github/workflows/``. No stdin, no env input, no network.
    Outputs: ``verify`` prints ``::error file=...,line=...::`` annotations on
        stderr per stale reference plus a one-line summary, exit 0 when clean
        and exit 1 on any stale reference; ``list`` prints every discovered
        ``<file>:<line>: <ref>`` pair on stdout (existing and stale alike).
    Failure policy: fails loud per CLAUDE.md section 4 (gate: a reference to a
        nonexistent workflow path exits non-zero).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Markdown trees excluded from the scan. ``docs/archive/`` is a point-in-time
# historical record; rewriting it to the current workflow set would falsify the
# history it exists to preserve. ``node_modules/`` is the gitignored bun
# dependency tree for the Mermaid gate (#1597): it is never committed and its
# vendored READMEs reference unrelated upstream workflow files, so scanning it
# would raise false positives when it is materialised locally or by the
# SessionStart bun installer.
EXCLUDED_DIRS: tuple[str, ...] = ("docs/archive/", "node_modules/")

# Lines carrying this marker bypass the scan. Mirrors scan_flake_pin_drift.py.
ACK_MARKER = "workflow-ref-ack"

# A path-form reference to a workflow file: the literal ``.github/workflows/``
# directory followed by a kebab/underscore filename and the ``.yml`` suffix.
# A leading ``.`` / ``/`` (from a relative Markdown link such as
# ``../../.github/workflows/x.yml``) is outside the capture; only the workflow
# basename is captured so existence resolves against WORKFLOWS_DIR regardless of
# how the reference was spelled. A literal ``*`` (e.g. ``.github/workflows/*.yml``)
# never matches because ``*`` is not in the filename character class.
_WORKFLOW_REF_RE = re.compile(r"\.github/workflows/([A-Za-z0-9._-]+\.yml)\b")


@dataclass(frozen=True)
class WorkflowRef:
    """One ``.github/workflows/<name>.yml`` reference found in a Markdown file."""

    doc: str  # repository-relative path of the Markdown file
    line: int  # 1-based line number
    name: str  # the referenced workflow basename, e.g. ``verify-pr.yml``


def _is_excluded(rel_posix: str) -> bool:
    """Return True when *rel_posix* sits under an excluded Markdown tree."""
    return any(rel_posix.startswith(prefix) for prefix in EXCLUDED_DIRS)


def iter_markdown(repo_root: Path) -> Iterator[Path]:
    """Yield every tracked ``*.md`` file outside the excluded trees.

    ``.git`` is skipped structurally (it holds no tracked Markdown), and the
    excluded-tree filter is applied on the repository-relative POSIX path so the
    same rule reads identically here and in the docstring.
    """
    for path in sorted(repo_root.rglob("*.md")):
        if ".git" in path.parts:
            continue
        rel = path.relative_to(repo_root).as_posix()
        if _is_excluded(rel):
            continue
        yield path


def find_refs(repo_root: Path) -> list[WorkflowRef]:
    """Return every workflow path reference discovered across the scanned docs."""
    refs: list[WorkflowRef] = []
    for path in iter_markdown(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # unreadable or binary-as-md: nothing to scan
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ACK_MARKER in line:
                continue
            for match in _WORKFLOW_REF_RE.finditer(line):
                refs.append(WorkflowRef(doc=rel, line=lineno, name=match.group(1)))
    return refs


def stale_refs(repo_root: Path, refs: list[WorkflowRef]) -> list[WorkflowRef]:
    """Return the subset of *refs* whose workflow file does not exist."""
    workflows = repo_root / ".github" / "workflows"
    return [ref for ref in refs if not (workflows / ref.name).is_file()]


def _cmd_verify(_args: argparse.Namespace) -> int:
    refs = find_refs(REPO_ROOT)
    stale = stale_refs(REPO_ROOT, refs)
    for ref in stale:
        print(
            f"::error file={ref.doc},line={ref.line}::doc references "
            f".github/workflows/{ref.name}, which does not exist. The workflow "
            f"was renamed or consolidated (see #1319 / #1325); repoint this "
            f"reference at the current workflow file, naming the job where "
            f"helpful.",
            file=sys.stderr,
        )
    if stale:
        print(
            f"FAIL: {len(stale)} reference(s) to nonexistent "
            f".github/workflows/*.yml across {len({r.doc for r in stale})} doc(s).",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: every .github/workflows/*.yml path reference resolves "
        f"({len(refs)} reference(s) checked)."
    )
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    for ref in find_refs(REPO_ROOT):
        print(f"{ref.doc}:{ref.line}: .github/workflows/{ref.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "verify", help="fail on any reference to a nonexistent workflow path"
    ).set_defaults(func=_cmd_verify)
    sub.add_parser(
        "list", help="print every discovered workflow path reference"
    ).set_defaults(func=_cmd_list)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
