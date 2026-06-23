#!/usr/bin/env python3
"""Deterministic gate: the bash and Python allowlist parsers agree.

The devcontainer egress posture has two parsers for
``.devcontainer/network/*.allowlist``: the bash ``read_allowlist`` in
``.devcontainer/scripts/_egress-lib.sh`` (used by the privileged applier on the
container start path, where a Python dependency is undesirable) and the Python
``resolve_hosts`` in ``scripts/_allowlist.py`` (used by the rationale gate, the
tests, and the CI egress tooling). If the two drift, the devcontainer and CI
would admit different host sets from the same source of truth.

This gate sources the bash library and runs its ``read_allowlist`` on every
committed allowlist, then asserts the resolved host set equals
``resolve_hosts``'s. ``read_allowlist`` performs no name resolution, so this is
pure parsing and needs no network. It is the deterministic guard (CLAUDE.md
section 3) that keeps the single source of truth single across two languages.

CLI::

    python3 scripts/scan_allowlist_parser_parity.py verify  # exit 1 on drift

Contract:
- Inputs: the ``verify`` subcommand; ``--repo-root`` (default ``.``). Reads
  every ``<repo-root>/.devcontainer/network/*.allowlist`` file and sources
  ``<repo-root>/.devcontainer/scripts/_egress-lib.sh`` under ``bash``.
- Outputs: ``::error file=...::`` annotations on stderr naming each allowlist
  whose bash and Python host sets differ (with the symmetric difference) or
  whose bash parse failed; exit 0 when every file agrees, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (a parser mismatch, a
  missing library, a missing network directory, no allowlist files, or a bash
  failure all exit non-zero); a missing ``bash`` raises and is surfaced.

Tested by ``tests/test_scan_allowlist_parser_parity.py``. Refs #1257, #696.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from _allowlist import resolve_hosts

NETWORK_SUBDIR = (".devcontainer", "network")
EGRESS_LIB_SUBPATH = (".devcontainer", "scripts", "_egress-lib.sh")
ALLOWLIST_GLOB = "*.allowlist"


def bash_resolve_hosts(allowlist: Path, lib: Path) -> set[str]:
    """Return the host set the bash ``read_allowlist`` resolves for *allowlist*.

    Sources *lib* under ``bash`` and runs ``read_allowlist`` on *allowlist*.
    Pure parsing; no name resolution; so no network is touched. Raises
    ``RuntimeError`` if ``bash`` is not on PATH and
    ``subprocess.CalledProcessError`` when the bash parse exits non-zero, so the
    caller can surface either as a loud failure.
    """
    bash = shutil.which("bash")
    if bash is None:
        raise RuntimeError("bash not found on PATH; cannot verify parser parity")
    script = (
        f"set -euo pipefail; source {shlex.quote(str(lib))}; "
        f"read_allowlist {shlex.quote(str(allowlist))}"
    )
    completed = subprocess.run(  # noqa: S603 -- argv is the resolved bash path + a quoted script
        [bash, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line for line in completed.stdout.split() if line}


def verify(repo_root: Path) -> list[str]:
    """Return a list of ``::error::`` strings for parser drift, else ``[]``."""
    lib = repo_root.joinpath(*EGRESS_LIB_SUBPATH)
    if not lib.is_file():
        return [
            f"::error::egress bash library not found at {lib}; cannot verify "
            f"allowlist parser parity."
        ]
    network_dir = repo_root.joinpath(*NETWORK_SUBDIR)
    if not network_dir.is_dir():
        return [
            f"::error::network allowlist directory not found at {network_dir}; "
            f"cannot verify allowlist parser parity."
        ]
    files = sorted(network_dir.glob(ALLOWLIST_GLOB))
    if not files:
        return [
            f"::error::no {ALLOWLIST_GLOB} files found in {network_dir}; "
            f"expected at least the shared allowlist."
        ]

    errors: list[str] = []
    for path in files:
        try:
            rel: Path | str = path.relative_to(repo_root)
        except ValueError:
            rel = path
        python_hosts = resolve_hosts(path)
        try:
            bash_hosts = bash_resolve_hosts(path, lib)
        except subprocess.CalledProcessError as exc:
            errors.append(
                f"::error file={rel}::bash read_allowlist failed for {rel}: "
                f"{exc.stderr.strip()}"
            )
            continue
        if python_hosts != bash_hosts:
            python_only = ", ".join(sorted(python_hosts - bash_hosts)) or "(none)"
            bash_only = ", ".join(sorted(bash_hosts - python_hosts)) or "(none)"
            errors.append(
                f"::error file={rel}::allowlist parser mismatch for {rel}: "
                f"python-only=[{python_only}]; bash-only=[{bash_only}]. The bash "
                f"applier (_egress-lib.sh read_allowlist) and "
                f"scripts/_allowlist.py resolve_hosts must agree on the host set."
            )
    return errors


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    errors = verify(repo_root)
    for err in errors:
        print(err, file=sys.stderr)
    if errors:
        print(
            f"FAIL: {len(errors)} allowlist file(s) where the bash and Python "
            f"parsers disagree.",
            file=sys.stderr,
        )
        return 1
    print("OK: the bash and Python allowlist parsers resolve identical host sets.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Fail when the bash and Python allowlist parsers disagree.",
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
