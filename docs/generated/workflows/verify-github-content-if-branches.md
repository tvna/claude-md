# Workflow if-branches: Verify GitHub issue content

This file is generated from `.github/workflows/verify-github-content.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_issues(["on: issues\ntypes: ['opened', 'edited', 'reopened']"])

    J_gate["gate"]

    T_issues --> J_gate
```
