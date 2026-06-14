# AST graph: scripts/stop_new_session_handoff_prompt.py

This file is generated from `scripts/stop_new_session_handoff_prompt.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

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

## turn_text(...)

```mermaid
flowchart TD
    N001["turn_text(...)"]
    N002["parts = []"]
    N003["for entry in turn:     for block in _content_blocks(entry):         if block.get('<str>') == '<str>' and isinstance(block.get('<str>'), str):             parts.append(block['<str>'])"]
    N004["return '<str>'.join(parts)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _strip_survey_vocab(...)

```mermaid
flowchart TD
    N001["_strip_survey_vocab(...)"]
    N002["for phrase in SURVEY_NEUTRALIZE:     lowered = lowered.replace(phrase.lower(), '<str>')"]
    N003["return lowered"]
    N001 -->|"start"| N002
    N002 --> N003
```

## signals_handoff(...)

```mermaid
flowchart TD
    N001["signals_handoff(...)"]
    N002["lowered = _strip_survey_vocab(...)"]
    N003["return any((cue in lowered for cue in HANDOFF_CUES))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## signals_terminal_wait(...)

```mermaid
flowchart TD
    N001["signals_terminal_wait(...)"]
    N002["lowered = lower(...)"]
    N003["return any((cue in lowered for cue in TERMINAL_WAIT_CUES))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## already_provided(...)

```mermaid
flowchart TD
    N001["already_provided(...)"]
    N002["lowered = lower(...)"]
    N003["return any((marker in lowered for marker in PROVIDED_MARKERS))"]
    N001 -->|"start"| N002
    N002 --> N003
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
    N009["text = turn_text(...)"]
    N010["if signals_terminal_wait(text)"]
    N011["return None"]
    N012["if not signals_handoff(text)"]
    N013["return None"]
    N014["if already_provided(text)"]
    N015["return None"]
    N016["return {'<str>': '<str>', '<str>': _BLOCK_REASON}"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
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
