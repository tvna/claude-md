# Workflow if-branches: Daily maintenance

This file is generated from `.github/workflows/daily-maintenance.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'days': {'description': 'scan-and-cl..."])

    J_scan_and_close["scan-and-close"]
    J_rescan["rescan"]
    J_scan["scan"]

    T_schedule --> J_scan_and_close
    T_workflow_dispatch --> J_scan_and_close
    T_schedule --> J_rescan
    T_workflow_dispatch --> J_rescan
    T_schedule --> J_scan
    T_workflow_dispatch --> J_scan
```
