# AST graph: scripts/check_hooks_path.py

This file is generated from `scripts/check_hooks_path.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _git_config(...)

```mermaid
flowchart TD
    N001["_git_config(...)"]
    N002["try"]
    N003["result = run_git(...)"]
    N004["except RuntimeError"]
    N005["return None"]
    N006["if result.returncode != 0"]
    N007["return None"]
    N008["return result.stdout.strip()"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _git_config_set(...)

```mermaid
flowchart TD
    N001["_git_config_set(...)"]
    N002["try"]
    N003["result = run_git(...)"]
    N004["except RuntimeError"]
    N005["return False"]
    N006["return result.returncode == 0"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
```

## check(...)

```mermaid
flowchart TD
    N001["check(...)"]
    N002["current = _git_config(...)"]
    N003["if current == _EXPECTED"]
    N004["return None"]
    N005["detail = '<str>' if current is None else f'<str>{current}<str>'"]
    N006["if _git_config_set('core.hooksPath', _EXPECTED)"]
    N007["message = f'<str>{detail}<str>{_EXPECTED}<str>{_HOOKS_FILE}<str>'"]
    N008["message = f'<str>{detail}<str>{_EXPECTED}'"]
    N009["return {'<str>': {'<str>': message}}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N007 --> N009
    N008 --> N009
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["try"]
    N003["output = check(...)"]
    N004["except Exception"]
    N005["exit(...)"]
    N006["if output is not None"]
    N007["print(...)"]
    N008["end"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
```
