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

The check covers two surfaces:

* ``scripts/*.py`` hook commands -- compared Claude → Codex only: Codex
  may add extra hooks for its own tooling (e.g.
  ``preflight_codex_github_footer.py``). Gaps that are structurally
  impossible to mirror in Codex are listed in :data:`ALLOWLIST`.
* ``scripts/install-*.sh`` SessionStart provisioners -- checked for
  cross-agent *parity*: an installer wired into one agent but absent from
  the other fails unless it carries an explicit, documented exemption in
  :data:`INSTALLER_PARITY_EXEMPTIONS`. This closes the false negative
  (#1607) where an installer wired into ``claude`` alone -- as
  ``install-bun.sh`` once was -- slipped past the gate because shell
  installers were excluded from comparison entirely.

Devin mirrors Codex byte-for-byte (``.devin/hooks.v1.json`` is generated
with ``"mirror": "codex"``), so comparing Claude against Codex covers all
three agents.

APM-managed superpowers hooks are skipped on both surfaces.

Exit codes:
* ``0`` -- no unsupported drift found.
* ``1`` -- at least one Claude hook script is absent from Codex coverage,
  or an installer is wired into a strict subset of agents, without an
  allowlist / exemption entry.

Tested by ``tests/test_scan_hook_coverage_drift.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
CODEX_HOOKS = REPO_ROOT / ".codex" / "hooks.json"

_SCRIPT_REF = re.compile(r"\bscripts/([a-zA-Z][\w]*)\.py\b")
_INSTALLER_REF = re.compile(r"\bscripts/(install-[a-zA-Z0-9-]+)\.sh\b")

# Claude hook scripts that have no Codex equivalent and cannot be
# trivially mirrored. Each entry pairs the script name with the
# reason so the exclusion is auditable.
ALLOWLIST: dict[str, str] = {
    "plan_approval_gate": (
        "Triggered by the Claude ``Write`` tool which has no Codex equivalent. "
        "Codex plan artifacts are managed differently and do not require this gate."
    ),
    "gen_mcp_json": (
        "Renders the Claude Code project-scope ``.mcp.json`` from apm.yml. "
        "Codex resolves MCP servers from its own client config, not this file, "
        "so there is no Codex counterpart to mirror."
    ),
}

# ``scripts/install-*.sh`` SessionStart provisioners that are intentionally
# wired into a strict subset of agents. Each entry is an explicit, documented
# per-agent exemption (Refs #1607): without it the installer-parity check
# fails, so a genuinely-missing agent cannot hide behind a silent gap. An
# installer absent here -- such as ``install-bun.sh`` -- MUST be wired into
# every agent or the gate fails loudly.
#
# The eight entries below are all Claude-only provisioners for the Claude Code
# on the Web remote environment (``CLAUDE_CODE_REMOTE=true``). Whether codex /
# devin sessions should also provision these tools is the open cross-agent
# audit tracked in #1604; listing them here keeps each gap visible and
# auditable rather than excluded from comparison.
INSTALLER_PARITY_EXEMPTIONS: dict[str, str] = {
    "install-rtk": "Claude-only Web provisioner for the rtk binary; cross-agent scope pending #1604 audit.",
    "install-apm": "Claude-only Web provisioner for the apm binary; cross-agent scope pending #1604 audit.",
    "install-actionlint": "Claude-only Web provisioner for the actionlint binary; cross-agent scope pending #1604 audit.",
    "install-waza": "Claude-only Web provisioner for the waza binary; cross-agent scope pending #1604 audit.",
    "install-ccusage": "Claude-only Web provisioner for the ccusage binary; cross-agent scope pending #1604 audit.",
    "install-zizmor": "Claude-only Web provisioner for the zizmor binary; cross-agent scope pending #1604 audit.",
    "install-lychee": "Claude-only Web provisioner for the lychee binary; cross-agent scope pending #1604 audit.",
    "install-betterleaks": "Claude-only Web provisioner for the betterleaks binary; cross-agent scope pending #1604 audit.",
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


def _iter_commands(data: dict[str, object]) -> Iterator[tuple[str, str]]:
    """Yield ``(event, command)`` for every non-superpowers hook command.

    Carries the defensive ``isinstance`` guards so malformed config sections
    are skipped rather than raising. Shared by :func:`_collect_hooks` and
    :func:`collect_installers`.
    """
    raw_hooks = data.get("hooks", {})
    if not isinstance(raw_hooks, dict):
        return
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
                yield event, command


def _collect_hooks(data: dict[str, object]) -> set[HookEntry]:
    """Return the set of (event, script) pairs from a hook config dict."""
    result: set[HookEntry] = set()
    for event, command in _iter_commands(data):
        for script in _extract_scripts_from_command(command):
            result.add(HookEntry(event=event, script=script))
    return result


def collect_installers(data: dict[str, object]) -> set[str]:
    """Return the set of ``scripts/install-*.sh`` names referenced in *data*.

    Names are bare installer stems, e.g. ``"install-bun"``. The event is
    irrelevant for parity -- an installer either provisions an agent or it
    does not -- so only the names are collected.
    """
    result: set[str] = set()
    for _event, command in _iter_commands(data):
        result.update(_INSTALLER_REF.findall(command))
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


def find_installer_drift(
    claude_installers: set[str],
    codex_installers: set[str],
    exemptions: dict[str, str],
) -> list[tuple[str, str, str]]:
    """Return installers wired into one agent but not the other.

    Parity is symmetric: an installer present in exactly one of the two
    agents (Devin mirrors Codex) is a gap. Each returned tuple is
    ``(installer, present_agent, absent_agent)``. Installers listed in
    *exemptions* are skipped.
    """
    drift: list[tuple[str, str, str]] = []
    for name in sorted(claude_installers ^ codex_installers):
        if name in exemptions:
            continue
        if name in claude_installers:
            drift.append((name, "claude", "codex"))
        else:
            drift.append((name, "codex", "claude"))
    return drift


def cmd_verify(args: argparse.Namespace) -> int:
    claude_path = Path(args.claude)
    codex_path = Path(args.codex)

    claude_settings = json.loads(claude_path.read_text(encoding="utf-8"))
    codex_data = json.loads(codex_path.read_text(encoding="utf-8"))

    claude_hooks = collect_claude_hooks(claude_settings)
    codex_hooks = collect_codex_hooks(codex_data)
    missing = find_drift(claude_hooks, codex_hooks, ALLOWLIST)

    claude_installers = collect_installers(claude_settings)
    codex_installers = collect_installers(codex_data)
    installer_drift = find_installer_drift(
        claude_installers, codex_installers, INSTALLER_PARITY_EXEMPTIONS
    )

    for entry in missing:
        print(
            f"::error file=.claude/settings.json::Claude {entry.event} hook "
            f"'scripts/{entry.script}.py' has no Codex counterpart and is not "
            f"in the allowlist. Add it to .codex/hooks.json or document the "
            f"gap in ALLOWLIST in scripts/scan_hook_coverage_drift.py.",
            file=sys.stderr,
        )

    for name, present, absent in installer_drift:
        print(
            f"::error file=scripts/agent_hooks_source.json::Installer "
            f"'scripts/{name}.sh' is wired into the {present} agent but absent "
            f"from {absent} (devin mirrors codex) and has no parity exemption. "
            f"Wire it into every agent in scripts/agent_hooks_source.json, or "
            f"document the gap in INSTALLER_PARITY_EXEMPTIONS in "
            f"scripts/scan_hook_coverage_drift.py.",
            file=sys.stderr,
        )

    for script, rationale in sorted(ALLOWLIST.items()):
        print(
            f"::notice::Allowlisted gap: scripts/{script}.py -- {rationale}",
            file=sys.stderr,
        )

    for name, rationale in sorted(INSTALLER_PARITY_EXEMPTIONS.items()):
        print(
            f"::notice::Installer parity exemption: scripts/{name}.sh -- {rationale}",
            file=sys.stderr,
        )

    if missing or installer_drift:
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
