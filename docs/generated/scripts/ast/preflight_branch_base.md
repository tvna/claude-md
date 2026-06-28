# AST graph: scripts/preflight_branch_base.py

This file is generated from `scripts/preflight_branch_base.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

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

## check_base_freshness(...)

```mermaid
flowchart TD
    N001["check_base_freshness(...)"]
    N002["rev_parse = run_git(...)"]
    N003["if rev_parse.returncode != 0"]
    N004["detail = strip(...)"]
    N005["return BranchBaseResult(status='<str>', detail=f'<str>{base_ref!r}<str>{detail}')"]
    N006["completed = run_git(...)"]
    N007["if completed.returncode == 0"]
    N008["return BranchBaseResult(status='<str>', detail=f'<str>{base_ref}')"]
    N009["if completed.returncode == 1"]
    N010["return BranchBaseResult(status='<str>', detail=f'<str>{base_ref}')"]
    N011["detail = strip(...)"]
    N012["return BranchBaseResult(status='<str>', detail=f'<str>{detail}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
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
    N010["return parser"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
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
    N009["result = check_base_freshness(...)"]
    N010["except RuntimeError"]
    N011["print(...)"]
    N012["return 1"]
    N013["if result.status == 'pass'"]
    N014["print(...)"]
    N015["return 0"]
    N016["print(...)"]
    N017["print(...)"]
    N018["print(...)"]
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
    N016 --> N017
    N017 --> N018
    N018 --> N019
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
