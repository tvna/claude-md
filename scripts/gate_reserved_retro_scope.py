#!/usr/bin/env python3
"""PreToolUse gate: forbid agent-created issues from using the reserved
``auto-retro`` scope.

Bound in ``.claude/settings.json`` (and mirrored in ``.codex/hooks.json`` /
``.devin/hooks.v1.json``) to ``mcp__github__issue_write``. When the call is a
``create`` whose ``title`` carries the reserved ``auto-retro`` Conventional
Commit scope, the create is denied with a ``permissionDecision: "deny"`` so the
agent cannot mint an issue that downstream automation mistakes for an
auto-opened retrospective.

One narrow exception (Refs #1581 / responsibility-separation design D1): the
pre-merge handoff survey opens the canonical retro IN-SESSION when the operator
reports a problem the CI detector cannot see (process repairs such as a
wrong-branch re-placement or a discarded-drift cleanup leave no PR-diff / CI /
review trace). That single permitted title is exactly the shape
:func:`auto_retro.build_retro_title` emits --
``chore(auto-retro): review PR #<N> repair loops`` -- matched by
:func:`auto_retro.is_canonical_handoff_retro_title`. Allowing only that exact
literal keeps every other ``auto-retro`` title denied, and because the
in-session retro uses the canonical shape, CI dedup
(:func:`auto_retro.find_existing_retro`) still recognises it and suppresses the
post-merge duplicate. The standalone retro carries no implementing PR, so it
does not trip ``verify-no-direct-retro-pr`` (which only fires on a PR that
links a retro issue).

Why this gate exists (Refs #1395): PR #1394 tripped the
``verify-no-direct-retro-pr`` CI gate because an agent-opened tracking issue
titled ``chore(auto-retro): ...`` satisfied
:func:`auto_retro.is_retro_issue_title`, so the linking PR looked like a direct
PR off an un-triaged retro. That cost one manual repair (the issue was renamed
to ``chore(retro-visibility): ...``). The ``auto-retro`` scope is reserved for
the CI ``open-retro`` job in ``.github/workflows/post-merge.yml`` -- which opens
the retro via ``scripts/auto_retro.py run`` through the ``gh`` REST boundary,
NOT through ``mcp__github__issue_write`` -- so this PreToolUse hook only ever
fires on the agent's own tool calls and never on the CI path. The boundary is
the tool surface itself; no event-source sniffing is needed.

Single source of truth: the reserved-scope decision reuses
:func:`auto_retro.is_retro_pr` (title's ``type(scope)`` token contains
``(auto-retro)`` for any Conventional Commit type) and
:func:`auto_retro.is_retro_issue_title` (the canonical / legacy retro-issue
title shapes that dedup, the sentinel, the label-derived prior, and the
no-direct-PR gate key on). Both predicates live in ``scripts/auto_retro.py``;
this gate imports them rather than re-deriving the match so the gate can never
drift from the detectors it protects.

Architecture mirrors :mod:`gate_issue_classification_labels`: pure
:func:`decide` on top, a single stdin/stdout boundary at the bottom
(:func:`main` via :func:`_hook_runtime.run_tool_hook`).

Failure modes (fail-open per CLAUDE.md section 4): off-target tool name, a
non-``create`` method, an absent or non-string ``title``, or malformed stdin
JSON -- all exit 0 with no decision so a hook bug never wedges the session. The
server-side ``verify-no-direct-retro-pr`` gate remains the backstop.

Refs #1395.
"""

from __future__ import annotations

from typing import Any

from _hook_runtime import build_deny, run_tool_hook
from auto_retro import (
    is_canonical_handoff_retro_title,
    is_retro_issue_title,
    is_retro_pr,
)

_TARGET_TOOL = "mcp__github__issue_write"
_CREATE_METHOD = "create"
_RESERVED_SCOPE = "auto-retro"


def uses_reserved_scope(title: str) -> bool:
    """Return ``True`` when *title* encroaches on the reserved ``auto-retro`` scope.

    Logical OR of the two single-source detectors in :mod:`auto_retro`:

    * :func:`auto_retro.is_retro_pr` -- the title's ``type(scope)`` token
      contains ``(auto-retro)`` for any Conventional Commit type (``chore``,
      ``fix``, ``docs``, ...). This is the literal "reserved scope" test.
    * :func:`auto_retro.is_retro_issue_title` -- the canonical
      ``chore(auto-retro)`` and legacy ``fix(auto-retro)`` retro-issue title
      prefixes that downstream dedup / no-direct-PR detection keys on, covering
      the malformed no-colon shapes that the regex-based ``is_retro_pr`` would
      miss.

    Reusing both keeps the gate's verdict identical to the detectors it guards.
    """
    return is_retro_pr(title) or is_retro_issue_title(title)


def build_reason() -> str:
    """Return the deny reason naming the reserved scope and the safe path."""
    return (
        "Blocked by scripts/gate_reserved_retro_scope.py: this "
        f"`{_TARGET_TOOL}` create uses the reserved `{_RESERVED_SCOPE}` scope "
        "in its title.\n\n"
        f"The `{_RESERVED_SCOPE}` Conventional Commit scope is reserved for "
        "the CI `open-retro` job in .github/workflows/post-merge.yml, which "
        "opens retrospective issues via scripts/auto_retro.py. An agent must "
        "not mint an issue with this scope: a title like "
        "`chore(auto-retro): ...` satisfies auto_retro.is_retro_issue_title, "
        "so the verify-no-direct-retro-pr CI gate then treats the linking PR "
        "as a direct PR off an un-triaged retro and blocks it (the #1394 "
        "false positive).\n\n"
        "Rename the title to a non-reserved scope -- e.g. "
        "`chore(retro-visibility): ...` -- and retry.\n\n"
        "The ONLY permitted exception is the canonical pre-merge handoff "
        "retro, whose title must be EXACTLY "
        "`chore(auto-retro): review PR #<N> repair loops` (the shape "
        "auto_retro.build_retro_title emits). If you are recording a "
        "handoff-survey problem, first check for an existing retro for PR "
        "#<N>: comment on it if one exists, otherwise create it with that "
        "exact title. Refs #1395. Refs #1581."
    )


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a deny decision for a reserved-scope create, else ``None``."""
    if tool_name != _TARGET_TOOL:
        return None
    if tool_input.get("method") != _CREATE_METHOD:
        return None

    title = tool_input.get("title")
    if not isinstance(title, str):
        return None
    if not uses_reserved_scope(title):
        return None
    # Narrow exception (Refs #1581): the pre-merge handoff survey opens the
    # canonical retro in-session when the operator reports a problem CI cannot
    # see. Only the exact build_retro_title shape is permitted; every other
    # ``auto-retro`` title stays denied. The single-source predicate lives in
    # auto_retro so the allow-list can never drift from the title producer.
    if is_canonical_handoff_retro_title(title):
        return None
    return build_deny(build_reason())


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_tool_hook("gate_reserved_retro_scope", decide)


if __name__ == "__main__":
    raise SystemExit(main())
