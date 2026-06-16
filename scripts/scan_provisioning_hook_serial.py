#!/usr/bin/env python3
"""Require pre-commit hooks that provision a shared binary to be serial.

The #1150 ``PermissionError [Errno 13]`` came from prek running the
skill-quality-gate hook in PARALLEL across SKILL.md batches while
``install_waza.sh`` wrote the shared ``~/.local/bin/waza``: a concurrent exec
hit a half-written binary. The fix added ``require_serial: true`` plus an
atomic install. This gate keeps the discipline from regressing: a FUTURE hook
that provisions a shared binary must also be serial, or prek may race it again
(retro #1152, #1155).

The rule:

* Parse ``.pre-commit-config.yaml``.
* A hook is "provisioning" when its ``entry`` references an installer script
  -- matched by ``install_<name>.sh`` (e.g. ``scripts/install_waza.sh``). These
  write a shared binary to a fixed path, so parallel copies race.
* Every provisioning hook must declare ``require_serial: true``. Fail loud
  otherwise.

CLI::

    python3 scripts/scan_provisioning_hook_serial.py verify  # exit 1 on a gap
    python3 scripts/scan_provisioning_hook_serial.py list     # print such hooks

Fails loud per CLAUDE.md section 4. Tested by
``tests/test_scan_provisioning_hook_serial.py``. Refs #1150, #1152, #1155.

Contract:
    Inputs: the ``verify`` or ``list`` subcommand; ``.pre-commit-config.yaml``
        at the repo root. No stdin, no env input.
    Outputs: ``verify`` prints ``::error::`` per provisioning hook missing
        ``require_serial: true`` and a one-line summary, exit 0 when clean and
        exit 1 on any gap; ``list`` prints each provisioning hook id and its
        require_serial value.
    Failure policy: fails loud per CLAUDE.md section 4 (gate: a non-serial
        provisioning hook exits non-zero; an unparseable config exits non-zero).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / ".pre-commit-config.yaml"

# An ``entry`` that runs a shared-binary installer script.
_PROVISIONING_RE = re.compile(r"install_\w+\.sh")


def provisioning_hooks(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every hook whose entry references an installer script."""
    hooks: list[dict[str, Any]] = []
    for repo in config.get("repos", []) or []:
        for hook in repo.get("hooks", []) or []:
            entry = str(hook.get("entry", ""))
            if _PROVISIONING_RE.search(entry):
                hooks.append(hook)
    return hooks


def find_gaps(config: dict[str, Any]) -> list[str]:
    """Return ``::error::`` strings for provisioning hooks not require_serial."""
    errors: list[str] = []
    for hook in provisioning_hooks(config):
        if hook.get("require_serial") is not True:
            hook_id = hook.get("id", "<unknown>")
            errors.append(
                f"::error::pre-commit hook '{hook_id}' provisions a shared "
                f"binary (entry runs an install_*.sh) but is not "
                f"'require_serial: true'. Parallel copies race on the shared "
                f"path (PermissionError, #1150). Add require_serial: true."
            )
    return errors


def _load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"::error::cannot read {path}: {exc}") from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise SystemExit(f"::error::{path} did not parse as a mapping")
    return data


def _cmd_verify(_args: argparse.Namespace) -> int:
    errors = find_gaps(_load_config())
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(f"FAIL: {len(errors)} provisioning hook(s) not require_serial.",
              file=sys.stderr)
        return 1
    print("OK: every provisioning pre-commit hook is require_serial.")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    for hook in provisioning_hooks(_load_config()):
        print(f"{hook.get('id', '<unknown>')}\trequire_serial={hook.get('require_serial')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify", help="fail on a non-serial provisioning hook").set_defaults(
        func=_cmd_verify
    )
    sub.add_parser("list", help="print provisioning hooks and their serial flag").set_defaults(
        func=_cmd_list
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
