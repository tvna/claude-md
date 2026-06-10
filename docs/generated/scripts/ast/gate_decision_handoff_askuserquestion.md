# AST graph: scripts/gate_decision_handoff_askuserquestion.py

This file is generated from `scripts/gate_decision_handoff_askuserquestion.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

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

## final_assistant_turn(...)

```mermaid
flowchart TD
    N001["final_assistant_turn(...)"]
    N002["last_user = -1"]
    N003["for idx, entry in enumerate(entries):     if _entry_role(entry) == '<str>':         last_user = idx"]
    N004["return [entry for entry in entries[last_user + 1:] if _entry_role(entry) == '<str>']"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## turn_used_tool(...)

```mermaid
flowchart TD
    N001["turn_used_tool(...)"]
    N002["for entry in turn:     for block in _content_blocks(entry):         if block.get('<str>') == '<str>' and block.get('<str>') == tool_name:             return True"]
    N003["return False"]
    N001 -->|"start"| N002
    N002 --> N003
```

## last_text_block(...)

```mermaid
flowchart TD
    N001["last_text_block(...)"]
    N002["text = '<str>'"]
    N003["for entry in turn:     for block in _content_blocks(entry):         if block.get('<str>') == '<str>' and isinstance(block.get('<str>'), str):             text = block['<str>']"]
    N004["return text"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _enumerated_option_count(...)

```mermaid
flowchart TD
    N001["_enumerated_option_count(...)"]
    N002["return sum((1 for line in text.splitlines() if _OPTION_LINE_RE.match(line)))"]
    N001 -->|"start"| N002
```

## delegates_decision(...)

```mermaid
flowchart TD
    N001["delegates_decision(...)"]
    N002["if not text"]
    N003["return False"]
    N004["if '?' not in text and '？' not in text"]
    N005["return False"]
    N006["lowered = lower(...)"]
    N007["if any((cue in lowered for cue in CHOICE_CUES))"]
    N008["return True"]
    N009["return _enumerated_option_count(text) >= 2"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["if event.get('hook_event_name') not in (None, 'Stop')"]
    N003["return None"]
    N004["if event.get('stop_hook_active')"]
    N005["return None"]
    N006["turn = final_assistant_turn(...)"]
    N007["if not turn"]
    N008["return None"]
    N009["if turn_used_tool(turn, _STRUCTURED_QUESTION_TOOL)"]
    N010["return None"]
    N011["if turn_used_tool(turn, _PLAN_MODE_TOOL)"]
    N012["return None"]
    N013["if not delegates_decision(last_text_block(turn))"]
    N014["return None"]
    N015["return {'<str>': '<str>', '<str>': _BLOCK_REASON}"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
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
