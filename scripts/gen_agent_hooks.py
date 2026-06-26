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

The same source also owns the Claude ``permissions`` block (RFC #2022 A-2).
A platform-neutral top-level ``permissions`` section declares each intent's
Claude rule strings plus its cross-platform realization: ``realized_by`` (a
hook enforcing the same intent for codex/devin) or ``claude_only`` (a
Claude-only intent with no portable target). :func:`build_claude_permissions`
compiles the ``allow``/``deny`` block injected into ``.claude/settings.json``,
and :func:`verify_permission_parity` (folded into ``--check``) fails when a
``realized_by`` hook is not wired into both ``.codex/hooks.json`` and
``.devin/hooks.v1.json``; the reconcile-with-Codex drift gate.

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

# The Claude ``permissions`` rule kinds, in the order they are emitted into
# ``.claude/settings.json``. ``ask`` is accepted for forward-compatibility even
# though the current source declares only ``allow`` and ``deny``.
PERMISSION_KINDS = ("allow", "deny", "ask")


def _validate_permission_intent(kind: str, intent: Any) -> None:
    """Validate one permission intent; raise ``ValueError`` on a malformed entry.

    Each intent carries its Claude rule strings (``claude``) plus its
    cross-platform realization: either ``realized_by`` (a hook that enforces the
    same intent for codex/devin) or ``claude_only`` (a Claude-only intent with
    no portable target, which must still carry a ``rationale``). Every intent
    names a tracking ``issue``.
    """
    if not isinstance(intent, dict):
        raise ValueError(f"permissions.{kind} entry must be a mapping")
    name = intent.get("intent")
    if not isinstance(name, str) or not name:
        raise ValueError(f"permissions.{kind} entry missing a string 'intent'")
    rules = intent.get("claude")
    if not isinstance(rules, list) or not rules or not all(isinstance(r, str) and r for r in rules):
        raise ValueError(f"permissions intent {name!r}: 'claude' must be a non-empty list of strings")
    if intent.get("claude_only"):
        rationale = intent.get("rationale")
        if not isinstance(rationale, str) or not rationale:
            raise ValueError(f"permissions intent {name!r}: claude_only requires a string 'rationale'")
    else:
        realized_by = intent.get("realized_by")
        if not isinstance(realized_by, str) or not realized_by:
            raise ValueError(
                f"permissions intent {name!r}: declare either a string 'realized_by' "
                "(a hook enforcing the same intent for codex/devin) or 'claude_only': true"
            )
    issue = intent.get("issue")
    if not isinstance(issue, str) or not issue:
        raise ValueError(f"permissions intent {name!r}: missing a string 'issue'")


def build_claude_permissions(source: dict[str, Any]) -> dict[str, Any] | None:
    """Compile the Claude ``permissions`` block from the neutral source section.

    Returns ``None`` when the source declares no ``permissions`` section. Each
    intent's ``claude`` rule strings are concatenated under their kind
    (``allow``/``deny``/``ask``) preserving declaration order, so the rendered
    block stays byte-stable. Raises ``ValueError`` on a malformed section.
    """
    perms = source.get("permissions")
    if perms is None:
        return None
    if not isinstance(perms, dict):
        raise ValueError("source 'permissions' must be a mapping")
    block: dict[str, Any] = {}
    for kind in PERMISSION_KINDS:
        intents = perms.get(kind)
        if intents is None:
            continue
        if not isinstance(intents, list):
            raise ValueError(f"permissions.{kind} must be a list")
        rules: list[str] = []
        for intent in intents:
            _validate_permission_intent(kind, intent)
            rules.extend(intent["claude"])
        block[kind] = rules
    return block


def verify_permission_parity(source: dict[str, Any], rendered: dict[str, str]) -> list[str]:
    """Return cross-platform permission parity problems; empty when none.

    Every permission intent that declares ``realized_by`` (a hook enforcing the
    same intent for codex/devin) must have that hook wired into BOTH the codex
    and devin rendered configs. ``claude_only`` intents declare no
    cross-platform target and are exempt (their well-formedness is checked when
    the block is built). This is the reconcile-with-Codex drift gate the RFC
    flagged: a Claude permission whose portable enforcement is missing fails.
    """
    perms = source.get("permissions")
    if not isinstance(perms, dict):
        return []
    corpus = {path: (rendered.get(path) or "") for path in (".codex/hooks.json", ".devin/hooks.v1.json")}
    problems: list[str] = []
    for kind in PERMISSION_KINDS:
        for intent in perms.get(kind) or []:
            if not isinstance(intent, dict) or intent.get("claude_only"):
                continue
            realized_by = intent.get("realized_by")
            if not isinstance(realized_by, str) or not realized_by:
                continue
            name = intent.get("intent")
            for path, text in corpus.items():
                if realized_by not in text:
                    problems.append(
                        f"permissions intent {name!r}: realized_by {realized_by!r} "
                        f"is not wired in {path}; cross-platform enforcement is missing"
                    )
    return problems


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


def _with_permissions(config: dict[str, Any], permissions: dict[str, Any] | None) -> dict[str, Any]:
    """Return *config* with *permissions* inserted right after ``$schema``.

    A no-op (returns *config* unchanged) when *permissions* is ``None``. Builds
    a new dict rather than mutating, so the Claude target stays independent of
    any mirror sharing. Placement after ``$schema`` keeps the rendered
    ``.claude/settings.json`` key order (``$schema``, ``permissions``,
    ``hooks``) byte-stable.
    """
    if permissions is None:
        return config
    result: dict[str, Any] = {}
    placed = False
    for key, value in config.items():
        result[key] = value
        if key == "$schema":
            result["permissions"] = permissions
            placed = True
    if not placed:
        result = {"permissions": permissions, **config}
    return result


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

    claude_permissions = build_claude_permissions(source)

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
        if agent == "claude":
            config = _with_permissions(config, claude_permissions)
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
        source = _load_source()
        rendered = render_targets(source)
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
        for problem in verify_permission_parity(source, rendered):
            print(f"::error file={SOURCE.name}::{problem}", file=sys.stderr)
            stale = True
        return 1 if stale else 0

    for rel, text in rendered.items():
        (REPO_ROOT / rel).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
