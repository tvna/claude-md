# Workflow if-branches: CodeQL

This file is generated from `.github/workflows/codeql.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request\npaths: ['scripts/**', '.github/workflows/cod..."])
    T_push(["on: push\nbranches: ['main']\npaths: ['scripts/**', '.github/workflows/cod..."])
    T_schedule(["on: schedule"])

    J_analyze["analyze"]

    T_pull_request --> J_analyze
    T_push --> J_analyze
    T_schedule --> J_analyze
```
