#!/usr/bin/env python3
"""PreToolUse gate: block runtime reads of local credential files.

Registered as a ``PreToolUse`` hook for the ``Read`` and ``Bash`` matchers in
``.claude/settings.json``. It denies any attempt to read credential-bearing
local files at session runtime; the gap a gap analysis against the community
"Claude Code Hardening Cheat Sheet" surfaced as the highest-priority missing
control (issue #1222, parent #178 "Credential Access" row).

Two surfaces are covered, mirroring the cheat sheet's two recommendations:

- **Read tool**: ``tool_input.file_path`` is matched against the sensitive
  path patterns directly.
- **Bash tool**: a ``tool_input.command`` that runs a file-reading command
  (``cat``/``less``/``grep``/``sed``/``awk``/...) against a sensitive path is
  denied. This blocks the ``cat .env`` style bypass of the Read matcher.

What counts as sensitive (basename globs + credential directories):

- ``.env`` / ``.env.*`` (dotenv files)
- ``*.pem`` / ``*.key`` (private keys / certs)
- ``credentials*`` (cloud credential files)
- ``id_rsa`` / ``id_ed25519`` (SSH private keys)
- any path under ``~/.ssh``, ``~/.aws``, ``~/.gnupg``, or ``~/.config/gcloud``

Design (CLAUDE.md section 4: minimal, fail loud on a match, never widen
exposure):

- The deny reason names the matched **path** only; never the file's
  **content**. The hook never opens the file, so no secret value can leak into
  the gate output, CI logs, or the transcript.
- Parse-error fail-open is intentional and narrow: a malformed stdin event
  logs to stderr and exits 0 so a hook bug never wedges the session. A path
  that matches a sensitive pattern is always denied; the fail-open applies
  only to the I/O boundary, not to the decision.

Escape hatch: add a tracked path to :data:`ALLOWLIST_PATHS` with a rationale
when a path matches a pattern but is a known non-secret fixture. The list may
only shrink (ratchet); adding a real secret here is a review-blocking defect.
This mirrors ``scripts/scan_secrets.py``.

Tested by ``tests/test_block_sensitive_reads.py``. Refs #1222.
"""

from __future__ import annotations

import fnmatch
import shlex
import sys
from pathlib import PurePosixPath
from typing import Any

from _hook_runtime import emit_decision, read_event

# Basename globs that mark a path as credential-bearing.
_SENSITIVE_BASENAME_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "credentials*",
    "id_rsa",
    "id_ed25519",
)

# A path is sensitive if any of these appears as a directory segment.
_SENSITIVE_DIR_SEGMENTS: frozenset[str] = frozenset({".ssh", ".aws", ".gnupg"})

# Commands that read file contents. Presence of one of these AND a sensitive
# path token in the same Bash command is what triggers a deny.
_READ_COMMANDS: frozenset[str] = frozenset(
    {
        "cat", "tac", "nl", "less", "more", "head", "tail",
        "grep", "egrep", "fgrep", "rg", "ag",
        "sed", "awk", "cut", "sort", "uniq",
        "xxd", "od", "hexdump", "strings", "base64",
        "vi", "vim", "view", "nano", "emacs",
        "cp", "install", "dd",
    }
)

# Reviewed non-secret paths that match a pattern above. Ratchet: may only
# shrink. Empty today; the repo ships no such fixture.
ALLOWLIST_PATHS: frozenset[str] = frozenset()

_DENY_RULE = "credential-read-guard"


def _normalize(path: str) -> str:
    """Strip surrounding quotes/whitespace from a raw token or file path."""
    return path.strip().strip("'\"")


def is_sensitive_path(path: str) -> bool:
    """Return True when *path* points at credential-bearing material.

    Pure and side-effect free: it inspects the path string only and never
    touches the filesystem, so it cannot read a secret value. Matching is on
    the basename globs and on the credential directory segments; the
    ``~/.config/gcloud`` directory is matched as the ``.config`` + ``gcloud``
    segment pair.
    """
    cleaned = _normalize(path)
    if not cleaned:
        return False
    if cleaned in ALLOWLIST_PATHS:
        return False

    pure = PurePosixPath(cleaned)
    name = pure.name
    for glob in _SENSITIVE_BASENAME_GLOBS:
        if fnmatch.fnmatch(name, glob):
            return True

    segments = set(pure.parts)
    if segments & _SENSITIVE_DIR_SEGMENTS:
        return True
    return ".config" in segments and "gcloud" in segments


def _tokenize(command: str) -> list[str]:
    """Best-effort shell tokenization; fall back to whitespace split."""
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _bash_sensitive_target(command: str) -> str | None:
    """Return a matched sensitive path when *command* reads one, else None.

    Requires BOTH a read command and a sensitive path token to be present, so
    a benign mention (e.g. ``echo .env``) is not denied while ``cat .env`` is.
    """
    tokens = _tokenize(command)
    if not tokens:
        return None
    has_reader = any(_normalize(tok) in _READ_COMMANDS for tok in tokens)
    if not has_reader:
        return None
    for tok in tokens:
        if is_sensitive_path(tok):
            return _normalize(tok)
    return None


def _deny(path: str) -> dict[str, Any]:
    return {
        "permissionDecision": "deny",
        "decisionReason": (
            f"[{_DENY_RULE}] Reading credential-bearing path is blocked: "
            f"{path!r}.\n\n"
            "This guard prevents local secrets (.env, *.pem, *.key, SSH/cloud "
            "credential files) from reaching the agent and any output sink "
            "(logs, PR bodies, comments, external APIs); CLAUDE.md section 4.\n"
            "If this path is a reviewed non-secret, add it to ALLOWLIST_PATHS "
            "in scripts/block_sensitive_reads.py with a rationale."
        ),
    }


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny decision for a credential-file read, else None.

    Pass-through (None) when the tool is neither Read nor Bash, or when no
    sensitive path is targeted.
    """
    if tool_name == "Read":
        path = str(tool_input.get("file_path") or "")
        if path and is_sensitive_path(path):
            return _deny(_normalize(path))
        return None

    if tool_name == "Bash":
        command = str(tool_input.get("command") or "")
        matched = _bash_sensitive_target(command)
        if matched is not None:
            return _deny(matched)
        return None

    return None


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write a deny decision when warranted."""
    del argv
    event = read_event("block_sensitive_reads")
    if event is None:
        return 0

    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str):
        print(
            "::error::block_sensitive_reads: event missing tool_name",
            file=sys.stderr,
        )
        return 0

    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    emit_decision(decide(tool_name, tool_input), "block_sensitive_reads", auditable=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
