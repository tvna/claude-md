# Workflow if-branches: Verify PR

This file is generated from `.github/workflows/verify-pr.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request(["on: pull_request\ntypes: ['opened', 'edited', 'synchronize', '..."])

    J_portable_pr_policy["portable-pr-policy"]
    J_verify_design_philosophy["verify-design-philosophy"]
    J_verify_dependabot_labels["verify-dependabot-labels"]
    J_verify_ruleset_sync["verify-ruleset-sync"]

    T_pull_request --> J_portable_pr_policy
    T_pull_request --> J_verify_design_philosophy
    T_pull_request --> J_verify_dependabot_labels
    T_pull_request --> J_verify_ruleset_sync
```
