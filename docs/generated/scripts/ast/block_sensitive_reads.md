# AST graph: scripts/block_sensitive_reads.py

This file is generated from `scripts/block_sensitive_reads.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _normalize(...)

```mermaid
flowchart TD
    N001["_normalize(...)"]
    N002["return path.strip().strip('<str>')"]
    N001 -->|"start"| N002
```

## is_sensitive_path(...)

```mermaid
flowchart TD
    N001["is_sensitive_path(...)"]
    N002["cleaned = _normalize(...)"]
    N003["if not cleaned"]
    N004["return False"]
    N005["if cleaned in ALLOWLIST_PATHS"]
    N006["return False"]
    N007["pure = PurePosixPath(...)"]
    N008["name = pure.name"]
    N009["for glob in _SENSITIVE_BASENAME_GLOBS:     if fnmatch.fnmatch(name, glob):         return True"]
    N010["segments = set(...)"]
    N011["if segments & _SENSITIVE_DIR_SEGMENTS"]
    N012["return True"]
    N013["return '<str>' in segments and '<str>' in segments"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```

## _tokenize(...)

```mermaid
flowchart TD
    N001["_tokenize(...)"]
    N002["try"]
    N003["return shlex.split(command)"]
    N004["except ValueError"]
    N005["return command.split()"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## _bash_sensitive_target(...)

```mermaid
flowchart TD
    N001["_bash_sensitive_target(...)"]
    N002["tokens = _tokenize(...)"]
    N003["if not tokens"]
    N004["return None"]
    N005["has_reader = any(...)"]
    N006["if not has_reader"]
    N007["return None"]
    N008["for tok in tokens:     if is_sensitive_path(tok):         return _normalize(tok)"]
    N009["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## _deny(...)

```mermaid
flowchart TD
    N001["_deny(...)"]
    N002["return {'<str>': '<str>', '<str>': f'<str>{_DENY_RULE}<str>{path!r}<str>'}"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if tool_name == 'Read'"]
    N003["path = str(...)"]
    N004["if path and is_sensitive_path(path)"]
    N005["return _deny(_normalize(path))"]
    N006["return None"]
    N007["if tool_name == 'Bash'"]
    N008["command = str(...)"]
    N009["matched = _bash_sensitive_target(...)"]
    N010["if matched is not None"]
    N011["return _deny(matched)"]
    N012["return None"]
    N013["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N002 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N007 -->|"false"| N013
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["event = read_event(...)"]
    N004["if event is None"]
    N005["return 0"]
    N006["tool_name = get(...)"]
    N007["if not isinstance(tool_name, str)"]
    N008["print(...)"]
    N009["return 0"]
    N010["tool_input = get(...)"]
    N011["if not isinstance(tool_input, dict)"]
    N012["tool_input = {}"]
    N013["emit_decision(...)"]
    N014["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N013
    N013 --> N014
```
