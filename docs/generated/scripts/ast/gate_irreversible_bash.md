# AST graph: scripts/gate_irreversible_bash.py

This file is generated from `scripts/gate_irreversible_bash.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _normalize(...)

```mermaid
flowchart TD
    N001["_normalize(...)"]
    N002["return token.strip().strip('<str>')"]
    N001 -->|"start"| N002
```

## _segments(...)

```mermaid
flowchart TD
    N001["_segments(...)"]
    N002["return [seg.strip() for seg in _SEGMENT_SPLIT.split(command) if seg.strip()]"]
    N001 -->|"start"| N002
```

## _tokenize(...)

```mermaid
flowchart TD
    N001["_tokenize(...)"]
    N002["try"]
    N003["return shlex.split(segment)"]
    N004["except ValueError"]
    N005["return segment.split()"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## _leading_command(...)

```mermaid
flowchart TD
    N001["_leading_command(...)"]
    N002["index = 0"]
    N003["while index < len(tokens) and _ASSIGN_RE.match(tokens[index]):     index += 1"]
    N004["if index >= len(tokens)"]
    N005["return ('<str>', [])"]
    N006["name = PurePosixPath(_normalize(tokens[index])).name"]
    N007["return (name, tokens[index + 1:])"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```

## _has_short_flag(...)

```mermaid
flowchart TD
    N001["_has_short_flag(...)"]
    N002["return any((arg.startswith('<str>') and (not arg.startswith('<str>')) and (char in arg[1:]) for arg in args))"]
    N001 -->|"start"| N002
```

## _is_rm_recursive_force(...)

```mermaid
flowchart TD
    N001["_is_rm_recursive_force(...)"]
    N002["recursive = _has_short_flag(args, '<str>') or _has_short_flag(args, '<str>') or '<str>' in args"]
    N003["force = _has_short_flag(args, '<str>') or '<str>' in args"]
    N004["return recursive and force"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _classify(...)

```mermaid
flowchart TD
    N001["_classify(...)"]
    N002["(cmd, args) = _leading_command(...)"]
    N003["if not cmd"]
    N004["return None"]
    N005["if cmd == 'rm' and _is_rm_recursive_force(args)"]
    N006["return '<str>'"]
    N007["if cmd == 'git' and 'push' in args and ('--force' in args or '-f' in args)"]
    N008["return '<str>'"]
    N009["if cmd == 'find' and '-delete' in args"]
    N010["return '<str>'"]
    N011["if cmd == 'dd' and any((arg.startswith('of=') for arg in args))"]
    N012["return '<str>'"]
    N013["if cmd == 'mkfs' or cmd.startswith('mkfs.')"]
    N014["return '<str>'"]
    N015["if cmd == 'shred'"]
    N016["return '<str>'"]
    N017["if cmd == 'truncate' and ('-s' in args or any((arg.startswith('--size') for arg in args)))"]
    N018["return '<str>'"]
    N019["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
```

## _deny(...)

```mermaid
flowchart TD
    N001["_deny(...)"]
    N002["return {'<str>': '<str>', '<str>': f'<str>{_DENY_RULE}<str>{label}<str>{_ACK_MARKER}<str>'}"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if tool_name != 'Bash'"]
    N003["return None"]
    N004["command = str(...)"]
    N005["if not command.strip()"]
    N006["return None"]
    N007["if _ACK_MARKER in command"]
    N008["return None"]
    N009["for segment in _segments(command):     label = _classify(segment)     if label is not None:         return _deny(label)"]
    N010["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
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
