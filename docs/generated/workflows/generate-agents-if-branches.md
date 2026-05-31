# Workflow if-branches: Generate agent instructions

This file is generated from `.github/workflows/generate-agents.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_workflow_dispatch(["on: workflow_dispatch"])
    T_workflow_call(["on: workflow_call\ninputs: {'mode': {'description': 'generate (d..."])

    J_generate["generate"]
    S_J_generate_0(("Fail if generated instructions drifted (verify mode)"))
    S_J_generate_1(("Open pull request if generated instructions changed"))

    T_workflow_dispatch --> J_generate
    T_workflow_call --> J_generate
    J_generate -->|"${{ inputs.mode == 'verify' }}"| S_J_generate_0
    J_generate -->|"${{ inputs.mode != 'verify' }}"| S_J_generate_1
```
