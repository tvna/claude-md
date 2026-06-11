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
  three-way cross-agent *parity* (Refs #1607, #1609). An installer wired
  into any agent must be wired into **every** agent (``claude``, ``codex``,
  ``devin``) unless it carries a per-agent exemption in
  :data:`INSTALLER_PARITY_EXEMPTIONS` whose declared ``agents`` set EXACTLY
  matches where it is actually wired. The exemption is a contract, not a
  blanket skip: a genuinely-missing agent can no longer hide behind an
  entry that merely names the installer, and a stale exemption fails loudly.
  This closes the false negative where an installer wired into ``claude``
  alone -- as ``install-bun.sh`` once was -- slipped past the gate.

Devin is read directly from ``.devin/hooks.v1.json`` rather than assumed to
mirror Codex, so a broken ``"mirror": "codex"`` invariant cannot hide a
per-agent gap.

APM-managed superpowers hooks are skipped on both surfaces.

Exit codes:
* ``0`` -- no unsupported drift found.
* ``1`` -- at least one Claude hook script is absent from Codex coverage,
  or an installer violates three-way parity (subset-wired without a
  matching exemption, or a malformed/stale/dangling exemption).

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
DEVIN_HOOKS = REPO_ROOT / ".devin" / "hooks.v1.json"

# The three agents whose SessionStart provisioners must stay at parity. Devin
# is read directly (not assumed to mirror Codex) so a broken mirror cannot hide
# a per-agent installer gap -- defense in depth over the generator's
# ``"mirror": "codex"`` invariant (Refs #1609).
AGENTS = ("claude", "codex", "devin")

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
# wired into a strict subset of agents. Each entry is a PER-AGENT CONTRACT, not
# a blanket skip (Refs #1607): it must declare the EXACT set of agents the
# installer is meant to run on, a rationale, and the tracking issue. The gate
# then verifies the declared set matches reality -- so an installer that is
# *genuinely* missing from an agent can no longer hide behind an exemption that
# merely names it, and a stale exemption (declared set != actual wiring, e.g.
# left behind after an installer became fully shared) fails loudly instead of
# rotting. A declaration covering all agents, or naming an installer wired into
# no agent, is itself rejected -- it would be a no-op exemption.
#
# Shape:
#   "install-foo": {
#       "agents": ["claude"],                 # non-empty strict subset of AGENTS
#       "rationale": "why foo is deliberately claude-only",
#       "issue": 1234,                          # tracks the per-agent decision
#   }
#
# Empty since #1608: the eight formerly Claude-only provisioners (rtk, apm,
# actionlint, waza, ccusage, zizmor, lychee, betterleaks) resolved the #1606
# cross-agent audit as "shared" and are now wired into all three agents, so no
# installer needs an exemption.
INSTALLER_PARITY_EXEMPTIONS: dict[str, dict[str, object]] = {}

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


def validate_exemption(name: str, spec: object) -> str:
    """Return an error string if *spec* is not a valid per-agent contract, else ''.

    A valid exemption is a mapping with a non-empty strict-subset ``agents``
    list (distinct values drawn from :data:`AGENTS`), a non-empty ``rationale``
    string, and an integer ``issue``. A declaration covering every agent is
    rejected because a fully-shared installer needs no exemption.
    """
    if not isinstance(spec, dict):
        return f"exemption for {name!r} must be a mapping with agents/rationale/issue keys"
    agents = spec.get("agents")
    if (
        not isinstance(agents, list)
        or not agents
        or len(set(agents)) != len(agents)
        or not set(agents) <= set(AGENTS)
    ):
        return (
            f"exemption for {name!r}: 'agents' must be a non-empty list of distinct "
            f"values drawn from {list(AGENTS)}"
        )
    if set(agents) == set(AGENTS):
        return (
            f"exemption for {name!r} declares all agents -- a fully-shared installer "
            "needs no exemption; remove the entry"
        )
    rationale = spec.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        return f"exemption for {name!r}: 'rationale' must be a non-empty string"
    issue = spec.get("issue")
    if not isinstance(issue, int) or isinstance(issue, bool):
        return f"exemption for {name!r}: 'issue' must be an int tracking the per-agent decision"
    return ""


def find_installer_parity_violations(
    installers_by_agent: dict[str, set[str]],
    exemptions: dict[str, dict[str, object]],
) -> list[str]:
    """Return human-readable cross-agent installer-parity violations.

    An installer wired into any agent must be wired into **every** agent in
    :data:`AGENTS` unless it carries a per-agent exemption whose declared
    ``agents`` set EXACTLY matches where it is actually wired. Violations are:

    * a malformed exemption (see :func:`validate_exemption`);
    * an exemption naming an installer wired into no agent (dangling);
    * an installer wired into a strict subset of agents with no exemption;
    * an exemption whose declared agent set != the actual wiring (stale).

    *installers_by_agent* maps each agent name to its set of installer stems.
    """
    all_agents = set(AGENTS)
    universe: set[str] = set()
    for names in installers_by_agent.values():
        universe |= names

    violations: list[str] = []

    for name in sorted(exemptions):
        err = validate_exemption(name, exemptions[name])
        if err:
            violations.append(err)
        elif name not in universe:
            violations.append(
                f"exemption {name!r} names an installer wired into no agent; "
                "remove the dangling exemption"
            )

    for name in sorted(universe):
        actual = {agent for agent in AGENTS if name in installers_by_agent.get(agent, set())}
        spec = exemptions.get(name)
        if spec is not None and not validate_exemption(name, spec):
            declared_agents = spec["agents"]
            # validate_exemption guarantees ``agents`` is a list here; the
            # isinstance guard keeps the type checker happy without an assert.
            declared = set(declared_agents) if isinstance(declared_agents, list) else set()
            if actual != declared:
                violations.append(
                    f"installer {name!r} exemption declares agents {sorted(declared)} "
                    f"but it is wired into {sorted(actual)}; reconcile the wiring in "
                    "scripts/agent_hooks_source.json or the exemption (stale exemption)"
                )
            continue
        if spec is not None:
            # malformed exemption already reported above; do not double-flag parity.
            continue
        if actual != all_agents:
            missing = sorted(all_agents - actual)
            violations.append(
                f"installer {name!r} is wired into {sorted(actual)} but missing from "
                f"{missing}; wire it into every agent in scripts/agent_hooks_source.json, "
                "or add a per-agent exemption (agents/rationale/issue) to "
                "INSTALLER_PARITY_EXEMPTIONS in scripts/scan_hook_coverage_drift.py"
            )
    return violations


def cmd_verify(args: argparse.Namespace) -> int:
    claude_settings = json.loads(Path(args.claude).read_text(encoding="utf-8"))
    codex_data = json.loads(Path(args.codex).read_text(encoding="utf-8"))
    devin_data = json.loads(Path(args.devin).read_text(encoding="utf-8"))

    claude_hooks = collect_claude_hooks(claude_settings)
    codex_hooks = collect_codex_hooks(codex_data)
    missing = find_drift(claude_hooks, codex_hooks, ALLOWLIST)

    installers_by_agent = {
        "claude": collect_installers(claude_settings),
        "codex": collect_installers(codex_data),
        "devin": collect_installers(devin_data),
    }
    parity_violations = find_installer_parity_violations(
        installers_by_agent, INSTALLER_PARITY_EXEMPTIONS
    )

    for entry in missing:
        print(
            f"::error file=.claude/settings.json::Claude {entry.event} hook "
            f"'scripts/{entry.script}.py' has no Codex counterpart and is not "
            f"in the allowlist. Add it to .codex/hooks.json or document the "
            f"gap in ALLOWLIST in scripts/scan_hook_coverage_drift.py.",
            file=sys.stderr,
        )

    for message in parity_violations:
        print(
            f"::error file=scripts/agent_hooks_source.json::{message}.",
            file=sys.stderr,
        )

    for script, rationale in sorted(ALLOWLIST.items()):
        print(
            f"::notice::Allowlisted gap: scripts/{script}.py -- {rationale}",
            file=sys.stderr,
        )

    for name, spec in sorted(INSTALLER_PARITY_EXEMPTIONS.items()):
        exempt_agents = spec.get("agents")
        exempt_rationale = spec.get("rationale")
        print(
            f"::notice::Installer parity exemption: scripts/{name}.sh "
            f"(agents={exempt_agents}) -- {exempt_rationale}",
            file=sys.stderr,
        )

    if missing or parity_violations:
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
    verify.add_argument(
        "--devin",
        default=str(DEVIN_HOOKS),
        help="Path to .devin/hooks.v1.json.",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
