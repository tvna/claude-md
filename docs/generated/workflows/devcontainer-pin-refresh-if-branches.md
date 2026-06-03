# Workflow if-branches: Refresh devcontainer pin PR

This file is generated from `.github/workflows/devcontainer-pin-refresh.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_push(["on: push\nbranches: ['main']"])
    T_workflow_dispatch(["on: workflow_dispatch"])

    J_refresh["refresh"]

    T_push --> J_refresh
    T_workflow_dispatch --> J_refresh
```
