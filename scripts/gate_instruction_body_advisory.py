#!/usr/bin/env python3
"""PreToolUse advisory: surface the PR-body obligation at commit time.

Refs #1710 (retro #1703, repair 1). The universal-instruction-text PR body
gates -- ``verify_text_delta_section`` (a ``## Text delta`` section is required
when ``CLAUDE.md`` / ``AGENTS.md`` / ``.apm/instructions/**`` change) and
``verify_instruction_text_growth`` (a ``text-growth-ack:`` line is required when
``.apm/instructions/**`` grows net-positive) -- run only at pre-push, after the
work is committed. PR #1698 hit exactly that gap: the agent committed an
instruction-text edit before preparing the body, and learned the requirement
only when the first ``git push`` was rejected. That is the same after-the-work
detection shape as the late-rebase loop (#1632): a deterministic requirement
that fires after the commit instead of in front of it.

This hook left-shifts the *awareness* (not the enforcement) to the moment the
agent commits an instruction-text edit. It is **advisory only and never
blocks**: it injects a non-blocking ``additionalContext`` reminder so the agent
prepares the ``## Text delta`` section (and, when ``.apm/instructions/**`` is
staged, the ``text-growth-ack:`` line) while composing the PR body, rather than
discovering the requirement at push. The push-time gates remain the
enforcement backstop (defense-in-depth, CLAUDE.md section 4); this only removes
the surprise.

Architecture mirrors :mod:`preflight_session_base_freshness`: pure detection on
top, a single subprocess boundary (:func:`_staged_files`) at the bottom, the
stdin/stdout contract delegated to :mod:`_hook_runtime`.

Contract:
- Inputs: a PreToolUse event on stdin (a Bash ``command`` string).
- Outputs: a non-blocking ``additionalContext`` payload when a ``git commit``
  stages universal instruction text; nothing otherwise.
- Failure policy: fails open (any error, off-target tool, or non-commit command
  yields no advisory) so the reminder can never wedge a commit; the push-time
  gates still enforce the requirement.

Tested by ``tests/test_gate_instruction_body_advisory.py``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from _hook_runtime import run_event_hook

REPO_ROOT = Path(__file__).resolve().parent.parent

# Mirror preflight_session_base_freshness's commit detector: match a ``git
# commit`` anywhere in the command (commits are chained, e.g. ``git add -A &&
# git commit``), but keep plumbing like ``git commit-tree`` out.
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit(?![\w-])")

# The universal instruction set, byte-aligned with verify_text_delta_section
# and verify_instruction_text_growth so the advisory tracks the gates it warns
# about. Exact-match mirrors plus the source directory prefix.
_INSTRUCTION_FILES: frozenset[str] = frozenset({"CLAUDE.md", "AGENTS.md"})
_INSTRUCTION_DIR_PREFIX = ".apm/instructions/"


def _is_instruction_path(path: str) -> bool:
    cleaned = path.strip()
    return cleaned in _INSTRUCTION_FILES or cleaned.startswith(_INSTRUCTION_DIR_PREFIX)


def _is_source_path(path: str) -> bool:
    """True for an ``.apm/instructions/**`` *source* edit (text-growth scope)."""
    return path.strip().startswith(_INSTRUCTION_DIR_PREFIX)


def build_advice(staged: list[str]) -> str | None:
    """Return the reminder text when *staged* touches instruction text, else None.

    The message always names the ``## Text delta`` section. When an
    ``.apm/instructions/**`` *source* file is staged it also names the
    ``text-growth-ack:`` line, since that gate scopes to the source only. ASCII
    so it is safe in any context sink.
    """
    instruction = sorted(p for p in staged if _is_instruction_path(p))
    if not instruction:
        return None
    needs_growth_ack = any(_is_source_path(p) for p in instruction)
    pretty = ", ".join(instruction)
    parts = [
        "Instruction-text edit staged for commit "
        f"({pretty}). Before pushing, the PR body will need a '## Text delta' "
        "section (enforced by verify_text_delta_section at push)"
    ]
    if needs_growth_ack:
        parts.append(
            " and, because .apm/instructions/** changed, a 'text-growth-ack:' "
            "line when the net char count grows (verify_instruction_text_growth)"
        )
    parts.append(
        ". Prepare those now so the requirement does not surface as a rejected "
        "push (retro #1703, repair 1). This is a reminder, not a block."
    )
    return "".join(parts)


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return a non-blocking additionalContext payload, or None to stay silent."""
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_COMMIT_RE.search(command):
        return None
    advice = build_advice(_staged_files())
    if advice is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": advice,
        }
    }


def _staged_files(*, runner=subprocess.run) -> list[str]:
    """Return the staged file paths, or ``[]`` on any error (fail-open).

    The single impure surface. ``git diff --cached --name-only`` lists what the
    pending commit will record; a failed invocation yields ``[]`` so the
    advisory simply stays silent.
    """
    try:
        result = runner(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    return run_event_hook("gate_instruction_body_advisory", decide)


if __name__ == "__main__":
    raise SystemExit(main())
