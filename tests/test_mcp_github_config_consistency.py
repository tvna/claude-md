"""Contract tests for the local GitHub MCP server declaration (#1063, #1067).

``apm.yml`` is the single source of truth: it declares the `github` stdio server
(under ``dependencies.mcp``) pointing at the launch wrapper. The generated
``.mcp.json`` mirror; rendered by ``scripts/gen_mcp_json.py``; is prohibited
from being committed (repo-scope #58/#1067); it must stay gitignored so the
render cannot accidentally check it in.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.shard_default

ROOT = Path(__file__).resolve().parents[1]
APM_YML = ROOT / "apm.yml"
WRAPPER = "scripts/mcp_github_launch.sh"


def test_apm_yml_declares_github_stdio_server_via_wrapper() -> None:
    data = yaml.safe_load(APM_YML.read_text(encoding="utf-8"))
    servers = {s["name"]: s for s in data["dependencies"]["mcp"] if "name" in s}
    server = servers["github"]
    assert server["transport"] == "stdio"
    assert server["command"] == WRAPPER


def test_wrapper_and_minter_exist() -> None:
    assert (ROOT / WRAPPER).exists()
    assert (ROOT / "scripts" / "mint_github_app_token.py").exists()


def test_generated_mcp_json_is_gitignored() -> None:
    """The generated client mirror must never be committable."""
    result = subprocess.run(
        ["git", "check-ignore", ".mcp.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, ".mcp.json is not gitignored; the generated MCP mirror could be committed"
    assert result.stdout.strip() == ".mcp.json"


def test_no_secret_literals_in_tracked_configs() -> None:
    # The wrapper legitimately *assigns* the minted token to a shell variable
    # from a command substitution; that is not a secret literal. What must never
    # appear in any tracked file is a hardcoded credential value: a PEM private
    # key block or a GitHub token literal.
    secret_markers = ("-----BEGIN", "ghp_", "ghs_", "github_pat_")
    for path in (APM_YML, ROOT / WRAPPER):
        text = path.read_text(encoding="utf-8")
        for marker in secret_markers:
            assert marker not in text, f"{path.name} contains a secret-like literal: {marker!r}"
