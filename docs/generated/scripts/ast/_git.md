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
