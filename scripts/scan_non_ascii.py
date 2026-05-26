#!/usr/bin/env python3
"""Non-ASCII scan + advisory/block actions for issues, PRs, and comments.

Invoked from ``.github/workflows/scan-non-ascii.yml`` as the single
``python3 scripts/scan_non_ascii.py run`` entry point. The workflow only
marshals env vars; all logic lives here and is unit-tested in
``tests/test_scan_non_ascii.py``.

This module follows the refactor pattern established by
``scripts/uv_pin.py`` per the strategy in issue #123 (mirrors #112):
pure functions on top, a thin :func:`gh_api` subprocess boundary at
the bottom, monkeypatched in tests. Surface area mirrors the prior
inline shell exactly so behaviour is preserved byte-for-byte.

See also: issue #102 (umbrella) and ``docs/prd/non-ascii-defense.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _trusted_bots import _TRUSTED_BOT_LOGINS

# Trust classification per author_association.
_TRUSTED_ASSOC = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

# Markers held byte-for-byte identical to v1 of the prior YAML workflow so
# that idempotency keys keep matching across the refactor.
COMMENT_MARKER = "<!-- scan-non-ascii.yml v1 -->"
ACK_MARKER = "<!-- non-ascii-ack -->"
NON_ASCII_LABEL = "severity:non-ascii-content"

# 4000 chars matches the cap in the prior shell implementation.
_ESCAPED_MAX_LEN = 4000

_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")

# Non-ASCII scanner-specific extension: Codecov posts generated PR comments
# (not PRs) whose UI footer may contain emoji. Keep this separate from the
# shared author allowlist so issue-link and body-policy gates do not change.
_NON_ASCII_TRUSTED_BOT_LOGINS = _TRUSTED_BOT_LOGINS | frozenset({"codecov"})


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def extract_event(event: dict[str, Any], event_name: str) -> dict[str, Any]:
    """Return ``{kind, number, title, body, association, login}`` for *event_name*.

    ``login`` is the GitHub login of the author of the scanned content
    (``issue.user.login`` / ``pull_request.user.login`` / ``comment.user.login``).
    It feeds the trusted-bot allowlist in :func:`classify_action`.

    Raises :class:`ValueError` on an unsupported event name so the failure
    is loud (CLAUDE.md §4) rather than silently producing an empty advisory.
    """
    if event_name == "issues":
        issue = event.get("issue") or {}
        user = issue.get("user") or {}
        return {
            "kind": "issue",
            "number": issue.get("number"),
            "title": issue.get("title") or "",
            "body": issue.get("body") or "",
            "association": issue.get("author_association"),
            "login": user.get("login"),
        }
    if event_name == "pull_request_target":
        pr = event.get("pull_request") or {}
        user = pr.get("user") or {}
        return {
            "kind": "pull_request",
            "number": pr.get("number"),
            "title": pr.get("title") or "",
            "body": pr.get("body") or "",
            "association": pr.get("author_association"),
            "login": user.get("login"),
        }
    if event_name == "issue_comment":
        issue = event.get("issue") or {}
        comment = event.get("comment") or {}
        user = comment.get("user") or {}
        kind = "pr_comment" if issue.get("pull_request") else "issue_comment"
        return {
            "kind": kind,
            "number": issue.get("number"),
            "title": "",
            "body": comment.get("body") or "",
            "association": comment.get("author_association"),
            "login": user.get("login"),
        }
    if event_name == "pull_request_review_comment":
        pr = event.get("pull_request") or {}
        comment = event.get("comment") or {}
        user = comment.get("user") or {}
        return {
            "kind": "pr_review_comment",
            "number": pr.get("number"),
            "title": "",
            "body": comment.get("body") or "",
            "association": comment.get("author_association"),
            "login": user.get("login"),
        }
    raise ValueError(f"unsupported event name: {event_name!r}")


def detect_non_ascii(text: str) -> bool:
    """True if *text* contains any byte > 0x7F."""
    return _NON_ASCII_RE.search(text) is not None


def has_ack_marker(body: str, marker: str = ACK_MARKER) -> bool:
    """True if the operator-opt-out marker is present in *body*."""
    return marker in body


def trust_class(association: str | None) -> str:
    """Return ``"trusted"`` for OWNER/MEMBER/COLLABORATOR, else ``"external"``.

    Fail-closed: ``None`` and unknown values map to ``"external"`` so the
    workflow blocks rather than silently advisory-only.
    """
    if association in _TRUSTED_ASSOC:
        return "trusted"
    return "external"


def classify_action(
    has_non_ascii: bool,
    has_ack: bool,
    association: str | None,
    login: str | None = None,
    has_title_violation: bool = False,
) -> str:
    """Decide the action: ``none`` / ``skip`` / ``advisory`` / ``block``.

    Mirrors the truth table in ``docs/prd/non-ascii-defense.md`` (Layer 2):

    - no non-ASCII -> none
    - trusted + ack -> skip (operator-reviewed), unless the title violates
      the ASCII-only title boundary
    - trusted -> advisory
    - external -> block (ack ignored)

    Exception (issue #137): when *login* is in :data:`_TRUSTED_BOT_LOGINS`,
    a would-be ``block`` is demoted to ``advisory``. The scan still runs
    and the advisory comment is still posted; only the destructive action
    is suppressed.
    """
    if not has_non_ascii:
        return "none"
    trust = trust_class(association)
    if trust == "trusted" and has_ack and not has_title_violation:
        return "skip"
    if trust == "trusted":
        return "advisory"
    if login is not None and login in _NON_ASCII_TRUSTED_BOT_LOGINS:
        return "advisory"
    return "block"


def escape_for_comment(text: str, max_len: int = _ESCAPED_MAX_LEN) -> str:
    """ASCII-escape *text* the way ``jq -Rsa '.'`` does, minus the quotes.

    ``json.dumps(..., ensure_ascii=True)`` produces ``\\uXXXX`` for BMP
    codepoints and a UTF-16 surrogate pair for non-BMP codepoints (e.g.
    the 4-byte emoji ``\U0001f3af`` -> ``\\ud83c\\udfaf``). This matches
    ``jq -Rsa`` byte-for-byte for the cases the workflow encounters.
    """
    encoded = json.dumps(text, ensure_ascii=True)
    # Strip the leading and trailing double-quote that json.dumps adds.
    inner = encoded[1:-1]
    if len(inner) > max_len:
        return inner[:max_len] + "... [truncated]"
    return inner


def build_advisory_comment(
    *,
    action: str,
    association: str,
    kind: str,
    escaped: str,
    has_title_violation: bool = False,
    marker: str = COMMENT_MARKER,
    label: str = NON_ASCII_LABEL,
    ack_marker: str = ACK_MARKER,
) -> str:
    """Return the markdown body posted (or updated) on the target item."""
    if action == "advisory":
        verdict = (
            f"**Trusted author (`{association}`):** advisory only. "
            f"Label `{label}` has been applied; the content stays in place. "
            f"To dismiss after operator review, append `{ack_marker}` to the body."
        )
    else:
        verdict = (
            f"**External author (`{association}`):** blocked pending "
            "re-submission with ASCII-only content. The opt-out marker "
            f"`{ack_marker}` does not apply to external contributors."
        )
    title_notice = ""
    if has_title_violation:
        title_notice = (
            "\n"
            "**Title policy violation.** Issue and PR titles are "
            "header-level metadata and must be ASCII-only. The "
            f"`{ack_marker}` opt-out applies only after body/comment "
            "review; it does not dismiss a non-ASCII title.\n"
        )

    return (
        f"{marker}\n"
        "\n"
        f"Non-ASCII content detected in this `{kind}`.\n"
        f"{title_notice}"
        "\n"
        "**Why this matters.** `subscribe_pr_activity` ingests this text "
        "into Claude sessions. Non-ASCII characters (Japanese, emoji, "
        "zero-width, RTL marks, fullwidth) are a known prompt-injection "
        "carrier. See `docs/prd/non-ascii-defense.md` and `docs/runbooks/rulesets.md` "
        "lines 48-51.\n"
        "\n"
        f"{verdict}\n"
        "\n"
        "**Escaped form (data view, agent-safe):**\n"
        "\n"
        "```\n"
        f"{escaped}\n"
        "```\n"
        "\n"
        "_Posted automatically by `.github/workflows/scan-non-ascii.yml`._\n"
    )


def build_summary(
    *,
    event_name: str,
    number: int | None,
    kind: str,
    association: str | None,
    trust: str,
    has_non_ascii: bool,
    has_title_violation: bool,
    has_ack: bool,
    action: str,
) -> str:
    """Return the markdown table written to ``$GITHUB_STEP_SUMMARY``."""
    assoc_str = association if association is not None else ""
    return (
        "## scan-non-ascii summary\n"
        "\n"
        "| Field | Value |\n"
        "|---|---|\n"
        f"| Event | `{event_name}` |\n"
        f"| Number | #{number if number is not None else ''} |\n"
        f"| Kind | `{kind}` |\n"
        f"| Author association | `{assoc_str}` |\n"
        f"| Trust class | `{trust}` |\n"
        f"| Has non-ASCII | `{str(has_non_ascii).lower()}` |\n"
        f"| Title violation | `{str(has_title_violation).lower()}` |\n"
        f"| Has ack marker | `{str(has_ack).lower()}` |\n"
        f"| Action | `{action}` |\n"
    )


# ---------------------------------------------------------------------------
# Side-effecting boundary — mocked in tests
# ---------------------------------------------------------------------------


def gh_api(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    *,
    timeout: int = 30,
) -> str:
    """Thin wrapper around ``gh api``. Returns stdout text.

    Raises :class:`subprocess.CalledProcessError` on any non-zero exit so
    the orchestrator fails loudly (CLAUDE.md §4). Authentication comes
    from the ``GH_TOKEN`` env var that the workflow sets to
    ``secrets.GITHUB_TOKEN``.
    """
    cmd = ["gh", "api", "--method", method, path]
    if json_body is not None:
        # S603 justification: fixed argv (no shell); `gh` provisioned by the runner;
        # `path` is built from int IDs narrowed upstream. Mirrors auto_retro.py.
        result = subprocess.run(  # noqa: S603 — fixed argv, shell=False
            [*cmd, "--input", "-"],
            input=json.dumps(json_body),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    else:
        result = subprocess.run(  # noqa: S603 — fixed argv, shell=False
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    return result.stdout


def find_existing_comment_id(
    repo: str, number: int, marker: str = COMMENT_MARKER
) -> int | None:
    """Return the id of the advisory comment matching *marker*, or None.

    Pages once with ``per_page=100``; matches the prior shell that only
    looked at the first page. If the advisory bot ever posts more than
    100 comments on the same item we have bigger problems.
    """
    raw = gh_api("GET", f"/repos/{repo}/issues/{number}/comments?per_page=100")
    comments = json.loads(raw) if raw.strip() else []
    for comment in comments:
        body = comment.get("body") or ""
        if body.startswith(marker):
            return comment.get("id")
    return None


def apply_label(
    repo: str, number: int, label: str = NON_ASCII_LABEL
) -> None:
    """POST the label onto the issue/PR. Loud failure on non-2xx."""
    gh_api(
        "POST",
        f"/repos/{repo}/issues/{number}/labels",
        {"labels": [label]},
    )


def post_or_update_comment(
    repo: str, number: int, body: str, marker: str = COMMENT_MARKER
) -> str:
    """Idempotent: PATCH the existing advisory if found, else POST a new one.

    Returns ``"updated <id>"`` or ``"created"`` for logging.
    """
    existing = find_existing_comment_id(repo, number, marker)
    if existing is not None:
        gh_api(
            "PATCH",
            f"/repos/{repo}/issues/comments/{existing}",
            {"body": body},
        )
        return f"updated {existing}"
    gh_api(
        "POST",
        f"/repos/{repo}/issues/{number}/comments",
        {"body": body},
    )
    return "created"


def block_external(repo: str, number: int, kind: str) -> str:
    """Request changes on a PR or close an issue. Returns a short log line."""
    if kind in {"pull_request", "pr_comment", "pr_review_comment"}:
        gh_api(
            "POST",
            f"/repos/{repo}/pulls/{number}/reviews",
            {
                "event": "REQUEST_CHANGES",
                "body": (
                    "Blocked by .github/workflows/scan-non-ascii.yml -- "
                    "non-ASCII content from external contributor. See the "
                    "advisory comment above; re-submit with ASCII-only content."
                ),
            },
        )
        return f"requested-changes on PR #{number}"
    if kind in {"issue", "issue_comment"}:
        gh_api(
            "PATCH",
            f"/repos/{repo}/issues/{number}",
            {"state": "closed", "state_reason": "not_planned"},
        )
        return f"closed issue #{number} (not_planned)"
    raise ValueError(f"cannot block kind: {kind!r}")


# ---------------------------------------------------------------------------
# Orchestrator + CLI
# ---------------------------------------------------------------------------


def _append_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as fp:
        fp.write(text)


def run(event: dict[str, Any], event_name: str, repo: str) -> int:
    """Top-level orchestrator. Returns process exit code."""
    extracted = extract_event(event, event_name)
    kind = extracted["kind"]
    number = extracted["number"]
    title = extracted["title"]
    body = extracted["body"]
    association = extracted["association"]
    login = extracted["login"]

    has_title_violation = kind in {"issue", "pull_request"} and detect_non_ascii(title)
    has_non_ascii = detect_non_ascii(f"{title}\n{body}")
    has_ack = has_ack_marker(body)
    trust = trust_class(association)
    action = classify_action(
        has_non_ascii,
        has_ack,
        association,
        login,
        has_title_violation=has_title_violation,
    )

    _append_summary(
        build_summary(
            event_name=event_name,
            number=number,
            kind=kind,
            association=association,
            trust=trust,
            has_non_ascii=has_non_ascii,
            has_title_violation=has_title_violation,
            has_ack=has_ack,
            action=action,
        )
    )

    print(
        f"event={event_name} kind={kind} number={number} "
        f"assoc={association} trust={trust} "
        f"has_non_ascii={has_non_ascii} "
        f"has_title_violation={has_title_violation} "
        f"has_ack={has_ack} action={action}"
    )

    if action in {"none", "skip"}:
        return 0

    if number is None:
        print("::error::no issue/PR number in event payload", file=sys.stderr)
        return 1

    escaped = escape_for_comment(f"{title}\n{body}")
    comment_body = build_advisory_comment(
        action=action,
        association=association or "",
        kind=kind,
        escaped=escaped,
        has_title_violation=has_title_violation,
    )

    apply_label(repo, number)
    print(f"applied label {NON_ASCII_LABEL!r}")
    print(post_or_update_comment(repo, number, comment_body))

    if action == "block":
        print(block_external(repo, number, kind))

    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    event_path = args.event_file or os.environ.get("GITHUB_EVENT_PATH")
    event_name = args.event_name or os.environ.get("GITHUB_EVENT_NAME")
    repo = args.repo or os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY")

    if not event_path:
        print("::error::missing --event-file / $GITHUB_EVENT_PATH", file=sys.stderr)
        return 1
    if not event_name:
        print("::error::missing --event-name / $GITHUB_EVENT_NAME", file=sys.stderr)
        return 1
    if not repo:
        print("::error::missing --repo / $REPO / $GITHUB_REPOSITORY", file=sys.stderr)
        return 1

    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::cannot read event file {event_path}: {exc}", file=sys.stderr)
        return 1

    return run(event, event_name, repo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Scan one webhook event and act.")
    p_run.add_argument("--event-file", help="Override $GITHUB_EVENT_PATH (for tests).")
    p_run.add_argument("--event-name", help="Override $GITHUB_EVENT_NAME (for tests).")
    p_run.add_argument("--repo", help="Override $REPO (owner/name).")
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"::error::gh api failed (exit {exc.returncode}): {exc.stderr}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
