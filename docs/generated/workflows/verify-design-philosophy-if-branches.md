# Workflow if-branches: Verify design philosophy doc

This file is generated from `.github/workflows/verify-design-philosophy.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request"])
    T_merge_group(["on: merge_group"])

    J_verify["verify"]

    T_pull_request --> J_verify
    T_merge_group --> J_verify
```
