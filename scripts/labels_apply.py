from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from _github_api import API_VERSION
from _github_api import apply_call as github_apply_call

HEX_COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$")
API_ROOT = "https://api.github.com"


def validate_sot(sot: list[dict[str, Any]]) -> None:
    if not isinstance(sot, list):
        raise ValueError("labels SoT must be a JSON array")
    for entry in sot:
        name = entry.get("name") if isinstance(entry, dict) else None
        display_name = name if isinstance(name, str) and name else "<missing>"
        if not isinstance(name, str) or not name:
            raise ValueError("label <missing>: name must be a non-empty string")
        color = entry.get("color")
        if not isinstance(color, str) or not HEX_COLOR_RE.fullmatch(color):
            raise ValueError(f"label {display_name}: color must be a 6-character hex string")
        description = entry.get("description")
        if not isinstance(description, str):
            raise ValueError(f"label {display_name}: description must be a string")
        if len(description) > 100:
            raise ValueError(f"label {display_name}: description must be <=100 characters")


def decide_label_action(
    *,
    sot_entry: dict[str, Any],
    live_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    name = str(sot_entry["name"])
    color = str(sot_entry["color"])
    description = str(sot_entry["description"])
    if live_entry is None:
        return {
            "action": "POST",
            "method": "POST",
            "url_suffix": "/labels",
            "payload": {"name": name, "color": color, "description": description},
            "color_changed": False,
            "desc_changed": False,
        }

    color_changed = live_entry.get("color") != color
    desc_changed = (live_entry.get("description") or "") != description
    if not color_changed and not desc_changed:
        return {
            "action": "NOOP",
            "method": "",
            "url_suffix": "",
            "payload": None,
            "color_changed": False,
            "desc_changed": False,
        }

    return {
        "action": "PATCH",
        "method": "PATCH",
        "url_suffix": f"/labels/{urllib.parse.quote(name, safe='')}",
        "payload": {"color": color, "description": description},
        "color_changed": color_changed,
        "desc_changed": desc_changed,
    }


def decide_prune_action(
    *,
    live_name: str,
    in_sot: bool,
    prune: bool,
    dry_run: bool,
) -> Literal["skip", "report", "plan-delete", "delete"]:
    _ = live_name
    if in_sot:
        return "skip"
    if not prune:
        return "report"
    if dry_run:
        return "plan-delete"
    return "delete"


def render_action_row(name: str, action: str, color_changed: str, desc_changed: str, result: str) -> str:
    return (
        f"| `{_escape_cell(name)}` | {_escape_cell(action)} | {_escape_cell(color_changed)} | "
        f"{_escape_cell(desc_changed)} | {_escape_cell(result)} |"
    )


def fetch_live_labels(
    repo: str,
    token: str,
    *,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    request = urllib.request.Request(f"{API_ROOT}/repos/{repo}/labels?per_page=100")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", API_VERSION)
    with opener(request) as response:
        labels = json.loads(response.read().decode("utf-8"))
    if len(labels) >= 100:
        raise RuntimeError(
            f"Live label count is {len(labels)} (>=100); pagination required but not implemented. "
            "Update this workflow to paginate before retrying."
        )
    return labels


def load_sot(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        sot = json.load(handle)
    validate_sot(sot)
    return sot


def run(
    *,
    mode: Literal["plan", "apply"],
    repo: str,
    sot_path: Path,
    prune: bool,
    dry_run: bool,
    summary_file: Path,
    token: str,
    live_labels: list[dict[str, Any]] | None = None,
    apply_call: Callable[..., tuple[int, str]] = github_apply_call,
) -> int:
    sot = load_sot(sot_path)
    live = live_labels if live_labels is not None else fetch_live_labels(repo, token)
    live_by_name = {str(entry.get("name")): entry for entry in live}
    sot_names = {str(entry["name"]) for entry in sot}
    rows: list[str] = []

    _write_summary_header(summary_file, dry_run=dry_run, prune=prune, sot_count=len(sot), live_count=len(live))

    for entry in sot:
        name = str(entry["name"])
        decision = decide_label_action(sot_entry=entry, live_entry=live_by_name.get(name))
        action = str(decision["action"])
        if action == "NOOP":
            rows.append(render_action_row(name, "no-op", "no", "no", "unchanged"))
            continue

        color_changed = _changed_cell(decision["color_changed"], is_post=action == "POST")
        desc_changed = _changed_cell(decision["desc_changed"], is_post=action == "POST")
        if mode == "plan" or dry_run:
            rows.append(render_action_row(name, f"plan-only ({action})", color_changed, desc_changed, "dry-run"))
            continue

        code, body = apply_call(
            method=str(decision["method"]),
            url=f"{API_ROOT}/repos/{repo}{decision['url_suffix']}",
            payload=decision["payload"],
            token=token,
        )
        if not 200 <= code < 300:
            _append_rows(summary_file, rows)
            _append_error(
                summary_file,
                f"Error applying `{name}` ({decision['method']}, HTTP {_format_code(code)}):",
                body,
            )
            print(f"::error::Failed to {decision['method']} label '{name}' (last HTTP {_format_code(code)}).")
            return 1
        rows.append(render_action_row(name, f"{action} applied", color_changed, desc_changed, f"HTTP {code}"))

    for live_entry in live:
        live_name = str(live_entry.get("name"))
        prune_action = decide_prune_action(
            live_name=live_name,
            in_sot=live_name in sot_names,
            prune=prune,
            dry_run=(mode == "plan" or dry_run),
        )
        if prune_action == "skip":
            continue
        if prune_action == "report":
            rows.append(render_action_row(live_name, "report-only (not in SoT)", "—", "—", "kept (prune=false)"))
            continue
        if prune_action == "plan-delete":
            rows.append(render_action_row(live_name, "plan-only (DELETE)", "—", "—", "dry-run"))
            continue

        code, body = apply_call(
            method="DELETE",
            url=f"{API_ROOT}/repos/{repo}/labels/{urllib.parse.quote(live_name, safe='')}",
            payload=None,
            token=token,
        )
        if not 200 <= code < 300:
            _append_rows(summary_file, rows)
            _append_error(summary_file, f"Error deleting `{live_name}` (HTTP {_format_code(code)}):", body)
            print(f"::error::Failed to DELETE label '{live_name}' (last HTTP {_format_code(code)}).")
            return 1
        rows.append(render_action_row(live_name, "DELETE applied", "—", "—", f"HTTP {code}"))

    _append_rows(summary_file, rows)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_common_args(subparsers.add_parser("validate"))
    _add_common_args(subparsers.add_parser("plan"))
    _add_common_args(subparsers.add_parser("apply"))
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            load_sot(args.sot)
            return 0
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            print("::error::GH_TOKEN is not set.")
            return 1
        return run(
            mode=args.command,
            repo=args.repo,
            sot_path=args.sot,
            prune=_parse_bool(args.prune),
            dry_run=_parse_bool(args.dry_run),
            summary_file=args.summary_file,
            token=token,
        )
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as error:
        print(f"::error::{error}")
        return 1


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=os.environ.get("REPO", ""))
    parser.add_argument("--sot", type=Path, default=Path(".github/labels.json"))
    parser.add_argument("--prune", default="false")
    parser.add_argument("--dry-run", default="true")
    parser.add_argument("--summary-file", type=Path, default=Path(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")))


def _write_summary_header(summary_file: Path, *, dry_run: bool, prune: bool, sot_count: int, live_count: int) -> None:
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with summary_file.open("a", encoding="utf-8") as handle:
        handle.write("## Apply labels — dispatch summary\n\n")
        handle.write(f"- dry_run: `{str(dry_run).lower()}`\n")
        handle.write(f"- prune: `{str(prune).lower()}`\n")
        handle.write(f"- SoT entries: {sot_count}\n")
        handle.write(f"- Live labels: {live_count}\n\n")
        handle.write("| Name | Action | Color changed | Description changed | Result |\n")
        handle.write("|---|---|---|---|---|\n")


def _append_rows(summary_file: Path, rows: list[str]) -> None:
    with summary_file.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(f"{row}\n")


def _append_error(summary_file: Path, title: str, body: str) -> None:
    with summary_file.open("a", encoding="utf-8") as handle:
        handle.write(f"\n**{title}**\n")
        handle.write("```\n")
        handle.write(body)
        if body and not body.endswith("\n"):
            handle.write("\n")
        handle.write("```\n")


def _parse_bool(raw: str | bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"invalid boolean: {raw}")


def _changed_cell(changed: bool, *, is_post: bool) -> str:
    if is_post:
        return "—"
    return "yes" if changed else "no"


def _escape_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _format_code(code: int) -> str:
    return "000" if code == 0 else str(code)


if __name__ == "__main__":
    sys.exit(main())
