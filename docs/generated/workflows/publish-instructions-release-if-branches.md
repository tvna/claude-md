# Workflow if-branches: Publish instructions release

This file is generated from `.github/workflows/publish-instructions-release.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_push(["on: push\ntags: ['instructions-v*']"])
    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'version': {'description': 'Release ..."])

    J_publish["publish"]

    T_push --> J_publish
    T_workflow_dispatch --> J_publish
```
