# AST graph: scripts/_session_branches.py

This file is generated from `scripts/_session_branches.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## read_authorized_set(...)

```mermaid
flowchart TD
    N001["read_authorized_set(...)"]
    N002["try"]
    N003["text = read_text(...)"]
    N004["except OSError"]
    N005["return set()"]
    N006["return {line.strip() for line in text.splitlines() if line.strip()}"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
```

## append_branch(...)

```mermaid
flowchart TD
    N001["append_branch(...)"]
    N002["branch = strip(...)"]
    N003["if not branch or branch in read_authorized_set(path)"]
    N004["return"]
    N005["try"]
    N006["existing = read_text(...)"]
    N007["except OSError"]
    N008["existing = '<str>'"]
    N009["separator = '<str>' if not existing or existing.endswith('<str>') else '<str>'"]
    N010["with contextlib.suppress(OSError), path.open('<str>', encoding='<str>') as handle:
    handle.write(separator + branch + '<str>')"]
    N011["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N008 --> N009
    N009 --> N010
    N010 --> N011
```

## is_authorized(...)

```mermaid
flowchart TD
    N001["is_authorized(...)"]
    N002["if not branch"]
    N003["return False"]
    N004["if branch in PROTECTED"]
    N005["return False"]
    N006["return branch in authorized"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```
