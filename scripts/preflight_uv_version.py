#!/usr/bin/env python3
"""Fail loudly when ``uv --version`` does not match ``[tool.uv].required-version``.

Refs #1207. PR #1206 added a workspace-local pinned uv but the workaround
only reached VS Code's integrated terminal, not the Claude Code process
PATH that runs ``analyzing-data``'s Stop hook. The visible symptom was
``Required uv version ==X.Y.Z does not match the running version ...``
firing every assistant turn, indistinguishable at merge time from a
silent success. This gate surfaces the mismatch loudly with a one-line
fix-it message, so the next host-uv drift cannot look green to CI while
breaking the hook loop.

Tested by ``tests/test_preflight_uv_version.py``.

Contract:
    Inputs: ``verify`` subcommand and (optional) ``--repo-root`` /
        ``--pyproject`` paths. No stdin. ``uv`` must resolve on PATH for
        a meaningful check; missing ``uv`` is reported as a hard
        failure with the same fix-it message as a version mismatch.
    Outputs: ``OK: uv X.Y.Z matches [tool.uv].required-version`` on
        stdout when aligned; a one-line fix-it message on stderr when
        mismatched. Exit 0 on match, 1 on mismatch, missing uv, or
        unreadable pin.
    Failure policy: fails loud per CLAUDE.md section 4 -- a mismatch is
        the *intended* signal, never silently swallowed. A missing uv
        binary is treated as a mismatch (the gate's job is to guarantee
        the runtime can satisfy the pin, and a missing binary cannot).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import uv_pin

REPO_ROOT = Path(__file__).resolve().parent.parent

# One-line fix-it message. Kept short so it survives in a hook fail-line
# without scrolling, and concrete so the operator does not need to
# remember the workaround script's path.
_FIX_IT = (
    "Run scripts/setup_pinned_uv.sh and restart this Claude Code session, "
    "or enter `nix develop`."
)


@dataclass(frozen=True)
class VersionResult:
    """Outcome of comparing ``uv --version`` to the pin."""

    status: str  # "pass" | "fail"
    detail: str


def parse_uv_version(output: str) -> str | None:
    """Return the version token from ``uv --version`` stdout, or None.

    The expected shape is ``uv X.Y.Z (...)`` -- the second whitespace
    token is the version. Any other shape returns None so the caller
    fails loudly rather than guessing.
    """
    tokens = output.strip().split()
    if len(tokens) < 2 or tokens[0] != "uv":
        return None
    return tokens[1]


def probe_uv_version(uv_path: str | None = None) -> str | None:
    """Return the running ``uv --version`` token, or None if uv is absent."""
    resolved = uv_path or shutil.which("uv")
    if resolved is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 -- argv is hard-coded
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return parse_uv_version(completed.stdout)


def check_version(*, pin: str, running: str | None) -> VersionResult:
    """Compare *running* uv version to *pin* and return the result."""
    if running is None:
        return VersionResult(
            status="fail",
            detail=f"uv not found on PATH; pin requires =={pin}",
        )
    if running != pin:
        return VersionResult(
            status="fail",
            detail=f"uv {running} does not match pin =={pin}",
        )
    return VersionResult(
        status="pass",
        detail=f"uv {running} matches [tool.uv].required-version",
    )


def _cmd_verify(args: argparse.Namespace) -> int:
    pyproject = Path(args.pyproject) if args.pyproject else Path(args.repo_root) / "pyproject.toml"
    try:
        pin = uv_pin.read_pin(pyproject)
    except ValueError as exc:
        print(f"error: cannot read uv pin: {exc}", file=sys.stderr)
        return 1

    running = probe_uv_version()
    result = check_version(pin=pin, running=running)
    if result.status == "pass":
        print(f"OK: {result.detail}")
        return 0
    print(f"error: {result.detail}. {_FIX_IT}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Exit 1 when uv --version does not match [tool.uv].required-version.",
    )
    p_verify.add_argument("--repo-root", default=str(REPO_ROOT))
    p_verify.add_argument(
        "--pyproject",
        default=None,
        help="Override the pyproject.toml path (defaults to --repo-root/pyproject.toml).",
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
