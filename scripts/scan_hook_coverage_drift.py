#!/usr/bin/env python3
"""Detect drift between Claude and Codex hook coverage.

Refs #615. Compares the repo-script hook commands in
``.claude/settings.json`` against ``.codex/hooks.json`` and fails when
a supported Claude hook command is absent from Codex coverage.

Comparison model
----------------
For each hook event (``SessionStart``, ``PreToolUse``, ``PostToolUse``)
this script collects the set of ``scripts/*.py`` invocations declared in
each file and checks that every Claude entry has a Codex counterpart.

The check is intentionally narrow:

* Only ``scripts/*.py`` commands are compared.  Shell helpers like
  ``scripts/install-uv.sh`` and APM-managed superpowers hooks are
  excluded because Codex has its own equivalents outside this model.
* Only Claude → Codex direction is checked: Codex may add extra hooks
  for its own tooling (e.g. ``preflight_codex_github_footer.py``).
* Gaps that are structurally impossible to mirror in Codex are listed in
  :data:`ALLOWLIST` with inline rationale.

Exit codes:
* ``0`` -- no unsupported drift found.
* ``1`` -- at least one Claude hook script is absent from Codex coverage
  and is not in the allowlist.

Tested by ``tests/test_scan_hook_coverage_drift.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
CODEX_HOOKS = REPO_ROOT / ".codex" / "hooks.json"

_SCRIPT_REF = re.compile(r"\bscripts/([a-zA-Z][\w]*)\.py\b")

# Claude hook scripts that have no Codex equivalent and cannot be
# trivially mirrored. Each entry pairs the script name with the
# reason so the exclusion is auditable.
ALLOWLIST: dict[str, str] = {
    "plan_approval_gate": (
        "Triggered by the Claude ``Write`` tool which has no Codex equivalent. "
        "Codex plan artifacts are managed differently and do not require this gate."
    ),
    "gate_merge_retro_survey_askuserquestion": (
        "Drives the Claude-only ``AskUserQuestion`` tool (no Codex/Devin "
        "equivalent) to run a pre-merge retro/satisfaction survey, mirroring "
        "``gate_decision_handoff_askuserquestion``. Cannot be mirrored in Codex "
        "hooks because that harness has no structured-question tool."
    ),
}

# Hook event keys recognised in both config files.
HOOK_EVENTS = ("SessionStart", "PreToolUse", "PostToolUse")


@dataclass(frozen=True)
class HookEntry:
    """A single normalised hook: one event + one script reference."""

    event: str
    script: str  # e.g. "preflight_non_ascii"


def _extract_scripts_from_command(command: str) -> list[str]:
    return _SCRIPT_REF.findall(command)


def _is_superpowers(group: object) -> bool:
    return isinstance(group, dict) and group.get("_apm_source") == "superpowers"


def _collect_hooks(data: dict[str, object]) -> set[HookEntry]:
    """Return the set of (event, script) pairs from a hook config dict."""
    result: set[HookEntry] = set()
    raw_hooks = data.get("hooks", {})
    if not isinstance(raw_hooks, dict):
        return result
    for event in HOOK_EVENTS:
        raw_groups = raw_hooks.get(event, [])
        if not isinstance(raw_groups, list):
            continue
        for group in raw_groups:
            if not isinstance(group, dict):
                continue
            if _is_superpowers(group):
                continue
            handlers = group.get("hooks", [])
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                if not isinstance(handler, dict):
                    continue
                command = handler.get("command", "")
                if not isinstance(command, str):
                    continue
                for script in _extract_scripts_from_command(command):
                    result.add(HookEntry(event=event, script=script))
    return result


def collect_claude_hooks(settings: dict[str, object]) -> set[HookEntry]:
    """Return the set of (event, script) pairs from ``.claude/settings.json``."""
    return _collect_hooks(settings)


def collect_codex_hooks(hooks_data: dict[str, object]) -> set[HookEntry]:
    """Return the set of (event, script) pairs from ``.codex/hooks.json``."""
    return _collect_hooks(hooks_data)


def find_drift(
    claude_hooks: set[HookEntry],
    codex_hooks: set[HookEntry],
    allowlist: dict[str, str],
) -> list[HookEntry]:
    """Return Claude hooks absent from Codex and not in *allowlist*.

    Matching is event-specific: a script covered in ``PostToolUse`` does
    not satisfy a Claude ``PreToolUse`` requirement.
    """
    codex_pairs = {(h.event, h.script) for h in codex_hooks}
    missing: list[HookEntry] = []
    for entry in sorted(claude_hooks, key=lambda h: (h.event, h.script)):
        if (entry.event, entry.script) not in codex_pairs and entry.script not in allowlist:
            missing.append(entry)
    return missing


def cmd_verify(args: argparse.Namespace) -> int:
    claude_path = Path(args.claude)
    codex_path = Path(args.codex)

    claude_settings = json.loads(claude_path.read_text(encoding="utf-8"))
    codex_data = json.loads(codex_path.read_text(encoding="utf-8"))

    claude_hooks = collect_claude_hooks(claude_settings)
    codex_hooks = collect_codex_hooks(codex_data)
    missing = find_drift(claude_hooks, codex_hooks, ALLOWLIST)

    for entry in missing:
        print(
            f"::error file=.claude/settings.json::Claude {entry.event} hook "
            f"'scripts/{entry.script}.py' has no Codex counterpart and is not "
            f"in the allowlist. Add it to .codex/hooks.json or document the "
            f"gap in ALLOWLIST in scripts/scan_hook_coverage_drift.py.",
            file=sys.stderr,
        )

    for script, rationale in sorted(ALLOWLIST.items()):
        print(
            f"::notice::Allowlisted gap: scripts/{script}.py -- {rationale}",
            file=sys.stderr,
        )

    if missing:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect drift between Claude and Codex hook coverage.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser("verify", help="Run the drift check.")
    verify.add_argument(
        "--claude",
        default=str(CLAUDE_SETTINGS),
        help="Path to .claude/settings.json.",
    )
    verify.add_argument(
        "--codex",
        default=str(CODEX_HOOKS),
        help="Path to .codex/hooks.json.",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
