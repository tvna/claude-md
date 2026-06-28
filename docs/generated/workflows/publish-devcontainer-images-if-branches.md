# Workflow if-branches: Publish devcontainer images

This file is generated from `.github/workflows/publish-devcontainer-images.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_push(["on: push\nbranches: ['main']\npaths: ['.devcontainer/images/**', '.devcont..."])
    T_workflow_dispatch(["on: workflow_dispatch"])

    J_build["build"]
    S_J_build_0(("Stage flake into nix-warm-claude feature"))
    J_scan["scan"]
    J_publish["publish"]
    J_update_pins["update-pins"]

    T_push --> J_build
    T_workflow_dispatch --> J_build
    J_build -->|"matrix.agent == 'claude'"| S_J_build_0
    J_build --> J_scan
    J_build --> J_publish
    J_publish -->|"github.event_name == 'push'"| J_update_pins
```
