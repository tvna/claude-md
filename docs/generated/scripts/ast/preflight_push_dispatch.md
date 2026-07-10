# AST graph: scripts/preflight_push_dispatch.py

This file is generated from `scripts/preflight_push_dispatch.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["for check in _CHECKS:     try:         decision = check(event)     except Exception as exc:         print(f'<str>{getattr(check, '<str>', '<str>')}<str>{exc}', file=sys.stderr)         continue     if decision is not None:         return decision"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_event_hook('<str>', decide, auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
```
