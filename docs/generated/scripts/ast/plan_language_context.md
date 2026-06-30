# AST graph: scripts/plan_language_context.py

This file is generated from `scripts/plan_language_context.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## resolve_language(...)

```mermaid
flowchart TD
    N001["resolve_language(...)"]
    N002["if env_lang and env_lang.strip()"]
    N003["return env_lang.strip()"]
    N004["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## build_context_message(...)

```mermaid
flowchart TD
    N001["build_context_message(...)"]
    N002["return f'<str>{iso}<str>{iso}<str>'"]
    N001 -->|"start"| N002
```

## build_handoff_message(...)

```mermaid
flowchart TD
    N001["build_handoff_message(...)"]
    N002["return '<str>'"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["iso = resolve_language(...)"]
    N003["message = build_context_message(iso) if iso is not None else build_handoff_message()"]
    N004["return {'<str>': {'<str>': '<str>', '<str>': message}}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _read_event_stdin(...)

```mermaid
flowchart TD
    N001["_read_event_stdin(...)"]
    N002["raw = read(...)"]
    N003["if not raw.strip()"]
    N004["return {}"]
    N005["event = loads(...)"]
    N006["if not isinstance(event, dict)"]
    N007["raise ValueError(f'<str>{type(event).__name__}')"]
    N008["return event"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["try"]
    N004["_read_event_stdin(...)"]
    N005["except (json.JSONDecodeError, ValueError)"]
    N006["print(...)"]
    N007["return 0"]
    N008["env_lang = get(...)"]
    N009["decision = decide(...)"]
    N010["emit_decision(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
```
