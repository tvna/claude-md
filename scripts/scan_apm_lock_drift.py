#!/usr/bin/env python3
"""Fail when apm.lock.yaml does not lock the MCP deps declared in apm.yml.

``apm.yml`` is the source of truth for dependencies; ``apm.lock.yaml`` is the
resolved lock. The existing CI gates run ``apm compile`` and diff the compiled
``CLAUDE.md`` / ``AGENTS.md``, but nothing guards the lockfile itself. So when a
new MCP server is added to ``apm.yml`` and ``apm install`` is not re-run, the
lockfile silently loses its ``mcp_servers`` / ``mcp_configs`` block and drifts
(observed for ``context7``: declared in apm.yml and present in .mcp.json, yet
absent from apm.lock.yaml). Refs #1321.

This gate makes that discipline deterministic and registry-free. It reads the
MCP deps declared under ``dependencies.mcp`` in ``apm.yml`` and the locked
``mcp_servers`` / ``mcp_configs`` in ``apm.lock.yaml``, then fails on any:

* declared MCP server missing from ``mcp_servers`` or ``mcp_configs``;
* locked transport/url that does not match the declaration;
* locked MCP server with no matching declaration (orphan left after removal).

It does NOT re-resolve over the network: comparing the two committed files is
enough to catch the drift class above without a flaky registry round-trip. The
fix when it fires is to run ``apm install`` and commit the regenerated lockfile.

CLI::

    python3 scripts/scan_apm_lock_drift.py verify  # exit 1 on drift
    python3 scripts/scan_apm_lock_drift.py list     # print declared vs locked

Fails loud per CLAUDE.md section 4. Tested by
``tests/test_scan_apm_lock_drift.py``. Refs #1321.

Contract:
    Inputs: the ``verify`` or ``list`` subcommand; ``apm.yml`` (declared MCP
        deps) and ``apm.lock.yaml`` (locked MCP block) at the repo root. No
        stdin, no env input, no network.
    Outputs: ``verify`` prints ``::error::`` annotations on stderr per drift row
        and a one-line summary, exit 0 when clean and exit 1 on any drift;
        ``list`` prints the declared and locked MCP servers on stdout.
    Failure policy: fails loud per CLAUDE.md section 4 (gate: any lockfile drift
        exits non-zero; a missing or unparseable apm.yml / apm.lock.yaml exits
        non-zero).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

APM_YML_REL = "apm.yml"
APM_LOCK_REL = "apm.lock.yaml"

# MCP config fields compared between declaration and lock. ``name`` is the dict
# key on both sides, so only the wire-relevant fields are diffed here.
COMPARED_FIELDS: tuple[str, ...] = ("transport", "url")


def declared_mcp(apm_yml_text: str) -> dict[str, dict[str, str]]:
    """Return ``{name: {transport, url}}`` for each MCP dep in apm.yml."""
    data = yaml.safe_load(apm_yml_text) or {}
    deps = (data.get("dependencies") or {}).get("mcp") or []
    result: dict[str, dict[str, str]] = {}
    for entry in deps:
        if not isinstance(entry, dict) or "name" not in entry:
            continue  # malformed row: nothing to lock against
        name = str(entry["name"])
        result[name] = {f: str(entry[f]) for f in COMPARED_FIELDS if f in entry}
    return result


def locked_mcp(lock_text: str) -> tuple[set[str], dict[str, dict[str, str]]]:
    """Return ``(mcp_servers set, {name: {transport, url}})`` from the lockfile."""
    data = yaml.safe_load(lock_text) or {}
    servers = {str(s) for s in (data.get("mcp_servers") or [])}
    configs: dict[str, dict[str, str]] = {}
    for name, cfg in (data.get("mcp_configs") or {}).items():
        if not isinstance(cfg, dict):
            continue
        configs[str(name)] = {f: str(cfg[f]) for f in COMPARED_FIELDS if f in cfg}
    return servers, configs


def find_drift(
    declared: dict[str, dict[str, str]],
    servers: set[str],
    configs: dict[str, dict[str, str]],
) -> list[str]:
    """Return ``::error::`` strings for every apm.yml-vs-lock MCP mismatch."""
    errors: list[str] = []
    remediation = (
        "run `apm install` and commit the regenerated apm.lock.yaml (#1321)"
    )
    for name, decl in sorted(declared.items()):
        if name not in servers:
            errors.append(
                f"::error file={APM_LOCK_REL}::declared MCP server '{name}' is "
                f"missing from mcp_servers -- {remediation}."
            )
        if name not in configs:
            errors.append(
                f"::error file={APM_LOCK_REL}::declared MCP server '{name}' is "
                f"missing from mcp_configs -- {remediation}."
            )
            continue
        for field, want in decl.items():
            got = configs[name].get(field)
            if got != want:
                errors.append(
                    f"::error file={APM_LOCK_REL}::MCP server '{name}' {field} "
                    f"drifted: apm.yml='{want}' lock='{got}' -- {remediation}."
                )
    for name in sorted(servers | set(configs)):
        if name not in declared:
            errors.append(
                f"::error file={APM_LOCK_REL}::locked MCP server '{name}' is not "
                f"declared in apm.yml -- {remediation}."
            )
    return errors


def _read(repo_root: Path, rel: str) -> str:
    path = repo_root / rel
    if not path.is_file():
        raise SystemExit(f"::error::{rel} not found at {path}")
    return path.read_text(encoding="utf-8")


def _load(repo_root: Path) -> tuple[
    dict[str, dict[str, str]], set[str], dict[str, dict[str, str]]
]:
    declared = declared_mcp(_read(repo_root, APM_YML_REL))
    servers, configs = locked_mcp(_read(repo_root, APM_LOCK_REL))
    return declared, servers, configs


def _cmd_verify(_args: argparse.Namespace) -> int:
    declared, servers, configs = _load(REPO_ROOT)
    errors = find_drift(declared, servers, configs)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(
            f"FAIL: {len(errors)} apm.lock.yaml MCP drift row(s) vs apm.yml.",
            file=sys.stderr,
        )
        return 1
    print(f"OK: {len(declared)} declared MCP server(s) match apm.lock.yaml.")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    declared, servers, configs = _load(REPO_ROOT)
    print(f"declared (apm.yml): {sorted(declared)}")
    print(f"mcp_servers (lock): {sorted(servers)}")
    print(f"mcp_configs (lock): {sorted(configs)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify", help="fail on apm.lock.yaml MCP drift").set_defaults(
        func=_cmd_verify
    )
    sub.add_parser("list", help="print declared vs locked MCP servers").set_defaults(
        func=_cmd_list
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
