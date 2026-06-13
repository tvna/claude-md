# AST graph: scripts/preflight_session_branch_authz.py

This file is generated from `scripts/preflight_session_branch_authz.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _read_authorized_branches(...)

```mermaid
flowchart TD
    N001["_read_authorized_branches(...)"]
    N002["return read_authorized_set(_SESSION_BRANCH_FILE)"]
    N001 -->|"start"| N002
```

## _current_branch(...)

```mermaid
flowchart TD
    N001["_current_branch(...)"]
    N002["try"]
    N003["head = strip(...)"]
    N004["except OSError"]
    N005["return None"]
    N006["if not head.startswith(_HEAD_REF_PREFIX)"]
    N007["return None"]
    N008["branch = strip(...)"]
    N009["return branch or None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## _resolve_target(...)

```mermaid
flowchart TD
    N001["_resolve_target(...)"]
    N002["create_flags = _CREATE_FLAGS_SWITCH if verb == '<str>' else _CREATE_FLAGS_CHECKOUT"]
    N003["positional = None"]
    N004["i = 0"]
    N005["n = len(...)"]
    N006["while i < n:     tok = tokens[i]     if tok == '<str>':         break     if tok.startswith('<str>') and tok != '<str>':         if tok in _DETACH_FLAGS:             return None         if '<str>' in tok:             flag, value = tok.split('<str>', 1)             if flag in create_flags:                 return ('<str>', value) if value else None             i += 1             continue         if tok in create_flags:             if i + 1 < n and (not tokens[i + 1].startswith('<str>')):                 return ('<str>', tokens[i + 1])             return None         i += 1         continue     if positional is None and tok != '<str>':         positional = tok     i += 1"]
    N007["if verb == 'switch' and positional"]
    N008["return ('<str>', positional)"]
    N009["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## _iter_branch_targets(...)

```mermaid
flowchart TD
    N001["_iter_branch_targets(...)"]
    N002["targets = []"]
    N003["for segment in _SEGMENT_SPLIT_RE.split(command):     match = _GIT_SWITCH_HEAD_RE.match(segment.strip())     if match is None:         continue     verb = match.group(1)     try:         tokens = shlex.split(match.group(2))     except ValueError:         continue     resolved = _resolve_target(verb, tokens)     if resolved is not None:         targets.append(resolved)"]
    N004["return targets"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _target_hint(...)

```mermaid
flowchart TD
    N001["_target_hint(...)"]
    N002["pushable = sorted(...)"]
    N003["return pushable[0] if pushable else sorted(authorized)[0]"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _deny_switch(...)

```mermaid
flowchart TD
    N001["_deny_switch(...)"]
    N002["authorized_list = join(...)"]
    N003["hint = _target_hint(...)"]
    N004["action = '<str>' if mode == '<str>' else '<str>'"]
    N005["return build_deny(f'<str>{authorized_list}<str>{action}<str>{branch}<str>{hint}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _deny_edit(...)

```mermaid
flowchart TD
    N001["_deny_edit(...)"]
    N002["authorized_list = join(...)"]
    N003["hint = _target_hint(...)"]
    N004["return build_deny(f'<str>{path}<str>{current}<str>{authorized_list}<str>{hint}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _is_within_repo(...)

```mermaid
flowchart TD
    N001["_is_within_repo(...)"]
    N002["return resolved == REPO_ROOT or REPO_ROOT in resolved.parents"]
    N001 -->|"start"| N002
```

## _decide_bash(...)

```mermaid
flowchart TD
    N001["_decide_bash(...)"]
    N002["authorized = _read_authorized_branches(...)"]
    N003["if not authorized"]
    N004["return None"]
    N005["for mode, branch in _iter_branch_targets(command):     if not is_authorized(branch, authorized):         return _deny_switch(mode, branch, authorized)"]
    N006["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## _decide_edit(...)

```mermaid
flowchart TD
    N001["_decide_edit(...)"]
    N002["raw_path = tool_input.get('<str>') or tool_input.get('<str>')"]
    N003["if not isinstance(raw_path, str) or not raw_path"]
    N004["return None"]
    N005["try"]
    N006["resolved = resolve(...)"]
    N007["except (OSError, RuntimeError, ValueError)"]
    N008["return None"]
    N009["if not _is_within_repo(resolved)"]
    N010["return None"]
    N011["authorized = _read_authorized_branches(...)"]
    N012["if not authorized"]
    N013["return None"]
    N014["current = _current_branch(...)"]
    N015["if not current"]
    N016["return None"]
    N017["if is_authorized(current, authorized)"]
    N018["return None"]
    N019["return _deny_edit(current, authorized, raw_path)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if os.environ.get(_REMOTE_ENV_VAR, '').lower() != 'true'"]
    N003["return None"]
    N004["tool_name = get(...)"]
    N005["tool_input = event.get('<str>') or {}"]
    N006["if not isinstance(tool_input, dict)"]
    N007["return None"]
    N008["if tool_name == 'Bash'"]
    N009["return _decide_bash(str(tool_input.get('<str>') or '<str>'))"]
    N010["if tool_name in _EDIT_TOOLS"]
    N011["return _decide_edit(tool_input)"]
    N012["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_event_hook('<str>', decide, auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
```
