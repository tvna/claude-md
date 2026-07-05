# AST graph: scripts/_security_drift_families.py

This file is generated from `scripts/_security_drift_families.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## issue_labels(...)

```mermaid
flowchart TD
    N001["issue_labels(...)"]
    N002["try"]
    N003["return _ssot.consumer_labels('<str>')"]
    N004["except (KeyError, TypeError)"]
    N005["raise RuntimeError(f'<str>{exc}')"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```
