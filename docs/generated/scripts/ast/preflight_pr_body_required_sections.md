# AST graph: scripts/preflight_pr_body_required_sections.py

This file is generated from `scripts/preflight_pr_body_required_sections.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["required = required_sections(...)"]
    N003["headings = extract_headings(...)"]
    N004["return missing_sections(required, headings)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## build_deny_reason(...)

```mermaid
flowchart TD
    N001["build_deny_reason(...)"]
    N002["missing_csv = join(...)"]
    N003["return f'<str>{tool_name}<str>{missing_csv}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if canonical_github_tool(tool_name) not in _TARGET_TOOLS"]
    N003["return None"]
    N004["body = get(...)"]
    N005["if not isinstance(body, str)"]
    N006["return None"]
    N007["missing = evaluate(...)"]
    N008["if not missing"]
    N009["return None"]
    N010["return build_deny(build_deny_reason(tool_name, missing))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_tool_hook('<str>', decide)"]
    N001 -->|"start"| N002
    N002 --> N003
```
