# AST graph: scripts/gate_cache_regime_advisor.py

This file is generated from `scripts/gate_cache_regime_advisor.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## amortization_advice(...)

```mermaid
flowchart TD
    N001["amortization_advice(...)"]
    N002["if write_tokens < _MIN_WRITE_TOKENS"]
    N003["return None"]
    N004["ratio = read_tokens / write_tokens if write_tokens else 0.0"]
    N005["if ratio >= _MIN_AMORTIZATION_RATIO"]
    N006["return None"]
    N007["return f'<str>{ratio:<str>}<str>{read_tokens:<str>}<str>{write_tokens:<str>}<str>{_MIN_AMORTIZATION_RATIO:<str>}<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["if event.get('hook_event_name') not in (None, 'Stop')"]
    N003["return None"]
    N004["if event.get('stop_hook_active')"]
    N005["return None"]
    N006["transcript_path = get(...)"]
    N007["if not isinstance(transcript_path, str) or not transcript_path"]
    N008["return None"]
    N009["entries = load_transcript(...)"]
    N010["tokens = aggregate_usages(...)"]
    N011["write_tokens = tokens.cache_write_5m + tokens.cache_write_1h"]
    N012["return amortization_advice(tokens.cache_read, write_tokens)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["event = read_event(...)"]
    N003["if event is None"]
    N004["return 0"]
    N005["try"]
    N006["advice = evaluate(...)"]
    N007["except Exception"]
    N008["print(...)"]
    N009["return 0"]
    N010["if advice is not None"]
    N011["print(...)"]
    N012["emit_decision(...)"]
    N013["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N012
    N012 --> N013
```
