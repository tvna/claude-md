# AST graph: scripts/preflight_push_prek.py

This file is generated from `scripts/preflight_push_prek.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _run_prek(...)

```mermaid
flowchart TD
    N001["_run_prek(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (OSError, subprocess.SubprocessError)"]
    N005["print(...)"]
    N006["return None"]
    N007["if result.returncode != 0"]
    N008["detail = strip(...)"]
    N009["return build_deny(f'<str>{detail}<str>')"]
    N010["return None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N005 --> N006
    N003 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') != 'Bash'"]
    N003["return None"]
    N004["command = str(...)"]
    N005["if not _GIT_PUSH_RE.search(command)"]
    N006["return None"]
    N007["return _run_prek(runner=runner)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_event_hook('<str>', decide)"]
    N001 -->|"start"| N002
    N002 --> N003
```
