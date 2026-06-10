# AST graph: scripts/preflight_github_secrets.py

This file is generated from `scripts/preflight_github_secrets.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## iter_string_fields(...)

```mermaid
flowchart TD
    N001["iter_string_fields(...)"]
    N002["if isinstance(value, str)"]
    N003["(yield (path or '<str>', value))"]
    N004["if isinstance(value, dict)"]
    N005["for key, child in value.items():
    child_path = f'{path}<str>{key}' if path else str(key)
    yield from iter_string_fields(child, child_path)"]
    N006["if isinstance(value, list)"]
    N007["for index, child in enumerate(value):
    yield from iter_string_fields(child, f'{path}<str>{index}<str>')"]
    N008["end"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N003 --> N008
    N005 --> N008
    N007 --> N008
    N006 -->|"false"| N008
```

## first_finding(...)

```mermaid
flowchart TD
    N001["first_finding(...)"]
    N002["for field_path, text in iter_string_fields(tool_input):
    hits = scan_text(text)
    if hits:
        return (field_path, hits[0][1])"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## build_deny_reason(...)

```mermaid
flowchart TD
    N001["build_deny_reason(...)"]
    N002["return f'<str>{tool_name}<str>{field_path}<str>{rule_id}<str>{PRAGMA_ALLOWLIST}<str>'"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if canonical_github_tool(tool_name) not in _TARGET_TOOLS"]
    N003["return None"]
    N004["finding = first_finding(...)"]
    N005["if finding is None"]
    N006["return None"]
    N007["(field_path, rule_id) = finding"]
    N008["return build_deny(build_deny_reason(tool_name, field_path, rule_id))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_tool_hook('<str>', decide, auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
```
