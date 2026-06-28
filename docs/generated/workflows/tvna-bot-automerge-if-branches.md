# Workflow if-branches: Auto-merge tvna-bot PRs

This file is generated from `.github/workflows/tvna-bot-automerge.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_workflow_run(["on: workflow_run\nworkflows: ['Verify PR', 'Verify repository scri...\ntypes: ['completed']"])
    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch"])

    J_merge["merge"]

    T_workflow_run -->|"github.event_name == 'workflow_dispatch' || github.event_name == 'sched~"| J_merge
    T_schedule -->|"github.event_name == 'workflow_dispatch' || github.event_name == 'sched~"| J_merge
    T_workflow_dispatch -->|"github.event_name == 'workflow_dispatch' || github.event_name == 'sched~"| J_merge
```
