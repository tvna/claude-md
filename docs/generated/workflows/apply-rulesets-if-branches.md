# Workflow if-branches: Apply rulesets

This file is generated from `.github/workflows/apply-rulesets.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'ruleset': {'description': 'Which ru..."])

    J_apply["apply"]
    S_J_apply_0(("Guard dispatch ref"))
    S_J_apply_1(("Enable auto-delete head branches"))

    T_workflow_dispatch --> J_apply
    J_apply -->|"github.ref != 'refs/heads/main'"| S_J_apply_0
    J_apply -->|"${{ inputs.enable_auto_delete }}"| S_J_apply_1
```
