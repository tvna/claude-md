from __future__ import annotations

from pathlib import Path

import pytest
from _allowlist import resolve_hosts

pytestmark = pytest.mark.shard_ci_ops

ROOT = Path(__file__).resolve().parents[1]
NETWORK_DIR = ROOT / ".devcontainer" / "network"


def test_codex_allowlist_includes_openai_api_and_oauth_hosts() -> None:
    hosts = resolve_hosts(NETWORK_DIR / "codex.allowlist")

    assert {"api.openai.com", "auth.openai.com"} <= hosts
