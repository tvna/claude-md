# AST graph: scripts/pr_body_close_keyword_gate.py

This file is generated from `scripts/pr_body_close_keyword_gate.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## classify_action(...)

```mermaid
flowchart TD
    N001["classify_action(...)"]
    N002["if body_has_partial_marker(body)"]
    N003["return ('<str>', [])"]
    N004["cleaned = strip_html_comments(...)"]
    N005["classified = classify_refs(...)"]
    N006["if not classified"]
    N007["return ('<str>', [])"]
    N008["if any((kw != 'refs' for kw, _ in classified))"]
    N009["return ('<str>', [])"]
    N010["refs_only = sorted(...)"]
    N011["return ('<str>', refs_only)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
```

## fetch_labels(...)

```mermaid
flowchart TD
    N001["fetch_labels(...)"]
    N002["kwargs = {}"]
    N003["if opener is not None"]
    N004["kwargs['<str>'] = opener"]
    N005["if sleeper is not None"]
    N006["kwargs['<str>'] = sleeper"]
    N007["try"]
    N008["(status, body) = apply_call(...)"]
    N009["except Exception"]
    N010["return None"]
    N011["if not 200 <= status < 300"]
    N012["return None"]
    N013["try"]
    N014["data = loads(...)"]
    N015["except (json.JSONDecodeError, ValueError)"]
    N016["return None"]
    N017["raw_labels = data.get('<str>') if isinstance(data, dict) else None"]
    N018["if not isinstance(raw_labels, list)"]
    N019["return None"]
    N020["out = []"]
    N021["for entry in raw_labels:     if isinstance(entry, dict):         name = entry.get('<str>')         if isinstance(name, str):             out.append(name)     elif isinstance(entry, str):         out.append(entry)"]
    N022["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"try"| N014
    N013 -->|"raises"| N015
    N015 --> N016
    N014 --> N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 --> N021
    N021 --> N022
```

## all_tracking(...)

```mermaid
flowchart TD
    N001["all_tracking(...)"]
    N002["if not labels_by_number"]
    N003["return False"]
    N004["return all((labels is not None and TRACKING_LABEL in labels for labels in labels_by_number.values()))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _build_deny_reason(...)

```mermaid
flowchart TD
    N001["_build_deny_reason(...)"]
    N002["base = format_no_closing_keyword_msg(...)"]
    N003["if not token_present"]
    N004["suffix = f'<str>{TRACKING_LABEL}<str>'"]
    N005["if lookup_failed"]
    N006["suffix = '<str>'"]
    N007["suffix = '<str>'"]
    N008["return base + suffix"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N004 --> N008
    N006 --> N008
    N007 --> N008
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if canonical_github_tool(tool_name) not in _TARGET_TOOLS"]
    N003["return None"]
    N004["body = get(...)"]
    N005["if not isinstance(body, str)"]
    N006["return None"]
    N007["(action, refs_only) = classify_action(...)"]
    N008["if action in ('pass', 'skip')"]
    N009["return None"]
    N010["owner = get(...)"]
    N011["repo = get(...)"]
    N012["if not (isinstance(owner, str) and owner and isinstance(repo, str) and repo)"]
    N013["return None"]
    N014["token = token_getter(...)"]
    N015["if not token"]
    N016["reason = _build_deny_reason(...)"]
    N017["return _deny(tool_name, reason)"]
    N018["labels_by_number = {n: label_getter(owner, repo, n) for n in refs_only}"]
    N019["if all_tracking(labels_by_number)"]
    N020["return None"]
    N021["lookup_failed = any(...)"]
    N022["reason = _build_deny_reason(...)"]
    N023["return _deny(tool_name, reason)"]
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
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N018
    N018 --> N019
    N019 -->|"true"| N020
    N019 -->|"false"| N021
    N021 --> N022
    N022 --> N023
```

## _deny(...)

```mermaid
flowchart TD
    N001["_deny(...)"]
    N002["return {'<str>': {'<str>': '<str>', '<str>': '<str>', '<str>': f'<str>{tool_name}<str>{reason}'}}"]
    N001 -->|"start"| N002
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
    N007["tool_input = event.get('<str>') or {}"]
    N008["if not isinstance(tool_name, str) or not isinstance(tool_input, dict)"]
    N009["print(...)"]
    N010["return 0"]
    N011["def _token_getter() -> str | None:     return os.environ.get('<str>') or os.environ.get('<str>')"]
    N012["def _label_getter(owner: str, repo: str, number: int) -> list[str] | None:     token = _token_getter()     if not token:         return None     return fetch_labels(owner, repo, number, token=token)"]
    N013["emit_decision(...)"]
    N014["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
```
