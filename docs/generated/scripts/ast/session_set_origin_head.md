# AST graph: scripts/session_set_origin_head.py

This file is generated from `scripts/session_set_origin_head.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## origin_head_resolves(...)

```mermaid
flowchart TD
    N001["origin_head_resolves(...)"]
    N002["try"]
    N003["return run(['<str>', '<str>', '<str>', _ORIGIN_HEAD]).returncode == 0"]
    N004["except RuntimeError"]
    N005["return False"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## origin_main_exists(...)

```mermaid
flowchart TD
    N001["origin_main_exists(...)"]
    N002["try"]
    N003["return run(['<str>', '<str>', '<str>', _ORIGIN_MAIN]).returncode == 0"]
    N004["except RuntimeError"]
    N005["return False"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## set_origin_head(...)

```mermaid
flowchart TD
    N001["set_origin_head(...)"]
    N002["try"]
    N003["return run(['<str>', _ORIGIN_HEAD, _ORIGIN_MAIN]).returncode == 0"]
    N004["except RuntimeError"]
    N005["return False"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## configure(...)

```mermaid
flowchart TD
    N001["configure(...)"]
    N002["if origin_head_resolves(run)"]
    N003["return None"]
    N004["if not origin_main_exists(run)"]
    N005["message = f'<str>{_ORIGIN_HEAD}<str>{_ORIGIN_MAIN}<str>'"]
    N006["return _context(message)"]
    N007["if set_origin_head(run)"]
    N008["message = f'{_ORIGIN_HEAD}<str>{_ORIGIN_MAIN}<str>'"]
    N009["message = f'<str>{_ORIGIN_HEAD}<str>{_ORIGIN_HEAD}<str>{_ORIGIN_MAIN}'"]
    N010["return _context(message)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N008 --> N010
    N009 --> N010
```

## _context(...)

```mermaid
flowchart TD
    N001["_context(...)"]
    N002["return {'<str>': {'<str>': message}}"]
    N001 -->|"start"| N002
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["try"]
    N003["output = configure(...)"]
    N004["except Exception"]
    N005["exit(...)"]
    N006["if output is not None"]
    N007["print(...)"]
    N008["end"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
```
