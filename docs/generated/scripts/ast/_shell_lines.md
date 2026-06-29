# AST graph: scripts/_shell_lines.py

This file is generated from `scripts/_shell_lines.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _continues(...)

```mermaid
flowchart TD
    N001["_continues(...)"]
    N002["if line.lstrip().startswith('#')"]
    N003["return False"]
    N004["trailing = 0"]
    N005["for char in reversed(line):     if char == '<str>':         trailing += 1     else:         break"]
    N006["return trailing % 2 == 1"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## flatten_shell_continuations(...)

```mermaid
flowchart TD
    N001["flatten_shell_continuations(...)"]
    N002["out = []"]
    N003["pending = []"]
    N004["start = 0"]
    N005["for lineno, line in enumerate(text.splitlines(), start=1):     if _continues(line):         if not pending:             start = lineno         pending.append(line[:-1])         continue     if pending:         pending.append(line)         out.append((start, '<str>'.join((part.strip() for part in pending))))         pending = []     else:         out.append((lineno, line))"]
    N006["if pending"]
    N007["append(...)"]
    N008["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
```
