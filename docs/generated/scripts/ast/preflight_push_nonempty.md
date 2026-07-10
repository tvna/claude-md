# AST graph: scripts/preflight_push_nonempty.py

This file is generated from `scripts/preflight_push_nonempty.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _default_runner(...)

```mermaid
flowchart TD
    N001["_default_runner(...)"]
    N002["return run_git(args, cwd=REPO_ROOT, timeout=30)"]
    N001 -->|"start"| N002
```

## _resolve(...)

```mermaid
flowchart TD
    N001["_resolve(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (OSError, subprocess.SubprocessError)"]
    N005["return None"]
    N006["if result.returncode != 0"]
    N007["return None"]
    N008["sha = strip(...)"]
    N009["return sha or None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
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
    N007["if _SKIP_FLAG_RE.search(command)"]
    N008["return None"]
    N009["head = _resolve(...)"]
    N010["base = _resolve(...)"]
    N011["if head is None or base is None"]
    N012["return None"]
    N013["if head != base"]
    N014["return None"]
    N015["return build_deny(f'<str>{BASE_REF}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
```
