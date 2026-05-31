# Workflow if-branches: Deferred Post-merge checklist re-scan

This file is generated from `.github/workflows/auto-retro-post-merge-rescan.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'hours': {'description': 'Lookback w..."])

    J_rescan["rescan"]

    T_schedule --> J_rescan
    T_workflow_dispatch --> J_rescan
```
