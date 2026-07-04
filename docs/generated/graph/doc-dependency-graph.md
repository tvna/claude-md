# Document Dependency Graph

Auto-generated from `docs/graph/doc-dependencies.toml`. Do not edit manually.
Source: `python3 scripts/doc_graph_viz.py all-doc`.

Nodes: 31 | Edges: 21 (10 blocking, 11 advisory)

```mermaid
flowchart LR
    master_instructions(["master instructions"])
    claude_md["claude md"]
    agents_md["agents md"]
    design_philosophy_prd["design philosophy prd"]
    non_ascii_runbook["non ascii runbook"]
    security_control_inventory["security control inventory"]
    installer_download_retry_prd["installer download retry prd"]
    gitapex_ssot_registry_prd["gitapex ssot registry prd"]
    issue_pr_body_standard["issue pr body standard"]
    workflow_script_quality["workflow script quality"]
    pr_body_quality_enforcement["pr body quality enforcement"]
    loop_engineering_audit["loop engineering audit"]
    doc_dependency_runbook["doc dependency runbook"]
    ubiquitous_language["ubiquitous language"]
    apm_managed_paths["apm managed paths"]
    semver_universal_text_prd["semver universal text prd"]
    scan_design_philosophy_drift>"scan design philosophy drift"]
    preflight_non_ascii>"preflight non ascii"]
    scan_non_ascii>"scan non ascii"]
    body_policy>"body policy"]
    gate_doc_graph_pr>"gate doc graph pr"]
    doc_graph_lib>"doc graph lib"]
    validate_doc_graph_workflow[/"validate doc graph workflow"/]
    docs_generated_ownership["docs generated ownership"]
    preflight_issue_ci_staleness>"preflight issue ci staleness"]
    prd_template["prd template"]
    standard_template["standard template"]
    runbook_template["runbook template"]
    scan_runbook_template_drift>"scan runbook template drift"]
    preflight_runbook["preflight runbook"]
    scan_bypass_lever_doc_drift>"scan bypass lever doc drift"]
    master_instructions ==>|compiled to| claude_md
    master_instructions ==>|compiled to| agents_md
    master_instructions -->|governs| design_philosophy_prd
    master_instructions -->|governs| non_ascii_runbook
    master_instructions -->|governs| security_control_inventory
    master_instructions -->|governs| issue_pr_body_standard
    master_instructions -->|governs| workflow_script_quality
    master_instructions -->|governs| doc_dependency_runbook
    master_instructions -->|governs| ubiquitous_language
    design_philosophy_prd -->|derives from| ubiquitous_language
    ubiquitous_language -.->|enforced by| scan_design_philosophy_drift
    design_philosophy_prd -.->|enforced by| scan_design_philosophy_drift
    non_ascii_runbook -.->|enforced by| preflight_non_ascii
    non_ascii_runbook -.->|enforced by| scan_non_ascii
    issue_pr_body_standard -.->|enforced by| body_policy
    doc_dependency_runbook -.->|enforced by| gate_doc_graph_pr
    doc_dependency_runbook -.->|enforced by| validate_doc_graph_workflow
    gate_doc_graph_pr -.->|references| doc_graph_lib
    semver_universal_text_prd -.->|references| master_instructions
    runbook_template -.->|enforced by| scan_runbook_template_drift
    preflight_runbook -.->|enforced by| scan_bypass_lever_doc_drift
```

## Legend

### Node shapes

| Shape | Node type |
|---|---|
| `([...])` round | `universal_text` |
| `[...]` rectangle | `prd`, `standard`, `runbook`, `archive` |
| `>[...]` flag | `harness_script` |
| `[/.../]` parallelogram | `harness_workflow` |
| `[...]` rectangle | `compiled_artifact` |

### Edge styles

| Arrow | Edge type | Severity |
|---|---|---|
| `-->\|governs\|` solid | `governs` | blocking |
| `==>\|compiled to\|` double | `compiled_to` | blocking |
| `-->\|derives from\|` solid | `derives_from` | blocking |
| `-.->` dashed | `enforced_by`, `implements`, `references` | advisory |

Blocking edges: co-change required or waived (`doc-graph-waiver: NODE_ID; reason`).
Advisory edges: informational note only.
