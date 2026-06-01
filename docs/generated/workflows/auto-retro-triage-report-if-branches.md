# Workflow if-branches: Refresh auto-retro triage report

This file is generated from `.github/workflows/auto-retro-triage-report.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch"])

    J_refresh["refresh"]

    T_schedule --> J_refresh
    T_workflow_dispatch --> J_refresh
```
