#!/usr/bin/env python3
"""Plan and apply repository rulesets from checked-in source-of-truth JSON.

This module keeps the mutating ``apply-rulesets`` workflow thin while leaving
the decision logic unit-testable. It intentionally uses the standard library
``urllib.request`` boundary so tests can inject a fake opener.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

API_VERSION = "2022-11-28"
API_ROOT = "https://api.github.com"
PROJECTION_KEYS = (
    "name",
    "target",
    "enforcement",
    "conditions",
    "bypass_actors",
    "rules",
)
TARGETS = {
    "all-branches": ["all-branches.json"],
    "dependabot": ["dependabot.json"],
    "main": ["main.json"],
    "all": ["all-branches.json", "dependabot.json", "main.json"],
}


def select_targets(
    choice: Literal["all-branches", "dependabot", "main", "all"],
) -> list[str]:
    try:
        return list(TARGETS[choice])
    except KeyError as exc:
        raise ValueError(f"Unknown ruleset input: {choice}") from exc


def decide_action(sot_name: str, live: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [item for item in live if item.get("name") == sot_name]
    if len(matches) == 0:
        return {"action": "POST", "live_id": None, "match_count": 0}
    if len(matches) == 1:
        return {
            "action": "PUT",
            "live_id": matches[0].get("id"),
            "match_count": 1,
        }
    return {
        "action": "ambiguous",
        "live_id": None,
        "match_count": len(matches),
    }


def canonical_projection(ruleset: dict[str, Any]) -> dict[str, Any]:
    return {key: ruleset.get(key) for key in PROJECTION_KEYS}


def render_diff_section(
    name: str,
    live_id: int,
    live: dict[str, Any],
    sot: dict[str, Any],
) -> str:
    live_text = _canonical_json_lines(canonical_projection(live))
    sot_text = _canonical_json_lines(canonical_projection(sot))
    diff = "".join(
        difflib.unified_diff(
            live_text,
            sot_text,
            fromfile="live",
            tofile="sot",
        )
    )
    return "\n".join(
        [
            "",
            f"<details><summary>Diff for <code>{name}</code> "
            f"(id {live_id})</summary>",
            "",
            "```diff",
            diff,
            "```",
            "</details>",
        ]
    )


def render_summary_row(
    file: str,
    name: str,
    matches: int,
    action: str,
    live_id: str | int | None,
) -> str:
    result_id = "\u2014" if live_id in (None, "") else str(live_id)
    return f"| {file} | {name} | {matches} | {action} | {result_id} |"


def fetch_live_rulesets(
    repo: str,
    token: str,
    *,
    opener=urllib.request.urlopen,
) -> list[dict[str, Any]]:
    body = _request_json(
        f"{API_ROOT}/repos/{repo}/rulesets",
        token=token,
        opener=opener,
    )
    if not isinstance(body, list):
        raise ValueError("GET /rulesets returned non-list JSON")
    return body


def fetch_live_ruleset(
    repo: str,
    ruleset_id: int,
    token: str,
    *,
    opener=urllib.request.urlopen,
) -> dict[str, Any]:
    body = _request_json(
        f"{API_ROOT}/repos/{repo}/rulesets/{ruleset_id}",
        token=token,
        opener=opener,
    )
    if not isinstance(body, dict):
        raise ValueError(f"ruleset {ruleset_id} returned non-object JSON")
    return body


def apply_call(
    *,
    method: str,
    url: str,
    payload_path: Path | None,
    token: str,
    opener=urllib.request.urlopen,
    sleeper=time.sleep,
) -> tuple[int, str]:
    payload = payload_path.read_bytes() if payload_path is not None else None
    final_code = 0
    final_body = ""
    for attempt in range(1, 4):
        code, body = _request(
            url,
            token=token,
            method=method,
            data=payload,
            opener=opener,
        )
        final_code, final_body = code, body
        if 200 <= code < 300:
            return code, body
        display_code = _display_http_code(code)
        print(f"Attempt {attempt}: HTTP {display_code} for {method} {url}")
        if code != 0 and code < 500:
            return code, body
        if attempt < 3:
            sleeper(attempt * 5)
    return final_code, final_body


def get_repo_setting(
    repo: str,
    key: str,
    token: str,
    *,
    opener=urllib.request.urlopen,
) -> Any:
    body = _request_json(f"{API_ROOT}/repos/{repo}", token=token, opener=opener)
    if not isinstance(body, dict):
        raise ValueError(f"GET /repos/{repo} returned non-object JSON")
    return body.get(key)


def patch_repo_setting(
    repo: str,
    payload: dict[str, Any],
    token: str,
    *,
    opener=urllib.request.urlopen,
) -> None:
    code, body = _request(
        f"{API_ROOT}/repos/{repo}",
        token=token,
        method="PATCH",
        data=json.dumps(payload).encode("utf-8"),
        opener=opener,
    )
    if not 200 <= code < 300:
        raise RuntimeError(
            f"Failed to patch repository setting (HTTP "
            f"{_display_http_code(code)}): {body}"
        )


def render_dispatch_header(
    *,
    choice: str,
    dry_run: bool,
    enable_auto_delete: bool,
) -> str:
    return "\n".join(
        [
            "## Apply rulesets \u2014 dispatch summary",
            "",
            f"- ruleset: `{choice}`",
            f"- dry_run: `{str(dry_run).lower()}`",
            f"- enable_auto_delete: `{str(enable_auto_delete).lower()}`",
            "",
            "| File | Ruleset name | Matches | Action | Result id |",
            "|---|---|---|---|---|",
        ]
    )


def plan_rulesets(
    *,
    repo: str,
    sot_dir: Path,
    choice: str,
    summary_file: Path,
    token: str,
    dry_run: bool,
    enable_auto_delete: bool,
    opener=urllib.request.urlopen,
) -> list[dict[str, Any]]:
    targets = select_targets(choice)  # type: ignore[arg-type]
    live_rulesets = fetch_live_rulesets(repo, token, opener=opener)
    rows: list[str] = [_dispatch_header_for(choice, dry_run, enable_auto_delete)]
    planned: list[dict[str, Any]] = []

    for file in targets:
        item, detail_rows = _plan_one_ruleset(
            file=file,
            repo=repo,
            sot_dir=sot_dir,
            live_rulesets=live_rulesets,
            token=token,
            opener=opener,
            pending_rows=rows,
            summary_file=summary_file,
        )
        rows.extend(detail_rows)
        if dry_run:
            rows.append(
                render_summary_row(
                    file,
                    str(item["name"]),
                    int(item["matches"]),
                    f"plan-only ({item['action']})",
                    item["live_id"],
                )
            )
        planned.append(item)

    _append_summary(summary_file, rows)
    return planned


def apply_rulesets(
    *,
    repo: str,
    sot_dir: Path,
    choice: str,
    summary_file: Path,
    token: str,
    enable_auto_delete: bool,
    opener=urllib.request.urlopen,
    sleeper=time.sleep,
) -> None:
    targets = select_targets(choice)  # type: ignore[arg-type]
    live_rulesets = fetch_live_rulesets(repo, token, opener=opener)
    _append_summary(
        summary_file,
        [_dispatch_header_for(choice, False, enable_auto_delete)],
    )
    for file in targets:
        item, detail_rows = _plan_one_ruleset(
            file=file,
            repo=repo,
            sot_dir=sot_dir,
            live_rulesets=live_rulesets,
            token=token,
            opener=opener,
            pending_rows=[],
            summary_file=summary_file,
        )
        if detail_rows:
            _append_summary(summary_file, detail_rows)
        action = str(item["action"])
        url = f"{API_ROOT}/repos/{repo}/rulesets"
        if action == "PUT":
            url = f"{url}/{item['live_id']}"
        code, body = apply_call(
            method=action,
            url=url,
            payload_path=item["path"],
            token=token,
            opener=opener,
            sleeper=sleeper,
        )
        if not 200 <= code < 300:
            display_code = _display_http_code(code)
            _append_summary(
                summary_file,
                [
                    "",
                    f"**Error applying {item['file']} (HTTP {display_code}):**",
                    "```",
                    body,
                    "```",
                ],
            )
            print(
                f"::error::Failed to {action} {item['file']} "
                f"(last HTTP {display_code})."
            )
            raise SystemExit(1)
        response = json.loads(body or "{}")
        _append_summary(
            summary_file,
            [
                render_summary_row(
                    str(item["file"]),
                    str(item["name"]),
                    int(item["matches"]),
                    f"{action} applied",
                    response.get("id"),
                )
            ],
        )


def auto_delete(
    *,
    repo: str,
    dry_run: bool,
    summary_file: Path,
    token: str,
    opener=urllib.request.urlopen,
) -> None:
    before = get_repo_setting(
        repo, "delete_branch_on_merge", token, opener=opener
    )
    if dry_run:
        _append_summary(
            summary_file,
            [
                "",
                "### Repository setting: `delete_branch_on_merge` (dry-run)",
                f"- Current: `{_json_scalar(before)}`",
                "- Planned: PATCH to `true`",
            ],
        )
        return

    patch_repo_setting(
        repo,
        {"delete_branch_on_merge": True},
        token,
        opener=opener,
    )
    after = get_repo_setting(repo, "delete_branch_on_merge", token, opener=opener)
    _append_summary(
        summary_file,
        [
            "",
            "### Repository setting: `delete_branch_on_merge`",
            f"- Before: `{_json_scalar(before)}`",
            f"- After: `{_json_scalar(after)}`",
        ],
    )


def _dispatch_header_for(
    choice: str,
    dry_run: bool,
    enable_auto_delete: bool,
) -> str:
    return render_dispatch_header(
        choice=choice,
        dry_run=dry_run,
        enable_auto_delete=enable_auto_delete,
    )


def _plan_one_ruleset(
    *,
    file: str,
    repo: str,
    sot_dir: Path,
    live_rulesets: list[dict[str, Any]],
    token: str,
    opener,
    pending_rows: list[str],
    summary_file: Path,
) -> tuple[dict[str, Any], list[str]]:
    path = sot_dir / file
    sot = _read_json_file(path)
    name = str(sot["name"])
    decision = decide_action(name, live_rulesets)
    match_count = int(decision["match_count"])
    action = str(decision["action"])
    live_id = decision["live_id"]

    if action == "ambiguous":
        pending_rows.append(render_summary_row(file, name, match_count, "abort", None))
        _append_summary(summary_file, pending_rows)
        print(
            f"::error::Multiple existing rulesets named '{name}' "
            f"({match_count}). Refusing to guess; resolve manually."
        )
        raise SystemExit(1)

    rows = []
    if action == "PUT":
        live = fetch_live_ruleset(repo, int(live_id), token, opener=opener)
        rows.append(render_diff_section(name, int(live_id), live, sot))

    return (
        {
            "file": file,
            "path": path,
            "name": name,
            "matches": match_count,
            "action": action,
            "live_id": live_id,
        },
        rows,
    )


def _canonical_json_lines(value: dict[str, Any]) -> list[str]:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    return text.splitlines(keepends=True)


def _read_json_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fp:
        body = json.load(fp)
    if not isinstance(body, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return body


def _append_summary(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        for line in lines:
            fp.write(line)
            fp.write("\n")


def _request_json(
    url: str,
    *,
    token: str,
    opener=urllib.request.urlopen,
) -> Any:
    code, body = _request(url, token=token, method="GET", opener=opener)
    if not 200 <= code < 300:
        raise RuntimeError(
            f"GET {url} failed (HTTP {_display_http_code(code)}): {body}"
        )
    return json.loads(body)


def _request(
    url: str,
    *,
    token: str,
    method: str,
    data: bytes | None = None,
    opener=urllib.request.urlopen,
) -> tuple[int, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        response = opener(request)
        return _response_status(response), _response_body(response)
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, str(exc.reason)


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None) or getattr(response, "code", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    return int(status)


def _response_body(response: Any) -> str:
    try:
        data = response.read()
    finally:
        close = getattr(response, "close", None)
        if close is not None:
            close()
    return data.decode("utf-8", errors="replace")


def _display_http_code(code: int) -> str:
    return "000" if code == 0 else str(code)


def _json_scalar(value: Any) -> str:
    return json.dumps(value)


def _env_token() -> str:
    import os

    token = os.environ.get("GH_TOKEN")
    if not token:
        print(
            '::error::RULESETS_PAT secret is not set. See docs/rulesets.md '
            '"Required secret".'
        )
        raise SystemExit(1)
    return token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", required=True)
    common.add_argument("--summary-file", required=True, type=Path)

    ruleset_common = argparse.ArgumentParser(add_help=False)
    ruleset_common.add_argument("--sot-dir", required=True, type=Path)
    ruleset_common.add_argument("--choice", required=True)
    ruleset_common.add_argument(
        "--enable-auto-delete",
        choices=("true", "false"),
        default="false",
        help="Render the dispatch input state in the summary header.",
    )

    plan = sub.add_parser("plan", parents=[common, ruleset_common])
    plan.set_defaults(func=_cmd_plan)

    apply = sub.add_parser("apply", parents=[common, ruleset_common])
    apply.set_defaults(func=_cmd_apply)

    auto = sub.add_parser("auto-delete", parents=[common])
    auto.add_argument("--dry-run", required=True, choices=("true", "false"))
    auto.set_defaults(func=_cmd_auto_delete)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        print(f"::error::{exc}")
        return 1
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _cmd_plan(args: argparse.Namespace) -> None:
    plan_rulesets(
        repo=args.repo,
        sot_dir=args.sot_dir,
        choice=args.choice,
        summary_file=args.summary_file,
        token=_env_token(),
        dry_run=True,
        enable_auto_delete=args.enable_auto_delete == "true",
    )


def _cmd_apply(args: argparse.Namespace) -> None:
    apply_rulesets(
        repo=args.repo,
        sot_dir=args.sot_dir,
        choice=args.choice,
        summary_file=args.summary_file,
        token=_env_token(),
        enable_auto_delete=args.enable_auto_delete == "true",
    )


def _cmd_auto_delete(args: argparse.Namespace) -> None:
    auto_delete(
        repo=args.repo,
        dry_run=args.dry_run == "true",
        summary_file=args.summary_file,
        token=_env_token(),
    )


if __name__ == "__main__":
    sys.exit(main())
