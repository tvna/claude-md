"""Cross-agent parity for the SessionStart provisioning installers.

The #1606 audit classified every ``scripts/install-*.sh`` SessionStart
provisioner as *shared*, and #1608 wired the formerly Claude-only ones
(rtk / apm / actionlint / waza / ccusage / zizmor / lychee / betterleaks)
into the codex target (devin mirrors codex) and widened each script's remote
gate to fire under Codex cloud as well as Claude Code on the Web.

These tests pin both halves of that contract so a future regression; an
installer wired into a strict subset of agents, or a provisioner that still
gates on ``CLAUDE_CODE_REMOTE`` alone and is therefore a no-op under Codex --
fails loudly:

* every provisioner registers on all three agents (claude, codex, devin), and
* every provisioner's session gate accepts both remote signals.

Refs #1606, #1608.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
CODEX_HOOKS = REPO_ROOT / ".codex" / "hooks.json"
DEVIN_HOOKS = REPO_ROOT / ".devin" / "hooks.v1.json"

# Bare installer stems, e.g. "install-rtk". The session_uv_local_pin provisioner
# is intentionally excluded: it is not an ``install-*.sh`` and aligns the
# local-host uv rather than provisioning a remote binary.
_INSTALLER_RE = re.compile(r"\bscripts/(install-[a-zA-Z0-9-]+)\.sh\b")

# The dual-signal session gate every provisioner must carry, mirroring
# install-uv.sh. Whitespace-tolerant so a reformat does not silently pass.
_DUAL_GATE_RE = re.compile(
    r'\[\s*"\$\{CLAUDE_CODE_REMOTE:-\}"\s*!=\s*"true"\s*\]'
    r'\s*&&\s*'
    r'\[\s*"\$\{CODEX_CODE_REMOTE:-\}"\s*!=\s*"true"\s*\]'
)

# Installers the audit (#1606) deems shared and #1608 wired everywhere.
EXPECTED_SHARED_INSTALLERS = {
    "install-uv",
    "install-bun",
    "install-rtk",
    "install-apm",
    "install-actionlint",
    "install-waza",
    "install-ccusage",
    "install-zizmor",
    "install-lychee",
    "install-betterleaks",
    "install-prek",
}


def _installers(config_path: Path) -> set[str]:
    """Return the bare install-*.sh stems referenced anywhere in a config."""
    return set(_INSTALLER_RE.findall(config_path.read_text(encoding="utf-8")))


def test_shared_installers_registered_on_all_three_agents() -> None:
    claude = _installers(CLAUDE_SETTINGS)
    codex = _installers(CODEX_HOOKS)
    devin = _installers(DEVIN_HOOKS)

    # Every audit-confirmed shared installer is present on each agent.
    assert claude >= EXPECTED_SHARED_INSTALLERS
    assert codex >= EXPECTED_SHARED_INSTALLERS
    assert devin >= EXPECTED_SHARED_INSTALLERS

    # Full parity: no installer is wired into a strict subset of agents.
    assert claude == codex == devin, (
        "installer set diverges across agents: "
        f"claude-only={sorted(claude - codex)} codex-only={sorted(codex - claude)} "
        f"devin-delta={sorted(devin ^ codex)}"
    )


def test_every_provisioner_gates_on_both_remote_signals() -> None:
    """Each wired install-*.sh exits only when BOTH remote signals are unset.

    Wiring an installer into codex is a no-op unless its gate also accepts
    CODEX_CODE_REMOTE, so this asserts the install-uv.sh dual-gate shape on
    every provisioner referenced by the generated configs.
    """
    provisioners = _installers(CLAUDE_SETTINGS) | _installers(CODEX_HOOKS)
    assert provisioners, "no install-*.sh provisioners found in the configs"

    for name in sorted(provisioners):
        script = REPO_ROOT / "scripts" / f"{name}.sh"
        assert script.exists(), f"{name}.sh referenced in a config but missing"
        body = script.read_text(encoding="utf-8")
        assert _DUAL_GATE_RE.search(body), (
            f"scripts/{name}.sh does not gate on both CLAUDE_CODE_REMOTE and "
            "CODEX_CODE_REMOTE; config wiring alone is a no-op under Codex. "
            "Mirror the install-uv.sh dual-signal gate."
        )
