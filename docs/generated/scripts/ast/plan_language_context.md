# AST graph: scripts/plan_language_context.py

This file is generated from `scripts/plan_language_context.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## parse_codeowners(...)

```mermaid
flowchart TD
    N001["parse_codeowners(...)"]
    N002["rules = []"]
    N003["for raw in text.splitlines():     line = raw.strip()     if not line or line.startswith('<str>'):         continue     parts = line.split()     if len(parts) < 2:         continue     pattern, handles = (parts[0], [p for p in parts[1:] if p.startswith('<str>')])     if handles:         rules.append((pattern, handles))"]
    N004["return rules"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## primary_owner(...)

```mermaid
flowchart TD
    N001["primary_owner(...)"]
    N002["counts = {}"]
    N003["order = []"]
    N004["for _pattern, handles in rules:     for handle in handles:         if handle not in counts:             order.append(handle)         counts[handle] = counts.get(handle, 0) + 1"]
    N005["if not counts"]
    N006["return None"]
    N007["max_count = max(...)"]
    N008["for handle in order:     if counts[handle] == max_count:         return handle"]
    N009["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
```

## load_owner_languages(...)

```mermaid
flowchart TD
    N001["load_owner_languages(...)"]
    N002["if not toml_text.strip()"]
    N003["return {}"]
    N004["import tomllib"]
    N005["data = loads(...)"]
    N006["out = {}"]
    N007["for key, value in data.items():     if isinstance(key, str) and isinstance(value, str):         out[key] = value"]
    N008["return out"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## resolve_language(...)

```mermaid
flowchart TD
    N001["resolve_language(...)"]
    N002["owner = primary_owner(...)"]
    N003["if owner is None"]
    N004["return (None, None)"]
    N005["languages = load_owner_languages(...)"]
    N006["return (owner, languages.get(owner))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## build_context_message(...)

```mermaid
flowchart TD
    N001["build_context_message(...)"]
    N002["return f'<str>{owner}<str>{iso}<str>{iso}<str>'"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["(owner, iso) = resolve_language(...)"]
    N003["if owner is None or iso is None"]
    N004["return None"]
    N005["return {'<str>': {'<str>': '<str>', '<str>': build_context_message(owner, iso)}}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _project_root(...)

```mermaid
flowchart TD
    N001["_project_root(...)"]
    N002["root = get(...)"]
    N003["if root"]
    N004["return Path(root)"]
    N005["if event is not None"]
    N006["cwd = get(...)"]
    N007["if isinstance(cwd, str) and cwd"]
    N008["return Path(cwd)"]
    N009["return Path.cwd()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N005 -->|"false"| N009
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
    N004["event = _read_event_stdin(...)"]
    N005["except (json.JSONDecodeError, ValueError)"]
    N006["print(...)"]
    N007["return 0"]
    N008["root = _project_root(...)"]
    N009["try"]
    N010["codeowners_text = read_text(...)"]
    N011["owners_toml_text = read_text(...)"]
    N012["except OSError"]
    N013["print(...)"]
    N014["return 0"]
    N015["try"]
    N016["decision = decide(...)"]
    N017["except Exception"]
    N018["print(...)"]
    N019["return 0"]
    N020["emit_decision(...)"]
    N021["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 --> N009
    N009 -->|"try"| N010
    N010 --> N011
    N009 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
    N011 --> N015
    N015 -->|"try"| N016
    N015 -->|"raises"| N017
    N017 --> N018
    N018 --> N019
    N016 --> N020
    N020 --> N021
```
