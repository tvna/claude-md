# Workflow if-branches: Scorecard

This file is generated from `.github/workflows/scorecard.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_push(["on: push\nbranches: ['main']"])
    T_pull_request(["on: pull_request\nbranches: ['main']\npaths: ['.github/**', 'scripts/**', 'flake.n..."])
    T_schedule(["on: schedule"])

    J_analysis["analysis"]
    S_J_analysis_0(("Upload SARIF to code scanning"))

    T_push --> J_analysis
    T_pull_request --> J_analysis
    T_schedule --> J_analysis
    J_analysis -->|"${{ github.event_name != 'pull_request' || github.event.pull_request.he~"| S_J_analysis_0
```
