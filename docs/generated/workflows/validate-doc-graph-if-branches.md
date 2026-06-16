# Workflow if-branches: Validate document dependency graph

This file is generated from `.github/workflows/validate-doc-graph.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request\nbranches: ['main']\ntypes: ['opened', 'synchronize', 'reopened',..."])

    J_validate["validate"]

    T_pull_request --> J_validate
```
