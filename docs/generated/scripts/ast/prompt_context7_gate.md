# AST graph: scripts/prompt_context7_gate.py

This file is generated from `scripts/prompt_context7_gate.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _prompt_text(...)

```mermaid
flowchart TD
    N001["_prompt_text(...)"]
    N002["prompt = get(...)"]
    N003["return prompt if isinstance(prompt, str) else '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## should_remind(...)

```mermaid
flowchart TD
    N001["should_remind(...)"]
    N002["if event.get('hook_event_name') != 'UserPromptSubmit'"]
    N003["return False"]
    N004["prompt = _prompt_text(...)"]
    N005["return bool(prompt and _LOOKUP_TERMS.search(prompt))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if not should_remind(event)"]
    N003["return None"]
    N004["return {'<str>': {'<str>': '<str>', '<str>': CONTEXT7_REMINDER}}"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["event = read_event(...)"]
    N004["if event is None"]
    N005["return 0"]
    N006["emit_decision(...)"]
    N007["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```
