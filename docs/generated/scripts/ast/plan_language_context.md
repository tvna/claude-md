# AST graph: scripts/plan_language_context.py

This file is generated from `scripts/plan_language_context.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## load_contributor_languages(...)

```mermaid
flowchart TD
    N001["load_contributor_languages(...)"]
    N002["if not toml_text.strip()"]
    N003["return {}"]
    N004["import tomllib"]
    N005["data = loads(...)"]
    N006["out = {}"]
    N007["for key, value in data.items():     if isinstance(key, str) and isinstance(value, str):         out[key.lower()] = value"]
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
    N002["if env_lang and env_lang.strip()"]
    N003["return ('<str>', env_lang.strip())"]
    N004["mapping = load_contributor_languages(...)"]
    N005["for source, identity in (('<str>', git_email), ('<str>', git_name)):     if identity and identity.strip():         iso = mapping.get(identity.strip().lower())         if iso:             return (source, iso)"]
    N006["return (None, None)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## build_context_message(...)

```mermaid
flowchart TD
    N001["build_context_message(...)"]
    N002["return f'<str>{source}<str>{iso}<str>{iso}<str>'"]
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
    N002["(source, iso) = resolve_language(...)"]
    N003["if source is not None and iso is not None"]
    N004["message = build_context_message(...)"]
    N005["message = build_handoff_message(...)"]
    N006["return {'<str>': {'<str>': '<str>', '<str>': message}}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N004 --> N006
    N005 --> N006
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

## _git_identity(...)

```mermaid
flowchart TD
    N001["_git_identity(...)"]
    N002["def _read(key: str) -> str | None:     cmd = ['<str>', '<str>', '<str>', key]     try:         result = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS, check=False)     except (OSError, subprocess.SubprocessError):         return None     if result.returncode != 0:         return None     value = result.stdout.strip()     return value or None"]
    N003["return (_read('<str>'), _read('<str>'))"]
    N001 -->|"start"| N002
    N002 --> N003
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
    N009["toml_path = root / _CONTRIBUTORS_TOML_PATH"]
    N010["try"]
    N011["toml_text = read_text(...)"]
    N012["except FileNotFoundError"]
    N013["toml_text = '<str>'"]
    N014["except OSError"]
    N015["print(...)"]
    N016["return 0"]
    N017["env_lang = get(...)"]
    N018["(git_email, git_name) = _git_identity(...)"]
    N019["try"]
    N020["decision = decide(...)"]
    N021["except Exception"]
    N022["print(...)"]
    N023["return 0"]
    N024["emit_decision(...)"]
    N025["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N010 -->|"raises"| N014
    N014 --> N015
    N015 --> N016
    N011 --> N017
    N013 --> N017
    N017 --> N018
    N018 --> N019
    N019 -->|"try"| N020
    N019 -->|"raises"| N021
    N021 --> N022
    N022 --> N023
    N020 --> N024
    N024 --> N025
```
