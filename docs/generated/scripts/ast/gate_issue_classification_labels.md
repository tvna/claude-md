# AST graph: scripts/gate_issue_classification_labels.py

This file is generated from `scripts/gate_issue_classification_labels.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## load_axis_labels(...)

```mermaid
flowchart TD
    N001["load_axis_labels(...)"]
    N002["raw = loads(...)"]
    N003["if not isinstance(raw, list)"]
    N004["raise ValueError('<str>')"]
    N005["names = [entry['<str>'] for entry in raw if isinstance(entry, dict) and isinstance(entry.get('<str>'), str)]"]
    N006["axes = {}"]
    N007["for axis, prefix in _AXIS_PREFIXES:
    axes[axis] = frozenset((name for name in names if name.startswith(prefix)))"]
    N008["return axes"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## missing_axes(...)

```mermaid
flowchart TD
    N001["missing_axes(...)"]
    N002["present = {label for label in labels if isinstance(label, str)}"]
    N003["missing = []"]
    N004["for axis, _prefix in _AXIS_PREFIXES:
    valid = axes.get(axis) or frozenset()
    if not valid:
        continue
    if not present & valid:
        missing.append(axis)"]
    N005["return missing"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## build_reason(...)

```mermaid
flowchart TD
    N001["build_reason(...)"]
    N002["parts = []"]
    N003["for axis in missing:
    valid = sorted(axes.get(axis) or frozenset())
    parts.append(f'<str>{axis}<str>{'<str>'.join(valid)}<str>')"]
    N004["needed = join(...)"]
    N005["return f'<str>{_TARGET_TOOL}<str>{needed}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if tool_name != _TARGET_TOOL"]
    N003["return None"]
    N004["if tool_input.get('method') != _CREATE_METHOD"]
    N005["return None"]
    N006["try"]
    N007["axes = load_axis_labels(...)"]
    N008["except (OSError, json.JSONDecodeError, ValueError)"]
    N009["print(...)"]
    N010["return None"]
    N011["raw_labels = get(...)"]
    N012["labels = raw_labels if isinstance(raw_labels, list) else []"]
    N013["missing = missing_axes(...)"]
    N014["if not missing"]
    N015["return None"]
    N016["return build_deny(build_reason(missing, axes))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N009 --> N010
    N007 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_tool_hook('<str>', decide)"]
    N001 -->|"start"| N002
    N002 --> N003
```
