"""Tests for the $CLAUDE_ENV_FILE persistence-centralization gate.

scripts/scan_session_path_drift.py keeps the #1230 symmetry from regressing:
only scripts/_session_path.sh may write $CLAUDE_ENV_FILE; every other
scripts/*.sh must persist PATH via persist_session_path. These tests pin the
clean repo state, the stray-write failure, the gutted-helper failure, and that
the gate is wired into preflight_all.py + verify-agents.yml.

Refs #1230.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import scan_session_path_drift as gate

pytestmark = pytest.mark.shard_preflight
REPO_ROOT = Path(__file__).resolve().parents[1]


def _stage(tmp_path: Path, files: dict[str, str]) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (scripts / name).write_text(body, encoding="utf-8")
    return scripts


_HELPER_BODY = (
    "#!/usr/bin/env bash\n"
    "persist_session_path() {\n"
    '  echo "export PATH=\\"${1}:\\$PATH\\"" >> "${CLAUDE_ENV_FILE}"\n'
    "}\n"
)


def test_real_repo_is_clean() -> None:
    """The shipped repo must satisfy the invariant."""
    assert gate.stray_writes(REPO_ROOT / "scripts") == []
    assert gate.helper_writes_env_file(REPO_ROOT / "scripts") is True


def test_clean_staged_repo_passes(tmp_path: Path) -> None:
    scripts = _stage(
        tmp_path,
        {
            "_session_path.sh": _HELPER_BODY,
            "install-foo.sh": (
                "#!/usr/bin/env bash\n"
                '. "${SCRIPT_DIR}/_session_path.sh"\n'
                'persist_session_path "${HOME}/.local/bin"\n'
            ),
        },
    )
    assert gate.stray_writes(scripts) == []
    assert gate.helper_writes_env_file(scripts) is True


def test_inline_write_outside_helper_is_flagged(tmp_path: Path) -> None:
    scripts = _stage(
        tmp_path,
        {
            "_session_path.sh": _HELPER_BODY,
            "install-bar.sh": (
                "#!/usr/bin/env bash\n"
                'echo "export PATH=\\"${d}:\\$PATH\\"" >> "$CLAUDE_ENV_FILE"\n'
            ),
        },
    )
    strays = gate.stray_writes(scripts)
    assert [w.script for w in strays] == ["install-bar.sh"]


def test_comment_mention_is_not_flagged(tmp_path: Path) -> None:
    """A comment naming the variable carries no redirection, so it is fine."""
    scripts = _stage(
        tmp_path,
        {
            "_session_path.sh": _HELPER_BODY,
            "install-baz.sh": (
                "#!/usr/bin/env bash\n"
                "# Persist PATH for the session via $CLAUDE_ENV_FILE.\n"
                'persist_session_path "${HOME}/.local/bin"\n'
            ),
        },
    )
    assert gate.stray_writes(scripts) == []


def test_gutted_helper_is_flagged(tmp_path: Path) -> None:
    scripts = _stage(
        tmp_path,
        {
            "_session_path.sh": (
                "#!/usr/bin/env bash\n"
                "persist_session_path() { export PATH=\"${1}:${PATH}\"; }\n"
            ),
        },
    )
    assert gate.helper_writes_env_file(scripts) is False


def test_verify_exit_codes(tmp_path: Path) -> None:
    clean = _stage(tmp_path / "clean", {"_session_path.sh": _HELPER_BODY})
    assert gate.main(["verify", "--scripts-dir", str(clean)]) == 0

    dirty = _stage(
        tmp_path / "dirty",
        {
            "_session_path.sh": _HELPER_BODY,
            "x.sh": 'echo foo >> "${CLAUDE_ENV_FILE}"\n',
        },
    )
    assert gate.main(["verify", "--scripts-dir", str(dirty)]) == 1


def test_gate_runs_in_ci_and_preflight() -> None:
    """The gate must be wired into both CI and the preflight aggregator."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "verify-agents.yml").read_text(
        encoding="utf-8"
    )
    assert "scan_session_path_drift.py verify" in workflow

    manifest = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "preflight_all.py"), "--list"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "scan_session_path_drift" in manifest
