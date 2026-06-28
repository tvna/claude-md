# AST graph: scripts/post_merge_retro_append.py

This file is generated from `scripts/post_merge_retro_append.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _walk(...)

```mermaid
flowchart TD
    N001["_walk(...)"]
    N002["out = []"]
    N003["stack = [value]"]
    N004["while stack and len(out) < 200:     node = stack.pop()     out.append(node)     if isinstance(node, dict):         stack.extend(node.values())     elif isinstance(node, list):         stack.extend(node)"]
    N005["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## extract_merge_coords(...)

```mermaid
flowchart TD
    N001["extract_merge_coords(...)"]
    N002["owner = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N003["repo = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N004["pr_number = None"]
    N005["if isinstance(tool_input, dict)"]
    N006["val = get(...)"]
    N007["if isinstance(val, int) and val > 0"]
    N008["pr_number = str(...)"]
    N009["if isinstance(val, str) and val.isdecimal()"]
    N010["pr_number = val"]
    N011["if pr_number is None"]
    N012["for node in _walk(tool_response):     if isinstance(node, str):         m = _PR_URL_RE.search(node)         if m:             if owner is None:                 owner = m.group(1)             if repo is None:                 repo = m.group(2)             pr_number = m.group(3)             break"]
    N013["return (owner, repo, pr_number)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N008 --> N011
    N010 --> N011
    N009 -->|"false"| N011
    N005 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N013
```

## _build_context(...)

```mermaid
flowchart TD
    N001["_build_context(...)"]
    N002["return {'<str>': {'<str>': '<str>', '<str>': message}}"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') != TARGET_TOOL"]
    N003["return None"]
    N004["tool_input = event.get('<str>') or {}"]
    N005["tool_response = get(...)"]
    N006["(owner, repo, pr_number) = extract_merge_coords(...)"]
    N007["if pr_number is None"]
    N008["return _build_context(f'<str>{TARGET_TOOL}<str>{RETRO_TITLE_PREFIX}<str>')"]
    N009["pr_label = f'{owner}<str>{repo}<str>{pr_number}' if owner and repo else f'<str>{pr_number}'"]
    N010["return _build_context(f'<str>{pr_label}<str>{RETRO_TITLE_PREFIX}<str>{pr_label}<str>{pr_number}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["event = read_event(...)"]
    N004["if event is None"]
    N005["return 0"]
    N006["if not isinstance(event, dict)"]
    N007["return 0"]
    N008["emit_decision(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```
