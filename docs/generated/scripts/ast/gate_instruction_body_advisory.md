# AST graph: scripts/gate_instruction_body_advisory.py

This file is generated from `scripts/gate_instruction_body_advisory.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _is_instruction_path(...)

```mermaid
flowchart TD
    N001["_is_instruction_path(...)"]
    N002["cleaned = strip(...)"]
    N003["return cleaned in _INSTRUCTION_FILES or cleaned.startswith(_INSTRUCTION_DIR_PREFIX)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _is_source_path(...)

```mermaid
flowchart TD
    N001["_is_source_path(...)"]
    N002["return path.strip().startswith(_INSTRUCTION_DIR_PREFIX)"]
    N001 -->|"start"| N002
```

## build_advice(...)

```mermaid
flowchart TD
    N001["build_advice(...)"]
    N002["instruction = sorted(...)"]
    N003["if not instruction"]
    N004["return None"]
    N005["needs_growth_ack = any(...)"]
    N006["pretty = join(...)"]
    N007["parts = [f'<str>{pretty}<str>']"]
    N008["if needs_growth_ack"]
    N009["append(...)"]
    N010["append(...)"]
    N011["return '<str>'.join(parts)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
    N010 --> N011
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') != 'Bash'"]
    N003["return None"]
    N004["command = str(...)"]
    N005["if not _GIT_COMMIT_RE.search(command)"]
    N006["return None"]
    N007["advice = build_advice(...)"]
    N008["if advice is None"]
    N009["return None"]
    N010["return {'<str>': {'<str>': '<str>', '<str>': advice}}"]
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

## _staged_files(...)

```mermaid
flowchart TD
    N001["_staged_files(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (subprocess.SubprocessError, OSError)"]
    N005["return []"]
    N006["return [line for line in result.stdout.splitlines() if line.strip()]"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["return run_event_hook('<str>', decide)"]
    N001 -->|"start"| N002
```
