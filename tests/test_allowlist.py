"""Tests for ``scripts/_allowlist.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath`` key
under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _allowlist import resolve_hosts, split_inline_comment

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# split_inline_comment
# ---------------------------------------------------------------------------


def test_split_inline_comment_strips_trailing_rationale() -> None:
    assert split_inline_comment("api.example.com  # why") == ("api.example.com", "why")


def test_split_inline_comment_no_hash_yields_empty_rationale() -> None:
    assert split_inline_comment("  api.example.com  ") == ("api.example.com", "")


def test_split_inline_comment_standalone_comment_has_empty_content() -> None:
    assert split_inline_comment("# just a comment") == ("", "just a comment")


# ---------------------------------------------------------------------------
# resolve_hosts
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_resolve_hosts_strips_comments_and_blank_lines(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "a.allowlist",
        "\n".join(
            [
                "# standalone comment",
                "",
                "api.example.com  # inline rationale",
                "   ",
                "cdn.example.com",
            ]
        ),
    )
    assert resolve_hosts(f) == {"api.example.com", "cdn.example.com"}


def test_resolve_hosts_expands_includes_relative_to_file(tmp_path: Path) -> None:
    _write(tmp_path / "shared.allowlist", "github.com  # shared host\n")
    f = _write(
        tmp_path / "agent.allowlist",
        "@include shared.allowlist\napi.agent.com  # agent host\n",
    )
    assert resolve_hosts(f) == {"github.com", "api.agent.com"}


def test_resolve_hosts_dedups_across_includes(tmp_path: Path) -> None:
    _write(tmp_path / "shared.allowlist", "github.com  # shared\n")
    f = _write(
        tmp_path / "agent.allowlist",
        "@include shared.allowlist\ngithub.com  # duplicate, deduped\n",
    )
    assert resolve_hosts(f) == {"github.com"}


def test_resolve_hosts_matches_committed_shared_allowlist() -> None:
    network_dir = Path(__file__).resolve().parents[1] / ".devcontainer" / "network"
    hosts = resolve_hosts(network_dir / "shared.allowlist")
    # The consolidated allowlist (#1420) carries the shared hosts plus every
    # agent's API endpoints (Anthropic and OpenAI), shared by all containers.
    assert {"api.anthropic.com", "api.openai.com", "auth.openai.com", "github.com"} <= hosts
