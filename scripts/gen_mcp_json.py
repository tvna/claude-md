#!/usr/bin/env python3
"""Render the Claude Code project-scope ``.mcp.json`` from ``apm.yml``.

``apm.yml`` is the single source of truth for this repo's MCP server
declarations (the ``dependencies.mcp`` block). Claude Code, however, reads
project-scope MCP servers from a rendered ``.mcp.json`` at the repo root.
That rendered file is a build artifact -- it can carry per-client
credentials in ``env`` blocks -- so it is ``.gitignore``-d and never
committed (see ``docs/standards/repo-scope.md``).

This generator closes the gap the ignore rule opens: it deterministically
re-renders ``.mcp.json`` from ``apm.yml`` so the file's *generation* is
guaranteed even though the file itself is uncommitted. It is wired into the
``SessionStart`` hook chain in ``.claude/settings.json`` so every Claude
Code session starts with a current ``.mcp.json``.

The render is offline and idempotent: it only reads ``apm.yml`` and writes
``.mcp.json``; it never contacts an MCP endpoint or mutates user-scope
config such as ``~/.claude.json``. Secrets are never baked in -- an
authenticated server supplies its key via the runtime ``env`` indirection
documented in ``docs/runbooks/context7-mcp.md``, not from this file.

Usage::

    python3 scripts/gen_mcp_json.py          # write .mcp.json
    python3 scripts/gen_mcp_json.py --check   # exit 1 if .mcp.json is stale

Exit codes:
    0  ``.mcp.json`` written (default) or already current (``--check``).
    1  ``--check`` only: ``.mcp.json`` is missing or does not match the
       render of ``apm.yml``.
    2  ``apm.yml`` is missing or malformed.

Tested by ``tests/test_gen_mcp_json.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
APM_YML = REPO_ROOT / "apm.yml"
MCP_JSON = REPO_ROOT / ".mcp.json"


def _server_entry(server: dict[str, Any]) -> dict[str, Any]:
    """Map one ``apm.yml`` MCP declaration to a ``.mcp.json`` server object.

    Mirrors the field shape Claude Code expects: ``transport`` becomes the
    ``type`` discriminator, ``url`` carries through for the network
    transports, and a ``stdio`` declaration carries its ``command`` /
    ``args``. Unknown transports are rejected loudly rather than rendered
    into config Claude Code would silently ignore.
    """
    transport = server.get("transport", "http")
    if transport in ("http", "sse"):
        url = server.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError(f"MCP server {server.get('name')!r}: {transport} transport requires a 'url'")
        return {"type": transport, "url": url}
    if transport == "stdio":
        command = server.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError(f"MCP server {server.get('name')!r}: stdio transport requires a 'command'")
        entry: dict[str, Any] = {"type": "stdio", "command": command}
        args = server.get("args")
        if args is not None:
            entry["args"] = args
        return entry
    raise ValueError(f"MCP server {server.get('name')!r}: unsupported transport {transport!r}")


def render_mcp_config(apm_data: dict[str, Any]) -> dict[str, Any]:
    """Return the ``.mcp.json`` document rendered from parsed ``apm.yml`` data.

    Servers without a ``name`` are rejected -- the key is the server's
    identity in ``.mcp.json`` and a nameless entry is a declaration error.
    """
    servers = (apm_data.get("dependencies") or {}).get("mcp") or []
    mcp_servers: dict[str, Any] = {}
    for server in servers:
        if not isinstance(server, dict):
            raise ValueError(f"MCP declaration must be a mapping, got {type(server).__name__}")
        name = server.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("MCP declaration is missing a 'name'")
        mcp_servers[name] = _server_entry(server)
    return {"mcpServers": mcp_servers}


def _load_apm() -> dict[str, Any]:
    try:
        raw = APM_YML.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error file=apm.yml::unreadable: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        print(f"::error file=apm.yml::invalid YAML: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if not isinstance(data, dict):
        print("::error file=apm.yml::top-level document is not a mapping", file=sys.stderr)
        raise SystemExit(2)
    return data


def _serialise(config: dict[str, Any]) -> str:
    """Render the config as canonical JSON with a trailing newline."""
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render .mcp.json from apm.yml.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if .mcp.json is missing or out of date instead of writing it.",
    )
    args = parser.parse_args(argv)

    try:
        config = render_mcp_config(_load_apm())
    except ValueError as exc:
        print(f"::error file=apm.yml::{exc}", file=sys.stderr)
        return 2
    rendered = _serialise(config)

    if args.check:
        try:
            current = MCP_JSON.read_text(encoding="utf-8")
        except OSError:
            print("::error file=.mcp.json::missing; run scripts/gen_mcp_json.py", file=sys.stderr)
            return 1
        if current != rendered:
            print("::error file=.mcp.json::stale; run scripts/gen_mcp_json.py", file=sys.stderr)
            return 1
        return 0

    MCP_JSON.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
