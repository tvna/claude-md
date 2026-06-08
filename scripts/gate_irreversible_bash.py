#!/usr/bin/env python3
"""PreToolUse gate: require confirmation/dry-run for irreversible Bash ops.

Registered as a ``PreToolUse`` hook for the ``Bash`` matcher in
``.claude/settings.json`` (and mirrored in ``.codex/hooks.json``). It denies a
Bash command whose leading command in any shell segment is a high-confidence
irreversible or outward-facing operation -- the section 4.1 "keep confirmations
and dry-runs for any irreversible or outward-facing operation" rule, which had
no deterministic backstop beyond the force-push freshness check
(``preflight_branch_base.py``). Issue #1453.

Covered operations (command-position only, so a benign mention such as
``echo "rm -rf /"`` is never denied):

- ``rm`` carrying BOTH a recursive (``-r``/``-R``/``--recursive``) and a force
  (``-f``/``--force``) flag -- unrecoverable recursive delete.
- ``git push`` with ``--force``/``-f`` -- history overwrite. ``--force-with-lease``
  is the safer, allowed form and passes.
- ``find ... -delete`` -- bulk delete.
- ``dd of=...`` -- raw device/file overwrite.
- ``mkfs`` / ``mkfs.*`` -- filesystem creation (destroys the target).
- ``shred`` -- unrecoverable overwrite.
- ``truncate -s`` -- in-place file truncation.

Design (CLAUDE.md section 4: make wrong actions hard, right actions easy):

- The gate denies rather than silently allowing; the deny reason names the
  matched operation and points at the two safe paths -- run a dry-run/reversible
  variant, or, when the destruction is genuinely intended and reviewed, append a
  ``# irreversible-ack`` comment to opt in. The ack mirrors the
  ``# compile-source-ack`` escape-hatch precedent (``scan_compile_from_source``).
- Detection is command-position aware: each shell segment (split on ``;`` ``&&``
  ``||`` ``|`` and newlines) is tokenized and only its leading command (after
  any ``NAME=value`` prefix) is classified, so a destructive token buried in an
  argument or a quoted string does not trip the gate.
- Parse-error fail-open is intentional and narrow: a malformed stdin event logs
  to stderr and exits 0 so a hook bug never wedges the session. The fail-open
  applies only to the stdin I/O boundary -- a matched destructive command is
  always denied.

The gate is deliberately high-confidence / low-false-positive: it covers the
unambiguous destructive idioms only and is a backstop, not a substitute for the
operator judgement the section 4 rule still requires.

Contract:
- Inputs: a PreToolUse hook event as JSON on stdin (``tool_name`` plus
  ``tool_input``; the Bash matcher carries a ``command`` string). No flags.
- Outputs: a JSON ``permissionDecision`` deny object on stdout when the command
  is an irreversible operation; nothing on stdout on pass-through. Always
  exits 0.
- Failure policy: fails open at the stdin boundary per CLAUDE.md section 4 (a
  malformed event never wedges the session) and fails loud-by-deny on a matched
  irreversible operation.

Tested by ``tests/test_gate_irreversible_bash.py``. Refs #1453.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import PurePosixPath
from typing import Any

from _hook_runtime import emit_decision, read_event

_DENY_RULE = "irreversible-op-guard"

# Opt-in marker: a reviewed, intentional irreversible command carries this
# comment and is allowed through, ratcheting the judgement onto the author.
_ACK_MARKER = "# irreversible-ack"

# Shell separators that begin a new command position.
_SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")

# A leading ``NAME=value`` environment assignment to skip before the command.
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _normalize(token: str) -> str:
    """Strip surrounding quotes/whitespace from a raw token."""
    return token.strip().strip("'\"")


def _segments(command: str) -> list[str]:
    """Split *command* into shell segments at command-position boundaries."""
    return [seg.strip() for seg in _SEGMENT_SPLIT.split(command) if seg.strip()]


def _tokenize(segment: str) -> list[str]:
    """Best-effort shell tokenization; fall back to whitespace split."""
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _leading_command(tokens: list[str]) -> tuple[str, list[str]]:
    """Return ``(command_basename, args)``, skipping ``VAR=value`` prefixes.

    The basename of the command token is used so an absolute path such as
    ``/bin/rm`` classifies the same as ``rm``.
    """
    index = 0
    while index < len(tokens) and _ASSIGN_RE.match(tokens[index]):
        index += 1
    if index >= len(tokens):
        return "", []
    name = PurePosixPath(_normalize(tokens[index])).name
    return name, tokens[index + 1 :]


def _has_short_flag(args: list[str], char: str) -> bool:
    """Return True when *char* appears in a combined short flag (e.g. ``-rf``)."""
    return any(
        arg.startswith("-") and not arg.startswith("--") and char in arg[1:]
        for arg in args
    )


def _is_rm_recursive_force(args: list[str]) -> bool:
    """Return True when ``rm`` *args* request a recursive AND forced delete."""
    recursive = (
        _has_short_flag(args, "r")
        or _has_short_flag(args, "R")
        or "--recursive" in args
    )
    force = _has_short_flag(args, "f") or "--force" in args
    return recursive and force


def _classify(segment: str) -> str | None:
    """Return a human label for the irreversible op in *segment*, else None."""
    cmd, args = _leading_command(_tokenize(segment))
    if not cmd:
        return None
    if cmd == "rm" and _is_rm_recursive_force(args):
        return "recursive force delete (rm -rf)"
    if cmd == "git" and "push" in args and ("--force" in args or "-f" in args):
        return "force push (git push --force)"
    if cmd == "find" and "-delete" in args:
        return "bulk delete (find -delete)"
    if cmd == "dd" and any(arg.startswith("of=") for arg in args):
        return "raw overwrite (dd of=)"
    if cmd == "mkfs" or cmd.startswith("mkfs."):
        return "filesystem creation (mkfs)"
    if cmd == "shred":
        return "unrecoverable overwrite (shred)"
    if cmd == "truncate" and (
        "-s" in args or any(arg.startswith("--size") for arg in args)
    ):
        return "in-place truncation (truncate -s)"
    return None


def _deny(label: str) -> dict[str, Any]:
    return {
        "permissionDecision": "deny",
        "decisionReason": (
            f"[{_DENY_RULE}] Irreversible/outward-facing operation blocked: "
            f"{label}.\n\n"
            "CLAUDE.md section 4.1 requires a confirmation or dry-run for an "
            "operation that cannot be undone. Prefer a reversible or dry-run "
            "variant first (list what would be removed, push without --force, "
            "target a file copy). If the destruction is genuinely intended and "
            f"reviewed, append a '{_ACK_MARKER}' comment to the command to opt in."
        ),
    }


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny decision for an irreversible Bash command, else None.

    Pass-through (None) when the tool is not Bash, the command is empty, the
    opt-in marker is present, or no shell segment leads with a covered
    destructive command.
    """
    if tool_name != "Bash":
        return None
    command = str(tool_input.get("command") or "")
    if not command.strip():
        return None
    if _ACK_MARKER in command:
        return None
    for segment in _segments(command):
        label = _classify(segment)
        if label is not None:
            return _deny(label)
    return None


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write a deny decision when warranted."""
    del argv
    event = read_event("gate_irreversible_bash")
    if event is None:
        return 0

    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str):
        print(
            "::error::gate_irreversible_bash: event missing tool_name",
            file=sys.stderr,
        )
        return 0

    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    emit_decision(
        decide(tool_name, tool_input), "gate_irreversible_bash", auditable=False
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
