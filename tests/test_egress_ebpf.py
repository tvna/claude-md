"""Tests for ``.devcontainer/scripts/_egress-ebpf.sh`` and ``egress-correlation.bt``.

These exercise the pure ``check`` detection seam (no root, no privileged calls)
with its kernel/capability inputs overridden via env, the default-off no-op
behaviour of ``start`` / ``stop``, the graceful-skip path, and structural
invariants of the bpftrace program. The actual eBPF attach / event capture
CANNOT be exercised here (no CAP_BPF / BTF / tracefs in CI/sandbox); the
end-to-end steps live in ``docs/runbooks/devcontainers.md`` for a capable
NET_ADMIN/CAP_BPF devcontainer.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".devcontainer" / "scripts" / "_egress-ebpf.sh"
BT = REPO_ROOT / ".devcontainer" / "scripts" / "egress-correlation.bt"

# CapEff hex (no 0x) with CAP_PERFMON (bit 38) and CAP_BPF (bit 39) set.
CAP_BPF_PERFMON = format((1 << 38) | (1 << 39), "x")


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _supported_env(tmp_path: Path) -> dict[str, str]:
    """An env where every ``check`` precondition is satisfiable unprivileged."""
    btf = tmp_path / "vmlinux"
    btf.write_text("", encoding="utf-8")
    tracefs = tmp_path / "tracing"
    tracefs.mkdir()
    env = dict(os.environ)
    env.update(
        {
            "BPFTRACE_BIN": "/bin/sh",  # a real, on-PATH executable stands in
            "BTF_PATH": str(btf),
            "TRACEFS_PATH": str(tracefs),
            "CAP_EFF": CAP_BPF_PERFMON,
        }
    )
    return env


def _unsupported_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "BPFTRACE_BIN": "/nonexistent/bpftrace",
            "BTF_PATH": "/nonexistent/btf",
            "TRACEFS_PATH": "/nonexistent/tracing",
            "CAP_EFF": "0",
        }
    )
    return env


def test_check_reports_supported_when_all_preconditions_met(tmp_path: Path) -> None:
    res = _run("check", env=_supported_env(tmp_path))
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "supported"


def test_check_skips_with_reasons_when_unsupported() -> None:
    res = _run("check", env=_unsupported_env())
    assert res.returncode == 3
    assert res.stdout.strip() == "skip"
    # Every blocking precondition is named on stderr.
    assert "bpftrace not found" in res.stderr
    assert "BTF" in res.stderr
    assert "tracefs" in res.stderr
    assert "CAP_BPF" in res.stderr


def test_start_is_noop_when_disabled() -> None:
    env = dict(os.environ)
    env.pop("EGRESS_EBPF", None)
    res = _run("start", env=env)
    assert res.returncode == 0
    assert "disabled (opt-in" in res.stderr


def test_stop_is_noop_when_disabled() -> None:
    env = dict(os.environ)
    env.pop("EGRESS_EBPF", None)
    res = _run("stop", env=env)
    assert res.returncode == 0
    assert "disabled (opt-in" in res.stderr


def test_start_skips_gracefully_on_unsupported_kernel() -> None:
    # Enabled but the kernel cannot run eBPF: start must skip, not fail the boot.
    env = _unsupported_env()
    env["EGRESS_EBPF"] = "1"
    res = _run("start", env=env)
    assert res.returncode == 0
    assert "skipped" in res.stderr


def test_unknown_subcommand_exits_usage() -> None:
    res = _run("bogus")
    assert res.returncode == 64
    assert "usage:" in res.stderr


def test_script_syntax_is_valid() -> None:
    res = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_script_sources_egress_lib_for_shared_helpers() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "_egress-lib.sh" in text


def test_bt_program_records_correlation_without_payload_contents() -> None:
    text = BT.read_text(encoding="utf-8")
    # Probes that establish process<->egress correlation.
    assert "kprobe:tcp_connect" in text
    assert "tracepoint:syscalls:sys_enter_openat" in text
    # Records pid + comm and the destination / path only.
    assert "pid" in text
    assert "comm" in text
    assert "ntop(" in text
    # Must NEVER read syscall payload buffers (no write/read buffer contents).
    assert "args->buf" not in text
    assert "str(args->buf" not in text
    # The no-content guarantee is documented in the program itself.
    assert "payload contents NOT recorded" in text


def test_flake_declares_bpftrace() -> None:
    flake = (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")
    assert "bpftrace" in flake


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_devcontainer_adds_bpf_and_perfmon_caps_not_sys_admin(agent: str) -> None:
    config = json.loads(
        (REPO_ROOT / ".devcontainer" / agent / "devcontainer.json").read_text(encoding="utf-8")
    )
    run_args = config.get("runArgs", [])
    assert "--cap-add=BPF" in run_args
    assert "--cap-add=PERFMON" in run_args
    # CAP_BPF/CAP_PERFMON are the least-privilege path; never fall back to SYS_ADMIN.
    assert "--cap-add=SYS_ADMIN" not in run_args
    assert not any("SYS_ADMIN" in arg for arg in run_args)


def test_runbook_documents_ebpf_monitor_and_honest_limitation() -> None:
    doc = (REPO_ROOT / "docs" / "runbooks" / "devcontainers.md").read_text(encoding="utf-8")
    assert "EGRESS_EBPF" in doc
    assert "_egress-ebpf.sh" in doc
    assert "egress-correlation.bt" in doc
    assert "bpftrace" in doc
    assert "CVE-2025-32955" in doc
    # The graceful-skip posture is documented.
    assert "skips gracefully" in doc or "skip" in doc
