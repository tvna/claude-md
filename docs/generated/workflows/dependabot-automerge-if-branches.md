# Workflow if-branches: Dependabot auto-merge audit

This file is generated from `.github/workflows/dependabot-automerge.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request_target(["on: pull_request_target\ntypes: ['opened', 'synchronize', 'reopened',..."])

    J_audit["audit"]
    S_J_audit_0(("Request GitHub auto-merge"))
    S_J_audit_1(("Disable GitHub auto-merge if no longer eligible"))

    T_pull_request_target -->|"github.event.pull_request.user.login == 'dependabot[bot]'"| J_audit
    J_audit -->|"steps.audit.outputs.should_enable == 'true'"| S_J_audit_0
    J_audit -->|"steps.audit.outputs.should_enable != 'true'"| S_J_audit_1
```
