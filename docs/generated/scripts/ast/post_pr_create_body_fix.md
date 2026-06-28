# AST graph: scripts/post_pr_create_body_fix.py

This file is generated from `scripts/post_pr_create_body_fix.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## build_harness_session_footer(...)

```mermaid
flowchart TD
    N001["build_harness_session_footer(...)"]
    N002["if env.get(_REMOTE_ENV_VAR, '').strip().lower() != 'true'"]
    N003["return None"]
    N004["raw = strip(...)"]
    N005["if not raw"]
    N006["return None"]
    N007["token = raw[len(_CSE_PREFIX):] if raw.startswith(_CSE_PREFIX) else raw"]
    N008["if not token"]
    N009["return None"]
    N010["footer = f'<str>{_AGENT_NAME}<str>{_SESSION_URL_PREFIX}{token}<str>'"]
    N011["if not _AGENT_ATTRIBUTION_FOOTER_RE.fullmatch(footer)"]
    N012["return None"]
    N013["return footer"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```

## has_trailing_agent_footer(...)

```mermaid
flowchart TD
    N001["has_trailing_agent_footer(...)"]
    N002["lines = splitlines(...)"]
    N003["return bool(lines and _AGENT_ATTRIBUTION_FOOTER_RE.fullmatch(lines[-1].strip()))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## extract_trailing_agent_footer(...)

```mermaid
flowchart TD
    N001["extract_trailing_agent_footer(...)"]
    N002["found = None"]
    N003["for line in html.unescape(body.replace('<str>', '<str>')).splitlines():     stripped = line.strip()     if _AGENT_ATTRIBUTION_FOOTER_RE.fullmatch(stripped):         found = stripped"]
    N004["return found"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _walk(...)

```mermaid
flowchart TD
    N001["_walk(...)"]
    N002["out = []"]
    N003["stack = [value]"]
    N004["while stack and len(out) < 200:     node = stack.pop()     out.append(node)     if isinstance(node, dict):         stack.extend(node.values())     elif isinstance(node, list):         stack.extend(node)"]
    N005["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## extract_pr_coords(...)

```mermaid
flowchart TD
    N001["extract_pr_coords(...)"]
    N002["for node in _walk(tool_response):     if isinstance(node, str):         m = _PR_URL_RE.search(node)         if m:             return (m.group(1), m.group(2), m.group(3))"]
    N003["owner = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N004["repo = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N005["for node in _walk(tool_response):     if not isinstance(node, dict):         continue     for key in _NUMBER_KEYS:         val = node.get(key)         if isinstance(val, int) and val > 0:             return (owner, repo, str(val))         if isinstance(val, str) and val.isdecimal():             return (owner, repo, val)"]
    N006["return (None, None, None)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## extract_stored_body(...)

```mermaid
flowchart TD
    N001["extract_stored_body(...)"]
    N002["for node in _walk(tool_response):     if isinstance(node, dict):         val = node.get('<str>')         if isinstance(val, str):             return val"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _build_context(...)

```mermaid
flowchart TD
    N001["_build_context(...)"]
    N002["return {'<str>': {'<str>': '<str>', '<str>': message}}"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') != TARGET_TOOL"]
    N003["return None"]
    N004["tool_input = event.get('<str>') or {}"]
    N005["tool_response = get(...)"]
    N006["body = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N007["if not isinstance(body, str) or not body.strip()"]
    N008["return _build_context('<str>')"]
    N009["(owner, repo, pr_number) = extract_pr_coords(...)"]
    N010["if pr_number is None"]
    N011["return _build_context('<str>')"]
    N012["pr_label = f'{owner}<str>{repo}<str>{pr_number}' if owner and repo else f'<str>{pr_number}'"]
    N013["normalized = normalize_pr_body(...)"]
    N014["stored = extract_stored_body(...)"]
    N015["if not has_trailing_agent_footer(normalized)"]
    N016["carried_footer = build_harness_session_footer(...)"]
    N017["if carried_footer is None and stored is not None"]
    N018["carried_footer = extract_trailing_agent_footer(...)"]
    N019["if carried_footer is not None"]
    N020["normalized = f'{normalized.rstrip()}<str>{carried_footer}'"]
    N021["body_repr = normalized if len(normalized) <= _MAX_BODY_PREVIEW else normalized[:_MAX_BODY_PREVIEW] + '<str>'"]
    N022["dropped = detect_dropped_angle_tokens(body, stored) if stored is not None else []"]
    N023["warning = '<str>'"]
    N024["if dropped"]
    N025["tokens = join(...)"]
    N026["warning = f'<str>{tokens}<str>'"]
    N027["return _build_context(f'<str>{pr_label}<str>{owner or '<str>'}<str>{repo or '<str>'}<str>{pr_number}<str>{warning}<str>{body_repr}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N017 -->|"true"| N018
    N018 --> N019
    N017 -->|"false"| N019
    N019 -->|"true"| N020
    N020 --> N021
    N019 -->|"false"| N021
    N015 -->|"false"| N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
    N024 -->|"true"| N025
    N025 --> N026
    N026 --> N027
    N024 -->|"false"| N027
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["event = read_event(...)"]
    N004["if event is None"]
    N005["return 0"]
    N006["if not isinstance(event, dict)"]
    N007["return 0"]
    N008["emit_decision(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```
