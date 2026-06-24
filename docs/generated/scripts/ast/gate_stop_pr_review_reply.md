# AST graph: scripts/gate_stop_pr_review_reply.py

This file is generated from `scripts/gate_stop_pr_review_reply.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _content_blocks(...)

```mermaid
flowchart TD
    N001["_content_blocks(...)"]
    N002["if not isinstance(entry, dict)"]
    N003["return []"]
    N004["message = get(...)"]
    N005["if not isinstance(message, dict)"]
    N006["return []"]
    N007["content = get(...)"]
    N008["if isinstance(content, list)"]
    N009["return [block for block in content if isinstance(block, dict)]"]
    N010["return []"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
```

## _entry_role(...)

```mermaid
flowchart TD
    N001["_entry_role(...)"]
    N002["if not isinstance(entry, dict)"]
    N003["return '<str>'"]
    N004["message = get(...)"]
    N005["if isinstance(message, dict)"]
    N006["role = get(...)"]
    N007["if isinstance(role, str)"]
    N008["return role"]
    N009["entry_type = get(...)"]
    N010["return entry_type if isinstance(entry_type, str) else '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N005 -->|"false"| N009
    N009 --> N010
```

## _entry_text(...)

```mermaid
flowchart TD
    N001["_entry_text(...)"]
    N002["if not isinstance(entry, dict)"]
    N003["return '<str>'"]
    N004["message = get(...)"]
    N005["if not isinstance(message, dict)"]
    N006["return '<str>'"]
    N007["content = get(...)"]
    N008["if isinstance(content, str)"]
    N009["return content"]
    N010["if isinstance(content, list)"]
    N011["parts = []"]
    N012["for block in content:     if isinstance(block, dict) and block.get('<str>') == '<str>':         text = block.get('<str>')         if isinstance(text, str):             parts.append(text)"]
    N013["return '<str>'.join(parts)"]
    N014["return '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 -->|"true"| N011
    N011 --> N012
    N012 --> N013
    N010 -->|"false"| N014
```

## is_review_webhook(...)

```mermaid
flowchart TD
    N001["is_review_webhook(...)"]
    N002["if _entry_role(entry) != 'user'"]
    N003["return False"]
    N004["text = _entry_text(...)"]
    N005["if '<github-webhook-activity>' not in text"]
    N006["return False"]
    N007["return any((marker in text for marker in REVIEW_MARKERS))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## _extract_session_login(...)

```mermaid
flowchart TD
    N001["_extract_session_login(...)"]
    N002["get_me_ids = set(...)"]
    N003["get_me_found = False"]
    N004["for entry in entries:     for block in _content_blocks(entry):         if block.get('<str>') == '<str>' and block.get('<str>') == '<str>':             get_me_found = True             tool_id = block.get('<str>')             if isinstance(tool_id, str) and tool_id:                 get_me_ids.add(tool_id)"]
    N005["if not get_me_found"]
    N006["return None"]
    N007["for entry in entries:     if _entry_role(entry) != '<str>':         continue     for block in _content_blocks(entry):         if block.get('<str>') != '<str>':             continue         tool_use_id = block.get('<str>', '<str>')         if get_me_ids and tool_use_id not in get_me_ids:             continue         result_content = block.get('<str>')         texts: list[str] = []         if isinstance(result_content, str):             texts.append(result_content)         elif isinstance(result_content, list):             for c in result_content:                 if isinstance(c, dict) and c.get('<str>') == '<str>':                     t = c.get('<str>')                     if isinstance(t, str):                         texts.append(t)         for text in texts:             try:                 data = json.loads(text)                 if isinstance(data, dict):                     login = data.get('<str>')                     if isinstance(login, str) and login:                         return login             except json.JSONDecodeError:                 pass"]
    N008["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
```

## _is_self_authored_webhook(...)

```mermaid
flowchart TD
    N001["_is_self_authored_webhook(...)"]
    N002["if not session_login"]
    N003["return False"]
    N004["text = _entry_text(...)"]
    N005["m = search(...)"]
    N006["return m is not None and m.group(1) == session_login"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## has_reply_tool_call(...)

```mermaid
flowchart TD
    N001["has_reply_tool_call(...)"]
    N002["for entry in entries[after_idx + 1:]:     for block in _content_blocks(entry):         if block.get('<str>') == '<str>' and block.get('<str>') in REPLY_TOOLS:             return True"]
    N003["return False"]
    N001 -->|"start"| N002
    N002 --> N003
```

## find_unaddressed_review_webhooks(...)

```mermaid
flowchart TD
    N001["find_unaddressed_review_webhooks(...)"]
    N002["return [idx for idx, entry in enumerate(entries) if is_review_webhook(entry) and (not _is_self_authored_webhook(entry, session_login)) and (not has_reply_tool_call(entries, idx))]"]
    N001 -->|"start"| N002
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["if event.get('hook_event_name') not in (None, 'Stop')"]
    N003["return None"]
    N004["if event.get('stop_hook_active')"]
    N005["return None"]
    N006["session_login = _extract_session_login(...)"]
    N007["if not find_unaddressed_review_webhooks(entries, session_login)"]
    N008["return None"]
    N009["return {'<str>': '<str>', '<str>': _BLOCK_REASON}"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## load_transcript(...)

```mermaid
flowchart TD
    N001["load_transcript(...)"]
    N002["if not isinstance(path_value, str) or not path_value"]
    N003["return []"]
    N004["path = Path(...)"]
    N005["try"]
    N006["raw = read_text(...)"]
    N007["except OSError"]
    N008["return []"]
    N009["entries = []"]
    N010["for line in raw.splitlines():     line = line.strip()     if not line:         continue     try:         entries.append(json.loads(line))     except json.JSONDecodeError:         continue"]
    N011["return entries"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N009 --> N010
    N010 --> N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["event = read_event(...)"]
    N003["if event is None"]
    N004["return 0"]
    N005["try"]
    N006["entries = load_transcript(...)"]
    N007["decision = evaluate(...)"]
    N008["except Exception"]
    N009["print(...)"]
    N010["return 0"]
    N011["emit_decision(...)"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N006 --> N007
    N005 -->|"raises"| N008
    N008 --> N009
    N009 --> N010
    N007 --> N011
    N011 --> N012
```
