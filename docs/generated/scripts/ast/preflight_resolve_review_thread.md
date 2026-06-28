# AST graph: scripts/preflight_resolve_review_thread.py

This file is generated from `scripts/preflight_resolve_review_thread.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["event = read_event(...)"]
    N003["if event is None"]
    N004["return 0"]
    N005["try"]
    N006["emit_decision(...)"]
    N007["except Exception"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N008 --> N009
```
