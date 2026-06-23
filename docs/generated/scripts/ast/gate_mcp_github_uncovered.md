# AST graph: scripts/gate_mcp_github_uncovered.py

This file is generated from `scripts/gate_mcp_github_uncovered.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if not tool_name.startswith(_MCP_GITHUB_PREFIX)"]
    N003["return None"]
    N004["if tool_name in HOOK_COVERED_TOOLS"]
    N005["return None"]
    N006["if tool_name in READ_ONLY_TOOLS"]
    N007["return None"]
    N008["return {'<str>': '<str>', '<str>': f'<str>{tool_name}<str>'}"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["event = read_event(...)"]
    N004["if event is None"]
    N005["return 0"]
    N006["tool_name = get(...)"]
    N007["if not isinstance(tool_name, str)"]
    N008["print(...)"]
    N009["return 0"]
    N010["emit_decision(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
```
