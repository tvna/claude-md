# AST graph: scripts/_ssot.py

This file is generated from `scripts/_ssot.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _load(...)

```mermaid
flowchart TD
    N001["_load(...)"]
    N002["global _registry"]
    N003["if _registry is None"]
    N004["_registry = loads(...)"]
    N005["return _registry"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## consumer_labels(...)

```mermaid
flowchart TD
    N001["consumer_labels(...)"]
    N002["for entry in _load().get('<str>', []):     if isinstance(entry, dict) and entry.get('<str>') == path:         labels = entry.get('<str>')         if not isinstance(labels, list):             raise TypeError(f'<str>{path!r}<str>{labels!r}<str>{_REGISTRY_PATH}')         return tuple(labels)"]
    N003["raise KeyError(f'<str>{path!r}<str>{_REGISTRY_PATH}')"]
    N001 -->|"start"| N002
    N002 --> N003
```

## routing_rules(...)

```mermaid
flowchart TD
    N001["routing_rules(...)"]
    N002["routing = get(...)"]
    N003["if not isinstance(routing, dict)"]
    N004["raise TypeError(f'<str>{_REGISTRY_PATH}')"]
    N005["rules = get(...)"]
    N006["if not isinstance(rules, list)"]
    N007["raise TypeError(f'<str>{_REGISTRY_PATH}')"]
    N008["return tuple(rules)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _reset_for_tests(...)

```mermaid
flowchart TD
    N001["_reset_for_tests(...)"]
    N002["global _registry"]
    N003["_registry = None"]
    N004["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
