# AST graph: scripts/gate_agents_skills_edit.py

This file is generated from `scripts/gate_agents_skills_edit.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _normalize(...)

```mermaid
flowchart TD
    N001["_normalize(...)"]
    N002["token = strip(...)"]
    N003["while token.startswith('<str>'):     token = token[2:]"]
    N004["return token"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _match_normalized(...)

```mermaid
flowchart TD
    N001["_match_normalized(...)"]
    N002["for prefix in MANAGED_PREFIXES:     root = prefix.rstrip('<str>')     if token == root or token.endswith('<str>' + root) or token.startswith(prefix) or ('<str>' + prefix in token):         return prefix"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## matched_prefix(...)

```mermaid
flowchart TD
    N001["matched_prefix(...)"]
    N002["return _match_normalized(_normalize(path))"]
    N001 -->|"start"| N002
```

## _managed_target(...)

```mermaid
flowchart TD
    N001["_managed_target(...)"]
    N002["normalized = _normalize(...)"]
    N003["return normalized if _match_normalized(normalized) is not None else None"]
    N001 -->|"start"| N002
    N002 --> N003
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

## _segments(...)

```mermaid
flowchart TD
    N001["_segments(...)"]
    N002["segments = []"]
    N003["buf = []"]
    N004["quote = None"]
    N005["i = 0"]
    N006["n = len(...)"]
    N007["while i < n:     ch = command[i]     if quote is not None:         buf.append(ch)         if ch == quote:             quote = None         i += 1     elif ch in ('<str>', '<str>'):         quote = ch         buf.append(ch)         i += 1     elif ch in ('<str>', '<str>'):         segments.append('<str>'.join(buf))         buf = []         i += 1     elif ch == '<str>':         segments.append('<str>'.join(buf))         buf = []         i += 2 if command[i:i + 2] == '<str>' else 1     elif ch == '<str>' and (not (buf and buf[-1] == '<str>')):         segments.append('<str>'.join(buf))         buf = []         i += 2 if command[i:i + 2] == '<str>' else 1     else:         buf.append(ch)         i += 1"]
    N008["append(...)"]
    N009["return [seg.strip() for seg in segments if seg.strip()]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## _redirect_targets(...)

```mermaid
flowchart TD
    N001["_redirect_targets(...)"]
    N002["targets = []"]
    N003["skip_next = False"]
    N004["for index, token in enumerate(tokens):     if skip_next:         skip_next = False         continue     match = _REDIRECT_RE.match(token)     if match is None:         continue     attached = match.group(1)     if attached:         targets.append(attached)     elif index + 1 < len(tokens):         targets.append(tokens[index + 1])         skip_next = True"]
    N005["return targets"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _mutator_targets(...)

```mermaid
flowchart TD
    N001["_mutator_targets(...)"]
    N002["targets = []"]
    N003["for arg in args:     target = _managed_target(arg)     if target is None and '<str>' in arg:         target = _managed_target(arg.split('<str>', 1)[1])     if target is not None:         targets.append(target)"]
    N004["return targets"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _dash_c_script(...)

```mermaid
flowchart TD
    N001["_dash_c_script(...)"]
    N002["for index, arg in enumerate(args):     if _DASH_C_RE.match(arg) and index + 1 < len(args):         return args[index + 1]"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _segment_write_targets(...)

```mermaid
flowchart TD
    N001["_segment_write_targets(...)"]
    N002["tokens = _tokenize(...)"]
    N003["targets = [managed for raw in _redirect_targets(tokens) if (managed := _managed_target(raw)) is not None]"]
    N004["(cmd, args) = _leading_command(...)"]
    N005["if cmd in _SHELL_COMMANDS and depth < _MAX_RECURSION_DEPTH"]
    N006["script = _dash_c_script(...)"]
    N007["if script"]
    N008["extend(...)"]
    N009["if cmd in _WRITE_COMMANDS"]
    N010["extend(...)"]
    N011["return targets"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N005 -->|"false"| N009
    N009 -->|"true"| N010
    N008 --> N011
    N007 -->|"false"| N011
    N010 --> N011
    N009 -->|"false"| N011
```

## managed_write_targets(...)

```mermaid
flowchart TD
    N001["managed_write_targets(...)"]
    N002["targets = []"]
    N003["for segment in _segments(command):     targets.extend(_segment_write_targets(segment, depth))"]
    N004["return list(dict.fromkeys(targets))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _change_path_guidance(...)

```mermaid
flowchart TD
    N001["_change_path_guidance(...)"]
    N002["return '<str>'"]
    N001 -->|"start"| N002
```

## _deny_edit(...)

```mermaid
flowchart TD
    N001["_deny_edit(...)"]
    N002["return build_deny(f'<str>{path}<str>{prefix}<str>' + _change_path_guidance())"]
    N001 -->|"start"| N002
```

## _deny_bash(...)

```mermaid
flowchart TD
    N001["_deny_bash(...)"]
    N002["pretty = join(...)"]
    N003["return build_deny(f'<str>{pretty}<str>' + _change_path_guidance())"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _decide_edit(...)

```mermaid
flowchart TD
    N001["_decide_edit(...)"]
    N002["raw_path = tool_input.get('<str>') or tool_input.get('<str>')"]
    N003["if not isinstance(raw_path, str) or not raw_path"]
    N004["return None"]
    N005["prefix = matched_prefix(...)"]
    N006["if prefix is None"]
    N007["return None"]
    N008["return _deny_edit(raw_path, prefix)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _decide_bash(...)

```mermaid
flowchart TD
    N001["_decide_bash(...)"]
    N002["if not command.strip()"]
    N003["return None"]
    N004["targets = managed_write_targets(...)"]
    N005["if not targets"]
    N006["return None"]
    N007["return _deny_bash(targets)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if tool_name in _EDIT_TOOLS"]
    N003["return _decide_edit(tool_input)"]
    N004["if tool_name == 'Bash'"]
    N005["return _decide_bash(str(tool_input.get('<str>') or '<str>'))"]
    N006["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_tool_hook('<str>', decide, auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
```
