#!/usr/bin/env python3
"""PreToolUse gate: deny a Bash ``git`` command that disables commit signing.

Registered as a ``PreToolUse`` hook for the ``Bash`` matcher in
``.claude/settings.json`` (and mirrored in ``.codex/hooks.json`` /
``.devin/hooks.v1.json`` via ``scripts/agent_hooks_source.json``). It denies a
Bash command whose leading command in any shell segment is ``git`` and which
turns off commit signing for that invocation; the agent-Bash-tool sibling of
``scan_workflow_unsigned_commit.py`` (which guards the CI-side unsigned
``git push`` authoring path). Issue #1713.

Three deterministic gates cover the unsigned-commit category from different
angles, and they are complementary rather than redundant (CLAUDE.md section 3,
one category covered end to end):

- This gate blocks a Bash ``git`` command that *disables* signing for an
  invocation. It is necessary but not sufficient: it cannot see a commit that
  lands unsigned for a reason other than an explicit bypass flag.
- ``preflight_push_unsigned_commits.py`` closes that remaining hole at the push
  boundary by inspecting each commit a Bash ``git push`` would ship for a raw
  ``gpgsig`` header (via ``git cat-file commit``, not ``git verify-commit``,
  which false-positives where ``gpg.ssh.allowedSignersFile`` is unconfigured)
  and denying the push when any commit carries none. This catches the Codex
  Desktop case where the worktree carries no signing key, so a plain
  ``git commit`` produces an unsigned commit even with ``commit.gpgsign=true``
  (Issue #2138). That is the agent-Bash-*push* sibling, where this gate is the
  agent-Bash-*command* sibling.
- ``scan_workflow_unsigned_commit.py`` guards the third path: a ``git push`` in
  a CI workflow ``run:`` block (the bot-authoring path). All three honor the
  same ``# unsigned-ack`` opt-in marker.

This repository configures ``commit.gpgsign=true`` with an ssh signing key, so a
plain ``git commit`` produces a Verified commit. The only reason to disable
signing inline is to defeat that requirement, so the gate denies the two
equivalent spellings of that one bypass (the section 4 "generalize the category"
discipline; both forms are the same harm):

- ``-c commit.gpgsign=<false-ish>``; the inline config override named in the
  request. A false-ish value is one of git's documented booleans for false:
  ``false``, ``0``, ``no``, ``off`` (case-insensitive). The value must follow a
  ``-c`` token, so a positional argument that merely looks like the assignment
  is not matched.
- ``--no-gpg-sign``; the per-command flag accepted by the committing
  subcommands (``commit``, ``merge``, ``rebase``, ``cherry-pick``, ...), which
  has the identical effect.

The benign forms pass through: a plain ``git commit`` (signs per repo config),
``-c commit.gpgsign=true``, and ``git config commit.gpgsign false`` is out of
scope here; this gate targets the per-invocation override, not a persistent
config change (which the operator can still make deliberately).

Design (CLAUDE.md section 4: make wrong actions hard, right actions easy):

- The gate denies rather than silently allowing; the deny reason names the
  matched bypass and points at the safe path; commit normally so signing
  applies; or, when the unsigned commit is genuinely intended and reviewed
  (e.g. a throwaway scratch repo), append an ``# unsigned-ack`` comment to opt
  in. The ack reuses the marker established by ``scan_workflow_unsigned_commit``
  for the same unsigned-commit category.
- Detection is command-position aware: each shell segment (split on ``;`` ``&&``
  ``||`` ``|`` and newlines) is tokenized and only its leading command (after
  any ``NAME=value`` prefix) is classified, so a destructive token buried in an
  argument or a quoted string (``echo "git -c commit.gpgsign=false"``) does not
  trip the gate.
- Parse-error fail-open is intentional and narrow: a malformed stdin event logs
  to stderr and exits 0 so a hook bug never wedges the session. The fail-open
  applies only to the stdin I/O boundary; a matched bypass is always denied.

Contract:
- Inputs: a PreToolUse hook event as JSON on stdin (``tool_name`` plus
  ``tool_input``; the Bash matcher carries a ``command`` string). No flags.
- Outputs: a JSON ``permissionDecision`` deny object on stdout when the command
  disables commit signing; nothing on stdout on pass-through. Always exits 0.
- Failure policy: fails open at the stdin boundary per CLAUDE.md section 4 (a
  malformed event never wedges the session) and fails loud-by-deny on a matched
  signing bypass.

Tested by ``tests/test_gate_unsigned_commit_bash.py``. Refs #1713.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import PurePosixPath
from typing import Any

from _hook_runtime import emit_decision, read_event

_DENY_RULE = "commit-signing-bypass-guard"

# Opt-in marker: a reviewed, intentional unsigned commit carries this comment
# and is allowed through. Reuses the marker established by
# ``scan_workflow_unsigned_commit`` for the same unsigned-commit category.
_ACK_MARKER = "# unsigned-ack"

# Shell separators that begin a new command position.
_SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")

# A leading ``NAME=value`` environment assignment to skip before the command.
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# ``commit.gpgsign`` set to one of git's false-ish booleans (case-insensitive).
# The key itself is case-insensitive in git, so the whole token is matched
# case-insensitively.
_GPGSIGN_OFF_RE = re.compile(r"^commit\.gpgsign=(?:false|0|no|off)$", re.IGNORECASE)


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
    ``/usr/bin/git`` classifies the same as ``git``.
    """
    index = 0
    while index < len(tokens) and _ASSIGN_RE.match(tokens[index]):
        index += 1
    if index >= len(tokens):
        return "", []
    name = PurePosixPath(_normalize(tokens[index])).name
    return name, tokens[index + 1 :]


