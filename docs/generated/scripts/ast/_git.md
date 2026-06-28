# AST graph: scripts/_git.py

This file is generated from `scripts/_git.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## run_git(...)

```mermaid
flowchart TD
    N001["run_git(...)"]
    N002["git = which(...)"]
    N003["if git is None"]
    N004["raise RuntimeError('<str>')"]
    N005["return subprocess.run([git, *args], cwd=cwd, check=check, capture_output=True, text=True, timeout=timeout)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## make_runner(...)

```mermaid
flowchart TD
    N001["make_runner(...)"]
    N002["def runner(args: list[str]) -> subprocess.CompletedProcess[str]:     return run_git(args, cwd=cwd, timeout=timeout)"]
    N003["return runner"]
    N001 -->|"start"| N002
    N002 --> N003
```

## rev_list(...)

```mermaid
flowchart TD
    N001["rev_list(...)"]
    N002["try"]
    N003["result = runner(...)"]
    N004["except (RuntimeError, OSError, subprocess.SubprocessError)"]
    N005["return None"]
    N006["if result.returncode != 0"]
    N007["return None"]
    N008["return [line.strip() for line in result.stdout.splitlines() if line.strip()]"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```
