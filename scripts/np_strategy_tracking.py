#!/usr/bin/env python3
"""Apply the tracking classification to an issue delivered as N PRs.

When a single issue is deliberately delivered as N stacked or sibling
PRs, the first-merged PR must NOT close the issue. The deterministic
opt-out the harness honors is the ``type:tracking`` label on the
referenced issue (the ``all_tracking`` path in
``scripts/issue_link.py`` / ``scripts/pr_body_close_keyword_gate.py``):
sibling PRs then cite ``Refs #N`` without a body marker that the GitHub
MCP write tools delete (#1035).

This module turns that manual relabel into a deterministic step. Given
an issue and the sibling PR numbers, it computes the label set with the
``type`` family swapped to ``type:tracking`` -- per
``.github/label-policy.toml`` the ``type`` family is
``exactly_one_for_normal_issues``, so the swap removes the prior type
label rather than adding a second one -- and, in ``apply`` mode, writes
the new label set and records the rationale as an issue comment.

The label decision is a pure function (:func:`plan_label_swap`) so it is
fully testable offline; the GitHub mutation is a thin boundary on top of
``scripts/_github_api.apply_call``. ``plan`` is the default mode (dry
run); ``apply`` is explicit because it mutates a privileged resource.

Tested by ``tests/test_np_strategy_tracking.py``. Refs #1035, #1005.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from _github_api import apply_call as github_apply_call
from _ref_classifier import TRACKING_LABEL

API_ROOT = "https://api.github.com"
TYPE_PREFIX = "type:"


def plan_label_swap(labels: list[str]) -> dict[str, Any]:
    """Return the swap plan that makes *labels* carry exactly tracking.

    Drops every ``type:*`` label and adds ``type:tracking`` once,
    preserving the order of the non-type labels. The returned dict has:

    * ``already_tracking`` -- True iff the only ``type:*`` label present
      is the tracking label (nothing to change).
    * ``removed`` -- the ``type:*`` labels that will be dropped.
    * ``result`` -- the full, de-duplicated label-name list to PUT.
    """
    type_labels = [name for name in labels if name.startswith(TYPE_PREFIX)]
    non_type = [name for name in labels if not name.startswith(TYPE_PREFIX)]
    removed = [name for name in type_labels if name != TRACKING_LABEL]
    already_tracking = type_labels == [TRACKING_LABEL]

    result: list[str] = []
    for name in [*non_type, TRACKING_LABEL]:
        if name not in result:
            result.append(name)
    return {
        "already_tracking": already_tracking,
        "removed": removed,
        "result": result,
    }


def format_rationale(
    issue: int,
    prs: list[int],
    removed: list[str],
    reason: str | None = None,
) -> str:
    """Render the ASCII rationale recorded as an issue comment."""
    pr_list = ", ".join(f"#{p}" for p in prs) if prs else "(none specified)"
    swapped = (
        ", ".join(f"'{name}'" for name in removed)
        if removed
        else "(no prior type label)"
    )
    text = (
        f"Applied '{TRACKING_LABEL}' to #{issue} for an N-PR delivery "
        f"strategy (sibling PRs: {pr_list}). Swapped prior type "
        f"label(s): {swapped}, per .github/label-policy.toml (the "
        "'type' family is exactly_one_for_normal_issues). Sibling PRs "
        f"may now cite 'Refs #{issue}' without the body opt-out marker "
        "the GitHub MCP write tools strip. Refs #1035."
    )
    if reason:
        text += f" Reason: {reason}"
    return text


def fetch_labels(
    repo: str,
    issue: int,
    token: str,
    *,
    apply_call: Callable[..., tuple[int, str]] = github_apply_call,
) -> list[str]:
    """Return the label names on ``<repo>#<issue>`` or raise on failure."""
    code, body = apply_call(
        method="GET",
        url=f"{API_ROOT}/repos/{repo}/issues/{issue}",
        payload=None,
        token=token,
    )
    if not 200 <= code < 300:
        raise RuntimeError(f"failed to read labels for #{issue} (HTTP {code})")
    data = json.loads(body)
    raw = data.get("labels", []) if isinstance(data, dict) else []
    names: list[str] = []
    for entry in raw:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
        elif isinstance(entry, str):
            names.append(entry)
    return names


def put_labels(
    repo: str,
    issue: int,
    labels: list[str],
    token: str,
    *,
    apply_call: Callable[..., tuple[int, str]] = github_apply_call,
) -> int:
    """Replace the label set on ``<repo>#<issue>`` or raise on failure."""
    code, _ = apply_call(
        method="PUT",
        url=f"{API_ROOT}/repos/{repo}/issues/{issue}/labels",
        payload={"labels": labels},
        token=token,
    )
    if not 200 <= code < 300:
        raise RuntimeError(f"failed to set labels on #{issue} (HTTP {code})")
    return code


def post_comment(
    repo: str,
    issue: int,
    body_text: str,
    token: str,
    *,
    apply_call: Callable[..., tuple[int, str]] = github_apply_call,
) -> int:
    """Record *body_text* as a comment on ``<repo>#<issue>``."""
    code, _ = apply_call(
        method="POST",
        url=f"{API_ROOT}/repos/{repo}/issues/{issue}/comments",
        payload={"body": body_text},
        token=token,
    )
    if not 200 <= code < 300:
        raise RuntimeError(f"failed to comment on #{issue} (HTTP {code})")
    return code


def run(
    *,
    mode: str,
    repo: str,
    issue: int,
    prs: list[int],
    reason: str | None,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = github_apply_call,
) -> int:
    labels = fetch_labels(repo, issue, token, apply_call=apply_call)
    plan = plan_label_swap(labels)
    rationale = format_rationale(issue, prs, plan["removed"], reason)

    if plan["already_tracking"]:
        print(f"no-op: #{issue} already carries '{TRACKING_LABEL}'.")
        return 0

    print(f"plan: #{issue} labels {labels} -> {plan['result']}")
    print(f"plan: remove {plan['removed']}, add '{TRACKING_LABEL}'")
    print(f"rationale: {rationale}")

    if mode == "plan":
        print("dry-run: no changes applied (use 'apply' to mutate).")
        return 0

    put_labels(repo, issue, plan["result"], token, apply_call=apply_call)
    post_comment(repo, issue, rationale, token, apply_call=apply_call)
    print(
        f"applied: #{issue} now carries '{TRACKING_LABEL}'; "
        "rationale recorded."
    )
    return 0


def parse_prs(raw: str | None) -> list[int]:
    """Parse a ``--prs`` value (``"1033,1034"`` or ``"#1033 1034"``)."""
    if not raw:
        return []
    out: list[int] = []
    for token in raw.replace(",", " ").split():
        out.append(int(token.lstrip("#")))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("plan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=os.environ.get("REPO", ""))
        p.add_argument("--issue", type=int, required=True)
        p.add_argument(
            "--prs",
            default="",
            help="Sibling PR numbers, comma- or space-separated.",
        )
        p.add_argument(
            "--reason",
            default=None,
            help="Optional extra rationale recorded with the swap.",
        )
    args = parser.parse_args(argv)

    if not args.repo:
        print("::error::--repo (or $REPO) is required.")
        return 1
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        print("::error::GH_TOKEN is not set.")
        return 1

    try:
        return run(
            mode=args.mode,
            repo=args.repo,
            issue=args.issue,
            prs=parse_prs(args.prs),
            reason=args.reason,
            token=token,
        )
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"::error::{error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
