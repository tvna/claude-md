#!/usr/bin/env python3
"""Fail when a devcontainer egress allowlist host has no triage rationale.

Issue #1170 (child of #696): the devcontainer egress posture is
deny-by-default, and a new outbound destination is admitted by adding a
hostname to ``.devcontainer/network/*.allowlist``. Nothing tied "a host is
in the allowlist" to "the host was triaged" -- the observe / evaluate /
decide procedure in ``docs/runbooks/devcontainer-tool-network-triage.md`` --
so an unevaluated destination could land on reviewer memory alone.

This is the deterministic gate that closes that loop. Every host entry in an
allowlist file MUST carry an inline trailing rationale comment recording the
triage decision::

    api.anthropic.com  # Anthropic API endpoint used by the Claude CLI at runtime.

``@include`` directives, blank lines, and standalone comment lines need no
rationale. The inline ``#`` is stripped by the allowlist parser in
``.devcontainer/scripts/apply-egress-allowlist.sh`` and by
``tests/test_devcontainer_allowlist.py``, so the rationale never changes the
resolved host set.

CLI::

    python3 scripts/scan_allowlist_rationale.py verify  # exit 1 on a bare host

Contract:
- Inputs: the ``verify`` subcommand; ``--repo-root`` (default ``.``); the
  text of every ``<repo-root>/.devcontainer/network/*.allowlist`` file.
- Outputs: ``::error file=...,line=...::`` annotations on stderr naming each
  host entry that lacks an inline rationale comment; exit 0 when every host
  is annotated, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (a bare host entry, a
  missing network directory, or no allowlist files all exit non-zero).

Tested by ``tests/test_scan_allowlist_rationale.py``. Refs #1170, #696.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

NETWORK_SUBDIR = (".devcontainer", "network")
ALLOWLIST_GLOB = "*.allowlist"


def _split_inline_comment(raw: str) -> tuple[str, str]:
    """Return ``(content, rationale)`` for an allowlist line.

    ``content`` is the text before the first ``#`` (stripped); ``rationale``
    is the text after it (stripped). A line with no ``#`` yields an empty
    rationale. Hostnames never contain ``#``, so the first ``#`` always
    delimits the inline comment.
    """
    hash_idx = raw.find("#")
    if hash_idx == -1:
        return raw.strip(), ""
    return raw[:hash_idx].strip(), raw[hash_idx + 1 :].strip()


def check_file(path: Path, repo_root: Path) -> list[str]:
    """Return ``::error::`` strings for host entries missing a rationale."""
    try:
        rel: Path | str = path.relative_to(repo_root)
    except ValueError:
        rel = path
    errors: list[str] = []
    for lineno, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue  # blank line or standalone comment
        content, rationale = _split_inline_comment(raw)
        if content.startswith("@include"):
            continue  # include directive needs no rationale of its own
        if not content:
            continue  # defensive: line was only an inline comment
        if not rationale:
            errors.append(
                f"::error file={rel},line={lineno}::host '{content}' in {rel} "
                f"has no triage rationale. Add an inline comment "
                f"'{content}  # <why this destination is allowed>' after running "
                f"the triage in "
                f"docs/runbooks/devcontainer-tool-network-triage.md."
            )
    return errors


def verify(repo_root: Path) -> list[str]:
    """Return a list of ``::error::`` strings for un-triaged allowlist hosts."""
    network_dir = repo_root.joinpath(*NETWORK_SUBDIR)
    if not network_dir.is_dir():
        return [
            f"::error::network allowlist directory not found at {network_dir}; "
            f"cannot verify egress destination triage rationale."
        ]
    files = sorted(network_dir.glob(ALLOWLIST_GLOB))
    if not files:
        return [
            f"::error::no {ALLOWLIST_GLOB} files found in {network_dir}; "
            f"expected at least the shared allowlist."
        ]
    errors: list[str] = []
    for path in files:
        errors.extend(check_file(path, repo_root))
    return errors


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    errors = verify(repo_root)
    for err in errors:
        print(err, file=sys.stderr)
    if errors:
        print(
            f"FAIL: {len(errors)} egress allowlist host(s) without a triage "
            f"rationale.",
            file=sys.stderr,
        )
        return 1
    print("OK: every egress allowlist host carries a triage rationale.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Fail when an allowlist host lacks an inline triage rationale.",
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
