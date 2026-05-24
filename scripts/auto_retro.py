#!/usr/bin/env python3
"""Auto-open a retrospective issue when a pull request is merged.

Invoked from ``.github/workflows/auto-retro.yml`` as the single
``python3 scripts/auto_retro.py run`` entry point. The workflow only
marshals env vars; all logic lives here and is unit-tested in
``tests/test_auto_retro.py``.

Implements CLAUDE.md section 3: "After each merge, auto-open a
retrospective issue -- make this deterministic, not operator-memory."
Refs #234.

Follows the refactor pattern established by ``scripts/scan_non_ascii.py``:
pure functions on top, a thin :func:`gh_api` subprocess boundary at the
bottom, monkeypatched in tests.

Skip conditions:

* the merged PR is itself a retrospective. Detected when the title
  starts with ``retro(`` or ``retro:``, OR when the title's
  ``type(scope)`` token contains the literal ``(retro)`` scope (e.g.
  ``docs(retro):``, ``feat(retro):``). The second branch covers
  retro-closing PRs that the title policy forces to use a non-``retro``
  Conventional Commit type. Avoids recursion.
* the merged PR was authored or merged by a login in
  ``_trusted_bots._TRUSTED_BOT_LOGINS``
* a retro issue already exists for the source PR (open or closed)
* the merged PR has zero inline review comments (positive-control
  merge: no observable repair history to record). Falls back to
  creating the retro when the comments lookup raises, so transient
  API errors preserve the audit trail.

Issue shape mirrors ``body_policy._ISSUE_COMMON_REQUIRED`` so the
auto-opened issue passes ``verify-body-policy``. The script does not
import that constant to avoid a circular dependency at workflow load
time; ``tests/test_auto_retro.py`` asserts the two stay aligned.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from _trusted_bots import _TRUSTED_BOT_LOGINS
from issue_link import extract_refs, strip_html_comments

FALLBACK_TYPE_SCOPE = "retro"

# Section names mirror body_policy._ISSUE_COMMON_REQUIRED so the
# auto-opened retro issue passes verify-body-policy. Drift between the
# two is caught by tests/test_auto_retro.py::test_required_sections_align.
_REQUIRED_SECTIONS: tuple[str, ...] = (
    "Scope",
    "Facts",
    "Proposed work",
    "Verification",
    "Acceptance criteria",
)

# Conservative match: lowercase Conventional Commit token with optional
# parenthetic scope. Non-matching titles fall back to FALLBACK_TYPE_SCOPE
# and the retro body records the fallback in its Facts section.
_TYPE_SCOPE_RE = re.compile(r"^([a-z][a-z0-9-]*(?:\([a-z0-9-]+\))?)\s*:")


@dataclass(frozen=True)
class MergedPR:
    number: int
    title: str
    merged: bool
    merged_at: str
    merged_by_login: str | None
    user_login: str | None
    layer_labels: tuple[str, ...]
    html_url: str
    body: str = ""
    commits: int = 0


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def parse_event(event: dict[str, Any]) -> MergedPR:
    """Extract the fields the retro flow needs from a pull_request event.

    Raises :class:`ValueError` when the event payload has no
    ``pull_request`` object or no ``number``. ``merged == false`` is NOT
    raised here; callers (run, _cmd_run) decide what to do with an
    unmerged event so the workflow stays composable.
    """
    pr = event.get("pull_request") or {}
    number = pr.get("number")
    if number is None:
        raise ValueError("event payload has no pull_request.number")

    merged_by = pr.get("merged_by") or {}
    user = pr.get("user") or {}
    labels = pr.get("labels") or []
    layer_labels = tuple(
        (lbl.get("name") or "")
        for lbl in labels
        if (lbl.get("name") or "").startswith("layer:")
    )
    return MergedPR(
        number=int(number),
        title=str(pr.get("title") or ""),
        merged=bool(pr.get("merged")),
        merged_at=str(pr.get("merged_at") or ""),
        merged_by_login=merged_by.get("login"),
        user_login=user.get("login"),
        layer_labels=layer_labels,
        html_url=str(pr.get("html_url") or ""),
        body=str(pr.get("body") or ""),
        commits=int(pr.get("commits") or 0),
    )


def extract_type_scope(pr_title: str) -> str:
    """Extract the ``type(scope)`` token from a Conventional Commit title.

    Returns ``""`` when the title does not match; callers should fall
    back to :data:`FALLBACK_TYPE_SCOPE`.
    """
    match = _TYPE_SCOPE_RE.match(pr_title)
    if match is None:
        return ""
    return match.group(1)


def is_retro_pr(pr_title: str) -> bool:
    """True if the PR is itself a retrospective (skip to avoid recursion).

    Matches in two ways: (a) title starts with ``retro(`` or ``retro:``
    (case-insensitive, leading whitespace stripped); (b) the title's
    ``type(scope)`` token literally contains ``(retro)``. The second
    branch covers retro-closing PRs like ``docs(retro): ...`` that the
    title policy forces to use a non-``retro`` Conventional Commit type.
    """
    stripped = pr_title.lstrip().lower()
    if stripped.startswith("retro(") or stripped.startswith("retro:"):
        return True
    token = extract_type_scope(stripped) or ""
    return "(retro)" in token


def should_skip(
    pr: MergedPR, trusted_bots: frozenset[str] = _TRUSTED_BOT_LOGINS
) -> tuple[bool, str]:
    """Return ``(skip, reason)``. Empty *reason* when not skipping."""
    if pr.merged_by_login is not None and pr.merged_by_login in trusted_bots:
        return True, f"merged by trusted bot ({pr.merged_by_login})"
    if pr.user_login is not None and pr.user_login in trusted_bots:
        return True, f"authored by trusted bot ({pr.user_login})"
    if is_retro_pr(pr.title):
        return True, "PR is itself a retrospective (avoid recursion)"
    return False, ""


def compute_repair_signals(
    pr: MergedPR, has_inline_comments: bool
) -> dict[str, bool]:
    """Return a dict of `signal_name -> fired` describing observable repair
    evidence on the merged PR. Used by :func:`run` to decide whether to open
    a retrospective issue.

    Each signal is independently weak; their logical OR is the gate. The
    historical signal (`has_inline_comments`) is retained verbatim; the
    remaining heuristics catch repair loops captured outside the PR's
    review thread -- in sibling issues, in fix-typed titles, or in
    fix-up commits squashed at merge. See issue #298 for the reproducer:
    PR #275 and PR #288 merged with zero inline review comments yet
    carried substantial repair history in issues #287 and #273.

    Signals returned:

    - ``inline_review_comments``: at least one comment on the PR's
      review thread (the legacy gate).
    - ``body_cites_refs``: PR body has at least one line-anchored
      ``Refs|Closes|Fixes|Resolves #N``. Reuses
      :func:`issue_link.extract_refs`.
    - ``fix_typed_title``: PR title starts with ``fix(`` (Conventional
      Commit `fix` type).
    - ``multi_commit_pr``: source branch had more than one commit before
      the merge (squash-merge collapses these but the commit count is
      still reported on the closed event payload).
    """
    body_without_comments = strip_html_comments(pr.body or "")
    refs = extract_refs(body_without_comments)
    fix_typed = pr.title.lstrip().lower().startswith("fix(")
    return {
        "inline_review_comments": bool(has_inline_comments),
        "body_cites_refs": len(refs) > 0,
        "fix_typed_title": fix_typed,
        "multi_commit_pr": pr.commits > 1,
    }


def render_repair_signals(signals: dict[str, bool]) -> str:
    """Render a one-line summary of the signal aggregate for log/summary use."""
    return ", ".join(f"{name}={str(fired).lower()}" for name, fired in signals.items())


def build_retro_title(pr: MergedPR) -> str:
    """``retro(<type>): review PR #<N> repair loops``.

    Strips the optional ``(scope)`` from the source ``type(scope)`` token
    to keep the generated title at a single nesting level. Without this,
    a source PR titled ``docs(retro): ...`` would produce
    ``retro(docs(retro)): ...`` -- nested parens that break the
    Conventional Commit shape of the auto-opened retro title.
    """
    token = extract_type_scope(pr.title) or FALLBACK_TYPE_SCOPE
    type_only = token.split("(", 1)[0]
    return f"retro({type_only}): review PR #{pr.number} repair loops"


def build_retro_body(pr: MergedPR, commit_subjects: list[str]) -> str:
    """Return the markdown body. Contains every section in :data:`_REQUIRED_SECTIONS`."""
    type_scope = extract_type_scope(pr.title)
    fallback_note = ""
    if not type_scope:
        fallback_note = (
            "\n- Note: source PR title did not parse as a Conventional "
            "Commit-style `type(scope): subject`; retro title falls back to "
            f"`{FALLBACK_TYPE_SCOPE}`.\n"
        )
    layer_str = (
        ", ".join(pr.layer_labels) if pr.layer_labels else "(none on source PR)"
    )
    commits_block = (
        "\n".join(f"  - {subj}" for subj in commit_subjects)
        if commit_subjects
        else "  - (no commit subjects fetched)"
    )
    return (
        "## Scope\n"
        "\n"
        f"Retrospective for merged PR #{pr.number} (`{pr.title}`). "
        "Review repair-free merge reproducibility per CLAUDE.md section 3: "
        "list every repair required between PR open and merge; identify the "
        "earliest deterministic gate that should have prevented each repair; "
        "and state how the next run will reproduce the no-repair path.\n"
        "\n"
        "## Facts\n"
        "\n"
        f"- Source PR: #{pr.number} -- {pr.title}\n"
        f"- Source PR URL: {pr.html_url}\n"
        f"- Merged at (UTC): {pr.merged_at}\n"
        f"- Merged by: {pr.merged_by_login or '(unknown)'}\n"
        f"- Source PR author: {pr.user_login or '(unknown)'}\n"
        f"- Layer labels inherited from source PR: {layer_str}\n"
        "- Commit subjects in PR (repair-history candidates):\n"
        f"{commits_block}\n"
        f"{fallback_note}"
        "\n"
        "## Proposed work\n"
        "\n"
        "1. Repair history -- list every reviewer / CI / hook repair "
        "between PR open and merge as a table "
        "`| # | Repair | What the reviewer caught |`.\n"
        "2. Classification -- tag each repair with one of: "
        "`missing deterministic gate` / `unclear agent instruction` / "
        "`external or human decision that cannot be automated`.\n"
        "3. Earliest prevention point -- per repair, name the "
        "deterministic gate that should have caught it (workflow, hook, "
        "ruleset, label, preflight).\n"
        "4. No-repair reproduction path -- numbered steps the next "
        "similar PR should follow to land in one shot.\n"
        "5. `## Follow-up issues` -- list deferred gates as "
        "`- [ ] type(scope): <title> -- <rationale>` so a future "
        "extractor (issue #234 Part 2) can convert them into sub-issues.\n"
        "\n"
        "## Verification\n"
        "\n"
        "- Every repair in the table has a classification from the "
        "section 3 taxonomy.\n"
        "- Every repair has a named earliest prevention point.\n"
        "- The no-repair reproduction path matches what would happen if "
        "the deterministic gates from this retrospective were in place.\n"
        "- The `## Follow-up issues` section (if any) is machine-parseable "
        "per the bullet convention above.\n"
        "\n"
        "## Acceptance criteria\n"
        "\n"
        "- [ ] Repair history table complete.\n"
        "- [ ] Each repair classified with the section 3 taxonomy.\n"
        "- [ ] Each repair has an earliest prevention point.\n"
        "- [ ] No-repair reproduction path stated.\n"
        "- [ ] `## Follow-up issues` filed (or explicitly stated `(none)`).\n"
        "\n"
        "## Parent\n"
        "\n"
        "Refs CLAUDE.md section 3 (\"After each merge, auto-open a "
        f"retrospective issue\"). Source PR: #{pr.number}.\n"
        "\n"
        "_Opened automatically by `.github/workflows/auto-retro.yml`._\n"
    )


def find_existing_retro(
    search_items: list[dict[str, Any]], pr_number: int
) -> int | None:
    """Return the matching retro issue number from search results, or None.

    Match heuristic: title begins with ``retro(`` or ``retro:`` (case-
    insensitive after lstrip) AND contains ``PR #<N>`` not followed by
    another digit. The trailing ``(?!\\d)`` lookahead prevents PR-number
    prefix collisions (e.g. a lookup for #249 must not match a retro for
    #2490). The prefix guard avoids matching an unrelated retro that
    happens to share a type-scope token.
    """
    needle = re.compile(rf"PR #{pr_number}(?!\d)")
    for item in search_items:
        title = item.get("title") or ""
        stripped = title.lstrip().lower()
        if not (stripped.startswith("retro(") or stripped.startswith("retro:")):
            continue
        if needle.search(title):
            return item.get("number")
    return None


def issue_labels(layer_labels: tuple[str, ...]) -> list[str]:
    """Return the label list for the retro issue.

    Always ``type:docs`` + ``layer:meta``; appends any additional
    ``layer:*`` labels inherited from the source PR. Deduplicates while
    preserving order.
    """
    labels = ["type:docs", "layer:meta"]
    for lbl in layer_labels:
        if lbl and lbl not in labels:
            labels.append(lbl)
    return labels


# ---------------------------------------------------------------------------
# Side-effecting boundary -- mocked in tests
# ---------------------------------------------------------------------------


def gh_api(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    *,
    timeout: int = 30,
) -> str:
    """Thin wrapper around ``gh api``. Returns stdout text.

    Raises :class:`subprocess.CalledProcessError` on any non-zero exit
    so the orchestrator fails loudly (CLAUDE.md section 4).
    """
    cmd = ["gh", "api", "--method", method, path]
    if json_body is not None:
        result = subprocess.run(
            [*cmd, "--input", "-"],
            input=json.dumps(json_body),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    else:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    return result.stdout


def fetch_pr_commits(repo: str, pr_number: int) -> list[str]:
    """Return commit subjects (first line of each message) for the PR."""
    raw = gh_api("GET", f"/repos/{repo}/pulls/{pr_number}/commits?per_page=100")
    commits = json.loads(raw) if raw.strip() else []
    subjects: list[str] = []
    for entry in commits:
        message = ((entry.get("commit") or {}).get("message") or "")
        subjects.append(message.split("\n", 1)[0].strip())
    return subjects


def search_retro_issues(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Search open + closed issues for an existing retro referencing pr_number."""
    query = f'repo:{repo} type:issue in:title "PR #{pr_number}" "retro"'
    encoded = quote(query, safe="")
    raw = gh_api("GET", f"/search/issues?q={encoded}&per_page=50")
    data = json.loads(raw) if raw.strip() else {}
    return list(data.get("items") or [])


def has_review_comments(repo: str, pr_number: int) -> bool:
    """True iff the PR has at least one inline review (diff) comment.

    Used as a zero-repair signal: an empty list from
    ``/repos/{repo}/pulls/{pr_number}/comments`` means no reviewer left
    an inline comment, so the merge has no observable repair history to
    record. The orchestrator (:func:`run`) treats any exception from
    this call as fail-safe (proceeds to open the retro) so a transient
    API error never silently swallows the audit trail.
    """
    raw = gh_api(
        "GET", f"/repos/{repo}/pulls/{pr_number}/comments?per_page=1"
    )
    items = json.loads(raw) if raw.strip() else []
    return bool(items)


def create_issue(
    repo: str, title: str, body: str, labels: list[str]
) -> dict[str, Any]:
    """POST /repos/{repo}/issues and return the parsed response."""
    raw = gh_api(
        "POST",
        f"/repos/{repo}/issues",
        {"title": title, "body": body, "labels": labels},
    )
    return json.loads(raw) if raw.strip() else {}


# ---------------------------------------------------------------------------
# Orchestrator + CLI
# ---------------------------------------------------------------------------


def _append_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as fp:
        fp.write(text)


def _build_summary(pr: MergedPR, action: str, detail: str) -> str:
    return (
        "## auto-retro summary\n"
        "\n"
        "| Field | Value |\n"
        "|---|---|\n"
        f"| Source PR | #{pr.number} |\n"
        f"| Source PR title | `{pr.title}` |\n"
        f"| Merged at | {pr.merged_at} |\n"
        f"| Action | `{action}` |\n"
        f"| Detail | {detail} |\n"
    )


def run(event: dict[str, Any], repo: str) -> int:
    """Top-level orchestrator. Returns process exit code."""
    pr = parse_event(event)

    if not pr.merged:
        msg = f"PR #{pr.number} is not merged"
        print(f"skip: {msg}")
        _append_summary(_build_summary(pr, "skip", msg))
        return 0

    skip, reason = should_skip(pr)
    if skip:
        print(f"skip: {reason}")
        _append_summary(_build_summary(pr, "skip", reason))
        return 0

    existing_items = search_retro_issues(repo, pr.number)
    existing = find_existing_retro(existing_items, pr.number)
    if existing is not None:
        msg = f"existing retro issue #{existing} for PR #{pr.number}"
        print(f"skip: {msg}")
        _append_summary(_build_summary(pr, "skip", msg))
        return 0

    try:
        has_inline_comments = has_review_comments(repo, pr.number)
    except subprocess.CalledProcessError as exc:
        # Fail-safe: a transient comments-endpoint failure must NOT
        # silently swallow the retro creation. Surface the warning and
        # proceed as if comments were present.
        print(
            f"::warning::has_review_comments failed "
            f"(exit {exc.returncode}); proceeding to open retro",
            file=sys.stderr,
        )
        has_inline_comments = True

    signals = compute_repair_signals(pr, has_inline_comments)
    signal_summary = render_repair_signals(signals)
    if not any(signals.values()):
        msg = f"no repair signal fired ({signal_summary})"
        print(f"skip: {msg}")
        _append_summary(_build_summary(pr, "skip", msg))
        return 0

    commit_subjects = fetch_pr_commits(repo, pr.number)
    title = build_retro_title(pr)
    body = build_retro_body(pr, commit_subjects)
    labels = issue_labels(pr.layer_labels)

    created = create_issue(repo, title, body, labels)
    new_number = created.get("number")
    new_url = created.get("html_url") or ""
    msg = f"created retro issue #{new_number} ({new_url})"
    print(msg)
    _append_summary(_build_summary(pr, "created", msg))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    event_path = args.event_file or os.environ.get("GITHUB_EVENT_PATH")
    repo = (
        args.repo or os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY")
    )

    if not event_path:
        print(
            "::error::missing --event-file / $GITHUB_EVENT_PATH", file=sys.stderr
        )
        return 1
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY", file=sys.stderr
        )
        return 1

    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"::error::cannot read event file {event_path}: {exc}",
            file=sys.stderr,
        )
        return 1

    return run(event, repo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser(
        "run", help="Open a retrospective issue for a merged pull request."
    )
    p_run.add_argument(
        "--event-file", help="Override $GITHUB_EVENT_PATH (for tests)."
    )
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
