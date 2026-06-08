from __future__ import annotations

from pathlib import Path

import pytest
from _allowlist import resolve_hosts

pytestmark = pytest.mark.shard_ci_ops

ROOT = Path(__file__).resolve().parents[1]
NETWORK_DIR = ROOT / ".devcontainer" / "network"


def test_shared_allowlist_includes_consolidated_agent_api_hosts() -> None:
    # The per-agent claude/codex allowlists were consolidated into the single
    # shared.allowlist (#1420), so every agent endpoint resolves from it.
    hosts = resolve_hosts(NETWORK_DIR / "shared.allowlist")

    assert {"api.anthropic.com", "api.openai.com", "auth.openai.com"} <= hosts
