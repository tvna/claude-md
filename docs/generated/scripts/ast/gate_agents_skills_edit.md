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
    N002["lexer = shlex(...)"]
    N003["lexer.whitespace_split = True"]
    N004["try"]
    N005["return (list(lexer), False)"]
    N006["except ValueError"]
    N007["return (segment.split(), True)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
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

## _is_redirect_op(...)

```mermaid
flowchart TD
    N001["_is_redirect_op(...)"]
    N002["return '<str>' in token and set(token) <= {'<str>', '<str>', '<str>'}"]
    N001 -->|"start"| N002
```

## _redirect_targets(...)

```mermaid
flowchart TD
    N001["_redirect_targets(...)"]
    N002["targets = []"]
    N003["for index, token in enumerate(tokens):     if _is_redirect_op(token) and index + 1 < len(tokens):         targets.append(tokens[index + 1])"]
    N004["return targets"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _fallback_redirect_targets(...)

```mermaid
flowchart TD
    N001["_fallback_redirect_targets(...)"]
    N002["targets = []"]
    N003["skip_next = False"]
    N004["for index, token in enumerate(tokens):     if skip_next:         skip_next = False         continue     match = _FALLBACK_REDIRECT_RE.match(token)     if match is None:         continue     attached = match.group(1)     if attached:         targets.append(attached)     elif index + 1 < len(tokens):         targets.append(tokens[index + 1])         skip_next = True"]
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
    N002["(tokens, used_fallback) = _tokenize(...)"]
    N003["raw_targets = _fallback_redirect_targets(tokens) if used_fallback else _redirect_targets(tokens)"]
    N004["targets = [managed for raw in raw_targets if (managed := _managed_target(raw)) is not None]"]
    N005["(cmd, args) = _leading_command(...)"]
    N006["if cmd in _SHELL_COMMANDS and depth < _MAX_RECURSION_DEPTH"]
    N007["script = _dash_c_script(...)"]
    N008["if script"]
    N009["extend(...)"]
    N010["if cmd in _WRITE_COMMANDS"]
    N011["extend(...)"]
    N012["return targets"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N006 -->|"false"| N010
    N010 -->|"true"| N011
    N009 --> N012
    N008 -->|"false"| N012
    N011 --> N012
    N010 -->|"false"| N012
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

## _resolve_base(...)

```mermaid
flowchart TD
    N001["_resolve_base(...)"]
    N002["explicit = get(...)"]
    N003["if explicit"]
    N004["return explicit"]
    N005["actions_base = get(...)"]
    N006["if actions_base"]
    N007["return f'<str>{actions_base}'"]
    N008["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _changed_files(...)

```mermaid
flowchart TD
    N001["_changed_files(...)"]
    N002["result = runner(...)"]
    N003["return frozenset((line.strip() for line in result.stdout.splitlines() if line.strip()))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## managed_changes(...)

```mermaid
flowchart TD
    N001["managed_changes(...)"]
    N002["return frozenset((path for path in changed if path.startswith(MANAGED_PREFIXES)))"]
    N001 -->|"start"| N002
```

## _superpowers_pin(...)

```mermaid
flowchart TD
    N001["_superpowers_pin(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError)"]
    N005["return None"]
    N006["for line in result.stdout.splitlines():     if line.lstrip().startswith('<str>'):         continue     match = _SUPERPOWERS_PIN_RE.search(line)     if match:         return match.group(1)"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
```

## evaluate_pr(...)

```mermaid
flowchart TD
    N001["evaluate_pr(...)"]
    N002["if not managed or pin_changed"]
    N003["return (0, [])"]
    N004["pretty = join(...)"]
    N005["return (1, [f'<str>{pretty}<str>{_PIN_FILE}<str>'])"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["base = args.base_ref or _resolve_base()"]
    N003["try"]
    N004["changed = _changed_files(...)"]
    N005["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError)"]
    N006["print(...)"]
    N007["return 1"]
    N008["managed = managed_changes(...)"]
    N009["pin_changed = False"]
    N010["if managed"]
    N011["base_pin = _superpowers_pin(...)"]
    N012["head_pin = _superpowers_pin(...)"]
    N013["pin_changed = base_pin is not None and head_pin is not None and (base_pin != head_pin)"]
    N014["(code, errors) = evaluate_pr(...)"]
    N015["if code == 0"]
    N016["if managed"]
    N017["print(...)"]
    N018["print(...)"]
    N019["return 0"]
    N020["for line in errors:     print(line, file=sys.stderr)"]
    N021["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N010 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N017 --> N019
    N018 --> N019
    N015 -->|"false"| N020
    N020 --> N021
```

## _parse_verify_args(...)

```mermaid
flowchart TD
    N001["_parse_verify_args(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["return parser.parse_args(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["args = sys.argv[1:] if argv is None else argv"]
    N003["if args and args[0] == 'verify'"]
    N004["return _cmd_verify(_parse_verify_args(args[1:]))"]
    N005["return run_tool_hook('<str>', decide, auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```
