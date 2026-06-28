# AST graph: scripts/preflight_signed_commits.py

This file is generated from `scripts/preflight_signed_commits.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## ack_present(...)

```mermaid
flowchart TD
    N001["ack_present(...)"]
    N002["value = get(...)"]
    N003["return _ACK_MARKER_RE.search(value) is not None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## commits_in_range(...)

```mermaid
flowchart TD
    N001["commits_in_range(...)"]
    N002["return rev_list(runner, [f'{base_ref}<str>'])"]
    N001 -->|"start"| N002
```

## check_signed_commits(...)

```mermaid
flowchart TD
    N001["check_signed_commits(...)"]
    N002["commits = commits_in_range(...)"]
    N003["if commits is None"]
    N004["return SignedCommitsResult(status='<str>', detail=f'<str>{base_ref}<str>')"]
    N005["unsigned = tuple(...)"]
    N006["if unsigned"]
    N007["return SignedCommitsResult(status='<str>', detail=f'{len(unsigned)}<str>{len(commits)}<str>{base_ref}<str>', unsigned=unsigned)"]
    N008["return SignedCommitsResult(status='<str>', detail=f'<str>{len(commits)}<str>{base_ref}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
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
    N007["return parser"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["if runner is None"]
    N003["runner = make_runner(...)"]
    N004["result = check_signed_commits(...)"]
    N005["if result.status == 'pass'"]
    N006["print(...)"]
    N007["return 0"]
    N008["if result.status == 'skip'"]
    N009["print(...)"]
    N010["return 0"]
    N011["if ack_present()"]
    N012["print(...)"]
    N013["return 0"]
    N014["print(...)"]
    N015["print(...)"]
    N016["for sha in result.unsigned:     print(f'<str>{sha}', file=sys.stderr)"]
    N017["print(...)"]
    N018["print(...)"]
    N019["print(...)"]
    N020["return 1"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 --> N015
    N015 --> N016
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
