#!/usr/bin/env python3
"""Audit Dependabot PRs against the repository auto-merge policy.

The workflow keeps this script in audit-first mode until the policy file
sets ``enabled`` to true. Eligibility and enablement are separate on purpose:
operators can observe what would have been auto-merged before allowing the
workflow to request GitHub auto-merge.

Tracked by #185.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _trusted_bots import _TRUSTED_BOT_LOGINS

_BUMP_RE = re.compile(
    r"\bfrom\s+v?(?P<old>\d+(?:\.\d+){0,2})\s+to\s+v?(?P<new>\d+(?:\.\d+){0,2})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AuditResult:
    eligible: bool
    enabled: bool
    update_type: str | None
    ecosystem: str | None
    reasons: list[str]

    @property
    def should_enable(self) -> bool:
        return self.eligible and self.enabled


def classify_update_type(title: str) -> str | None:
    """Return ``major``, ``minor``, or ``patch`` from a Dependabot title."""
    match = _BUMP_RE.search(title)
    if match is None:
        return None
    old = _parse_version(match.group("old"))
    new = _parse_version(match.group("new"))
    if new[0] != old[0]:
        return "major"
    if new[1] != old[1]:
        return "minor"
    if new[2] != old[2]:
        return "patch"
    return "patch"


def infer_ecosystem(changed_files: list[str]) -> str | None:
    """Infer the Dependabot ecosystem from the touched files."""
    if changed_files and all(fnmatch.fnmatch(path, ".github/workflows/*") for path in changed_files):
        return "github-actions"
    allowed_uv = {"pyproject.toml", "uv.lock"}
    if changed_files and all(path in allowed_uv for path in changed_files):
        return "uv"
    return None


def audit(
    event: dict[str, Any],
    policy: dict[str, Any],
    changed_files: list[str],
) -> AuditResult:
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        return AuditResult(False, False, None, None, ["event has no pull_request object"])

    enabled = bool(policy.get("enabled", False))
    reasons: list[str] = []
    author = _nested_str(pr, "user", "login")
    head_ref = _nested_str(pr, "head", "ref")
    raw_title = pr.get("title")
    title: str = raw_title if isinstance(raw_title, str) else ""
    labels = _label_names(pr)
    draft = bool(pr.get("draft", False))

    if author not in _TRUSTED_BOT_LOGINS:
        reasons.append(f"author is not trusted: {author or '<missing>'}")
    if not head_ref.startswith("dependabot/"):
        reasons.append(f"head branch is not dependabot/*: {head_ref or '<missing>'}")
    if draft:
        reasons.append("pull request is draft")
    blocked_labels = sorted(label for label in labels if label.startswith("severity:"))
    if blocked_labels:
        reasons.append(f"manual-review label present: {', '.join(blocked_labels)}")

    update_type = classify_update_type(title)
    if update_type is None:
        reasons.append("title does not expose a semver from/to update")

    ecosystem = infer_ecosystem(changed_files)
    if ecosystem is None:
        reasons.append("changed files do not match an allowed ecosystem")

    if update_type is not None and ecosystem is not None:
        rule = _matching_rule(policy, ecosystem)
        if rule is None:
            reasons.append(f"no policy rule for ecosystem: {ecosystem}")
        else:
            allowed_update_types = set(_string_list(rule.get("update_types")))
            if update_type not in allowed_update_types:
                reasons.append(f"{ecosystem} {update_type} updates are not allowed")
            allowed_paths = _string_list(rule.get("paths"))
            unexpected = _unexpected_paths(changed_files, allowed_paths)
            if unexpected:
                reasons.append(f"unexpected changed path(s): {', '.join(unexpected)}")

    return AuditResult(
        eligible=not reasons,
        enabled=enabled,
        update_type=update_type,
        ecosystem=ecosystem,
        reasons=reasons,
    )


def render_markdown(result: AuditResult) -> str:
    lines = [
        "## Dependabot auto-merge audit",
        "",
        f"- policy enabled: `{str(result.enabled).lower()}`",
        f"- eligible: `{str(result.eligible).lower()}`",
        f"- would request auto-merge: `{str(result.should_enable).lower()}`",
        f"- ecosystem: `{result.ecosystem or 'unknown'}`",
        f"- update type: `{result.update_type or 'unknown'}`",
        "",
    ]
    if result.reasons:
        lines.append("### Blocking reasons")
        lines.extend(f"- {reason}" for reason in result.reasons)
    else:
        lines.append("No blocking reasons found.")
    lines.append("")
    return "\n".join(lines)


def _cmd_audit(args: argparse.Namespace) -> int:
    try:
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
        policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
        changed_files = _read_changed_files(Path(args.changed_files))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"::error::{error}")
        return 1

    result = audit(event, policy, changed_files)
    markdown = render_markdown(result)
    print(markdown)
    if args.summary_file:
        Path(args.summary_file).write_text(markdown, encoding="utf-8")
    if args.output:
        _write_outputs(Path(args.output), result)
    return 0


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = [int(part) for part in version.split(".")]
    parts.extend([0] * (3 - len(parts)))
    return (parts[0], parts[1], parts[2])


def _nested_str(data: dict[str, Any], *keys: str) -> str:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return current if isinstance(current, str) else ""


def _label_names(pr: dict[str, Any]) -> set[str]:
    labels = pr.get("labels", [])
    if not isinstance(labels, list):
        return set()
    names: set[str] = set()
    for label in labels:
        if isinstance(label, dict) and isinstance(label.get("name"), str):
            names.add(label["name"])
    return names


def _matching_rule(policy: dict[str, Any], ecosystem: str) -> dict[str, Any] | None:
    rules = policy.get("allow", [])
    if not isinstance(rules, list):
        return None
    for rule in rules:
        if isinstance(rule, dict) and rule.get("ecosystem") == ecosystem:
            return rule
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _unexpected_paths(changed_files: list[str], allowed_paths: list[str]) -> list[str]:
    unexpected: list[str] = []
    for path in changed_files:
        if not any(fnmatch.fnmatch(path, pattern) for pattern in allowed_paths):
            unexpected.append(path)
    return unexpected


def _read_changed_files(path: Path) -> list[str]:
    files = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    files = [line for line in files if line]
    if not files:
        raise ValueError("changed-files list is empty")
    return files


def _write_outputs(path: Path, result: AuditResult) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"eligible={str(result.eligible).lower()}\n")
        handle.write(f"enabled={str(result.enabled).lower()}\n")
        handle.write(f"should_enable={str(result.should_enable).lower()}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", help="Audit one Dependabot pull request.")
    p_audit.add_argument("--event", required=True, help="Path to GitHub event JSON.")
    p_audit.add_argument("--policy", required=True, help="Path to policy JSON.")
    p_audit.add_argument(
        "--changed-files",
        required=True,
        help="Path to newline-delimited changed files.",
    )
    p_audit.add_argument("--summary-file", help="Optional Markdown summary path.")
    p_audit.add_argument("--output", help="Optional GitHub Actions output file.")
    p_audit.set_defaults(func=_cmd_audit)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
