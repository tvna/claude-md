# AST graph: scripts/_secret_patterns.py

This file is generated from `scripts/_secret_patterns.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _looks_like_secret_value(...)

```mermaid
flowchart TD
    N001["_looks_like_secret_value(...)"]
    N002["lowered = lower(...)"]
    N003["if any((marker in lowered for marker in _PLACEHOLDER_MARKERS))"]
    N004["return False"]
    N005["if len(value) < 16"]
    N006["return False"]
    N007["has_digit = any(...)"]
    N008["has_alpha = any(...)"]
    N009["return has_digit and has_alpha"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
```

## scan_line(...)

```mermaid
flowchart TD
    N001["scan_line(...)"]
    N002["if PRAGMA_ALLOWLIST in line"]
    N003["return None"]
    N004["for rule in _RULES:
    match = rule.pattern.search(line)
    if match is None:
        continue
    if rule.value_group is not None:
        value = match.group(rule.value_group)
        if not _looks_like_secret_value(value):
            continue
    return rule.rule_id"]
    N005["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## scan_text(...)

```mermaid
flowchart TD
    N001["scan_text(...)"]
    N002["hits = []"]
    N003["for lineno, line in enumerate(text.splitlines(), start=1):
    rule_id = scan_line(line)
    if rule_id is not None:
        hits.append((lineno, rule_id))"]
    N004["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
