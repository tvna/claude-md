# AST graph: scripts/preflight_codex_github_footer.py

This file is generated from `scripts/preflight_codex_github_footer.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_body(...)

```mermaid
flowchart TD
    N001["extract_body(...)"]
    N002["body = get(...)"]
    N003["if body is None"]
    N004["return None"]
    N005["if not isinstance(body, str)"]
    N006["return '<str>'"]
    N007["return body"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## _first_string(...)

```mermaid
flowchart TD
    N001["_first_string(...)"]
    N002["for key in keys:     value = mapping.get(key)     if isinstance(value, str) and value.strip():         return value.strip()"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## resolve_model(...)

```mermaid
flowchart TD
    N001["resolve_model(...)"]
    N002["model = _first_string(...)"]
    N003["if model is not None"]
    N004["return model"]
    N005["metadata = get(...)"]
    N006["if isinstance(metadata, dict)"]
    N007["model = _first_string(...)"]
    N008["if model is not None"]
    N009["return model"]
    N010["env = os.environ if environ is None else environ"]
    N011["for name in _MODEL_ENV_NAMES:     value = env.get(name)     if value and value.strip():         return value.strip()"]
    N012["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N006 -->|"false"| N010
    N010 --> N011
    N011 --> N012
```

## build_deny_reason(...)

```mermaid
flowchart TD
    N001["build_deny_reason(...)"]
    N002["if model is None"]
    N003["return '<str>'"]
    N004["try"]
    N005["expected = build_codex_attribution_footer(...)"]
    N006["except ValueError"]
    N007["expected = f'<str>{exc}<str>'"]
    N008["return f'<str>{expected}<str>' + '<str>'.join(errors)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N007 --> N008
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if canonical_github_tool(tool_name) not in _TARGET_TOOLS"]
    N003["return None"]
    N004["body = extract_body(...)"]
    N005["if body is None"]
    N006["return None"]
    N007["event_data = {} if event is None else event"]
    N008["model = resolve_model(...)"]
    N009["if model is None"]
    N010["return build_deny(build_deny_reason([], None))"]
    N011["errors = verify_codex_attribution_footer(...)"]
    N012["if not errors"]
    N013["return None"]
    N014["return build_deny(build_deny_reason(errors, model))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["def _decide(event: dict[str, Any]) -> dict[str, Any] | None:     split = split_tool_event(event, '<str>')     if split is None:         return None     tool_name, tool_input = split     return decide(tool_name, tool_input, event=event)"]
    N004["return run_event_hook('<str>', _decide)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
