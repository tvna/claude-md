# AST graph: scripts/_allowlist.py

This file is generated from `scripts/_allowlist.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## split_inline_comment(...)

```mermaid
flowchart TD
    N001["split_inline_comment(...)"]
    N002["hash_idx = find(...)"]
    N003["if hash_idx == -1"]
    N004["return (raw.strip(), '<str>')"]
    N005["return (raw[:hash_idx].strip(), raw[hash_idx + 1:].strip())"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## resolve_hosts(...)

```mermaid
flowchart TD
    N001["resolve_hosts(...)"]
    N002["hosts = set(...)"]
    N003["base = path.parent"]
    N004["for raw in path.read_text(encoding='<str>').splitlines():     content, _rationale = split_inline_comment(raw)     if not content:         continue     if content.startswith(INCLUDE_PREFIX):         target = content[len(INCLUDE_PREFIX):].strip()         hosts |= resolve_hosts(base / target)         continue     hosts.add(content)"]
    N005["return hosts"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```
