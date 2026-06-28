# Workflow if-branches: Issue and PR triage

This file is generated from `.github/workflows/issue-pr-triage.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_issues(["on: issues\ntypes: ['opened', 'edited', 'labeled', 'unla..."])
    T_pull_request_target(["on: pull_request_target\ntypes: ['opened', 'edited', 'synchronize', '..."])
    T_issue_comment(["on: issue_comment\ntypes: ['created', 'edited']"])
    T_pull_request_review_comment(["on: pull_request_review_comment\ntypes: ['created', 'edited']"])

    J_scan["scan"]
    J_dependabot_author["dependabot-author"]

    T_issues -->|"github.actor != 'github-actions[bot]' && (   (github.event_name == 'iss~"| J_scan
    T_pull_request_target -->|"github.actor != 'github-actions[bot]' && (   (github.event_name == 'iss~"| J_scan
    T_issue_comment -->|"github.actor != 'github-actions[bot]' && (   (github.event_name == 'iss~"| J_scan
    T_pull_request_review_comment -->|"github.actor != 'github-actions[bot]' && (   (github.event_name == 'iss~"| J_scan
    T_pull_request_target -->|"github.event_name == 'pull_request_target' && startsWith(github.event.p~"| J_dependabot_author
```
