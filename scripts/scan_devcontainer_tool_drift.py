#!/usr/bin/env python3
"""Fail when a gate-required CLI is not provisioned in the devcontainer flake.

Issue #1103 retrospective for #1100: the skill quality gate shipped with a
pre-commit hook that needs the ``waza`` binary, but ``waza`` was never added
to ``flake.nix``. Inside the devcontainer (which has no Go toolchain and an
egress allowlist without the Go module proxy) a SKILL.md commit would have
hard-failed. The omission was invisible because nothing tied "a gate needs
tool X" to "the devcontainer provides tool X".

This is the deterministic gate that closes that loop. The authoritative list
of tools a gate needs at runtime is the union of ``required_bin`` across
``scripts/preflight_all.py`` STEPS. For each such tool this gate asserts that
``flake.nix`` provisions it -- matched by a registered marker string in
:data:`TOOL_FLAKE_MARKERS` -- or that the tool is explicitly excused in
:data:`ALLOWLIST` with a rationale. A new ``required_bin`` entry with neither
a marker nor an allowlist entry fails the gate with a remediation message.

CLI::

    python3 scripts/scan_devcontainer_tool_drift.py verify  # exit 1 on drift

Contract:
- Inputs: the ``verify`` subcommand; ``--repo-root`` (default ``.``); the
  ``required_bin`` declarations imported from ``scripts/preflight_all.py``;
  the text of ``<repo-root>/flake.nix``.
- Outputs: ``::error::`` annotations on stderr naming each gate-required tool
  that is neither provisioned in flake.nix nor allowlisted; exit 0 when every
  required tool is accounted for, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (gate: an unprovisioned
  required tool exits non-zero; a missing flake.nix also exits non-zero).

Tested by ``tests/test_scan_devcontainer_tool_drift.py``. Refs #1100, #1103.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Maps a runtime tool name (as it appears in a preflight_all.py Step
# ``required_bin``) to a marker string that MUST be present in flake.nix when
# the tool is provisioned by the devcontainer. The marker is the derivation /
# attribute name, which is stable and unique enough to detect drift without
# parsing Nix. Extend this when a new gate-required tool is added to the flake.
TOOL_FLAKE_MARKERS: dict[str, str] = {
    "uv": "pinned-uv",
    "waza": "waza-cli",
    "actionlint": "actionlint",
    "shellcheck": "shellcheck",
    # Refs #1597. The Mermaid syntax gate (scan_mermaid_syntax) runs the
    # official parser through bun; flake.nix sharedPackages provisions it.
    "bun": "bun",
}

# Tools a gate may require but that are intentionally NOT provisioned by the
# devcontainer flake. Each entry must carry a rationale. Empty by default --
# the safe default is "provision it, do not excuse it".
ALLOWLIST: dict[str, str] = {}


def required_bins() -> set[str]:
    """Return the union of ``required_bin`` across preflight_all.py STEPS."""
    # scripts/ is on sys.path[0] when run as a script and on pytest's
    # configured pythonpath, so the sibling import resolves in both contexts.
    import preflight_all

    bins: set[str] = set()
    for step in preflight_all.STEPS:
        bins.update(step.required_bin)
    return bins


def verify(repo_root: Path) -> list[str]:
    """Return a list of ``::error::`` strings for unprovisioned tools."""
    flake_path = repo_root / "flake.nix"
    if not flake_path.is_file():
        return [
            f"::error::flake.nix not found at {flake_path}; cannot verify "
            f"devcontainer tool provisioning."
        ]
    flake_text = flake_path.read_text(encoding="utf-8")

    errors: list[str] = []
    for tool in sorted(required_bins()):
        if tool in ALLOWLIST:
            continue
        marker = TOOL_FLAKE_MARKERS.get(tool)
        if marker is None:
            errors.append(
                f"::error::gate-required tool '{tool}' has no devcontainer "
                f"provisioning marker. Add '{tool}' to flake.nix and register "
                f"its marker in scan_devcontainer_tool_drift.TOOL_FLAKE_MARKERS, "
                f"or add it to ALLOWLIST with a rationale if it is "
                f"intentionally not in the container."
            )
            continue
        if marker not in flake_text:
            errors.append(
                f"::error::gate-required tool '{tool}' (marker '{marker}') is "
                f"not provisioned in flake.nix. A gate needs it at runtime but "
                f"the devcontainer does not supply it. Add the '{marker}' "
                f"derivation to flake.nix and include it in the dev shell."
            )
    return errors


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    errors = verify(repo_root)
    for err in errors:
        print(err, file=sys.stderr)
    if errors:
        print(
            f"FAIL: {len(errors)} gate-required tool(s) not provisioned in "
            f"the devcontainer flake.",
            file=sys.stderr,
        )
        return 1
    print("OK: every gate-required tool is provisioned in flake.nix.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Fail when a gate-required tool is missing from flake.nix.",
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
