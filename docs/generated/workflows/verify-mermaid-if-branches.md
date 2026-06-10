# Workflow if-branches: Verify Mermaid (docs)

This file is generated from `.github/workflows/verify-mermaid.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request\npaths: ['docs/**/*.md', 'scripts/scan_mermai..."])

    J_gate["gate"]

    T_pull_request --> J_gate
```
