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

## check_pushed_refs(...)

```mermaid
flowchart TD
    N001["check_pushed_refs(...)"]
    N002["(commits, undeterminable) = commits_for_pushed_refs(...)"]
    N003["unsigned = [sha for sha in commits if is_unsigned(runner, sha)]"]
    N004["scope = f'{len(commits)}<str>{len(refs)}<str>'"]
    N005["if unsigned"]
    N006["return SignedCommitsResult(status='<str>', detail=f'{len(unsigned)}<str>{scope}<str>', unsigned=tuple(unsigned))"]
    N007["if not commits and undeterminable"]
    N008["return SignedCommitsResult(status='<str>', detail=f'<str>{len(refs)}<str>')"]
    N009["return SignedCommitsResult(status='<str>', detail=f'<str>{scope}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
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
    N004["(refs, remote) = read_push_refs(...)"]
    N005["if refs"]
    N006["result = check_pushed_refs(...)"]
    N007["result = check_signed_commits(...)"]
    N008["if result.status == 'pass'"]
    N009["print(...)"]
    N010["return 0"]
    N011["if result.status == 'skip'"]
    N012["print(...)"]
    N013["return 0"]
    N014["if ack_present()"]
    N015["print(...)"]
    N016["return 0"]
    N017["print(...)"]
    N018["print(...)"]
    N019["for sha in result.unsigned:     print(f'<str>{sha}', file=sys.stderr)"]
    N020["print(...)"]
    N021["print(...)"]
    N022["print(...)"]
    N023["return 1"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N006 --> N008
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
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
