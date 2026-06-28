# AST graph: scripts/gate_handoff_retro_survey_askuserquestion.py

This file is generated from `scripts/gate_handoff_retro_survey_askuserquestion.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _build_block_reason(...)

```mermaid
flowchart TD
    N001["_build_block_reason(...)"]
    N002["pr_list = join(...)"]
    N003["return _BLOCK_REASON.format(pr_list=pr_list, primary=created[0])"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _marker_path(...)

```mermaid
flowchart TD
    N001["_marker_path(...)"]
    N002["return _MARKER_DIR / str(pr_number)"]
    N001 -->|"start"| N002
```

## _coerce_pr_number(...)

```mermaid
flowchart TD
    N001["_coerce_pr_number(...)"]
    N002["if isinstance(raw, bool)"]
    N003["return None"]
    N004["if isinstance(raw, int) and raw > 0"]
    N005["return raw"]
    N006["if isinstance(raw, float) and raw > 0 and raw.is_integer()"]
    N007["return int(raw)"]
    N008["if isinstance(raw, str) and raw.isdecimal() and (int(raw) > 0)"]
    N009["return int(raw)"]
    N010["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
```

## _coerce_satisfaction(...)

```mermaid
flowchart TD
    N001["_coerce_satisfaction(...)"]
    N002["if isinstance(raw, bool)"]
    N003["return None"]
    N004["value = None"]
    N005["if isinstance(raw, int)"]
    N006["value = raw"]
    N007["if isinstance(raw, float) and raw.is_integer() or (isinstance(raw, str) and raw.isdecimal())"]
    N008["value = int(...)"]
    N009["if value is None or not _MIN_SATISFACTION <= value <= _MAX_SATISFACTION"]
    N010["return None"]
    N011["return value"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N006 --> N009
    N008 --> N009
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

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

## _result_text(...)

```mermaid
flowchart TD
    N001["_result_text(...)"]
    N002["content = get(...)"]
    N003["if isinstance(content, str)"]
    N004["return content"]
    N005["if isinstance(content, list)"]
    N006["parts = [sub['<str>'] for sub in content if isinstance(sub, dict) and sub.get('<str>') == '<str>' and isinstance(sub.get('<str>'), str)]"]
    N007["return '<str>'.join(parts)"]
    N008["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
```

## created_pr_numbers(...)

```mermaid
flowchart TD
    N001["created_pr_numbers(...)"]
    N002["create_ids = set(...)"]
    N003["for entry in entries:     for block in _content_blocks(entry):         if block.get('<str>') != '<str>':             continue         if canonical_github_tool(str(block.get('<str>', '<str>'))) != _CREATE_PR_TOOL:             continue         tool_id = block.get('<str>')         if isinstance(tool_id, str) and tool_id:             create_ids.add(tool_id)"]
    N004["numbers = []"]
    N005["for entry in entries:     for block in _content_blocks(entry):         if block.get('<str>') != '<str>':             continue         if block.get('<str>') not in create_ids:             continue         if block.get('<str>'):             continue         match = _PULL_URL_RE.search(_result_text(block))         if not match:             continue         number = int(match.group(1))         if number > 0 and number not in numbers:             numbers.append(number)"]
    N006["return numbers"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## session_surveyed(...)

```mermaid
flowchart TD
    N001["session_surveyed(...)"]
    N002["return any((_marker_path(pr_number).exists() for pr_number in created))"]
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
    N006["created = created_pr_numbers(...)"]
    N007["if not created"]
    N008["return None"]
    N009["if session_surveyed(created)"]
    N010["return None"]
    N011["return {'<str>': '<str>', '<str>': _build_block_reason(created)}"]
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
    N010["for raw_line in raw.splitlines():     line = raw_line.strip()     if not line:         continue     try:         entries.append(json.loads(line))     except json.JSONDecodeError:         continue"]
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

## record(...)

```mermaid
flowchart TD
    N001["record(...)"]
    N002["mkdir(...)"]
    N003["payload = {'<str>': pr_number, '<str>': _SURVEY_PHASE, '<str>': datetime.now(UTC).isoformat()}"]
    N004["if satisfaction is not None"]
    N005["payload['<str>'] = satisfaction"]
    N006["if problem is not None"]
    N007["payload['<str>'] = problem"]
    N008["if needs_retro"]
    N009["payload['<str>'] = True"]
    N010["if retro_issue is not None"]
    N011["payload['<str>'] = retro_issue"]
    N012["write_text(...)"]
    N013["return True"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N012
    N012 --> N013
```

## run_gate(...)

```mermaid
flowchart TD
    N001["run_gate(...)"]
    N002["event = read_event(...)"]
    N003["if event is None"]
    N004["return 0"]
    N005["if not isinstance(event, dict)"]
    N006["return 0"]
    N007["try"]
    N008["entries = load_transcript(...)"]
    N009["decision = evaluate(...)"]
    N010["except Exception"]
    N011["print(...)"]
    N012["return 0"]
    N013["emit_decision(...)"]
    N014["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"try"| N008
    N008 --> N009
    N007 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N013 --> N014
```

## run_record(...)

```mermaid
flowchart TD
    N001["run_record(...)"]
    N002["pr_number = _coerce_pr_number(...)"]
    N003["if pr_number is None"]
    N004["print(...)"]
    N005["return 0"]
    N006["satisfaction = None"]
    N007["if raw_satisfaction is not None"]
    N008["satisfaction = _coerce_satisfaction(...)"]
    N009["if satisfaction is None"]
    N010["print(...)"]
    N011["return 0"]
    N012["retro_issue = None"]
    N013["if raw_retro_issue is not None"]
    N014["retro_issue = _coerce_pr_number(...)"]
    N015["if retro_issue is None"]
    N016["print(...)"]
    N017["return 1"]
    N018["if raw_needs_retro and retro_issue is None"]
    N019["print(...)"]
    N020["return 1"]
    N021["try"]
    N022["record(...)"]
    N023["except OSError"]
    N024["print(...)"]
    N025["return 1"]
    N026["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N007 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N018
    N013 -->|"false"| N018
    N018 -->|"true"| N019
    N019 --> N020
    N018 -->|"false"| N021
    N021 -->|"try"| N022
    N021 -->|"raises"| N023
    N023 --> N024
    N024 --> N025
    N022 --> N026
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["args = parse_args(...)"]
    N009["if args.record is not None"]
    N010["return run_record(args.record, args.satisfaction, args.problem, args.needs_retro, args.retro_issue)"]
    N011["return run_gate()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```
