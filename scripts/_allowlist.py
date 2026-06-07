#!/usr/bin/env python3
"""Shared parser for ``.devcontainer/network/*.allowlist`` files.

The devcontainer egress posture is deny-by-default: a destination is admitted
by adding a hostname to an allowlist file, and the resolved host set drives the
firewall rules applied by ``.devcontainer/scripts/apply-egress-allowlist.sh``.
The file format is one hostname per line, with ``@include <file>`` directives,
blank lines, standalone ``#`` comments, and inline trailing ``# rationale``
comments (enforced by ``scripts/scan_allowlist_rationale.py``).

Before this module the ``@include`` expansion and inline-comment stripping logic
was duplicated across the bash applier, ``tests/test_devcontainer_allowlist.py``,
and the rationale gate. This is the single Python implementation so those callers
cannot drift apart (CLAUDE.md section 3: single source of truth). The bash applier
keeps its own ``read_allowlist`` so the devcontainer start path carries no Python
dependency; a parser-parity gate guards bash vs. Python agreement separately.

This is an internal helper (``_`` prefix), imported by sibling scripts via the
``pythonpath = ["scripts"]`` pytest setting and the scripts' shared sys.path. It
is tested directly by ``tests/test_allowlist.py``.
"""

from __future__ import annotations

from pathlib import Path

# ``@include <file>`` directive prefix. The trailing space is significant: it
# matches the bash applier's ``[[ "$line" == @include\ * ]]`` test and the
# historical ``startswith("@include ")`` parser, so a bare ``@include`` with no
# argument is treated as an ordinary host entry rather than a directive.
INCLUDE_PREFIX = "@include "


def split_inline_comment(raw: str) -> tuple[str, str]:
    """Return ``(content, rationale)`` for an allowlist line.

    ``content`` is the text before the first ``#`` (stripped); ``rationale`` is
    the text after it (stripped). A line with no ``#`` yields an empty rationale.
    Hostnames never contain ``#``, so the first ``#`` always delimits the inline
    comment. This mirrors the bash applier's ``line="${line%%#*}"`` stripping.
    """
    hash_idx = raw.find("#")
    if hash_idx == -1:
        return raw.strip(), ""
    return raw[:hash_idx].strip(), raw[hash_idx + 1 :].strip()


def resolve_hosts(path: Path) -> set[str]:
    """Return the set of hostnames an allowlist resolves to, expanding includes.

    Each line is comment-stripped; blank/comment-only lines are skipped; an
    ``@include <file>`` directive recurses into ``<file>`` resolved relative to
    the including file's directory (every allowlist lives in the same network
    directory, so this matches the bash applier's fixed-base-dir expansion). The
    result is a de-duplicated set, equivalent to the applier's ``sort -u``.
    """
    hosts: set[str] = set()
    base = path.parent
    for raw in path.read_text(encoding="utf-8").splitlines():
        content, _rationale = split_inline_comment(raw)
        if not content:
            continue  # blank line or standalone comment
        if content.startswith(INCLUDE_PREFIX):
            target = content[len(INCLUDE_PREFIX) :].strip()
            hosts |= resolve_hosts(base / target)
            continue
        hosts.add(content)
    return hosts
