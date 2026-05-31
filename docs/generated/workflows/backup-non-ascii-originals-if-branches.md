# Workflow if-branches: Backup non-ASCII originals (P1)

This file is generated from `.github/workflows/backup-non-ascii-originals.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'issue_number': {'description': 'Iss..."])

    J_backup["backup"]
    S_J_backup_0(("Guard dispatch ref"))
    S_J_backup_1(("Post SHA-256 to issue"))

    T_workflow_dispatch --> J_backup
    J_backup -->|"github.event_name == 'workflow_dispatch' && github.ref != 'refs/heads/m~"| S_J_backup_0
    J_backup -->|"${{ github.event_name == 'workflow_dispatch' && inputs.issue_number != ~"| S_J_backup_1
```
