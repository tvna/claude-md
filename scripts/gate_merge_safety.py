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
``mergeable == true`` AND ``mergeable_state == "clean"``; no conflicts, all
required checks green, no pending required review. Any other state is denied
with a state-specific remediation:

- ``dirty``  -> merge conflict; use the replacement-branch recovery path.
- ``behind`` -> out of date; refresh via ``scripts/refresh_pr_branch.py --push``.
- ``blocked`` / ``unstable`` / ``unknown`` / ``draft`` / other -> required or
  optional checks pending or failing; re-check once CI settles.

This does NOT contradict CLAUDE.md section 3 ("drive to a terminal state
(merged, or closed)"): merge remains reachable; it is gated on objective
safety, not prohibited. The human approval that authorises a merge happens in
the operator chat (the agent posts review comments on the operator's behalf),
which a deterministic hook cannot read; this gate enforces only the objective
safety floor that is machine-verifiable.

Fail-closed: unlike most gates (which fail open per CLAUDE.md section 4 so a
hook bug never wedges the session), this gate DENIES when it cannot determine
mergeability; a missing ``GH_TOKEN``, an API failure, an unidentifiable PR,
or an unparseable event. Merge is irreversible-leaning, so the safe default is
to block and let the operator resolve, not to wave it through unverified.
Side effect: in an environment without ``GH_TOKEN`` every MCP merge is blocked
until a token is present; that is the intended safety posture for this
operation. (The stdin-parse fail-open in ``read_event`` still applies: a
malformed event yields no decision rather than a deny, because at that point
the tool/PR is unidentifiable; the catch-all ``gate_mcp_github_uncovered``
does not cover merge, so a no-decision there simply lets the other merge
preflights run; the operator still sees no false safety signal.)

Safety-boundary classification (#2403): this gate is a security-boundary
gate, the same class as the six push gates and
``preflight_github_secrets``. ``main`` passes ``auditable=False`` to
``emit_decision`` so ``CLAUDE_GATE_MODE=audit`` can never downgrade a merge
deny to a stderr warning; audit mode may only relax governance/workflow
gates, never this one.

Poll budget (#2404): mergeability is polled with this module's own
``_MERGE_GATE_MAX_POLLS`` budget, not ``check_pr_mergeability``'s advisory
default (10 polls, tuned for a fail-open PostToolUse path). The two scripts
sit in different safety classes (the poller is fail-open advisory, this
gate is fail-closed), so a tuning change made for the advisory path must
not silently retune this gate. A poll-budget expiry denies with an explicit
timeout-named message (:func:`_deny_for_poll_timeout`), distinct from the
generic ``unknown``-state remediation below.

Wiring: PreToolUse matcher ``mcp__github__merge_pull_request`` in the generated
agent configs (source: ``scripts/agent_hooks_source.json``, claude and codex).
``merge_pull_request`` is already in ``HOOK_COVERED_TOOLS`` in
``gate_mcp_github_uncovered.py``, so the catch-all passes it through to here.

Refs #1563, #2404.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import build_deny, emit_decision, read_event, split_tool_event
from check_pr_mergeability import _POLL_INTERVAL_SECONDS, _get_token, _poll_mergeability

# Own poll budget (#2404), independent of check_pr_mergeability._MAX_POLLS.
# That advisory default (10 polls) is tuned for a PostToolUse path whose
# module docstring says a failure "must never block"; this gate is
# fail-closed and blocks the agent synchronously, so it is sized more
# generously (double the advisory budget) rather than inheriting a value
# tuned for a different safety class. Only the poll count is overridden
# here; the per-poll interval (_POLL_INTERVAL_SECONDS) stays shared because
# _poll_mergeability has no independent interval parameter to override.
_MERGE_GATE_MAX_POLLS = 20

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
        "it up to date deterministically; do NOT force-push: from the PR branch "
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


def _deny_for_poll_timeout(label: str) -> dict[str, Any]:
    """Deny for a gate-side poll-budget expiry (#2404). Reached only when
    ``mergeable`` is still ``None`` AND GitHub explicitly returned the literal
    string ``"unknown"`` for ``mergeable_state`` on the final poll, i.e.
    GitHub had not finished computing mergeability within this gate's own
    budget. Deliberately narrower than "mergeable is None and the *defaulted*
    state reads unknown": a malformed/partial payload that is merely missing
    the ``mergeable_state`` key is a different, likely persistent problem and
    falls through to :func:`_deny_for_state` instead, so it is not reassured
    away as a benign timing race. The deny names the timeout explicitly so
    the agent knows a bare retry (not the generic ``unknown``-state
    remediation) is the right next step for a genuine poll-timeout.
    """
    sleep_seconds = (_MERGE_GATE_MAX_POLLS - 1) * _POLL_INTERVAL_SECONDS
    return build_deny(
        f"`mcp__github__merge_pull_request` is blocked for {label}: this "
        f"gate's own poll budget ({_MERGE_GATE_MAX_POLLS} attempts, "
        f"{_POLL_INTERVAL_SECONDS}s apart, at least ~{sleep_seconds:.0f}s of sleep "
        "alone plus each poll's own network latency) expired before GitHub "
        "returned a determinate mergeable value (mergeable is still null). "
        "This is a poll-timeout: this gate's own budget ran out, not "
        "necessarily a persistent GitHub-side problem. Re-check the PR "
        "mergeable_state via the GitHub REST API and re-try. If this keeps "
        "recurring across multiple attempts for the same PR, mergeability "
        "computation may be genuinely stuck (e.g. an unusually large diff); "
        "see docs/runbooks/merge-readiness-loop.md rather than retrying "
        "indefinitely."
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

    Polls with this gate's own :data:`_MERGE_GATE_MAX_POLLS` budget (#2404),
    not ``check_pr_mergeability``'s advisory default, so a tuning change made
    for that fail-open PostToolUse path cannot silently retune this
    fail-closed gate. A poll-budget expiry (``mergeable`` still ``None`` after
    the budget) denies via :func:`_deny_for_poll_timeout`, which names the
    timeout explicitly rather than reusing the generic ``unknown``-state
    remediation.

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

    pr_data = poller(owner, repo, pr_number, token=actual_token, max_polls=_MERGE_GATE_MAX_POLLS)
    if not isinstance(pr_data, dict):
        return build_deny(_API_FAILED_REASON)

    mergeable = pr_data.get("mergeable")
    raw_state = pr_data.get("mergeable_state")
    state = str(raw_state or "unknown").lower()
    if mergeable is True and state == "clean":
        return None
    # Poll-timeout is narrower than "state defaults to unknown": it fires only
    # when GitHub itself returned the literal string "unknown" alongside a
    # still-null mergeable, not when mergeable_state was missing/malformed
    # (which the `or "unknown"` fallback above would otherwise collapse into
    # the same value). A malformed payload is a different, likely persistent
    # problem and should not be reassured away as a benign timing race.
    if mergeable is None and isinstance(raw_state, str) and raw_state.strip().lower() == "unknown":
        return _deny_for_poll_timeout(label)

    return _deny_for_state(label, mergeable, state)


def main(argv: list[str] | None = None) -> int:
    """Read the PreToolUse event from stdin and emit a deny decision if unsafe.

    Always returns 0 (the process exit code is fail-open at the stdin-parse
    layer); the merge-specific fail-closed behaviour lives in :func:`decide`,
    which emits a deny rather than relying on a non-zero exit.

    ``auditable=False`` so ``CLAUDE_GATE_MODE=audit`` can never disable this
    security-boundary gate (#2403).
    """
    del argv
    event = read_event(_SCRIPT)
    if event is None:
        return 0
    split = split_tool_event(event, _SCRIPT)
    if split is None:
        return 0
    emit_decision(decide(*split), _SCRIPT, auditable=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
