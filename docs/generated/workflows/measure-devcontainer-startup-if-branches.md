# Workflow if-branches: Measure devcontainer startup

This file is generated from `.github/workflows/measure-devcontainer-startup.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'agent': {'description': 'Which devc..."])

    J_measure["measure"]
    S_J_measure_0(("Build image from source"))

    T_workflow_dispatch --> J_measure
    J_measure -->|"inputs.build_from_source"| S_J_measure_0
```
