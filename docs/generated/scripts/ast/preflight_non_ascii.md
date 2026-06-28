# AST graph: scripts/preflight_non_ascii.py

This file is generated from `scripts/preflight_non_ascii.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_text_fields(...)

```mermaid
flowchart TD
    N001["extract_text_fields(...)"]
    N002["title = tool_input.get('<str>') or '<str>'"]
    N003["body = tool_input.get('<str>') or '<str>'"]
    N004["if not isinstance(title, str)"]
    N005["title = '<str>'"]
    N006["if not isinstance(body, str)"]
    N007["body = '<str>'"]
    N008["return (title, body)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
```

## offending_fields(...)

```mermaid
flowchart TD
    N001["offending_fields(...)"]
    N002["out = []"]
    N003["if title and detect_non_ascii(title)"]
    N004["append(...)"]
    N005["if body and detect_non_ascii(body)"]
    N006["append(...)"]
    N007["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
```

## build_deny_reason(...)

```mermaid
flowchart TD
    N001["build_deny_reason(...)"]
    N002["where = '<str>'.join(fields) if fields else '<str>'"]
    N003["return f'<str>{tool_name}<str>{where}<str>{where}<str>{ack_marker}<str>{escaped}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if canonical_github_tool(tool_name) not in _TARGET_TOOLS"]
    N003["return None"]
    N004["(title, body) = extract_text_fields(...)"]
    N005["if has_ack_marker(body)"]
    N006["return None"]
    N007["fields = offending_fields(...)"]
    N008["if not fields"]
    N009["return None"]
    N010["escaped = escape_for_comment(...)"]
    N011["reason = build_deny_reason(...)"]
    N012["return build_deny(reason)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 --> N012
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_tool_hook('<str>', decide, auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
```
