# AST graph: scripts/gate_unsigned_commit_bash.py

This file is generated from `scripts/gate_unsigned_commit_bash.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

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

## _disables_signing(...)

```mermaid
flowchart TD
    N001["_disables_signing(...)"]
    N002["for i, raw in enumerate(args):     arg = _normalize(raw)     if arg == '<str>':         return '<str>'     if arg == '<str>' and i + 1 < len(args):         value = _normalize(args[i + 1])         if _GPGSIGN_OFF_RE.match(value):             return '<str>'"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _classify(...)

```mermaid
flowchart TD
    N001["_classify(...)"]
    N002["(cmd, args) = _leading_command(...)"]
    N003["if cmd != 'git'"]
    N004["return None"]
    N005["return _disables_signing(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
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
