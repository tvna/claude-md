#!/usr/bin/env python3
"""Ruleset drift detection helpers (invoked from .github/workflows/weekly-maintenance.yml).

Pure functions classify SoT-vs-live rulesets and render the Markdown bodies that
the workflow uses for `$GITHUB_STEP_SUMMARY` and `gh issue create --body-file`.
Side-effect wrappers (HTTP GETs against the rulesets API, and `gh issue create`)
take injectable boundaries so the CLI is fully unit-testable.

See #126 (refactor) and #30 / #116 (origin) for context. #1004 added
server-default parameter normalization and canonical rule-list ordering to the
projection (superseding the #30 / #116 "preserve raw rule order" decision, which
predated the evidence that GitHub re-orders rules on PUT -- see #1036), and the
`reconcile` rolling-issue dedup / auto-close replacing the per-run flood
(#998 / #1000 / #1002).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from _github_api import API_VERSION

API_ROOT = "https://api.github.com"
SOT_PROJECTION_KEYS = ("name", "target", "enforcement", "conditions", "bypass_actors", "rules")
ISSUE_LABELS = ("layer:meta", "type:fix")

# Stable rolling-issue titles (#1004): ONE open issue per kind, date in the body
# (not the title), so recurring drift updates one issue instead of stacking
# duplicates (#998/#1000/#1002). Still satisfies `type(scope): summary`.
SOT_ISSUE_TITLE = "fix(ruleset-drift): SoT vs live drift detected"
UNKNOWN_ISSUE_TITLE = "fix(ruleset-drift): unknown ruleset detected"

# Body marker carrying the drift-content hash; reconcile diffs it against the open
# issue to tell changed drift (comment) from re-observed (silent).
HASH_MARKER_PREFIX = "<!-- ruleset-drift-hash: "
HASH_MARKER_SUFFIX = " -->"
ReconcileAction = Literal["create", "append", "silent", "close"]

# ASCII close comments posted when a rolling issue's drift/unknown clears (#1004).
SOT_RESOLVED_COMMENT = (
    "Auto-closed by ruleset-drift: the latest run found no SoT-vs-live drift. "
    "If drift recurs the weekly job reopens a fresh rolling issue.\n"
)
UNKNOWN_RESOLVED_COMMENT = (
    "Auto-closed by ruleset-drift: the latest run found no unknown live "
    "rulesets. If one reappears the weekly job reopens a fresh rolling issue.\n"
)

# Documented GitHub server-populated rule parameters, keyed by rule type (#1004).
# GitHub echoes these onto the live ruleset even when the SoT file omits them,
# which produced non-convergent false-positive drift (#998 / #1000 / #1002).
# A parameter is stripped only when its value equals the documented default, so a
# live value that diverges from the default still surfaces as genuine drift.
# Extend this map (with the documented default) when a new server-default
# parameter is observed; do not strip keys whose default is unknown.
SERVER_DEFAULT_PARAMETERS: dict[str, dict[str, Any]] = {
    "pull_request": {"required_reviewers": []},
    "required_status_checks": {"do_not_enforce_on_create": False},
}
DEFAULT_SOT_FILES = ("main.json", "all-branches.json")


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def _normalize_rule(rule: Any) -> Any:
    """Strip server-default parameters from a single rule (#1004).

    Returns non-dict input unchanged. Removes a parameter only when its value
    equals the documented default for the rule's ``type``; a parameter whose
    value diverges from the default is preserved so real drift still surfaces.
    A ``parameters`` object that becomes empty after pruning is dropped so the
    rule matches the bare ``{"type": ...}`` shape the SoT files use. The input
    rule is not mutated.
    """
    if not isinstance(rule, dict):
        return rule
    rule_type = rule.get("type")
    defaults = SERVER_DEFAULT_PARAMETERS.get(rule_type, {}) if isinstance(rule_type, str) else {}
    params = rule.get("parameters")
    if not defaults or not isinstance(params, dict):
        return rule
    pruned = {
        key: value
        for key, value in params.items()
        if not (key in defaults and value == defaults[key])
    }
    result = dict(rule)
    if pruned:
        result["parameters"] = pruned
    else:
        result.pop("parameters", None)
    return result


def _normalize_rules(rules: Any) -> Any:
    """Prune server defaults and sort rules into a canonical order (#1004).

    Returns non-list input unchanged (mirrors jq emitting the raw value when a
    side omits ``rules``). Rules are sorted by ``(type, canonical-serialization)``
    so a reorder applied by GitHub on PUT (#1036) no longer reads as drift while
    a genuine add/remove/change still does.
    """
    if not isinstance(rules, list):
        return rules
    normalized = [_normalize_rule(rule) for rule in rules]
    normalized.sort(
        key=lambda rule: (
            str(rule.get("type", "")) if isinstance(rule, dict) else "",
            json.dumps(rule, sort_keys=True, ensure_ascii=False),
        )
    )
    return normalized


def canonical_projection(ruleset: dict[str, Any]) -> dict[str, Any]:
    """Return the subset {name, target, enforcement, conditions, bypass_actors, rules}.

    Mirrors `jq '{name, target, enforcement, conditions, bypass_actors, rules}'`.
    Missing keys are emitted as None (jq emits null for missing keys), so the
    canonical text stays comparable when one side omits an optional field. The
    ``rules`` list is normalized (server defaults pruned, canonical order) so
    server-populated fields and GitHub-applied reordering do not read as drift
    (#1004); both SoT and live pass through the same normalization.
    """
    projection = {key: ruleset.get(key) for key in SOT_PROJECTION_KEYS}
    projection["rules"] = _normalize_rules(projection["rules"])
    return projection


def canonical_json(ruleset: dict[str, Any]) -> str:
    """jq -S byte-equivalent serialization of the canonical projection.

    `jq -S` sorts object keys recursively, uses 2-space indent, emits raw UTF-8
    (no `\\uXXXX` escapes), and appends a trailing newline. `json.dumps` matches
    all of that with `sort_keys=True, indent=2, ensure_ascii=False` plus an
    explicit `+ "\\n"`.
    """
    return (
        json.dumps(
            canonical_projection(ruleset),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


def classify(sot: dict[str, Any], live_rulesets: list[dict[str, Any]]) -> dict[str, Any]:
    """Match a SoT ruleset to live rulesets by name.

    Returns ``{"status", "live_id", "match_count"}`` where status is:
      - ``"ambiguous"`` when more than one live ruleset shares the SoT name
      - ``"missing-on-live"`` when no live ruleset has that name
      - ``"matched"`` when exactly one live ruleset matches (caller resolves
        ``in-sync`` vs ``drift`` by running ``diff_canonical``).
    """
    name = sot["name"]
    matches = [r for r in live_rulesets if r.get("name") == name]
    if len(matches) > 1:
        return {"status": "ambiguous", "live_id": None, "match_count": len(matches)}
    if not matches:
        return {"status": "missing-on-live", "live_id": None, "match_count": 0}
    return {"status": "matched", "live_id": int(matches[0]["id"]), "match_count": 1}


def diff_canonical(
    *,
    sot: dict[str, Any],
    live: dict[str, Any],
    sot_path: str,
    live_path: str,
) -> str:
    """Return unified diff (live -> sot) of canonical projections.

    Empty string when the canonical projections are equal. The from/tofile
    paths surface in the diff header (`--- live_path`, `+++ sot_path`).
    """
    sot_text = canonical_json(sot)
    live_text = canonical_json(live)
    if sot_text == live_text:
        return ""
    return "".join(
        difflib.unified_diff(
            live_text.splitlines(keepends=True),
            sot_text.splitlines(keepends=True),
            fromfile=live_path,
            tofile=sot_path,
            n=3,
        )
    )


def find_unknown(
    sot_names: set[str],
    live: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return [{id, name, target, enforcement}] for live rulesets not in SoT.

    Order preserved from the input ``live`` list (matches the jq pipeline's
    array-iteration order in the original shell).
    """
    return [
        {
            "id": entry["id"],
            "name": entry["name"],
            "target": entry["target"],
            "enforcement": entry["enforcement"],
        }
        for entry in live
        if entry.get("name") not in sot_names
    ]


# ---------------------------------------------------------------------------
# Rolling-issue dedup / auto-close (#1004)
# ---------------------------------------------------------------------------

def drift_hash(content: str) -> str:
    """Short hash of the run-invariant drift signature (status rows + diffs);
    excludes run date / URL so re-observed drift hashes the same (#1004)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def embed_hash_marker(body: str, content_hash: str) -> str:
    """Append the drift-content hash marker to an issue body (#1004)."""
    marker = f"{HASH_MARKER_PREFIX}{content_hash}{HASH_MARKER_SUFFIX}"
    return f"{body}\n{marker}\n"


def extract_hash_marker(body: str) -> str | None:
    """Return the drift-content hash embedded in ``body``, or None (#1004)."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(HASH_MARKER_PREFIX) and stripped.endswith(HASH_MARKER_SUFFIX):
            return stripped[len(HASH_MARKER_PREFIX):-len(HASH_MARKER_SUFFIX)].strip()
    return None


def decide_issue_action(
    *,
    detected: bool,
    existing_issue: dict[str, Any] | None,
    content_changed: bool,
) -> ReconcileAction:
    """Decide reconcile's action (#1004): present+none->create; present+changed
    ->append; present+same->silent; resolved+issue->close; resolved+none->silent."""
    if detected:
        if existing_issue is None:
            return "create"
        return "append" if content_changed else "silent"
    if existing_issue is None:
        return "silent"
    return "close"


# ---------------------------------------------------------------------------
# Markdown renderers
# ---------------------------------------------------------------------------

def render_summary_header(*, run_date: str, run_url: str) -> str:
    return (
        f"## Ruleset drift detection -- run {run_date}\n"
        "\n"
        f"- Run: {run_url}\n"
        "\n"
        "| File | Ruleset name | Live id | Status |\n"
        "|---|---|---|---|\n"
    )


def render_sot_issue_header(*, run_date: str, run_url: str, repo: str) -> str:
    return (
        "Parent: #30\n"
        "\n"
        f"Drift detected between `.github/rulesets/*.json` (SoT) and the live rulesets returned by `GET /repos/{repo}/rulesets`.\n"
        "\n"
        f"- Run: {run_url}\n"
        f"- Detected at: {run_date}\n"
        "\n"
        "## Affected rulesets\n"
        "\n"
        "| File | Ruleset name | Live id | Status |\n"
        "|---|---|---|---|\n"
    )


def render_status_row(*, file: str, name: str, live_id: int | str, status: str) -> str:
    return f"| `{file}` | `{name}` | {live_id} | {status} |\n"


def render_diff_block(*, name: str, live_id: int, diff_text: str) -> str:
    return (
        "\n"
        f"<details><summary>Diff for <code>{name}</code> (id {live_id})</summary>\n"
        "\n"
        "```diff\n"
        f"{diff_text}"
        "```\n"
        "</details>\n"
    )


def render_sot_issue_remediation() -> str:
    return (
        "\n"
        "## Remediation\n"
        "\n"
        "Re-dispatch the `Apply rulesets` workflow with `dry_run=false` once the SoT change has been reviewed (see `docs/runbooks/rulesets.md`).\n"
    )


def render_unknown_summary_header() -> str:
    return "\n### Unknown rulesets (live but not in SoT)\n\n"


def render_unknown_table_header() -> str:
    return "| Live id | Name | Target | Enforcement |\n|---|---|---|---|\n"


def render_unknown_row(entry: dict[str, Any]) -> str:
    return f"| {entry['id']} | `{entry['name']}` | {entry['target']} | {entry['enforcement']} |\n"


def render_unknown_issue_header(*, run_date: str, run_url: str) -> str:
    return (
        "Parent: #30\n"
        "\n"
        "One or more rulesets exist live but have no corresponding file in `.github/rulesets/`.\n"
        "\n"
        f"- Run: {run_url}\n"
        f"- Detected at: {run_date}\n"
        "\n"
        "## Unknown rulesets\n"
        "\n"
        "| Live id | Name | Target | Enforcement |\n"
        "|---|---|---|---|\n"
    )


def render_unknown_issue_remediation(*, repo: str) -> str:
    return (
        "\n"
        "## Remediation\n"
        "\n"
        f"Either (a) commit the live ruleset as a new `.github/rulesets/<name>.json` SoT file, "
        f"or (b) delete it via `gh api -X DELETE /repos/{repo}/rulesets/<id>` "
        "(see `docs/runbooks/rulesets.md` §\"Rollback\").\n"
    )


# ---------------------------------------------------------------------------
# Side-effect wrappers (HTTP + subprocess) with injectable boundaries
# ---------------------------------------------------------------------------

def fetch_live_rulesets_list(
    repo: str,
    token: str,
    *,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    # API_ROOT is the constant https://api.github.com endpoint; `repo` is sourced
    # from workflow `github.repository`. opener is injectable for tests.
    request = urllib.request.Request(f"{API_ROOT}/repos/{repo}/rulesets")  # noqa: S310 -- fixed https endpoint
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", API_VERSION)
    with opener(request) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_live_ruleset(
    repo: str,
    ruleset_id: int,
    token: str,
    *,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    # API_ROOT is the constant https://api.github.com endpoint; `ruleset_id` is
    # an int narrowed upstream. opener is injectable for tests.
    request = urllib.request.Request(f"{API_ROOT}/repos/{repo}/rulesets/{ruleset_id}")  # noqa: S310 -- fixed https endpoint
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", API_VERSION)
    with opener(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _run_gh(cmd: list[str], *, runner: Callable[..., Any] = subprocess.run) -> Any:
    """Run a `gh` CLI command with the shared capture/timeout/check policy."""
    return runner(cmd, capture_output=True, text=True, timeout=30, check=True)


def file_issue(
    repo: str,
    title: str,
    body_file: Path,
    labels: tuple[str, ...] = ISSUE_LABELS,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    cmd = ["gh", "issue", "create", "--repo", repo, "--title", title,
           "--body-file", str(body_file)]
    for label in labels:
        cmd.extend(["--label", label])
    _run_gh(cmd, runner=runner)


def find_rolling_issue(
    repo: str,
    title: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any] | None:
    """Return the open issue whose title exactly equals ``title`` (#1004); the
    ``--search`` keyword match is filtered so a superstring title is not used."""
    result = _run_gh(
        ["gh", "issue", "list", "--repo", repo, "--state", "open",
         "--search", f'"{title}" in:title', "--json", "number,title"],
        runner=runner,
    )
    for issue in json.loads(result.stdout or "[]"):
        if issue.get("title") == title:
            return {"number": int(issue["number"]), "title": issue["title"]}
    return None


def fetch_issue_body(
    repo: str,
    issue_number: int,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> str:
    """Return an issue body (used to read its embedded drift hash) (#1004)."""
    result = _run_gh(
        ["gh", "issue", "view", str(issue_number), "--repo", repo,
         "--json", "body", "--jq", ".body"],
        runner=runner,
    )
    return str(result.stdout)


def comment_on_issue(
    repo: str,
    issue_number: int,
    body_file: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    """Append a comment (rolling update) to an existing issue (#1004)."""
    _run_gh(
        ["gh", "issue", "comment", str(issue_number), "--repo", repo,
         "--body-file", str(body_file)],
        runner=runner,
    )


def close_issue_with_comment(
    repo: str,
    issue_number: int,
    comment: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    """Auto-close a rolling issue with a resolution comment (#1004)."""
    _run_gh(
        ["gh", "issue", "close", str(issue_number), "--repo", repo,
         "--reason", "completed", "--comment", comment],
        runner=runner,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def detect(
    *,
    repo: str,
    sot_dir: Path,
    sot_files: tuple[str, ...],
    run_url: str,
    run_date: str,
    token: str,
    summary_file: Path,
    sot_body_file: Path,
    unknown_body_file: Path,
    list_fetcher: Callable[[str, str], list[dict[str, Any]]] | None = None,
    ruleset_fetcher: Callable[[str, int, str], dict[str, Any]] | None = None,
) -> tuple[int, int]:
    """Run the full detection pipeline, write summary + body files, return counts.

    Returns ``(drift_count, unknown_count)``. Raises ``RuntimeError`` when more
    than one live ruleset shares a SoT name (the legacy ``exit 1`` behaviour).
    """
    list_fn = list_fetcher or (lambda r, t: fetch_live_rulesets_list(r, t))
    one_fn = ruleset_fetcher or (lambda r, i, t: fetch_live_ruleset(r, i, t))

    live = list_fn(repo, token)
    sot_entries: list[tuple[str, dict[str, Any]]] = []
    sot_names: set[str] = set()
    for filename in sot_files:
        path = sot_dir / filename
        with path.open(encoding="utf-8") as handle:
            entry = json.load(handle)
        sot_entries.append((filename, entry))
        sot_names.add(entry["name"])

    summary_chunks: list[str] = [render_summary_header(run_date=run_date, run_url=run_url)]
    sot_body_chunks: list[str] = [
        render_sot_issue_header(run_date=run_date, run_url=run_url, repo=repo)
    ]
    diff_blocks: list[str] = []
    sot_rows: list[str] = []  # run-invariant rows feeding the drift hash (#1004)
    drift_count = 0

    for filename, sot_entry in sot_entries:
        name = sot_entry["name"]
        decision = classify(sot_entry, live)

        if decision["status"] == "ambiguous":
            ambiguous_row = render_status_row(
                file=filename, name=name, live_id="--", status="ambiguous"
            )
            summary_chunks.append(ambiguous_row)
            _append(summary_file, "".join(summary_chunks))
            raise RuntimeError(
                f"Multiple existing rulesets named '{name}' "
                f"({decision['match_count']}). Refusing to guess; resolve manually."
            )

        if decision["status"] == "missing-on-live":
            row = render_status_row(
                file=filename, name=name, live_id="--", status="missing-on-live"
            )
            summary_chunks.append(row)
            sot_body_chunks.append(row)
            sot_rows.append(row)
            drift_count += 1
            continue

        live_id = int(decision["live_id"])
        live_entry = one_fn(repo, live_id, token)
        diff_text = diff_canonical(
            sot=sot_entry,
            live=live_entry,
            sot_path=f".github/rulesets/{filename}",
            # live_path is a label that appears only inside the diff header
            # rendered into the drift issue body; nothing is read from or
            # written to this path.
            live_path=f"/tmp/live-{filename}",  # noqa: S108 -- diff label only, no fs access
        )
        if not diff_text:
            summary_chunks.append(
                render_status_row(file=filename, name=name, live_id=live_id, status="in-sync")
            )
            continue

        row = render_status_row(file=filename, name=name, live_id=live_id, status="drift")
        summary_chunks.append(row)
        sot_body_chunks.append(row)
        sot_rows.append(row)
        drift_count += 1
        block = render_diff_block(name=name, live_id=live_id, diff_text=diff_text)
        summary_chunks.append(block)
        diff_blocks.append(block)

    if drift_count > 0:
        sot_body_chunks.append("\n## Diffs\n")
        sot_body_chunks.extend(diff_blocks)
        sot_body_chunks.append(render_sot_issue_remediation())

    unknown = find_unknown(sot_names, live)
    summary_chunks.append(render_unknown_summary_header())
    if not unknown:
        summary_chunks.append("_None._\n")
    else:
        summary_chunks.append(render_unknown_table_header())
        summary_chunks.extend(render_unknown_row(entry) for entry in unknown)

    _write(summary_file, "".join(summary_chunks))

    if drift_count > 0:
        sot_hash = drift_hash("".join(sot_rows) + "".join(diff_blocks))
        _write(sot_body_file, embed_hash_marker("".join(sot_body_chunks), sot_hash))

    if unknown:
        unknown_chunks: list[str] = [
            render_unknown_issue_header(run_date=run_date, run_url=run_url)
        ]
        unknown_rows = [render_unknown_row(entry) for entry in unknown]
        unknown_chunks.extend(unknown_rows)
        unknown_chunks.append(render_unknown_issue_remediation(repo=repo))
        unknown_hash = drift_hash("".join(unknown_rows))
        _write(unknown_body_file, embed_hash_marker("".join(unknown_chunks), unknown_hash))

    return drift_count, len(unknown)


def reconcile(
    *,
    repo: str,
    title: str,
    detected: bool,
    body_file: Path,
    close_comment: str,
    labels: tuple[str, ...] = ISSUE_LABELS,
) -> ReconcileAction:
    """Maintain a single rolling issue for one drift kind (#1004).

    Finds the open issue by exact title, compares the rendered drift hash against
    its marker, and creates / appends / stays silent / auto-closes per
    :func:`decide_issue_action`. Always runs so a resolved drift auto-closes.
    """
    current_hash = (
        extract_hash_marker(body_file.read_text(encoding="utf-8"))
        if detected and body_file.exists()
        else None
    )
    existing = find_rolling_issue(repo, title)
    content_changed = True
    if existing is not None and current_hash is not None:
        content_changed = (
            extract_hash_marker(fetch_issue_body(repo, existing["number"])) != current_hash
        )

    action = decide_issue_action(
        detected=detected, existing_issue=existing, content_changed=content_changed
    )
    if action == "create":
        file_issue(repo, title, body_file, labels)
    elif action == "append":
        assert existing is not None  # noqa: S101 -- invariant from decide_issue_action
        comment_on_issue(repo, existing["number"], body_file)
    elif action == "close":
        assert existing is not None  # noqa: S101 -- invariant from decide_issue_action
        close_issue_with_comment(repo, existing["number"], close_comment)
    return action


# ---------------------------------------------------------------------------
# CLI handlers
# ---------------------------------------------------------------------------

def _cmd_detect(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN_API", "")
    if not token:
        print("::error::GH_TOKEN_API is not set.", file=sys.stderr)
        return 1

    run_date = args.run_date or _utc_today()
    sot_files = tuple(args.sot_files) if args.sot_files else DEFAULT_SOT_FILES
    drift_count, unknown_count = detect(
        repo=args.repo,
        sot_dir=args.sot_dir,
        sot_files=sot_files,
        run_url=args.run_url,
        run_date=run_date,
        token=token,
        summary_file=args.summary_file,
        sot_body_file=args.sot_body_file,
        unknown_body_file=args.unknown_body_file,
    )

    print(f"run_date={run_date}")
    print(f"drift_count={drift_count}")
    print(f"unknown_count={unknown_count}")
    return 0


_RECONCILE_KINDS: dict[str, tuple[str, str]] = {
    "sot": (SOT_ISSUE_TITLE, SOT_RESOLVED_COMMENT),
    "unknown": (UNKNOWN_ISSUE_TITLE, UNKNOWN_RESOLVED_COMMENT),
}


def _parse_detected(raw: str) -> bool:
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"Invalid --detected value (expected true|false): {raw}")


def _cmd_reconcile(args: argparse.Namespace) -> int:
    title, close_comment = _RECONCILE_KINDS[args.kind]
    action = reconcile(
        repo=args.repo,
        title=title,
        detected=_parse_detected(args.detected),
        body_file=Path(args.body_file),
        close_comment=close_comment,
    )
    print(f"action={action}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_detect = sub.add_parser(
        "detect",
        help="Detect SoT-vs-live drift and unknown live rulesets.",
    )
    p_detect.add_argument("--repo", required=True)
    p_detect.add_argument("--sot-dir", type=Path, default=Path(".github/rulesets"))
    p_detect.add_argument(
        "--sot-file",
        dest="sot_files",
        action="append",
        default=None,
        help=(
            "Repeatable. Defaults to main.json + all-branches.json "
            "when omitted."
        ),
    )
    p_detect.add_argument("--run-url", required=True)
    p_detect.add_argument(
        "--run-date",
        default="",
        help="UTC date string; defaults to today (YYYY-MM-DD).",
    )
    p_detect.add_argument(
        "--summary-file",
        type=Path,
        default=Path(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")),
    )
    p_detect.add_argument(
        "--sot-body-file",
        type=Path,
        # CLI default for the detect subcommand. The workflow always passes an
        # explicit --sot-body-file under the runner home directory; this default
        # is for local one-shot debugging on a single-tenant runner.
        default=Path("/tmp/drift-sot-issue.md"),  # noqa: S108 -- workflow-supplied override expected in CI
    )
    p_detect.add_argument(
        "--unknown-body-file",
        type=Path,
        default=Path("/tmp/drift-unknown-issue.md"),  # noqa: S108 -- workflow-supplied override expected in CI
    )
    p_detect.set_defaults(func=_cmd_detect)

    p_reconcile = sub.add_parser(
        "reconcile",
        help=(
            "Maintain the single rolling drift/unknown issue: create, update "
            "(comment), stay silent, or auto-close based on the latest run."
        ),
    )
    p_reconcile.add_argument("--repo", required=True)
    p_reconcile.add_argument("--kind", required=True, choices=sorted(_RECONCILE_KINDS))
    p_reconcile.add_argument(
        "--detected",
        required=True,
        help="true when this kind was detected on the latest run, else false.",
    )
    p_reconcile.add_argument("--body-file", required=True)
    p_reconcile.set_defaults(func=_cmd_reconcile)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError,
            subprocess.CalledProcessError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


def _utc_today() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(content)


def _append(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


if __name__ == "__main__":
    raise SystemExit(main())
