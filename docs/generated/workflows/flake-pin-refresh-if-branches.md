# Workflow if-branches: Refresh flake tool pins

This file is generated from `.github/workflows/flake-pin-refresh.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch"])

    J_refresh["refresh"]
    S_J_refresh_0(("Recompute per-system hashes and bump flake.nix"))
    S_J_refresh_1(("Validate the bumped flake"))
    S_J_refresh_2(("Open bump PR"))

    T_schedule --> J_refresh
    T_workflow_dispatch --> J_refresh
    J_refresh -->|"steps.decide.outputs.target != ''"| S_J_refresh_0
    J_refresh -->|"steps.decide.outputs.target != ''"| S_J_refresh_1
    J_refresh -->|"steps.decide.outputs.target != ''"| S_J_refresh_2
```
