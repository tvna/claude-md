# Workflow if-branches: Monthly maintenance

This file is generated from `.github/workflows/monthly-maintenance.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'dry_run': {'description': 'Preview ..."])

    J_remind["remind"]

    T_schedule --> J_remind
    T_workflow_dispatch --> J_remind
```
