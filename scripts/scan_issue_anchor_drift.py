#!/usr/bin/env python3
"""Deterministic gate: tracking-issue numbers stay in ``.github/tracking-issues.toml``.

The workflow ``.github/workflows/verify-agents.yml`` invokes this module
from the ``lint-scripts-static`` job (mirrored locally by
``scripts/preflight_all.py``). It sustains the #1640 refactor as a
continuous check instead of reviewer memory (CLAUDE.md section 3): every
GitHub issue number that CI *writes to* must be resolved through
``scripts/issue_anchors.py`` at runtime, so an umbrella-issue renumbering
stays a one-file diff to the TOML.

Four checks:

* **Config sanity.** The anchor table loads (``issue_anchors.load_anchors``
  validation) and every declared ``consumers`` path exists, so the table
  cannot silently go stale against a renamed workflow or script.
* **Workflows.** No non-comment line under ``.github/workflows/*.yml``
  carries a functional hardcoded issue number: ``--issue`` /
  ``--issue-number`` with a literal digit, ``--commit-body`` /
  ``--commit-trailer`` with a literal ``Refs #N``, a ``Closes #N``
  reference, a bare ``Refs #N`` body line, or an ``*_ISSUE:`` env pin.
* **PR-body templates.** No ``.github/pr-body-templates/*.md`` line
  carries a literal ``Refs #N`` / ``Closes #N``; templates use
  ``__ISSUE_ANCHOR:<key>__`` tokens instead.
* **Script constants.** No module-level ``scripts/*.py`` constant whose
  name contains ``ISSUE`` is assigned an integer literal; constants resolve
  via ``issue_anchors.resolve``.

Provenance comments (``# Refs #NNN``) are history, not behaviour, and are
intentionally ignored: comment lines are skipped in workflows, and Python
comments/docstrings are invisible to the AST constant check.

Contract:
- Inputs: the ``verify`` subcommand; ``--repo-root`` (defaults to the
  repository root) and ``--config`` (defaults to
  ``.github/tracking-issues.toml`` under the repo root).
- Outputs: ``::error file=<path>,line=<n>::`` annotations on stderr for
  each violation; exit 0 when the tree is clean, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate, so
  a malformed config or any hardcoded functional issue number exits
  non-zero).

Tested by ``tests/test_scan_issue_anchor_drift.py``. Refs #1640.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from pathlib import Path

import issue_anchors

REPO_ROOT = Path(__file__).resolve().parent.parent

# Functional (behaviour-carrying) hardcoded issue-number shapes inside
# workflow run blocks, heredoc PR bodies, and env pins. Each pattern pairs
# with the remediation hint shown in the error annotation.
_WORKFLOW_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"--issue(?:-number)?[= ]+[\"']?\d"),
        "pass a value resolved via scripts/issue_anchors.py get <key>",
    ),
    (
        re.compile(r"--commit-(?:body|trailer)[= ]+[\"']?Refs #\d"),
        "build the trailer from scripts/issue_anchors.py get <key>",
    ),
    (
        re.compile(r"\bCloses #\d"),
        "use a __ISSUE_ANCHOR:<key>__ token and scripts/issue_anchors.py render",
    ),
    (
        re.compile(r"^\s*Refs #\d+\s*$"),
        "use a __ISSUE_ANCHOR:<key>__ token and scripts/issue_anchors.py render",
    ),
    (
        re.compile(r"^\s*[A-Z][A-Z0-9_]*ISSUE:\s*[\"']?\d"),
        "resolve the env value via scripts/issue_anchors.py get <key>",
    ),
)

_TEMPLATE_PATTERN = re.compile(r"\b(?:Refs|Closes) #\d")


def _check_config(repo_root: Path, config_path: Path) -> list[str]:
    """Validate the anchor table and its declared consumer paths."""
    try:
        issue_anchors.load_anchors(config_path)
    except (ValueError, OSError, tomllib.TOMLDecodeError) as error:
        return [f"::error file={_rel(config_path, repo_root)}::{error}"]

    errors: list[str] = []
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    for entry in data["anchors"]:
        for consumer in entry["consumers"]:
            if not (repo_root / consumer).exists():
                errors.append(
                    f"::error file={_rel(config_path, repo_root)}::anchor "
                    f"{entry['key']!r} lists consumer {consumer!r} which does "
                    "not exist; update the consumers list"
                )
    return errors


def _check_workflows(repo_root: Path) -> list[str]:
    """Flag functional hardcoded issue numbers in workflow files."""
    errors: list[str] = []
    for workflow in sorted((repo_root / ".github" / "workflows").glob("*.yml")):
        for lineno, line in enumerate(
            workflow.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if line.lstrip().startswith("#"):
                continue
            for pattern, hint in _WORKFLOW_PATTERNS:
                if pattern.search(line):
                    errors.append(
                        f"::error file={_rel(workflow, repo_root)},line={lineno}::"
                        f"hardcoded tracking-issue number ({line.strip()!r}); "
                        f"{hint} (.github/tracking-issues.toml)"
                    )
    return errors


def _check_templates(repo_root: Path) -> list[str]:
    """Flag literal issue references in PR-body templates."""
    errors: list[str] = []
    templates_dir = repo_root / ".github" / "pr-body-templates"
    if not templates_dir.is_dir():
        return errors
    for template in sorted(templates_dir.glob("*.md")):
        for lineno, line in enumerate(
            template.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _TEMPLATE_PATTERN.search(line):
                errors.append(
                    f"::error file={_rel(template, repo_root)},line={lineno}::"
                    f"hardcoded tracking-issue number ({line.strip()!r}); use a "
                    "__ISSUE_ANCHOR:<key>__ token (.github/tracking-issues.toml)"
                )
    return errors


def _check_script_constants(repo_root: Path) -> list[str]:
    """Flag module-level ``*ISSUE*`` constants assigned an integer literal."""
    errors: list[str] = []
    for script in sorted((repo_root / "scripts").glob("*.py")):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        for node in tree.body:
            targets: list[ast.expr]
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            if not (
                isinstance(value, ast.Constant)
                and isinstance(value.value, int)
                and not isinstance(value.value, bool)
            ):
                continue
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and "ISSUE" in target.id
                    and target.id.isupper()
                ):
                    errors.append(
                        f"::error file={_rel(script, repo_root)},line={node.lineno}::"
                        f"module constant {target.id} pins an issue number "
                        "literally; resolve it via issue_anchors.resolve(<key>) "
                        "(.github/tracking-issues.toml)"
                    )
    return errors


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def verify(repo_root: Path, config_path: Path) -> int:
    errors = [
        *_check_config(repo_root, config_path),
        *_check_workflows(repo_root),
        *_check_templates(repo_root),
        *_check_script_constants(repo_root),
    ]
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(
            f"scan_issue_anchor_drift: {len(errors)} violation(s).",
            file=sys.stderr,
        )
        return 1
    print("scan_issue_anchor_drift: clean.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_verify = sub.add_parser("verify", help="Scan for hardcoded tracking-issue numbers")
    p_verify.add_argument("--repo-root", default=str(REPO_ROOT))
    p_verify.add_argument(
        "--config",
        default=None,
        help="Anchor table (defaults to .github/tracking-issues.toml under --repo-root)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    config_path = (
        Path(args.config)
        if args.config
        else repo_root / ".github" / "tracking-issues.toml"
    )
    try:
        return verify(repo_root, config_path)
    except (OSError, SyntaxError, ValueError, KeyError, TypeError) as error:
        print(f"::error::scan_issue_anchor_drift: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