def _disables_signing(args: list[str]) -> str | None:
    """Return a human label for the signing bypass in *args*, else None.

    Matches ``--no-gpg-sign`` and a ``-c commit.gpgsign=<false-ish>`` pair. The
    config override is recognised only when the value token follows a ``-c``
    token, so a positional argument that merely looks like the assignment is not
    matched.
    """
    for i, raw in enumerate(args):
        arg = _normalize(raw)
        if arg == "--no-gpg-sign":
            return "commit signing bypass (git --no-gpg-sign)"
        if arg == "-c" and i + 1 < len(args):
            value = _normalize(args[i + 1])
            if _GPGSIGN_OFF_RE.match(value):
                return "commit signing bypass (git -c commit.gpgsign=false)"
    return None


def _classify(segment: str) -> str | None:
    """Return a label for a signing-bypass ``git`` command in *segment*, else None."""
    cmd, args = _leading_command(_tokenize(segment))
    if cmd != "git":
        return None
    return _disables_signing(args)


def _deny(label: str) -> dict[str, Any]:
    return {
        "permissionDecision": "deny",
        "decisionReason": (
            f"[{_DENY_RULE}] Commit-signing bypass blocked: {label}.\n\n"
            "This repository requires signed commits (commit.gpgsign=true with an "
            "ssh signing key), so a plain `git commit` produces a Verified commit. "
            "Disabling signing for a single invocation defeats that requirement and "
            "yields an Unverified commit. Commit normally and let signing apply. "
            "If an unsigned commit is genuinely intended and reviewed (for example, "
            f"a throwaway scratch repo), append an '{_ACK_MARKER}' comment to the "
            "command to opt in."
        ),
    }


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny decision for a signing-bypass Bash command, else None.

    Pass-through (None) when the tool is not Bash, the command is empty, the
    opt-in marker is present, or no shell segment leads with a ``git`` command
    that disables commit signing.
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
    event = read_event("gate_unsigned_commit_bash")
    if event is None:
        return 0

    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str):
        print(
            "::error::gate_unsigned_commit_bash: event missing tool_name",
            file=sys.stderr,
        )
        return 0

    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    emit_decision(decide(tool_name, tool_input), "gate_unsigned_commit_bash", auditable=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
