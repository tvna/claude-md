# AST graph: scripts/preflight_angle_token_drop.py

This file is generated from `scripts/preflight_angle_token_drop.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## find_angle_tokens(...)

```mermaid
flowchart TD
    N001["find_angle_tokens(...)"]
    N002["cleaned = strip_html_comments(...)"]
    N003["seen = set(...)"]
    N004["out = []"]
    N005["for token in _ANGLE_TOKEN_RE.findall(cleaned):     if token not in seen:         seen.add(token)         out.append(token)"]
    N006["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

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

## offending_tokens(...)

```mermaid
flowchart TD
    N001["offending_tokens(...)"]
    N002["out = {}"]
    N003["for field, text in (('<str>', title), ('<str>', body)):     if not text:         continue     tokens = find_angle_tokens(text)     if tokens:         out[field] = tokens"]
    N004["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## build_deny_reason(...)

```mermaid
flowchart TD
    N001["build_deny_reason(...)"]
    N002["where = join(...)"]
    N003["listed = join(...)"]
    N004["return f'<str>{tool_name}<str>{where}<str>{listed}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if canonical_github_tool(tool_name) not in _TARGET_TOOLS"]
    N003["return None"]
    N004["(title, body) = extract_text_fields(...)"]
    N005["offending = offending_tokens(...)"]
    N006["if not offending"]
    N007["return None"]
    N008["return build_deny(build_deny_reason(tool_name, offending))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
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
