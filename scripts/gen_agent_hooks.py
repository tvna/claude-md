#!/usr/bin/env python3
"""Render the per-agent hook configs from one source of truth.

The three agent hook configs; ``.claude/settings.json``,
``.codex/hooks.json`` and ``.devin/hooks.v1.json``; previously each carried
their hook ``command`` strings as **repo-root-relative paths** such as
``python3 scripts/check_hooks_path.py`` or ``scripts/install-uv.sh``. Those
only resolve when the agent happens to launch the hook with the working
directory at the repository root. When a session starts from a subdirectory
(``cd subdir && claude``), the relative path misses the script and the hook
silently fails to run; including the safety gates (branch/base checks,
non-ASCII preflight, sensitive-read blocks). See the recurrence-prevention
design in ``docs/standards/agent-hooks-generation.md``.

This generator closes that gap structurally:

* ``scripts/agent_hooks_source.json`` is the single source of truth. Its
  ``command`` strings stay in the clean repo-relative form humans read.
* For every command that references a repo script, the generator injects a
  **working-directory-independence wrapper**; :data:`HOOK_CWD_PREFIX` --
  that ``cd``\\ s to ``git rev-parse --show-toplevel`` before running the
  command. That is the same repo-root resolution ``.githooks/pre-push``
  already uses, and it deliberately does **not** use ``$CLAUDE_PROJECT_DIR``
  (unset in the FleetView remote environment; see #783).
* ``.devin/hooks.v1.json`` is a mirror of ``.codex/hooks.json`` (the Devin
  adapter must stay byte-for-byte in sync, per
  ``docs/standards/devin-apm-compatibility.md``), so the source declares it
  with ``"mirror": "codex"`` rather than duplicating the config.

The wrapper is applied at generation time, so it can never drift per agent or
be forgotten when a new hook is added; the recurrence-prevention contract is
the ``--check`` drift gate wired into ``.pre-commit-config.yaml`` and CI, which
fails when a committed config does not match a fresh render of the source.

Usage::

    python3 scripts/gen_agent_hooks.py           # write the agent configs
    python3 scripts/gen_agent_hooks.py --check    # exit 1 if any is stale

Exit codes:
    0  configs written (default) or already current (``--check``).
    1  ``--check`` only: at least one config is missing or stale.
    2  the source file is missing or malformed.

Tested by ``tests/test_gen_agent_hooks.py``.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "scripts" / "agent_hooks_source.json"

# Working-directory-independence wrapper. Prepended to every hook command that
# invokes a repo-local script so the script resolves no matter which directory
# the session started from. ``git rev-parse --show-toplevel`` is the repo-root
# resolver already used by ``.githooks/pre-push``; ``$CLAUDE_PROJECT_DIR`` is
# intentionally avoided because it is unset in the FleetView remote environment
# (#783) and would expand to a broken path.
HOOK_CWD_PREFIX = 'cd "$(git rev-parse --show-toplevel)" && '


def command_needs_wrap(command: str) -> bool:
    """Return True when *command* invokes a repo-local ``scripts/`` file.

    The wrapper is only meaningful for commands that reference a path
    relative to the repository root. Commands that are already
    location-independent; the APM/superpowers ``${CLAUDE_PLUGIN_ROOT}``
    passthrough, or a ``PATH`` binary such as ``rtk hook claude``; carry no
    ``scripts/`` token and are left untouched.
    """
    return any(token.startswith("scripts/") for token in command.split())


def wrap_command(command: str) -> str:
    """Prefix *command* with :data:`HOOK_CWD_PREFIX` when it needs it.

    Idempotent: an already-wrapped command is returned unchanged, so the
    generator is safe to run repeatedly.
    """
    if command.startswith(HOOK_CWD_PREFIX):
        return command
    if command_needs_wrap(command):
        return HOOK_CWD_PREFIX + command
    return command


def unwrap_command(command: str) -> str:
    """Strip :data:`HOOK_CWD_PREFIX` from *command* if present.

    The inverse of :func:`wrap_command`, exposed so config tests can assert
    against the clean repo-relative command without re-encoding the wrapper.
    """
    if command.startswith(HOOK_CWD_PREFIX):
        return command[len(HOOK_CWD_PREFIX) :]
    return command


def _wrap_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *config* with every hook command wrapped."""
    rendered = copy.deepcopy(config)
    hooks = rendered.get("hooks")
    if isinstance(hooks, dict):
        for groups in hooks.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                handlers = group.get("hooks")
                if not isinstance(handlers, list):
                    continue
                for handler in handlers:
                    if not isinstance(handler, dict):
                        continue
                    command = handler.get("command")
                    if isinstance(command, str):
                        handler["command"] = wrap_command(command)
    return rendered


def _serialise(config: dict[str, Any]) -> str:
    """Render a config as 2-space-indented JSON with a trailing newline."""
    return json.dumps(config, indent=2) + "\n"


def render_targets(source: dict[str, Any]) -> dict[str, str]:
    """Map each target path to its rendered (wrapped) JSON text.

    A target may declare ``"mirror": "<agent>"`` instead of its own
    ``config`` to reuse another target's rendered config verbatim; this is
    how the Devin adapter stays byte-for-byte identical to Codex.
    """
    targets = source.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("source 'targets' must be a non-empty list")

    configs_by_agent: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError(f"target must be a mapping, got {type(target).__name__}")
        agent = target.get("agent")
        if not isinstance(agent, str) or not agent:
            raise ValueError("target is missing a string 'agent'")
        if "config" in target:
            config = target["config"]
            if not isinstance(config, dict):
                raise ValueError(f"target {agent!r}: 'config' must be a mapping")
            configs_by_agent[agent] = config

    rendered: dict[str, str] = {}
    for target in targets:
        agent = target["agent"]
        path = target.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"target {agent!r} is missing a string 'path'")
        mirror = target.get("mirror")
        if mirror is not None:
            if mirror not in configs_by_agent:
                raise ValueError(f"target {agent!r}: mirror {mirror!r} has no config")
            config = configs_by_agent[mirror]
        elif agent in configs_by_agent:
            config = configs_by_agent[agent]
        else:
            raise ValueError(f"target {agent!r} declares neither 'config' nor 'mirror'")
        rendered[path] = _serialise(_wrap_config(config))
    return rendered


def _load_source() -> dict[str, Any]:
    try:
        raw = SOURCE.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error file={SOURCE.name}::unreadable: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"::error file={SOURCE.name}::invalid JSON: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if not isinstance(data, dict):
        print(f"::error file={SOURCE.name}::top-level document is not a mapping", file=sys.stderr)
        raise SystemExit(2)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render per-agent hook configs from the SoT.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any agent config is missing or out of date instead of writing it.",
    )
    args = parser.parse_args(argv)

    try:
        rendered = render_targets(_load_source())
    except ValueError as exc:
        print(f"::error file={SOURCE.name}::{exc}", file=sys.stderr)
        return 2

    if args.check:
        stale = False
        for rel, text in rendered.items():
            path = REPO_ROOT / rel
            try:
                current = path.read_text(encoding="utf-8")
            except OSError:
                print(f"::error file={rel}::missing; run python3 scripts/gen_agent_hooks.py", file=sys.stderr)
                stale = True
                continue
            if current != text:
                print(f"::error file={rel}::stale; run python3 scripts/gen_agent_hooks.py", file=sys.stderr)
                stale = True
        return 1 if stale else 0

    for rel, text in rendered.items():
        (REPO_ROOT / rel).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
