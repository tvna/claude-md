# AST graph: scripts/gate_merge_safety.py

This file is generated from `scripts/gate_merge_safety.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _pr_number(...)

```mermaid
flowchart TD
    N001["_pr_number(...)"]
    N002["if isinstance(value, bool)"]
    N003["return None"]
    N004["if isinstance(value, int)"]
    N005["return str(value)"]
    N006["if isinstance(value, str) and value.isdecimal()"]
    N007["return value"]
    N008["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _deny_for_state(...)

```mermaid
flowchart TD
    N001["_deny_for_state(...)"]
    N002["remediation = get(...)"]
    N003["return build_deny(f'<str>{label}<str>{mergeable!r}<str>{state!r}<str>{remediation}')"]
    N001 -->|"start"| N002
    N002 --> N003
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if tool_name != _TARGET_TOOL"]
    N003["return None"]
    N004["owner = get(...)"]
    N005["repo = get(...)"]
    N006["pr_number = _pr_number(...)"]
    N007["if not (isinstance(owner, str) and owner and isinstance(repo, str) and repo and pr_number)"]
    N008["return build_deny(_BAD_INPUT_REASON)"]
    N009["label = f'{owner}<str>{repo}<str>{pr_number}'"]
    N010["actual_token = token or _get_token()"]
    N011["if not actual_token"]
    N012["return build_deny(_MISSING_GH_AUTH_REASON)"]
    N013["pr_data = poller(...)"]
    N014["if not isinstance(pr_data, dict)"]
    N015["return build_deny(_API_FAILED_REASON)"]
    N016["mergeable = get(...)"]
    N017["state = lower(...)"]
    N018["if mergeable is True and state == 'clean'"]
    N019["return None"]
    N020["return _deny_for_state(label, mergeable, state)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
    N016 --> N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["event = read_event(...)"]
    N004["if event is None"]
    N005["return 0"]
    N006["split = split_tool_event(...)"]
    N007["if split is None"]
    N008["return 0"]
    N009["emit_decision(...)"]
    N010["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
```
