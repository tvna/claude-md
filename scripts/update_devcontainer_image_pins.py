#!/usr/bin/env python3
"""Update local devcontainer image pins after a successful image publish."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

AGENTS = ("claude", "codex")
IMAGE_PREFIX = "ghcr.io/tvna/claude-md-devcontainer"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PINNED_FROM_RE = re.compile(r"(pinned images were published from `)[0-9a-f]{40}(`)")
DOC_IMAGE_RE_TEMPLATE = r"(ghcr\.io/tvna/claude-md-devcontainer-{agent}:)[0-9a-f]{{40}}"


def validate_sha(sha: str) -> str:
    if not SHA_RE.fullmatch(sha):
        raise ValueError(f"expected a 40-character lowercase git SHA, got: {sha}")
    return sha


def update_agent_config(repo_root: Path, agent: str, sha: str) -> bool:
    path = repo_root / ".devcontainer" / agent / "devcontainer.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    expected_prefix = f"{IMAGE_PREFIX}-{agent}:"
    current = data.get("image")
    if not isinstance(current, str) or not current.startswith(expected_prefix):
        raise ValueError(f"{path} image must start with {expected_prefix}")

    updated = f"{expected_prefix}{sha}"
    if current == updated:
        return False

    data["image"] = updated
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def replace_once(text: str, pattern: re.Pattern[str], replacement: str, *, label: str) -> tuple[str, bool]:
    updated, count = pattern.subn(replacement, text)
    if count != 1:
        raise ValueError(f"expected exactly one {label} replacement, got {count}")
    return updated, updated != text


def update_runbook(repo_root: Path, sha: str) -> bool:
    path = repo_root / "docs" / "runbooks" / "devcontainers.md"
    text = path.read_text(encoding="utf-8")
    changed = False

    text, did_change = replace_once(text, PINNED_FROM_RE, rf"\g<1>{sha}\2", label="pinned-from SHA")
    changed = changed or did_change

    for agent in AGENTS:
        pattern = re.compile(DOC_IMAGE_RE_TEMPLATE.format(agent=agent))
        text, did_change = replace_once(text, pattern, rf"\g<1>{sha}", label=f"{agent} image SHA")
        changed = changed or did_change

    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def update_pins(repo_root: Path, sha: str) -> bool:
    validated_sha = validate_sha(sha)
    changed = False
    for agent in AGENTS:
        changed = update_agent_config(repo_root, agent, validated_sha) or changed
    changed = update_runbook(repo_root, validated_sha) or changed
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sha", help="Published devcontainer image git SHA tag.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root to update.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed = update_pins(args.repo_root, args.sha)
    print("updated devcontainer image pins" if changed else "devcontainer image pins already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
