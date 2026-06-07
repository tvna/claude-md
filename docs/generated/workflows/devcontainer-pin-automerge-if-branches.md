# Workflow if-branches: Auto-merge devcontainer pin PR

This file is generated from `.github/workflows/devcontainer-pin-automerge.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_check_suite(["on: check_suite\ntypes: ['completed']"])
    T_workflow_dispatch(["on: workflow_dispatch"])

    J_merge["merge"]

    T_workflow_dispatch -->|"github.event_name == 'workflow_dispatch' || startsWith(github.event.che~"| J_merge
```
