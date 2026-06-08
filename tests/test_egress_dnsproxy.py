"""Tests for ``.devcontainer/scripts/_egress-dnsproxy.sh``.

These exercise the ``generate-config`` seam -- pure stdout, no root, no kernel
calls -- and the default-off no-op behaviour of ``start`` / ``stop``. The
dnsmasq / ipset / resolv.conf kernel effects CANNOT be exercised here (no
NET_ADMIN in CI/sandbox); the end-to-end steps live in
``docs/runbooks/devcontainers.md`` for a NET_ADMIN devcontainer.

The script shells out to ``bash`` (present on every supported runner) and
sources ``_egress-lib.sh`` for ``read_allowlist``, so generation stays in
agreement with the Python parser via ``scan_allowlist_parser_parity.py``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".devcontainer" / "scripts" / "_egress-dnsproxy.sh"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _fixture(tmp_path: Path) -> Path:
    """A two-host allowlist exercising ``@include`` and comment stripping."""
    (tmp_path / "shared.allowlist").write_text("github.com  # shared host\n", encoding="utf-8")
    agent = tmp_path / "agent.allowlist"
    agent.write_text(
        "@include shared.allowlist\n# comment-only line\napi.anthropic.com  # claude api\n",
        encoding="utf-8",
    )
    return agent


def test_generate_config_emits_server_and_ipset_per_host(tmp_path: Path) -> None:
    agent = _fixture(tmp_path)
    res = _run("generate-config", str(agent), "--upstream", "1.1.1.1")
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()

    assert "no-resolv" in lines
    assert "server=1.1.1.1" in lines  # default upstream for non-matching queries
    for host in ("api.anthropic.com", "github.com"):
        assert f"server=/{host}/1.1.1.1" in lines
        assert f"ipset=/{host}/allowed-egress" in lines

    # Exactly one ipset line per resolved host (no duplicates, no extras).
    ipset_lines = [ln for ln in lines if ln.startswith("ipset=/")]
    assert len(ipset_lines) == 2


def test_generate_config_is_sorted_and_deterministic(tmp_path: Path) -> None:
    agent = _fixture(tmp_path)
    first = _run("generate-config", str(agent), "--upstream", "1.1.1.1")
    second = _run("generate-config", str(agent), "--upstream", "1.1.1.1")
    assert first.stdout == second.stdout

    # Hosts emitted in sort -u order: api.anthropic.com before github.com.
    body = first.stdout
    assert body.index("server=/api.anthropic.com/") < body.index("server=/github.com/")


def test_generate_config_supports_multiple_upstreams_and_ipset_name(tmp_path: Path) -> None:
    agent = _fixture(tmp_path)
    res = _run(
        "generate-config",
        str(agent),
        "--upstream",
        "1.1.1.1",
        "--upstream",
        "8.8.8.8",
        "--ipset-name",
        "custom-set",
    )
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert "server=/github.com/1.1.1.1" in lines
    assert "server=/github.com/8.8.8.8" in lines
    assert "ipset=/github.com/custom-set" in lines


def test_generate_config_runs_unprivileged_and_writes_nothing(tmp_path: Path) -> None:
    agent = _fixture(tmp_path)
    before = set(tmp_path.iterdir())
    res = _run("generate-config", str(agent), "--upstream", "1.1.1.1")
    assert res.returncode == 0, res.stderr
    # generate-config is a pure stdout seam: it must not create files.
    assert set(tmp_path.iterdir()) == before


def test_generate_config_rejects_missing_file(tmp_path: Path) -> None:
    res = _run("generate-config", str(tmp_path / "nope.allowlist"), "--upstream", "1.1.1.1")
    assert res.returncode == 66
    assert "not found" in res.stderr


def test_generate_config_errors_on_empty_allowlist(tmp_path: Path) -> None:
    empty = tmp_path / "empty.allowlist"
    empty.write_text("# only a comment\n", encoding="utf-8")
    res = _run("generate-config", str(empty), "--upstream", "1.1.1.1")
    assert res.returncode == 78
    assert "empty" in res.stderr


def _env_without_proxy_flag() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("EGRESS_DNS_PROXY", None)
    return env


def test_start_is_noop_when_disabled(tmp_path: Path) -> None:
    agent = _fixture(tmp_path)
    res = _run("start", str(agent), env=_env_without_proxy_flag())
    assert res.returncode == 0
    assert "disabled (opt-in" in res.stderr


def test_stop_is_noop_when_disabled() -> None:
    res = _run("stop", env=_env_without_proxy_flag())
    assert res.returncode == 0
    assert "disabled (opt-in" in res.stderr


def test_unknown_subcommand_exits_usage() -> None:
    res = _run("bogus")
    assert res.returncode == 64
    assert "usage:" in res.stderr


def test_script_syntax_is_valid() -> None:
    res = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_script_sources_egress_lib_for_single_source_parsing() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "_egress-lib.sh" in text
    assert "read_allowlist" in text


def test_flake_declares_dnsmasq_and_ipset() -> None:
    flake = (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")
    assert "dnsmasq" in flake
    assert "ipset" in flake


def test_runbook_documents_proxy_and_honest_limitation() -> None:
    doc = (REPO_ROOT / "docs" / "runbooks" / "devcontainers.md").read_text(encoding="utf-8")
    assert "EGRESS_DNS_PROXY" in doc
    assert "_egress-dnsproxy.sh" in doc
    assert "CVE-2025-32955" in doc
