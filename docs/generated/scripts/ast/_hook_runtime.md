# AST graph: scripts/_hook_runtime.py

This file is generated from `scripts/_hook_runtime.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _audit_mode_active(...)

```mermaid
flowchart TD
    N001["_audit_mode_active(...)"]
    N002["return os.environ.get(_GATE_MODE_ENV, '<str>').strip().lower() == _AUDIT_MODE"]
    N001 -->|"start"| N002
```

## _blocking_reason(...)

```mermaid
flowchart TD
    N001["_blocking_reason(...)"]
    N002["if decision.get('decision') == 'block'"]
    N003["return str(decision.get('<str>', '<str>'))"]
    N004["hook_output = get(...)"]
    N005["if isinstance(hook_output, dict) and hook_output.get('permissionDecision') == 'deny'"]
    N006["return str(hook_output.get('<str>', '<str>'))"]
    N007["if decision.get('permissionDecision') == 'deny'"]
    N008["return str(decision.get('<str>', decision.get('<str>', '<str>')))"]
    N009["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## read_event(...)

```mermaid
flowchart TD
    N001["read_event(...)"]
    N002["raw = read(...)"]
    N003["try"]
    N004["return json.loads(raw) if raw.strip() else {}"]
    N005["except json.JSONDecodeError"]
    N006["print(...)"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
```

## emit_decision(...)

```mermaid
flowchart TD
    N001["emit_decision(...)"]
    N002["if decision is None"]
    N003["return"]
    N004["if auditable and _audit_mode_active()"]
    N005["reason = _blocking_reason(...)"]
    N006["if reason is not None"]
    N007["label = script_name or '<str>'"]
    N008["print(...)"]
    N009["return"]
    N010["write(...)"]
    N011["end"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 --> N009
    N006 -->|"false"| N010
    N004 -->|"false"| N010
    N010 --> N011
```

## build_deny(...)

```mermaid
flowchart TD
    N001["build_deny(...)"]
    N002["return {'<str>': {'<str>': '<str>', '<str>': '<str>', '<str>': reason}}"]
    N001 -->|"start"| N002
```

## split_tool_event(...)

```mermaid
flowchart TD
    N001["split_tool_event(...)"]
    N002["tool_name = get(...)"]
    N003["tool_input = event.get('<str>') or {}"]
    N004["if not isinstance(tool_name, str) or not isinstance(tool_input, dict)"]
    N005["print(...)"]
    N006["return None"]
    N007["return (tool_name, tool_input)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
```

## run_event_hook(...)

```mermaid
flowchart TD
    N001["run_event_hook(...)"]
    N002["event = read_event(...)"]
    N003["if event is None or not isinstance(event, dict)"]
    N004["return 0"]
    N005["emit_decision(...)"]
    N006["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## run_tool_hook(...)

```mermaid
flowchart TD
    N001["run_tool_hook(...)"]
    N002["event = read_event(...)"]
    N003["if event is None or not isinstance(event, dict)"]
    N004["return 0"]
    N005["split = split_tool_event(...)"]
    N006["if split is None"]
    N007["return 0"]
    N008["emit_decision(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```
