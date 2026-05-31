# Workflow if-branches: Portable PR policy

This file is generated from `.github/workflows/portable-pr-policy.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request\ntypes: ['opened', 'edited', 'synchronize', '..."])
    T_merge_group(["on: merge_group"])

    J_gate["gate"]
    S_J_gate_0(("Validate title policy"))
    S_J_gate_1(("Validate body section structure"))
    S_J_gate_2(("Validate PR-issue link"))
    S_J_gate_3(("Validate linked issue titles"))
    S_J_gate_4(("Validate README translation parity"))

    T_pull_request --> J_gate
    T_merge_group --> J_gate
    J_gate -->|"${{ github.event_name != 'merge_group' }}"| S_J_gate_0
    J_gate -->|"${{ github.event_name != 'merge_group' }}"| S_J_gate_1
    J_gate -->|"${{ github.event_name != 'merge_group' }}"| S_J_gate_2
    J_gate -->|"${{ github.event_name != 'merge_group' }}"| S_J_gate_3
    J_gate -->|"${{ github.event_name != 'merge_group' }}"| S_J_gate_4
```
