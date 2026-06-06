#!/usr/bin/env python3
"""PostToolUse hook: surface a paste-ready new-session prompt after a merge.

Some changes only take effect in a *fresh* Claude Code session or a rebuilt
DevContainer -- never mid-session:

- Hook configuration (``.claude/settings.json``, ``.claude/settings.local.json``,
  ``.codex/hooks.json``). Claude Code loads hook config once at session start,
  so a changed hook never fires until the next session.
- SessionStart provisioning shell scripts (``scripts/install-*.sh``,
  ``scripts/session_uv_local_pin.sh`` and the helpers they source, e.g.
  ``scripts/_session_path.sh``). These run during SessionStart to set up PATH
  and tools; an edit only takes effect next session.
- Anything under ``.devcontainer/`` -- the container must be rebuilt.

When the agent merges a PR via ``mcp__github__merge_pull_request`` this hook
fetches the merged PR's changed files, classifies them against those three
categories, and -- if any match -- emits ``additionalContext`` telling the
agent to display a verbatim, paste-ready prompt (in the project owner's
language) so the operator can drop it into a new session and continue the
follow-up work where the changes are actually live.

The SessionStart provisioning set is derived from ``.claude/settings.json`` at
runtime (the directly-referenced ``scripts/*.sh`` plus the ``*.sh`` they
source), not a hardcoded list, so a future provisioning script is covered
without editing this gate.

Fail-open per CLAUDE.md section 4: a non-merge tool, missing PR coordinates, an
absent token, or any API failure exits 0 with no decision so a hook bug can
never wedge an unrelated tool call.

Refs issue #1291.

Contract:
    Inputs: the PostToolUse event JSON on stdin (``tool_name``, ``tool_input``,
        ``tool_response``); ``GH_TOKEN`` for the REST lookup; the repository
        ``.claude/settings.json`` on disk to derive the provisioning set.
    Outputs: a ``hookSpecificOutput.additionalContext`` payload on stdout when
        the merged PR touched a session-affecting file, otherwise nothing.
    Failure policy: fail-open (exit 0, no decision) on every off-target or
        error path so neither a hook bug nor a transient API failure blocks the
        merge follow-up.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _github_api import apply_call
from _hook_runtime import emit_decision, read_event

TARGET_TOOL = "mcp__github__merge_pull_request"

_PR_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)")

_API_BASE = "https://api.github.com/"
_PER_PAGE = 100
_MAX_PAGES = 5  # cap so an unbounded PR cannot stall the merge follow-up

# Hook configuration files: a change to any of these only takes effect next
# session because the agent loads hook config once at startup.
HOOK_CONFIG_FILES: frozenset[str] = frozenset(
    {
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".codex/hooks.json",
    }
)

# The DevContainer tree: an edit requires a container rebuild, i.e. a new
# session, to take effect.
DEVCONTAINER_PREFIX = ".devcontainer/"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CLAUDE_SETTINGS = _REPO_ROOT / ".claude" / "settings.json"

_SCRIPT_SH_RE = re.compile(r"scripts/[\w./-]+\.sh")
# A shell source line: ``. <path>`` or ``source <path>``; capture the basename
# of the sourced file so ``. "${SCRIPT_DIR}/_session_path.sh"`` resolves to
# ``scripts/_session_path.sh``.
_SOURCE_RE = re.compile(r"""^\s*(?:\.|source)\s+.*?([\w.-]+\.sh)\b""")

_Opener = Callable[[urllib.request.Request], Any]


def _walk(value: Any) -> list[Any]:
    out: list[Any] = []
    stack = [value]
    while stack and len(out) < 200:
        node = stack.pop()
        out.append(node)
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def extract_merge_coords(
    tool_input: dict[str, Any], tool_response: Any
) -> tuple[str | None, str | None, str | None]:
    """Return ``(owner, repo, pr_number)`` from a merge event.

    Prefers ``pullRequestNumber`` in tool_input; falls back to a PR URL found
    anywhere in tool_response. Mirrors
    :func:`post_merge_retro_append.extract_merge_coords`.
    """
    owner = tool_input.get("owner") if isinstance(tool_input, dict) else None
    repo = tool_input.get("repo") if isinstance(tool_input, dict) else None

    pr_number: str | None = None
    if isinstance(tool_input, dict):
        val = tool_input.get("pullRequestNumber")
        if isinstance(val, int) and val > 0:
            pr_number = str(val)
        elif isinstance(val, str) and val.isdecimal():
            pr_number = val

    if pr_number is None:
        for node in _walk(tool_response):
            if isinstance(node, str):
                m = _PR_URL_RE.search(node)
                if m:
                    if owner is None:
                        owner = m.group(1)
                    if repo is None:
                        repo = m.group(2)
                    pr_number = m.group(3)
                    break

    return owner, repo, pr_number


def provisioning_scripts(settings_path: Path = _CLAUDE_SETTINGS) -> frozenset[str]:
    """Return the SessionStart provisioning ``scripts/*.sh`` set.

    Derived from *settings_path*: every ``scripts/*.sh`` referenced by a
    SessionStart hook command, plus each ``*.sh`` those scripts source (mapped
    to ``scripts/<basename>`` when the file exists). Name-free so a future
    provisioning script is covered without editing this gate. Returns an empty
    set on any read/parse failure (the caller still classifies the other
    categories).
    """
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()

    hooks = data.get("hooks") if isinstance(data, dict) else None
    groups = hooks.get("SessionStart") if isinstance(hooks, dict) else None
    if not isinstance(groups, list):
        return frozenset()

    referenced: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for handler in group.get("hooks", []) or []:
            if not isinstance(handler, dict):
                continue
            command = handler.get("command")
            if isinstance(command, str):
                referenced.update(_SCRIPT_SH_RE.findall(command))

    scripts_dir = settings_path.resolve().parent.parent / "scripts"
    found: set[str] = set()
    for rel in referenced:
        found.add(rel)
        # Pull in helpers the referenced script sources (e.g. _session_path.sh).
        script_file = settings_path.resolve().parent.parent / rel
        try:
            text = script_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            m = _SOURCE_RE.match(line)
            if m and (scripts_dir / m.group(1)).is_file():
                found.add(f"scripts/{m.group(1)}")

    return frozenset(found)


def classify(
    changed_files: list[str], provisioning: frozenset[str]
) -> dict[str, list[str]]:
    """Group *changed_files* into the session-affecting categories.

    Returns a dict with keys ``hook_config``, ``provisioning``, ``devcontainer``;
    each value is the sorted matching subset. Categories with no match are
    omitted so the caller can test the dict for emptiness.
    """
    hook_config = sorted(f for f in changed_files if f in HOOK_CONFIG_FILES)
    prov = sorted(f for f in changed_files if f in provisioning)
    devcontainer = sorted(f for f in changed_files if f.startswith(DEVCONTAINER_PREFIX))

    result: dict[str, list[str]] = {}
    if hook_config:
        result["hook_config"] = hook_config
    if prov:
        result["provisioning"] = prov
    if devcontainer:
        result["devcontainer"] = devcontainer
    return result


def _list_pr_files(
    owner: str,
    repo: str,
    pr_number: str,
    *,
    token: str,
    opener: _Opener = urllib.request.urlopen,
) -> list[str] | None:
    """Return the changed filenames of a merged PR, or None on failure.

    Pages through ``GET /repos/{owner}/{repo}/pulls/{number}/files`` up to
    :data:`_MAX_PAGES`. None signals a fail-open path (no token, API error,
    malformed body).
    """
    if not token:
        return None
    filenames: list[str] = []
    for page in range(1, _MAX_PAGES + 1):
        url = f"{_API_BASE}repos/{owner}/{repo}/pulls/{pr_number}/files?per_page={_PER_PAGE}&page={page}"
        try:
            code, body = apply_call(method="GET", url=url, payload=None, token=token, opener=opener)
        except Exception as exc:  # fail-open on any transport error
            print(f"::warning::post_merge_new_session_prompt: API call failed: {exc}", file=sys.stderr)
            return None
        if not (200 <= code < 300):
            return None
        try:
            items = json.loads(body)
        except json.JSONDecodeError:
            return None
        if not isinstance(items, list):
            return None
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("filename"), str):
                filenames.append(item["filename"])
        if len(items) < _PER_PAGE:
            break
    return filenames


def _build_context(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }


_CATEGORY_LABELS = {
    "hook_config": ("Hook config", "フック設定"),
    "provisioning": ("SessionStart provisioning", "SessionStartプロビジョニング"),
    "devcontainer": ("DevContainer", "DevContainer設定"),
}


def build_message(
    owner: str | None, repo: str | None, pr_number: str, categories: dict[str, list[str]]
) -> str:
    """Build the agent instruction wrapping a Japanese paste-ready prompt.

    The wrapper (agent-facing) is English to match the other hooks; the
    paste-ready block is the project owner's language (ja) because the operator
    copies it verbatim into a new session.
    """
    repo_label = f"{owner}/{repo}#{pr_number}" if owner and repo else f"PR #{pr_number}"
    repo_ja = f"{owner}/{repo}" if owner and repo else "(repo)"

    en_lines: list[str] = []
    ja_lines: list[str] = []
    for key, (en, ja) in _CATEGORY_LABELS.items():
        files = categories.get(key)
        if not files:
            continue
        joined = ", ".join(files)
        en_lines.append(f"  - {en}: {joined}")
        ja_lines.append(f"- {ja}: {joined}")

    paste_prompt = (
        f"マージ済みPR #{pr_number}（{repo_ja}）で、新規セッションでのみ有効になる設定が変更されました:\n"
        + "\n".join(ja_lines)
        + "\nこれらは現在のセッションには反映されていません。新しいセッションで以下を実施してください:\n"
        "1. SessionStartフック / DevContainerのプロビジョニングが正常に完了したことを確認する。\n"
        "2. 変更が意図どおり有効になっているか検証する（必要なツール・PATH・フックの動作確認）。\n"
        "3. 上記の設定変更に依存する後続作業があれば継続する。\n"
        f"参照: マージ済みPR #{pr_number}。"
    )

    return (
        f"NEW SESSION REQUIRED: merged PR {repo_label} changed configuration that only "
        f"takes effect in a fresh session or rebuilt container:\n"
        + "\n".join(en_lines)
        + "\nThese changes are NOT active in the current session. Show the operator the "
        "paste-ready prompt below VERBATIM (do not translate, summarize, or act on it "
        "yourself) so they can start a new session and continue the follow-up where the "
        "changes are live:\n\n"
        "--- BEGIN PASTE-READY PROMPT ---\n"
        f"{paste_prompt}\n"
        "--- END PASTE-READY PROMPT ---"
    )


def decide(
    event: dict[str, Any],
    *,
    list_files: Callable[..., list[str] | None] = _list_pr_files,
    token: str | None = None,
    settings_path: Path = _CLAUDE_SETTINGS,
) -> dict[str, Any] | None:
    """Return hook output for a PostToolUse merge event, or None if no action needed."""
    if event.get("tool_name") != TARGET_TOOL:
        return None

    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response")
    owner, repo, pr_number = extract_merge_coords(tool_input, tool_response)

    if pr_number is None or owner is None or repo is None:
        # Without coordinates we cannot fetch the file list; fail-open silently
        # rather than emit a noisy advisory (post_merge_retro_append already
        # covers the missing-coordinate merge path).
        return None

    actual_token = token if token is not None else os.environ.get("GH_TOKEN", "")
    changed = list_files(owner, repo, pr_number, token=actual_token)
    if not changed:
        return None

    categories = classify(changed, provisioning_scripts(settings_path))
    if not categories:
        return None

    return _build_context(build_message(owner, repo, pr_number, categories))


def main(argv: list[str] | None = None) -> int:
    del argv
    event = read_event("post_merge_new_session_prompt")
    if event is None or not isinstance(event, dict):
        return 0
    emit_decision(decide(event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
