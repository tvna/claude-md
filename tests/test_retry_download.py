"""Behavior tests for ``scripts/_retry.sh`` (Refs #2038).

``_retry.sh`` is a sourced bash helper, so each test drives it through
``bash -c 'source scripts/_retry.sh; retry_download ...'`` with a stubbed
``curl`` (and ``sleep``) on ``PATH``. ``RETRY_BASE_DELAY=0`` keeps the suite
free of real sleeps; a ``sleep`` stub records the backoff delays so the
exponential schedule is asserted without wall-clock cost.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RETRY_SH = _REPO_ROOT / "scripts" / "_retry.sh"


def _make_curl_stub(stub_dir: Path, fail_count: int) -> None:
    """Write a ``curl`` stub that fails its first ``fail_count`` calls.

    The stub increments a counter file on each call; while the count is at or
    below ``fail_count`` it exits non-zero, otherwise it writes the output file
    (``-o DEST`` is the last argument from ``retry_download``) and exits 0.
    """
    counter = stub_dir / "curl.count"
    counter.write_text("0", encoding="utf-8")
    curl = stub_dir / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        f'count="$(cat "{counter}")"\n'
        'count=$((count + 1))\n'
        f'printf "%s" "$count" > "{counter}"\n'
        # Destination is the argument after -o.
        'dest=""\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "-o" ]; then dest="$2"; shift 2; continue; fi\n'
        '  shift\n'
        'done\n'
        f'if [ "$count" -le {fail_count} ]; then exit 22; fi\n'
        '[ -n "$dest" ] && printf "ok" > "$dest"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)


def _make_sleep_stub(stub_dir: Path) -> Path:
    """Write a ``sleep`` stub that records each delay it is asked to wait."""
    log = stub_dir / "sleep.log"
    sleep = stub_dir / "sleep"
    sleep.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$1" >> "{log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    sleep.chmod(0o755)
    return log


def _run_retry(
    stub_dir: Path,
    dest: Path,
    *,
    base_delay: str = "0",
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{stub_dir}:/usr/bin:/bin",
        "RETRY_BASE_DELAY": base_delay,
        "HOME": str(stub_dir),
    }
    script = (
        f'source "{_RETRY_SH}"\n'
        f'retry_download "https://example.test/asset.tgz" "{dest}" '
        f'"demotool" "scripts/install-demotool.sh"\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_success_first_attempt_no_retry(tmp_path: Path) -> None:
    """A download that succeeds immediately returns 0 and makes one curl call."""
    _make_curl_stub(tmp_path, fail_count=0)
    dest = tmp_path / "out.tgz"
    result = _run_retry(tmp_path, dest)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "curl.count").read_text(encoding="utf-8") == "1"
    assert dest.read_text(encoding="utf-8") == "ok"


def test_recovers_after_transient_failures(tmp_path: Path) -> None:
    """Two failures then success: 3 curl calls total, return 0."""
    _make_curl_stub(tmp_path, fail_count=2)
    dest = tmp_path / "out.tgz"
    result = _run_retry(tmp_path, dest)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "curl.count").read_text(encoding="utf-8") == "3"


def test_exhausts_four_attempts_then_fails(tmp_path: Path) -> None:
    """Permanent failure: 4 curl attempts (initial + 3 retries), return 1."""
    _make_curl_stub(tmp_path, fail_count=99)
    dest = tmp_path / "out.tgz"
    result = _run_retry(tmp_path, dest)
    assert result.returncode == 1
    assert (tmp_path / "curl.count").read_text(encoding="utf-8") == "4"


def test_exponential_backoff_schedule(tmp_path: Path) -> None:
    """Backoff with base 2 sleeps 2, 4, 8 seconds across the three retries."""
    _make_curl_stub(tmp_path, fail_count=99)
    log = _make_sleep_stub(tmp_path)
    dest = tmp_path / "out.tgz"
    result = _run_retry(tmp_path, dest, base_delay="2")
    assert result.returncode == 1
    delays = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    assert delays == ["2", "4", "8"]


def test_failure_emits_loud_stderr_banner(tmp_path: Path) -> None:
    """On exhaustion the helper prints a loud, actionable stderr banner."""
    _make_curl_stub(tmp_path, fail_count=99)
    dest = tmp_path / "out.tgz"
    result = _run_retry(tmp_path, dest)
    assert "DOWNLOAD FAILED" in result.stderr
    assert "demotool" in result.stderr
    assert "scripts/install-demotool.sh" in result.stderr


def test_failure_emits_sessionstart_additional_context_json(tmp_path: Path) -> None:
    """stdout carries exactly one valid SessionStart additionalContext object."""
    _make_curl_stub(tmp_path, fail_count=99)
    dest = tmp_path / "out.tgz"
    result = _run_retry(tmp_path, dest)
    stdout = result.stdout.strip()
    payload = json.loads(stdout)
    hook_out = payload["hookSpecificOutput"]
    assert hook_out["hookEventName"] == "SessionStart"
    assert "demotool" in hook_out["additionalContext"]


def test_success_keeps_stdout_clean(tmp_path: Path) -> None:
    """A successful download writes nothing to stdout (JSON-only contract)."""
    _make_curl_stub(tmp_path, fail_count=0)
    dest = tmp_path / "out.tgz"
    result = _run_retry(tmp_path, dest)
    assert result.stdout == ""
