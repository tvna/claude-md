# AST graph: scripts/preflight_merge_index_budget.py

This file is generated from `scripts/preflight_merge_index_budget.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## run_git(...)

```mermaid
flowchart TD
    N001["run_git(...)"]
    N002["return _run_git(args, cwd=repo)"]
    N001 -->|"start"| N002
```

## fetch_base(...)

```mermaid
flowchart TD
    N001["fetch_base(...)"]
    N002["completed = run_git(...)"]
    N003["if completed.returncode != 0"]
    N004["detail = strip(...)"]
    N005["raise RuntimeError(f'<str>{remote}<str>{base_branch}<str>{detail}')"]
    N006["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["if max_bytes is None"]
    N003["max_bytes = MAX_INDEX_BYTES"]
    N004["merge = run_git(...)"]
    N005["if merge.returncode not in (0, 1)"]
    N006["detail = strip(...)"]
    N007["raise RuntimeError(f'<str>{base_ref}<str>{head_ref}<str>{merge.returncode}<str>{detail}')"]
    N008["first_line = merge.stdout.splitlines()[0].strip() if merge.stdout.strip() else '<str>'"]
    N009["if not first_line"]
    N010["raise RuntimeError('<str>')"]
    N011["if merge.returncode == 1"]
    N012["return MergeBudgetResult(status='<str>', detail=f'<str>{base_ref}<str>{index_path.as_posix()}<str>')"]
    N013["tree = first_line"]
    N014["size_proc = run_git(...)"]
    N015["if size_proc.returncode != 0"]
    N016["return MergeBudgetResult(status='<str>', detail=f'{index_path.as_posix()}<str>')"]
    N017["size = int(...)"]
    N018["if size > max_bytes"]
    N019["return MergeBudgetResult(status='<str>', detail=f'<str>{index_path.as_posix()}<str>{size}<str>{base_ref}<str>{max_bytes}<str>', size=size)"]
    N020["return MergeBudgetResult(status='<str>', detail=f'<str>{index_path.as_posix()}<str>{size}<str>{max_bytes}<str>{base_ref}', size=size)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
```

## _build_parser(...)

```mermaid
flowchart TD
    N001["_build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["return parser"]
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
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["repo = Path(...)"]
    N003["try"]
    N004["base_ref = args.base_ref"]
    N005["if not args.skip_fetch"]
    N006["base_ref = fetch_base(...)"]
    N007["if not base_ref"]
    N008["base_ref = f'{args.remote}<str>{args.base_branch}'"]
    N009["result = evaluate(...)"]
    N010["except RuntimeError"]
    N011["print(...)"]
    N012["return 1"]
    N013["if result.status == 'pass'"]
    N014["print(...)"]
    N015["return 0"]
    N016["if result.status == 'conflict'"]
    N017["print(...)"]
    N018["return 0"]
    N019["print(...)"]
    N020["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
    N003 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
    N016 -->|"true"| N017
    N017 --> N018
    N016 -->|"false"| N019
    N019 --> N020
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["args = parse_args(...)"]
    N003["if args.command == 'verify'"]
    N004["return cmd_verify(args)"]
    N005["raise AssertionError(f'<str>{args.command}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```
