# Workflow if-branches: Post-merge automation

This file is generated from `.github/workflows/post-merge.yml` by `python3 scripts/workflow_diagram.py diagram-doc`. Do not edit it by hand; update the workflow YAML and regenerate instead.

```mermaid
flowchart TD

    T_pull_request_target(["on: pull_request_target\ntypes: ['closed']"])
    T_push(["on: push\nbranches: ['main']"])
    T_schedule(["on: schedule"])
    T_workflow_dispatch(["on: workflow_dispatch\ninputs: {'task': {'description': 'Post-merge ..."])

    J_open_retro["open-retro"]
    J_coverage["coverage"]
    S_J_coverage_0(("Upload coverage to Codecov"))
    S_J_coverage_1(("Upload test results to Codecov"))
    S_J_coverage_2(("Fail coverage job when coverage gate failed"))
    J_coverage_failure_issue["coverage-failure-issue"]
    J_maturity_summary["maturity-summary"]
    J_decision_tree["decision-tree"]
    S_J_decision_tree_0(("Mint GitHub App token"))
    S_J_decision_tree_1(("Open pull request if any generated doc changed"))
    J_triage_report["triage-report"]
    J_verify_docs_drift["verify-docs-drift"]

    T_pull_request_target -->|"github.event_name == 'pull_request_target' && github.event.pull_request~"| J_open_retro
    T_push -->|"github.event_name == 'push' || (github.event_name == 'workflow_dispatch~"| J_coverage
    T_workflow_dispatch -->|"github.event_name == 'push' || (github.event_name == 'workflow_dispatch~"| J_coverage
    J_coverage -->|"always()"| S_J_coverage_0
    J_coverage -->|"always()"| S_J_coverage_1
    J_coverage -->|"steps.coverage-tests.outcome == 'failure'"| S_J_coverage_2
    J_coverage -->|"always() && needs.coverage.outputs.coverage_gate_result == 'failure'"| J_coverage_failure_issue
    T_push -->|"github.event_name == 'push' || (github.event_name == 'workflow_dispatch~"| J_maturity_summary
    T_workflow_dispatch -->|"github.event_name == 'push' || (github.event_name == 'workflow_dispatch~"| J_maturity_summary
    T_push -->|"github.event_name == 'push' || (github.event_name == 'workflow_dispatch~"| J_decision_tree
    T_workflow_dispatch -->|"github.event_name == 'push' || (github.event_name == 'workflow_dispatch~"| J_decision_tree
    J_decision_tree -->|"${{ steps.drift.outputs.changed == 'true' }}"| S_J_decision_tree_0
    J_decision_tree -->|"${{ steps.drift.outputs.changed == 'true' }}"| S_J_decision_tree_1
    T_push -->|"github.event_name == 'push' || (github.event_name == 'workflow_dispatch~"| J_triage_report
    T_workflow_dispatch -->|"github.event_name == 'push' || (github.event_name == 'workflow_dispatch~"| J_triage_report
    T_push -->|"github.event_name == 'push' || github.event_name == 'schedule'"| J_verify_docs_drift
    T_schedule -->|"github.event_name == 'push' || github.event_name == 'schedule'"| J_verify_docs_drift
```
