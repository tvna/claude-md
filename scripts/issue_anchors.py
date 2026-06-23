#!/usr/bin/env python3
"""Resolve tracking-issue anchors from ``.github/tracking-issues.toml``.

CI writes to specific GitHub issues; rolling comments, ``Closes #`` lines,
commit trailers, PR-body ``Refs #`` lines. Hardcoding those numbers across
workflow YAML, PR-body templates, and script constants made an
umbrella-issue renumbering a multi-file hunt. This module is the single
runtime resolver: workflows call the CLI, scripts import the library, and
renumbering becomes a one-file diff to the TOML. The companion gate
``scripts/scan_issue_anchor_drift.py`` fails CI when a functional hardcoded
issue number reappears.

Usage::

    python3 scripts/issue_anchors.py get security-tracking
    python3 scripts/issue_anchors.py render --file /tmp/pr-body.md

``render`` substitutes every ``__ISSUE_ANCHOR:<key>__`` token in the file
in place, so heredoc-built PR bodies and the ``.github/pr-body-templates``
files can carry a stable token instead of a literal number.

Library surface: :func:`load_anchors`, :func:`resolve`, :func:`substitute`.

Contract:
- Inputs: the ``get <key>`` subcommand (prints the anchor's issue number)
  or the ``render --file PATH`` subcommand (rewrites *PATH* in place);
  both accept ``--config`` (defaults to ``.github/tracking-issues.toml``).
- Outputs: ``get`` prints the bare issue number to stdout; ``render``
  rewrites the file and prints a status line; exit 0 on success, exit 1
  with a ``::error::`` annotation on a missing or malformed config, an
  unknown key, or an unresolvable token.
- Failure policy: fails loud per CLAUDE.md section 4; a missing or wrong
  anchor must stop the calling workflow rather than let a comment, trailer,
  or PR body target the wrong issue.

Tested by ``tests/test_issue_anchors.py``. Refs #1640.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / ".github" / "tracking-issues.toml"

# Keys are lowercase kebab-case so the token grammar below stays unambiguous
# inside Markdown/YAML bodies.
_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ANCHOR_TOKEN = re.compile(r"__ISSUE_ANCHOR:([a-z0-9-]+)__")


def load_anchors(config_path: Path = CONFIG_PATH) -> dict[str, int]:
    """Return ``{key: issue_number}`` parsed from *config_path*.

    Fails loud (``ValueError`` / ``OSError`` / ``tomllib.TOMLDecodeError``)
    on a missing file, unparseable TOML, an unexpected ``schema_version``,
    a malformed anchor entry, or a duplicate key: a half-read anchor table
    must never silently route a write to the wrong issue.
    """
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(
            f"{config_path}: expected schema_version = 1, "
            f"got {data.get('schema_version')!r}"
        )
    raw_anchors = data.get("anchors")
    if not isinstance(raw_anchors, list) or not raw_anchors:
        raise ValueError(f"{config_path}: expected a non-empty [[anchors]] list")

    anchors: dict[str, int] = {}
    for entry in raw_anchors:
        if not isinstance(entry, dict):
            raise ValueError(f"{config_path}: anchor entry is not a table: {entry!r}")
        key = entry.get("key")
        if not isinstance(key, str) or not _KEY_PATTERN.match(key):
            raise ValueError(
                f"{config_path}: anchor key must match {_KEY_PATTERN.pattern}; "
                f"got {key!r}"
            )
        if key in anchors:
            raise ValueError(f"{config_path}: duplicate anchor key {key!r}")
        issue = entry.get("issue")
        # bool is an int subclass; reject it explicitly.
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            raise ValueError(
                f"{config_path}: anchor {key!r} needs a positive integer "
                f"'issue'; got {issue!r}"
            )
        consumers = entry.get("consumers")
        if (
            not isinstance(consumers, list)
            or not consumers
            or not all(isinstance(c, str) for c in consumers)
        ):
            raise ValueError(
                f"{config_path}: anchor {key!r} needs a non-empty 'consumers' "
                "list of file paths"
            )
        anchors[key] = issue
    return anchors


def resolve(key: str, *, config_path: Path = CONFIG_PATH) -> int:
    """Return the issue number for *key*. Unknown keys raise ``ValueError``."""
    anchors = load_anchors(config_path)
    if key not in anchors:
        raise ValueError(
            f"{config_path}: unknown anchor key {key!r}; "
            f"known keys: {', '.join(sorted(anchors))}"
        )
    return anchors[key]


def substitute(text: str, *, config_path: Path = CONFIG_PATH) -> str:
    """Replace every ``__ISSUE_ANCHOR:<key>__`` token in *text*.

    A token naming an unknown key raises ``ValueError`` instead of passing
    the unexpanded token through to a PR body or comment.
    """
    anchors = load_anchors(config_path)

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in anchors:
            raise ValueError(
                f"unknown anchor key {key!r} in token {match.group(0)!r}; "
                f"known keys: {', '.join(sorted(anchors))}"
            )
        return str(anchors[key])

    return ANCHOR_TOKEN.sub(_replace, text)


def _cmd_get(args: argparse.Namespace) -> int:
    print(resolve(args.key, config_path=Path(args.config)))
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    path = Path(args.file)
    rendered = substitute(
        path.read_text(encoding="utf-8"), config_path=Path(args.config)
    )
    path.write_text(rendered, encoding="utf-8")
    print(f"Rendered issue-anchor tokens in {path}.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_get = sub.add_parser("get", help="Print the issue number for an anchor key")
    p_get.add_argument("key", help="Anchor key, e.g. security-tracking")
    p_get.add_argument("--config", default=str(CONFIG_PATH))
    p_get.set_defaults(func=_cmd_get)

    p_render = sub.add_parser(
        "render", help="Substitute __ISSUE_ANCHOR:<key>__ tokens in a file, in place"
    )
    p_render.add_argument("--file", required=True, help="File to rewrite in place")
    p_render.add_argument("--config", default=str(CONFIG_PATH))
    p_render.set_defaults(func=_cmd_render)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError, tomllib.TOMLDecodeError) as error:
        print(f"::error::issue_anchors: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
