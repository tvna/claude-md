# AST graph: scripts/check_session_branch.py

This file is generated from `scripts/check_session_branch.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _ensure_seed_trailing_newline(...)

```mermaid
flowchart TD
    N001["_ensure_seed_trailing_newline(...)"]
    N002["try"]
    N003["existing = read_text(...)"]
    N004["except OSError"]
    N005["return"]
    N006["if not existing or existing.endswith('\n')"]
    N007["return"]
    N008["with contextlib.suppress(OSError):     path.write_text(existing + '<str>', encoding='<str>')"]
    N009["end"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## _current_branch(...)

```mermaid
flowchart TD
    N001["_current_branch(...)"]
    N002["try"]
    N003["result = run_git(...)"]
    N004["branch = strip(...)"]
    N005["return branch if branch else None"]
    N006["except (OSError, subprocess.SubprocessError, RuntimeError)"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 --> N004
    N004 --> N005
    N002 -->|"raises"| N006
    N006 --> N007
```

## check(...)

```mermaid
flowchart TD
    N001["check(...)"]
    N002["if os.environ.get(_REMOTE_ENV_VAR, '').lower() != 'true'"]
    N003["return None"]
    N004["branch = _current_branch(...)"]
    N005["if not branch"]
    N006["return None"]
    N007["_ensure_seed_trailing_newline(...)"]
    N008["append_branch(...)"]
    N009["message = f'<str>{branch}<str>{branch}'"]
    N010["return {'<str>': {'<str>': message}}"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
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
