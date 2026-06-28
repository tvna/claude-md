# AST graph: scripts/plan_approval_gate.py

This file is generated from `scripts/plan_approval_gate.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _is_plan_write(...)

```mermaid
flowchart TD
    N001["_is_plan_write(...)"]
    N002["if tool_name != 'Write'"]
    N003["return False"]
    N004["path = str(...)"]
    N005["return path.startswith(_PLAN_DIR) and path.endswith('<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## build_blocking_prompt(...)

```mermaid
flowchart TD
    N001["build_blocking_prompt(...)"]
    N002["return f'<str>{file_path}<str>'"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["tool_name = get(...)"]
    N003["tool_input = get(...)"]
    N004["if not isinstance(tool_input, dict)"]
    N005["return None"]
    N006["if not _is_plan_write(tool_name, tool_input)"]
    N007["return None"]
    N008["file_path = str(...)"]
    N009["return {'<str>': {'<str>': '<str>', '<str>': build_blocking_prompt(file_path)}}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["event = read_event(...)"]
    N003["if event is None or not isinstance(event, dict)"]
    N004["return 0"]
    N005["emit_decision(...)"]
    N006["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```
