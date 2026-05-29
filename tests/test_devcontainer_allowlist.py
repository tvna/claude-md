from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

ROOT = Path(__file__).resolve().parents[1]
NETWORK_DIR = ROOT / ".devcontainer" / "network"


def read_allowlist(path: Path) -> set[str]:
    hosts: set[str] = set()

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("@include "):
            hosts.update(read_allowlist(path.parent / line.removeprefix("@include ")))
            continue
        hosts.add(line)

    return hosts


def test_codex_allowlist_includes_openai_api_and_oauth_hosts() -> None:
    hosts = read_allowlist(NETWORK_DIR / "codex.allowlist")

    assert {"api.openai.com", "auth.openai.com"} <= hosts
