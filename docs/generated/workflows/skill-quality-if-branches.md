# Workflow if-branches: skill-quality

This file is generated from `.github/workflows/skill-quality.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request\npaths: ['.agents/skills/**/SKILL.md', 'scrip..."])

    J_skill_quality["skill-quality"]

    T_pull_request --> J_skill_quality
```
