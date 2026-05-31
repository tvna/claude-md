# Workflow if-branches: Portable PR policy

This file is generated from `.github/workflows/portable-pr-policy.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request\ntypes: ['opened', 'edited', 'synchronize', '..."])

    J_gate["gate"]

    T_pull_request --> J_gate
```
