# Workflow if-branches: Apply labels

This file is generated from `.github/workflows/apply-labels.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'dry_run': {'description': 'Plan onl..."])

    J_apply["apply"]
    S_J_apply_0(("Guard dispatch ref"))

    T_workflow_dispatch --> J_apply
    J_apply -->|"github.ref != 'refs/heads/main'"| S_J_apply_0
```
