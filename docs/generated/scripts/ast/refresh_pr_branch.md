# AST graph: scripts/refresh_pr_branch.py

This file is generated from `scripts/refresh_pr_branch.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## current_branch(...)

```mermaid
flowchart TD
    N001["current_branch(...)"]
    N002["cp = run_git(...)"]
    N003["if cp.returncode != 0"]
    N004["return None"]
    N005["name = strip(...)"]
    N006["return name or None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## worktree_dirty(...)

```mermaid
flowchart TD
    N001["worktree_dirty(...)"]
    N002["cp = run_git(...)"]
    N003["return bool(cp.stdout.strip())"]
    N001 -->|"start"| N002
    N002 --> N003
```

## behind_count(...)

```mermaid
flowchart TD
    N001["behind_count(...)"]
    N002["ref = f'{remote}<str>{base}'"]
    N003["cp = run_git(...)"]
    N004["if cp.returncode != 0"]
    N005["return -1"]
    N006["text = strip(...)"]
    N007["return int(text) if text.isdigit() else -1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```

## merge_would_conflict(...)

```mermaid
flowchart TD
    N001["merge_would_conflict(...)"]
    N002["ref = f'{remote}<str>{base}'"]
    N003["cp = run_git(...)"]
    N004["if cp.returncode == 0"]
    N005["return False"]
    N006["if cp.returncode == 1"]
    N007["return True"]
    N008["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## refresh(...)

```mermaid
flowchart TD
    N001["refresh(...)"]
    N002["branch = current_branch(...)"]
    N003["if branch is None"]
    N004["return (_PRECONDITION_EXIT, '<str>')"]
    N005["if branch == base"]
    N006["return (_PRECONDITION_EXIT, f'<str>{base}<str>')"]
    N007["if worktree_dirty(cwd=cwd)"]
    N008["return (_PRECONDITION_EXIT, '<str>')"]
    N009["if do_fetch"]
    N010["cp = run_git(...)"]
    N011["if cp.returncode != 0"]
    N012["return (_PRECONDITION_EXIT, f'<str>{remote}<str>{base}<str>{cp.stderr.strip()}')"]
    N013["count = behind_count(...)"]
    N014["if count < 0"]
    N015["return (_PRECONDITION_EXIT, f'<str>{remote}<str>{base}<str>')"]
    N016["if count == 0"]
    N017["return (0, f'<str>{branch}<str>{remote}<str>{base}<str>')"]
    N018["conflict = merge_would_conflict(...)"]
    N019["if conflict is None"]
    N020["return (_PRECONDITION_EXIT, '<str>')"]
    N021["if conflict"]
    N022["return (_CONFLICT_EXIT, f'<str>{branch}<str>{remote}<str>{base}<str>{count}<str>')"]
    N023["if dry_run"]
    N024["push_note = '<str>' if do_push else '<str>'"]
    N025["return (0, f'<str>{branch}<str>{remote}<str>{base}<str>{count}<str>{remote}<str>{base}<str>{push_note}<str>')"]
    N026["cp = run_git(...)"]
    N027["if cp.returncode != 0"]
    N028["return (_PRECONDITION_EXIT, f'<str>{remote}<str>{base}<str>{cp.stderr.strip()}')"]
    N029["if do_push"]
    N030["push = run_git(...)"]
    N031["if push.returncode != 0"]
    N032["return (_PRECONDITION_EXIT, f'<str>{remote}<str>{base}<str>{branch}<str>{push.stderr.strip()}')"]
    N033["return (0, f'<str>{remote}<str>{base}<str>{branch}<str>{count}<str>')"]
    N034["return (0, f'<str>{remote}<str>{base}<str>{branch}<str>{count}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N009 -->|"false"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N018 --> N019
    N019 -->|"true"| N020
    N019 -->|"false"| N021
    N021 -->|"true"| N022
    N021 -->|"false"| N023
    N023 -->|"true"| N024
    N024 --> N025
    N023 -->|"false"| N026
    N026 --> N027
    N027 -->|"true"| N028
    N027 -->|"false"| N029
    N029 -->|"true"| N030
    N030 --> N031
    N031 -->|"true"| N032
    N031 -->|"false"| N033
    N029 -->|"false"| N034
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["args = parse_args(...)"]
    N009["(code, message) = refresh(...)"]
    N010["stream = sys.stdout if code == 0 else sys.stderr"]
    N011["print(...)"]
    N012["return code"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
```
