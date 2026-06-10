#!/usr/bin/env python3
"""PreToolUse gate: allow ``mcp__github__merge_pull_request`` only when the
target PR is safely mergeable.

Rationale: a merge is an outward-facing, effectively irreversible operation --
it can trigger deploys, notifications, and downstream automation. CLAUDE.md
section 4 requires confirmations/dry-runs for such operations ("make wrong
actions hard, right actions easy"). Before this gate, ``merge_pull_request``
ran only the ASCII / secret preflights and had no check that the PR was
actually safe to merge, so a session could merge a PR with red required checks
or a conflicted branch. This is the gap between the documented prohibition and
the enforced one that this gate closes.

The merge is allowed (pass-through) only when GitHub reports the PR as
``mergeable == true`` AND ``mergeable_state == "clean"`` -- no conflicts, all
required checks green, no pending required review. Any other state is denied
with a state-specific remediation:

- ``dirty``  -> merge conflict; use the replacement-branch recovery path.
- ``behind`` -> out of date; refresh via ``scripts/refresh_pr_branch.py --push``.
- ``blocked`` / ``unstable`` / ``unknown`` / ``draft`` / other -> required or
  optional checks pending or failing; re-check once CI settles.

This does NOT contradict CLAUDE.md section 3 ("drive to a terminal state
(merged, or closed)"): merge remains reachable -- it is gated on objective
safety, not prohibited. The human approval that authorises a merge happens in
the operator chat (the agent posts review comments on the operator's behalf),
which a deterministic hook cannot read; this gate enforces only the objective
safety floor that is machine-verifiable.

Fail-closed: unlike most gates (which fail open per CLAUDE.md section 4 so a
hook bug never wedges the session), this gate DENIES when it cannot determine
mergeability -- a missing ``GH_TOKEN``, an API failure, an unidentifiable PR,
or an unparseable event. Merge is irreversible-leaning, so the safe default is
to block and let the operator resolve, not to wave it through unverified.
Side effect: in an environment without ``GH_TOKEN`` every MCP merge is blocked
until a token is present; that is the intended safety posture for this
operation. (The stdin-parse fail-open in ``read_event`` still applies: a
malformed event yields no decision rather than a deny, because at that point
the tool/PR is unidentifiable -- the catch-all ``gate_mcp_github_uncovered``
does not cover merge, so a no-decision there simply lets the other merge
preflights run; the operator still sees no false safety signal.)

Wiring: PreToolUse matcher ``mcp__github__merge_pull_request`` in the generated
agent configs (source: ``scripts/agent_hooks_source.json``, claude and codex).
``merge_pull_request`` is already in ``HOOK_COVERED_TOOLS`` in
``gate_mcp_github_uncovered.py``, so the catch-all passes it through to here.

Refs #1563.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import build_deny, emit_decision, read_event, split_tool_event
from check_pr_mergeability import _get_token, _poll_mergeability

_TARGET_TOOL = "mcp__github__merge_pull_request"
_SCRIPT = "gate_merge_safety"

# Per-state remediation appended to the deny reason. Keyed by GitHub's
# ``mergeable_state``. Anything not listed falls back to ``_GENERIC_REMEDIATION``.
_STATE_REMEDIATION: dict[str, str] = {
    "dirty": (
        "mergeable_state=dirty: the branch conflicts with the base. force-push "
        "is blocked and update_pull_request_branch is gated, so use the "
        "replacement-branch path: docs/runbooks/update-pr-branch-recovery.md."
    ),
    "behind": (
        "mergeable_state=behind: the branch is out of date (no conflict). Bring "
        "it up to date deterministically -- do NOT force-push: from the PR branch "
        "run `python3 scripts/refresh_pr_branch.py --push`. "
        "See docs/runbooks/refresh-behind-pr.md."
    ),
    "blocked": (
        "mergeable_state=blocked: a required status check is pending or failing, "
        "or a required review is missing. Wait for CI to settle and required "
        "gates to pass, then re-try. See docs/runbooks/merge-readiness-loop.md."
    ),
    "unstable": (
        "mergeable_state=unstable: a non-required check is failing. Only clean "
        "merges are allowed; investigate the failing check and re-try once it is "
        "green. See docs/runbooks/merge-readiness-loop.md."
    ),
    "draft": (
        "mergeable_state=draft: the PR is still a draft. Mark it ready for review "
        "before merging."
    ),
    "unknown": (
        "mergeable_state=unknown: GitHub has not finished computing mergeability. "
        "Re-check shortly via the GitHub REST API, then re-try once it settles."
    ),
}

_GENERIC_REMEDIATION = (
    "Only PRs with mergeable_state=clean (no conflicts, all required checks "
    "green) may be merged via MCP. Resolve the above and re-try. "
    "See docs/runbooks/merge-readiness-loop.md."
)

_MISSING_GH_AUTH_REASON = (
    "`mcp__github__merge_pull_request` is blocked: GH_TOKEN is not set, so the "
    "PR's mergeable state cannot be verified. This gate is fail-closed for "
    "merges (an irreversible, outward-facing operation): a merge is allowed "
    "only after confirming mergeable_state=clean. Provide GH_TOKEN and re-try."
)

_API_FAILED_REASON = (
    "`mcp__github__merge_pull_request` is blocked: the GitHub API call to verify "
    "the PR's mergeable state failed or timed out, so safety cannot be "
    "confirmed. This gate is fail-closed for merges. Re-check the PR "
    "mergeable_state via the GitHub REST API and re-try once it reads clean."
)

_BAD_INPUT_REASON = (
    "`mcp__github__merge_pull_request` is blocked: the call is missing a valid "
    "owner/repo/pullNumber, so the target PR cannot be identified and its "
    "mergeable state cannot be verified. This gate is fail-closed for merges. "
    "Supply owner, repo, and a numeric pullNumber and re-try."
)


def _pr_number(value: Any) -> str | None:
    """Return *value* as a decimal PR-number string, or None when unusable.

    ``bool`` is rejected explicitly (it is an ``int`` subclass) so ``True``
    never masquerades as PR #1.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.isdecimal():
        return value
    return None


