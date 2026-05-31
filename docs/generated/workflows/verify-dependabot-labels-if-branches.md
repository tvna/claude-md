# Workflow if-branches: Verify dependabot labels

This file is generated from `.github/workflows/verify-dependabot-labels.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request"])

    J_verify["verify"]

    T_pull_request --> J_verify
```
