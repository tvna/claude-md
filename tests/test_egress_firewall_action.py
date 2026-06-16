"""Tests for the custom egress-firewall composite action (umbrella #1257, PR4/PR5).

These lock the two properties that make the action safe and single-sourced:

* it is **permission-agnostic** -- it reads no GITHUB_TOKEN and no secrets, the
  same invariant the setup-uv action documents (it runs inline under the union
  of caller permissions);
* its CI self-test is **isolated** -- the dedicated job exercises the egress
  layer on its own, so it must not be a step in lint-scripts-static and must
  not feed the required `gate` aggregation, or a runner-specific network quirk
  would block unrelated work. PR5 promotes the job from audit to block mode
  (deny-by-default) while keeping that isolation.

The action reuses the devcontainer dispatcher (which sources _egress-lib.sh), so
the bash parser stays the single source of truth. The runner-side kernel
behaviour (iptables audit rules) is exercised only by the CI job, not here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION = REPO_ROOT / ".github" / "actions" / "egress-firewall" / "action.yml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "verify-agents.yml"


def _action_text() -> str:
    return ACTION.read_text(encoding="utf-8")


def test_action_is_a_composite_action() -> None:
    text = _action_text()
    assert "using: composite" in text
    assert "name: Egress firewall" in text


def test_action_is_permission_agnostic() -> None:
    text = _action_text()
    # No secret or token interpolation anywhere in the action body. The header
    # prose may say "GITHUB_TOKEN" in plain text; what must be absent is any
    # actual ``${{ secrets.* }}`` / ``${{ github.token }}`` usage.
    assert "${{ secrets." not in text
    assert "github.token" not in text


def test_action_defaults_to_audit_mode() -> None:
    text = _action_text()
    assert "default: audit" in text


def test_action_reuses_dispatcher_single_source() -> None:
    text = _action_text()
    # Reuse the dispatcher rather than re-implementing iptables logic, so the
    # parser stays parity-gated against scripts/_allowlist.py.
    assert "apply-egress-allowlist.sh" in text
    assert "_egress-lib.sh" in text
    assert "EGRESS_MODE" in text


def test_action_documents_honest_limitation() -> None:
    text = _action_text()
    assert "CVE-2025-32955" in text
    assert "not a sandbox" in text


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_yaml_is_parseable() -> None:
    assert yaml.safe_load(_workflow_text()) is not None


def test_selftest_job_exists_and_uses_the_action_in_block_mode() -> None:
    text = _workflow_text()
    assert "egress-firewall-selftest:" in text
    assert "uses: ./.github/actions/egress-firewall" in text
    # PR5: the block (deny-by-default) posture is explicit in the job, not
    # inherited by accident. The action default stays audit (asserted above).
    assert "mode: block" in text
    assert "mode: audit" not in text


def test_selftest_block_job_proves_both_egress_directions() -> None:
    text = _workflow_text()
    selftest_start = text.index("egress-firewall-selftest:")
    selftest_block = text[selftest_start:text.index("\n  gate:", selftest_start)]
    # Block mode is only meaningful if the job proves deny-by-default actually
    # denies: it must assert the OUTPUT policy is DROP and that a
    # non-allowlisted destination (example.com) is blocked, while github.com is
    # allowed by FQDN OR by the exact IP pre-resolved for this assertion.
    assert "-P OUTPUT DROP" in selftest_block
    assert 'allow_host="github.com"' in selftest_block
    assert "example.com" in selftest_block
    assert "@include shared.allowlist" in selftest_block
    assert "${ALLOW_IP}" in selftest_block
    assert "allowlist: .devcontainer/network/egress-selftest.allowlist" in selftest_block
    assert "${ALLOW_HOST}:443" in selftest_block
    assert "raw.githubusercontent.com" not in selftest_block


def test_selftest_block_job_restores_connectivity() -> None:
    text = _workflow_text()
    # Block sets OUTPUT DROP for every process on the runner; the isolated
    # self-test must restore ACCEPT on always() so it never strands the runner
    # agent's own egress (completion/telemetry) or later steps.
    selftest_start = text.index("egress-firewall-selftest:")
    selftest_block = text[selftest_start:]
    assert "if: always()" in selftest_block
    assert "iptables -P OUTPUT ACCEPT" in selftest_block


def test_selftest_job_is_isolated_from_the_required_gate() -> None:
    text = _workflow_text()
    # The required aggregation must not depend on the audit selftest.
    # Use the gate job's needs line (the one with lint-scripts-static) rather
    # than a hardcoded full string so adding legitimate new needs (e.g. the
    # coverage job added in #1800) does not break this assertion.
    needs_line = next(
        line
        for line in text.splitlines()
        if line.strip().startswith("needs: [") and "lint-scripts-static" in line
    )
    assert "lint-scripts-static" in needs_line
    assert "lint-scripts-pytest-gate" in needs_line
    assert "egress-firewall-selftest" not in needs_line


def test_selftest_job_is_not_a_step_in_lint_scripts_static() -> None:
    text = _workflow_text()
    static_start = text.index("lint-scripts-static:")
    selftest_start = text.index("egress-firewall-selftest:")
    # The audit action is wired only into the dedicated job, which is defined
    # after (outside) the lint-scripts-static job block.
    assert text.index("uses: ./.github/actions/egress-firewall") > selftest_start
    assert selftest_start > static_start