def _deny_for_state(label: str, mergeable: Any, state: str) -> dict[str, Any]:
    remediation = _STATE_REMEDIATION.get(state, _GENERIC_REMEDIATION)
    return build_deny(
        f"`mcp__github__merge_pull_request` is blocked for {label}: not safe to "
        f"merge (mergeable={mergeable!r}, mergeable_state={state!r}).\n\n"
        f"{remediation}"
    )


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    token: str = "",
    poller: Any = _poll_mergeability,
) -> dict[str, Any] | None:
    """Return a deny decision unless the target PR is safe to merge.

    Returns ``None`` (pass-through, merge allowed) only when the tool is
    ``merge_pull_request`` and GitHub reports ``mergeable is True`` and
    ``mergeable_state == "clean"``. Returns ``None`` for any other tool (not our
    concern). Every uncertain or unsafe case for the merge tool yields a deny
    (fail-closed).

    *token* / *poller* are injectable for tests; production uses ``GH_TOKEN``
    and the real mergeability poller.
    """
    if tool_name != _TARGET_TOOL:
        return None

    owner = tool_input.get("owner")
    repo = tool_input.get("repo")
    pr_number = _pr_number(tool_input.get("pullNumber"))
    if not (isinstance(owner, str) and owner and isinstance(repo, str) and repo and pr_number):
        return build_deny(_BAD_INPUT_REASON)

    label = f"{owner}/{repo}#{pr_number}"

    actual_token = token or _get_token()
    if not actual_token:
        return build_deny(_MISSING_GH_AUTH_REASON)

    pr_data = poller(owner, repo, pr_number, token=actual_token)
    if not isinstance(pr_data, dict):
        return build_deny(_API_FAILED_REASON)

    mergeable = pr_data.get("mergeable")
    state = str(pr_data.get("mergeable_state") or "unknown").lower()
    if mergeable is True and state == "clean":
        return None

    return _deny_for_state(label, mergeable, state)


def main(argv: list[str] | None = None) -> int:
    """Read the PreToolUse event from stdin and emit a deny decision if unsafe.

    Always returns 0 (the process exit code is fail-open at the stdin-parse
    layer); the merge-specific fail-closed behaviour lives in :func:`decide`,
    which emits a deny rather than relying on a non-zero exit.
    """
    del argv
    event = read_event(_SCRIPT)
    if event is None:
        return 0
    split = split_tool_event(event, _SCRIPT)
    if split is None:
        return 0
    emit_decision(decide(*split), _SCRIPT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
