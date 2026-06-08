"""Tests for ``scripts/gen_mcp_json.py`` (renders .mcp.json from apm.yml)."""

from __future__ import annotations

import json
from pathlib import Path

import gen_mcp_json as gen
import pytest

pytestmark = pytest.mark.shard_preflight


# --- render_mcp_config ------------------------------------------------------


def test_render_http_server() -> None:
    data = {"dependencies": {"mcp": [{"name": "context7", "transport": "http", "url": "https://mcp.example/mcp"}]}}
    assert gen.render_mcp_config(data) == {
        "mcpServers": {"context7": {"type": "http", "url": "https://mcp.example/mcp"}}
    }


def test_render_sse_server() -> None:
    data = {"dependencies": {"mcp": [{"name": "s", "transport": "sse", "url": "https://e/sse"}]}}
    assert gen.render_mcp_config(data) == {"mcpServers": {"s": {"type": "sse", "url": "https://e/sse"}}}


def test_render_defaults_to_http_transport() -> None:
    data = {"dependencies": {"mcp": [{"name": "s", "url": "https://e/mcp"}]}}
    assert gen.render_mcp_config(data)["mcpServers"]["s"]["type"] == "http"


def test_render_stdio_with_args() -> None:
    data = {"dependencies": {"mcp": [{"name": "local", "transport": "stdio", "command": "run", "args": ["--x"]}]}}
    assert gen.render_mcp_config(data) == {
        "mcpServers": {"local": {"type": "stdio", "command": "run", "args": ["--x"]}}
    }


def test_render_stdio_without_args_omits_key() -> None:
    data = {"dependencies": {"mcp": [{"name": "local", "transport": "stdio", "command": "run"}]}}
    assert gen.render_mcp_config(data) == {"mcpServers": {"local": {"type": "stdio", "command": "run"}}}


def test_render_no_mcp_block_yields_empty_servers() -> None:
    assert gen.render_mcp_config({"dependencies": {}}) == {"mcpServers": {}}
    assert gen.render_mcp_config({}) == {"mcpServers": {}}


@pytest.mark.parametrize(
    "data",
    [
        {"dependencies": {"mcp": ["not-a-mapping"]}},
        {"dependencies": {"mcp": [{"transport": "http", "url": "https://e"}]}},  # missing name
        {"dependencies": {"mcp": [{"name": "", "transport": "http", "url": "https://e"}]}},
        {"dependencies": {"mcp": [{"name": "s", "transport": "http"}]}},  # http missing url
        {"dependencies": {"mcp": [{"name": "s", "transport": "stdio"}]}},  # stdio missing command
        {"dependencies": {"mcp": [{"name": "s", "transport": "carrier-pigeon"}]}},  # unknown transport
    ],
)
def test_render_rejects_malformed_declarations(data: dict) -> None:
    with pytest.raises(ValueError):
        gen.render_mcp_config(data)


# --- repo apm.yml integration ----------------------------------------------


def test_repo_apm_yml_renders() -> None:
    """The committed apm.yml must render without error (it is the SoT)."""
    config = gen.render_mcp_config(gen._load_apm())
    assert "context7" in config["mcpServers"]


# --- CLI (main) -------------------------------------------------------------


def _patch_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, apm_body: str) -> Path:
    apm = tmp_path / "apm.yml"
    apm.write_text(apm_body, encoding="utf-8")
    mcp = tmp_path / ".mcp.json"
    monkeypatch.setattr(gen, "APM_YML", apm)
    monkeypatch.setattr(gen, "MCP_JSON", mcp)
    return mcp


_APM = "dependencies:\n  mcp:\n  - name: context7\n    transport: http\n    url: https://e/mcp\n"


def test_main_write_creates_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mcp = _patch_paths(monkeypatch, tmp_path, _APM)
    assert gen.main([]) == 0
    written = json.loads(mcp.read_text(encoding="utf-8"))
    assert written["mcpServers"]["context7"]["url"] == "https://e/mcp"
    assert mcp.read_text(encoding="utf-8").endswith("}\n")


def test_main_write_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mcp = _patch_paths(monkeypatch, tmp_path, _APM)
    gen.main([])
    first = mcp.read_text(encoding="utf-8")
    gen.main([])
    assert mcp.read_text(encoding="utf-8") == first


def test_main_check_passes_when_current(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path, _APM)
    gen.main([])
    assert gen.main(["--check"]) == 0


def test_main_check_fails_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path, _APM)
    assert gen.main(["--check"]) == 1


def test_main_check_fails_when_stale(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mcp = _patch_paths(monkeypatch, tmp_path, _APM)
    mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")
    assert gen.main(["--check"]) == 1


def test_main_render_error_returns_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = "dependencies:\n  mcp:\n  - transport: http\n    url: https://e/mcp\n"  # no name
    _patch_paths(monkeypatch, tmp_path, bad)
    assert gen.main([]) == 2


def test_load_apm_missing_exits_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gen, "APM_YML", tmp_path / "absent.yml")
    with pytest.raises(SystemExit) as exc:
        gen._load_apm()
    assert exc.value.code == 2


def test_load_apm_invalid_yaml_exits_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path, "key: [unterminated\n")
    with pytest.raises(SystemExit) as exc:
        gen._load_apm()
    assert exc.value.code == 2


def test_load_apm_non_mapping_exits_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(SystemExit) as exc:
        gen._load_apm()
    assert exc.value.code == 2
