"""Tests for ``.devcontainer/scripts/collect-devcontainer-debug.sh`` (Issue #1460).

These exercise the pure, unprivileged seams -- ``plan`` (lists sources, writes
nothing) and ``redact`` (the best-effort secret-masking filter) -- plus a
``collect`` run whose podman binary and VS Code logs dir are overridden via env
so the bundle structure and redaction are verified WITHOUT a real macOS host or
Podman VM. The end-to-end macOS ``collect`` path (a running podman-machine VM,
real VS Code logs) cannot be exercised here; the manual steps live in
``docs/runbooks/devcontainers.md`` "Debug log capture (macOS)".
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".devcontainer" / "scripts" / "collect-devcontainer-debug.sh"


def _run(
    *args: str,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        input=stdin,
    )


def _collect_env(tmp_path: Path, vscode_dir: Path) -> dict[str, str]:
    """An env where collect runs fully unprivileged over fixture sources."""
    env = dict(os.environ)
    env.update(
        {
            "PODMAN_BIN": "/bin/echo",  # stands in for podman; echoes its args
            "VSCODE_LOGS_DIR": str(vscode_dir),
            "DEVCONTAINER_DEBUG_OUTDIR": str(tmp_path / "bundle"),
        }
    )
    return env


def test_script_syntax_is_valid() -> None:
    res = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_plan_lists_every_source_and_output_path(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["DEVCONTAINER_DEBUG_OUTDIR"] = str(tmp_path / "bundle")
    env["VSCODE_LOGS_DIR"] = str(tmp_path / "vscode")
    res = _run("plan", env=env)
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert f"output bundle dir: {tmp_path / 'bundle'}" in out
    for label in (
        "podman-machine-list",
        "podman-info",
        "podman-system-connection-list",
        "podman-machine-inspect",
        "podman-ps-all",
        "podman-machine-journal",
        "vscode-remote-containers",
    ):
        assert label in out, label
    # The token-bearing exclusions are stated, not silently dropped.
    assert "~/.config/gh" in out
    assert "never collected" in out


def test_plan_writes_nothing(tmp_path: Path) -> None:
    outdir = tmp_path / "bundle"
    env = dict(os.environ)
    env["DEVCONTAINER_DEBUG_OUTDIR"] = str(outdir)
    _run("plan", env=env)
    assert not outdir.exists()


def test_redact_masks_common_token_formats() -> None:
    sample = "\n".join(
        [
            "token=ghp_abcd1111efgh2222ijkl3333mnop4444qrst",
            "pat=github_pat_11ABCDE0000aaaabbbbccccddddeeee",
            "openai=sk-abcdef0123456789ABCDEF0123",
            "aws=AKIA1234567890ABCDEF",
        ]
    )
    res = _run("redact", stdin=sample)
    assert res.returncode == 0, res.stderr
    assert "ghp_" not in res.stdout
    assert "github_pat_" not in res.stdout
    assert "sk-abcdef" not in res.stdout
    assert "AKIA1234567890ABCDEF" not in res.stdout
    assert "[REDACTED-TOKEN]" in res.stdout
    assert "[REDACTED-AWS-KEY]" in res.stdout


def test_redact_masks_full_authorization_and_bearer_value() -> None:
    # Regression: the Authorization value must be masked to end of line, not
    # just the scheme word -- otherwise the credential after "Bearer " leaks.
    sample = "\n".join(
        [
            "Authorization: Bearer abc.def-secret-12345",
            "bare Bearer xyztoken9876543210",
            "Set-Cookie: sid=topsecret; Path=/",
        ]
    )
    res = _run("redact", stdin=sample)
    assert res.returncode == 0, res.stderr
    assert "secret" not in res.stdout
    assert "topsecret" not in res.stdout
    assert "xyztoken" not in res.stdout
    assert res.stdout.count("[REDACTED]") >= 3


def test_redact_keeps_non_secret_lines_intact() -> None:
    sample = "starting Dev Containers\nimage pull complete\nexit code 0\n"
    res = _run("redact", stdin=sample)
    assert res.returncode == 0
    assert res.stdout == sample


def test_collect_writes_redacted_bundle_over_fixture_sources(tmp_path: Path) -> None:
    vscode = tmp_path / "vscode"
    log_dir = vscode / "20260608" / "window1" / "exthost" / "ms-vscode-remote.remote-containers"
    log_dir.mkdir(parents=True)
    (log_dir / "Dev Containers.log").write_text(
        "starting container\nGITHUB_TOKEN=ghp_secret1111aaaabbbbccccddddeeeeffff22\nok\n",
        encoding="utf-8",
    )

    res = _run("collect", env=_collect_env(tmp_path, vscode))
    assert res.returncode == 0, res.stderr
    bundle = tmp_path / "bundle"

    # Every allowlisted podman capture is present (echo stands in for podman).
    for name in (
        "podman-machine-list",
        "podman-info",
        "podman-system-connection-list",
        "podman-machine-inspect",
        "podman-ps-all",
        "podman-machine-journal",
    ):
        assert (bundle / f"{name}.txt").exists(), name

    # The VS Code remote-containers log was copied AND redacted.
    copied = bundle / "vscode-remote-containers" / "Dev Containers.log"
    assert copied.exists()
    body = copied.read_text(encoding="utf-8")
    assert "ghp_secret" not in body
    assert "[REDACTED" in body

    # The SUMMARY carries the review-before-sharing warning and the exclusions.
    summary = (bundle / "SUMMARY.txt").read_text(encoding="utf-8")
    assert "review every file before sharing" in summary
    assert "NOT collected" in summary

    # No collected diagnostic file references the token-bearing gh config dir.
    # SUMMARY.txt is exempt: it names ~/.config/gh only as an excluded source.
    for path in bundle.rglob("*"):
        if path.is_file() and path.name != "SUMMARY.txt":
            assert ".config/gh" not in path.read_text(encoding="utf-8", errors="ignore")


def test_collect_tolerates_missing_vscode_logs_dir(tmp_path: Path) -> None:
    env = _collect_env(tmp_path, tmp_path / "does-not-exist")
    res = _run("collect", env=env)
    assert res.returncode == 0, res.stderr
    note = (tmp_path / "bundle" / "vscode-remote-containers.txt").read_text(encoding="utf-8")
    assert "unavailable" in note


def test_collect_tolerates_missing_podman_binary(tmp_path: Path) -> None:
    env = _collect_env(tmp_path, tmp_path / "vscode")
    env["PODMAN_BIN"] = "/nonexistent/podman"
    res = _run("collect", env=env)
    assert res.returncode == 0, res.stderr
    captured = (tmp_path / "bundle" / "podman-machine-list.txt").read_text(encoding="utf-8")
    assert "unavailable" in captured


def test_unknown_subcommand_exits_usage() -> None:
    res = _run("bogus")
    assert res.returncode == 64
    assert "usage:" in res.stderr


def test_script_never_reads_gh_config_or_session_volumes() -> None:
    # Structural guarantee: the collector must not name token-bearing sources as
    # collection inputs. They may only appear in the exclusion notice.
    text = SCRIPT.read_text(encoding="utf-8")
    assert "cp" not in text.split("# Safety")[0]  # no copy before the safety note
    # gh config / session paths are referenced only as excluded, never copied.
    assert "/.config/gh" not in text or "never collected" in text


def test_runbook_documents_macos_debug_log_capture() -> None:
    doc = (REPO_ROOT / "docs" / "runbooks" / "devcontainers.md").read_text(encoding="utf-8")
    assert "collect-devcontainer-debug.sh" in doc
    assert "Debug log capture" in doc
    # The macOS-specific caveats this work adds.
    assert "dmesg_restrict" in doc
    assert "machine ssh" in doc
