# AST graph: scripts/gate_issue_close_comment.py

This file is generated from `scripts/gate_issue_close_comment.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _marker_path(...)

```mermaid
flowchart TD
    N001["_marker_path(...)"]
    N002["return _COMMENT_DIR / str(issue_number)"]
    N001 -->|"start"| N002
```

## _deny(...)

```mermaid
flowchart TD
    N001["_deny(...)"]
    N002["return {'<str>': '<str>', '<str>': reason}"]
    N001 -->|"start"| N002
```

## _coerce_issue_number(...)

```mermaid
flowchart TD
    N001["_coerce_issue_number(...)"]
    N002["if isinstance(raw, bool)"]
    N003["return None"]
    N004["if isinstance(raw, int) and raw > 0"]
    N005["return raw"]
    N006["if isinstance(raw, str) and raw.isdecimal() and (int(raw) > 0)"]
    N007["return int(raw)"]
    N008["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _is_close_action(...)

```mermaid
flowchart TD
    N001["_is_close_action(...)"]
    N002["return tool_name == _TARGET_TOOL and tool_input.get('<str>') == _CLOSE_STATE"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if not _is_close_action(tool_name, tool_input)"]
    N003["return None"]
    N004["issue_number = _coerce_issue_number(...)"]
    N005["if issue_number is None"]
    N006["return _deny(_UNRESOLVED_REASON)"]
    N007["if _marker_path(issue_number).exists()"]
    N008["return None"]
    N009["return _deny(f'<str>{issue_number}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## run_gate(...)

```mermaid
flowchart TD
    N001["run_gate(...)"]
    N002["event = read_event(...)"]
    N003["if event is None or not isinstance(event, dict)"]
    N004["emit_decision(...)"]
    N005["return 0"]
    N006["tool_name = get(...)"]
    N007["tool_input = get(...)"]
    N008["if not isinstance(tool_input, dict)"]
    N009["tool_input = {}"]
    N010["emit_decision(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
    N010 --> N011
```

## _extract_issue_number(...)

```mermaid
flowchart TD
    N001["_extract_issue_number(...)"]
    N002["return _coerce_issue_number(tool_input.get('<str>'))"]
    N001 -->|"start"| N002
```

## record(...)

```mermaid
flowchart TD
    N001["record(...)"]
    N002["issue_number = _extract_issue_number(...)"]
    N003["if issue_number is None"]
    N004["return False"]
    N005["mkdir(...)"]
    N006["touch(...)"]
    N007["return True"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## run_record(...)

```mermaid
flowchart TD
    N001["run_record(...)"]
    N002["event = read_event(...)"]
    N003["if event is None or not isinstance(event, dict)"]
    N004["return 0"]
    N005["tool_input = event.get('<str>') or {}"]
    N006["if not isinstance(tool_input, dict)"]
    N007["return 0"]
    N008["with contextlib.suppress(OSError):     record(tool_input)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["args = parse_args(...)"]
    N005["if args.record"]
    N006["return run_record()"]
    N007["return run_gate()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```
