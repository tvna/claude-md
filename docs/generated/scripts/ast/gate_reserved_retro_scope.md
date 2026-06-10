# AST graph: scripts/gate_reserved_retro_scope.py

This file is generated from `scripts/gate_reserved_retro_scope.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## uses_reserved_scope(...)

```mermaid
flowchart TD
    N001["uses_reserved_scope(...)"]
    N002["return is_retro_pr(title) or is_retro_issue_title(title)"]
    N001 -->|"start"| N002
```

## build_reason(...)

```mermaid
flowchart TD
    N001["build_reason(...)"]
    N002["return f'<str>{_TARGET_TOOL}<str>{_RESERVED_SCOPE}<str>{_RESERVED_SCOPE}<str>'"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if tool_name != _TARGET_TOOL"]
    N003["return None"]
    N004["if tool_input.get('method') != _CREATE_METHOD"]
    N005["return None"]
    N006["title = get(...)"]
    N007["if not isinstance(title, str)"]
    N008["return None"]
    N009["if not uses_reserved_scope(title)"]
    N010["return None"]
    N011["if is_canonical_handoff_retro_title(title)"]
    N012["return None"]
    N013["return build_deny(build_reason())"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
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
