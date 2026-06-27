#!/usr/bin/env python3
"""Scan ``scripts/*.py`` for direct ``gh`` CLI subprocess calls.

Policy (issue #909): production ``scripts/*.py`` must reach GitHub through the
approved REST wrapper (``scripts/_github_api.py`` / ``scripts/github_api.py``)
or covered ``mcp__github__*`` paths, never by shelling out to the ``gh`` CLI,
which may be absent in remote execution environments. This is the script-side
mirror of :mod:`scan_workflow_gh_calls` (issue #911), which guards the same
invariant for ``.github/workflows/*.yml``.

Detection is AST-based so prose mentions of ``gh`` in docstrings or comments
(e.g. operator runbooks embedded as module docstrings) are never flagged; only
executable ``gh`` invocations are. Two shapes are caught:

1. An argv list/tuple literal whose first element is the string ``"gh"``
   (e.g. ``["gh", "api", ...]`` passed to ``subprocess.run``).
2. A ``subprocess`` call (``run`` / ``Popen`` / ``call`` / ``check_output`` /
   ``check_call``) whose first positional argument is a string command whose
   first token is ``gh`` (e.g. ``subprocess.run("gh api ...", shell=True)``).

``ALLOWLIST_SCRIPTS`` documents intentional exceptions; it is empty so the gate
is fully strict. Add an entry only with an explicit migration rationale.

CLI::

    python3 scripts/scan_scripts_gh_calls.py verify  # exit 1 on violations
    python3 scripts/scan_scripts_gh_calls.py list     # print all matches

Contract:
- Inputs: the ``verify`` or ``list`` subcommand. No flags; the scanned root
  is the fixed ``scripts`` directory.
- Outputs: ``::error file=...::`` annotations on stderr naming each script and
  line with a direct ``gh`` call (``verify``); a ``[STATUS] script:line``
  listing on stdout (``list``).
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate, so any
  unallowlisted direct ``gh`` call exits 1).

Exit codes:
    0  verify passed (no violations) or list completed
    1  verify found unallowlisted gh calls
    2  usage error

Refs #909, #911.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

SCRIPTS_DIR = Path("scripts")

_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "call", "check_output", "check_call"})

_FRAGMENT_LEN = 80


class Violation(NamedTuple):
    script: str   # file basename
    line: int     # 1-based line number
    fragment: str  # short description of the offending call


# ---------------------------------------------------------------------------
# Allowlist
#
# Each entry documents one intentional exception. Required keys: ``script``
# (basename) and ``line`` is NOT used (line numbers drift); match on
# (``script``, ``rationale``) by listing the script once with a rationale.
# Keep empty so the gate enforces zero direct gh usage; add an entry only
# with an explicit, tracked rationale.
# ---------------------------------------------------------------------------
ALLOWLIST_SCRIPTS: frozenset[str] = frozenset()


def _argv_list_starts_with_gh(node: ast.List | ast.Tuple) -> bool:
    """True if *node* is a ``["gh", ...]`` / ``("gh", ...)`` literal."""
    if not node.elts:
        return False
    first = node.elts[0]
    return isinstance(first, ast.Constant) and first.value == "gh"


def _str_command_is_gh(node: ast.AST) -> bool:
    """True if *node* is a string constant whose first token is ``gh``."""
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    tokens = node.value.strip().split()
    return bool(tokens) and tokens[0] == "gh"


def _is_subprocess_call(node: ast.Call) -> bool:
    """True if *node* calls a ``subprocess`` runner function."""
    func = node.func
    # subprocess.run(...) / sp.run(...)
    if isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_FUNCS:
        return True
    # bare run(...) imported via ``from subprocess import run`` (best-effort)
    return bool(isinstance(func, ast.Name) and func.id in _SUBPROCESS_FUNCS)


def _iter_violations_in_tree(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """Yield (line, fragment) for every direct gh invocation in *tree*."""
    for node in ast.walk(tree):
        # Shape 1: any ["gh", ...] argv literal.
        if isinstance(node, ast.List | ast.Tuple) and _argv_list_starts_with_gh(node):
            yield node.lineno, 'argv literal starting with "gh"'
            continue
        # Shape 2: subprocess call with a "gh ..." string command.
        if isinstance(node, ast.Call) and _is_subprocess_call(node) and node.args and _str_command_is_gh(node.args[0]):
            yield node.lineno, 'subprocess call with "gh ..." command string'


def _iter_matches(scripts_dir: Path) -> Iterator[Violation]:
    """Yield a Violation for every direct gh call under *scripts_dir*.

    Files that cannot be parsed are skipped (a syntax error is the lint
    gate's concern, not this one). The scanner itself is excluded so its
    own example strings never self-trip.
    """
    self_name = Path(__file__).name
    for path in sorted(scripts_dir.glob("*.py")):
        if path.name == self_name:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for line, fragment in _iter_violations_in_tree(tree):
            yield Violation(script=path.name, line=line, fragment=fragment)


def find_violations(scripts_dir: Path = SCRIPTS_DIR) -> list[Violation]:
    """Return every unallowlisted direct gh call under *scripts_dir*."""
    return [v for v in _iter_matches(scripts_dir) if v.script not in ALLOWLIST_SCRIPTS]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan scripts/*.py for direct gh CLI subprocess calls.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="Exit 1 if any unallowlisted gh call is found")
    sub.add_parser("list", help="Print all gh calls found (allowed and violations)")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for v in _iter_matches(SCRIPTS_DIR):
            status = "ALLOWED" if v.script in ALLOWLIST_SCRIPTS else "VIOLATION"
            print(f"[{status}] {v.script}:{v.line}: {v.fragment}")
        return 0

    violations = find_violations(SCRIPTS_DIR)
    if not violations:
        return 0

    for v in violations:
        print(
            f"::error file=scripts/{v.script},line={v.line}::"
            f"Direct gh CLI call ({v.fragment}) in scripts/{v.script}. "
            f"Reach GitHub through scripts/_github_api.py (rest_json / paginate / "
            f"apply_call) or a covered mcp__github__* path; gh may be absent in "
            f"remote execution environments. See issue #909.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
