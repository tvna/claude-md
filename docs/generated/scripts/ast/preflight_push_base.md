# AST graph: scripts/preflight_push_base.py

This file is generated from `scripts/preflight_push_base.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') != 'Bash'"]
    N003["return None"]
    N004["command = str(...)"]
    N005["if not _GIT_PUSH_RE.search(command)"]
    N006["return None"]
    N007["script = REPO_ROOT / '<str>' / '<str>'"]
    N008["try"]
    N009["result = runner(...)"]
    N010["except (OSError, subprocess.SubprocessError)"]
    N011["print(...)"]
    N012["return None"]
    N013["if result.returncode != 0"]
    N014["detail = strip(...)"]
    N015["return build_deny(f'<str>{detail}<str>')"]
    N016["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_event_hook('<str>', decide, auditable=False)"]
    N001 -->|"start"| N002
    N002 --> N003
```
