# Workflow if-branches: ATT&CK coverage review reminder

This file is generated from `.github/workflows/attack-coverage-review-reminder.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'dry_run': {'description': 'Preview ..."])

    J_remind["remind"]
    S_J_remind_0(("Checkout repository"))
    S_J_remind_1(("Assemble review reminder comment"))
    S_J_remind_2(("Post review reminder comment on tracking issue"))

    T_schedule --> J_remind
    T_workflow_dispatch --> J_remind
    J_remind -->|"steps.gate.outputs.should_post == 'true'"| S_J_remind_0
    J_remind -->|"steps.gate.outputs.should_post == 'true'"| S_J_remind_1
    J_remind -->|"steps.gate.outputs.should_post == 'true'"| S_J_remind_2
```
