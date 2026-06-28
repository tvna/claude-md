# AST graph: scripts/_commit_signing.py

This file is generated from `scripts/_commit_signing.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## is_unsigned(...)

```mermaid
flowchart TD
    N001["is_unsigned(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (RuntimeError, OSError, subprocess.SubprocessError)"]
    N005["return False"]
    N006["if result.returncode != 0"]
    N007["return False"]
    N008["for line in result.stdout.splitlines():     if not line:         break     if line.startswith('<str>'):         return False"]
    N009["return True"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```
