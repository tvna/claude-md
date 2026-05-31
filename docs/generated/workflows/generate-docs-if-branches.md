# Workflow if-branches: Generate docs

This file is generated from `.github/workflows/generate-docs.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request\npaths: ['.github/workflows/generate-docs.yml..."])

    J_generate_docs["generate-docs"]

    T_pull_request --> J_generate_docs
```
