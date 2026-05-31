# Workflow if-branches: Auto-close untouched retrospective issues

This file is generated from `.github/workflows/auto-retro-sentinel.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'days': {'description': 'Inactivity ..."])

    J_scan_and_close["scan-and-close"]

    T_schedule --> J_scan_and_close
    T_workflow_dispatch --> J_scan_and_close
```
