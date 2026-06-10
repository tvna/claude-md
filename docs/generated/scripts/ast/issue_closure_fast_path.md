# AST graph: scripts/issue_closure_fast_path.py

This file is generated from `scripts/issue_closure_fast_path.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _search_merged_prs(...)

```mermaid
flowchart TD
    N001["_search_merged_prs(...)"]
    N002["actual_token = token or os.environ.get('<str>', '<str>')"]
    N003["if not actual_token"]
    N004["return None"]
    N005["query = f'<str>{owner}<str>{repo}<str>{issue_number}'"]
    N006["url = f'<str>{urllib.parse.quote(query)}<str>'"]
    N007["try"]
    N008["(code, body) = apply_call(...)"]
    N009["except Exception"]
    N010["print(...)"]
    N011["return None"]
    N012["if not 200 <= code < 300"]
    N013["return None"]
    N014["try"]
    N015["data = loads(...)"]
    N016["except json.JSONDecodeError"]
    N017["return None"]
    N018["if not isinstance(data, dict)"]
    N019["return None"]
    N020["items = data.get('<str>') or []"]
    N021["return [{'<str>': item.get('<str>'), '<str>': item.get('<str>'), '<str>': item.get('<str>'), '<str>': item.get('<str>')} for item in items if isinstance(item, dict)]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N010 --> N011
    N008 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 -->|"try"| N015
    N014 -->|"raises"| N016
    N016 --> N017
    N015 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 --> N021
```

## _extract_close_target(...)

```mermaid
flowchart TD
    N001["_extract_close_target(...)"]
    N002["if tool_name != _TARGET_TOOL"]
    N003["return None"]
    N004["state = get(...)"]
    N005["if state != _CLOSE_STATE"]
    N006["return None"]
    N007["owner = get(...)"]
    N008["repo = get(...)"]
    N009["raw_number = get(...)"]
    N010["if not (isinstance(owner, str) and owner)"]
    N011["return None"]
    N012["if not (isinstance(repo, str) and repo)"]
    N013["return None"]
    N014["if isinstance(raw_number, int) and raw_number > 0"]
    N015["return (owner, repo, raw_number)"]
    N016["if isinstance(raw_number, str) and raw_number.isdecimal()"]
    N017["return (owner, repo, int(raw_number))"]
    N018["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
```

## _format_context(...)

```mermaid
flowchart TD
    N001["_format_context(...)"]
    N002["issue_ref = f'{owner}<str>{repo}<str>{issue_number}'"]
    N003["if not prs"]
    N004["return f'<str>{issue_ref}<str>'"]
    N005["if len(prs) == 1"]
    N006["pr = prs[0]"]
    N007["url = pr.get('<str>') or f'{owner}<str>{repo}<str>{pr.get('<str>')}'"]
    N008["title = pr.get('<str>') or '<str>'"]
    N009["closed_at = pr.get('<str>') or '<str>'"]
    N010["return f'<str>{issue_ref}<str>{title}<str>{url}<str>{closed_at}<str>'"]
    N011["lines = [f'<str>{len(prs)}<str>{issue_ref}<str>']"]
    N012["for pr in prs:     url = pr.get('<str>') or f'<str>{pr.get('<str>')}'     title = pr.get('<str>') or '<str>'     lines.append(f'<str>{url}<str>{title}')"]
    N013["append(...)"]
    N014["return '<str>'.join(lines)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N005 -->|"false"| N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["target = _extract_close_target(...)"]
    N003["if target is None"]
    N004["return None"]
    N005["(owner, repo, issue_number) = target"]
    N006["prs = _search_merged_prs(...)"]
    N007["if prs is None"]
    N008["return None"]
    N009["context = _format_context(...)"]
    N010["return {'<str>': {'<str>': '<str>', '<str>': context}}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
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
    N006["if not isinstance(event, dict)"]
    N007["return 0"]
    N008["tool_name = get(...)"]
    N009["tool_input = event.get('<str>') or {}"]
    N010["if not isinstance(tool_input, dict)"]
    N011["tool_input = {}"]
    N012["emit_decision(...)"]
    N013["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N012
    N012 --> N013
```
