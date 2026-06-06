# Workflow if-branches: Verify repository scripts

This file is generated from `.github/workflows/verify-agents.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request"])

    J_lint_scripts_static["lint-scripts-static"]
    J_lint_scripts_pytest["lint-scripts-pytest"]
    S_J_lint_scripts_pytest_0(("Upload shard JUnit artifact"))
    J_lint_scripts_pytest_gate["lint-scripts-pytest-gate"]
    S_J_lint_scripts_pytest_gate_0(("Download all shard JUnit artifacts"))
    S_J_lint_scripts_pytest_gate_1(("Upload test results to Codecov"))
    J_egress_firewall_selftest["egress-firewall-selftest"]
    S_J_egress_firewall_selftest_0(("Restore OUTPUT policy (contain blast radius)"))
    J_gate["gate"]
    J_legacy_agent_instructions_context["legacy-agent-instructions-context"]

    T_pull_request --> J_lint_scripts_static
    T_pull_request --> J_lint_scripts_pytest
    J_lint_scripts_pytest -->|"always()"| S_J_lint_scripts_pytest_0
    J_lint_scripts_pytest -->|"always()"| J_lint_scripts_pytest_gate
    J_lint_scripts_pytest_gate -->|"always()"| S_J_lint_scripts_pytest_gate_0
    J_lint_scripts_pytest_gate -->|"always()"| S_J_lint_scripts_pytest_gate_1
    T_pull_request --> J_egress_firewall_selftest
    J_egress_firewall_selftest -->|"always()"| S_J_egress_firewall_selftest_0
    J_lint_scripts_static -->|"always()"| J_gate
    J_lint_scripts_pytest_gate -->|"always()"| J_gate
    J_gate -->|"always()"| J_legacy_agent_instructions_context
```
