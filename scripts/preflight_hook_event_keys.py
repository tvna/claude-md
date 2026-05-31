#!/usr/bin/env python3
"""Reject non-PascalCase hook event keys in the agent hook configs.

Issue #1030: a camelCase ``sessionStart`` key shipped in
``.claude/settings.json``, ``.codex/hooks.json``, and
``.devin/hooks.v1.json``. Claude Code and Codex match lifecycle hook
events case-sensitively in PascalCase (``SessionStart``), so the key
never fired -- it was a malformed duplicate of the superpowers
``session-start`` hook already present in the ``SessionStart`` array.

This is the deterministic gate that shifts detection left to commit
time: a camelCase event key (or any non-PascalCase key) under the
top-level ``hooks`` object fails before the change can be committed,
instead of waiting for the ``shard_preflight`` pytest regression in CI.

Registered as the ``preflight-hook-event-keys`` local hook in
``.pre-commit-config.yaml`` (commit stage), so it also runs at push time
via ``preflight_all.py``'s ``prek`` step and in CI.

Exit 0 when every hook event key is PascalCase; exit 1 on any violation.
Each hit emits ``::error file=<path>::...`` on stderr so the GitHub
Actions UI surfaces individual violations.

Tested by ``tests/test_preflight_hook_event_keys.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The agent hook configs whose top-level ``hooks`` event keys are gated.
HOOK_CONFIG_FILES: tuple[str, ...] = (
    ".claude/settings.json",
    ".codex/hooks.json",
    ".devin/hooks.v1.json",
)

# PascalCase: a leading uppercase letter followed by letters only. This is
# the exact shape Claude Code / Codex match lifecycle events against, so a
# camelCase key such as ``sessionStart`` is rejected without pinning a
# fixed event allowlist that would reject legitimate new PascalCase events.
PASCAL_CASE_RE = re.compile(r"^[A-Z][A-Za-z]+$")


def offending_event_keys(hooks: object) -> list[str]:
    """Return the non-PascalCase keys in a ``hooks`` mapping, sorted.

    A non-dict ``hooks`` value yields no keys -- the JSON-shape contract
    is enforced by the per-config tests; this gate only judges casing.
    """
    if not isinstance(hooks, dict):
        return []
    return sorted(key for key in hooks if not PASCAL_CASE_RE.match(str(key)))


def check_file(path: Path) -> list[str]:
    """Return human-readable violation messages for one config file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    hooks = data.get("hooks") if isinstance(data, dict) else None
    try:
        rel: Path = path.relative_to(REPO_ROOT)
    except ValueError:
        rel = path
    return [
        f"{rel}: hook event key {key!r} is not PascalCase; "
        f"lifecycle events are matched case-sensitively (e.g. 'SessionStart')"
        for key in offending_event_keys(hooks)
    ]


def verify() -> int:
    violations: list[str] = []
    for rel in HOOK_CONFIG_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            violations.append(f"{rel}: expected hook config file is missing")
            continue
        violations.extend(check_file(path))

    if violations:
        for message in violations:
            print(f"::error::{message}", file=sys.stderr)
        return 1

    print(f"OK: hook event keys are PascalCase in {len(HOOK_CONFIG_FILES)} config(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="verify",
        choices=("verify",),
        help="verify (default): fail on any non-PascalCase hook event key",
    )
    parser.parse_args(argv)
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
