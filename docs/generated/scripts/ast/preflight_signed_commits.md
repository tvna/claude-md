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

## parse_push_refs(...)

```mermaid
flowchart TD
    N001["parse_push_refs(...)"]
    N002["refs = []"]
    N003["for line in value.splitlines():     fields = line.split()     if len(fields) != 4:         continue     refs.append(PushRef(*fields))"]
    N004["return refs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## read_push_refs(...)

```mermaid
flowchart TD
    N001["read_push_refs(...)"]
    N002["source = os.environ if env is None else env"]
    N003["refs = parse_push_refs(...)"]
    N004["remote = source.get(_PUSH_REMOTE_ENV_VAR, '<str>') or _DEFAULT_REMOTE"]
    N005["return (refs, remote)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## check_pushed_refs(...)

```mermaid
flowchart TD
    N001["check_pushed_refs(...)"]
    N002["seen = set(...)"]
    N003["unsigned = []"]
    N004["inspected = 0"]
    N005["undeterminable = False"]
    N006["for ref in refs:     if is_all_zeros(ref.local_oid):         continue     remote_oid = None if is_all_zeros(ref.remote_oid) else ref.remote_oid     commits = commits_to_push(runner, local_sha=ref.local_oid, remote_sha=remote_oid, remote=remote)     if commits is None:         undeterminable = True         continue     for sha in commits:         if sha in seen:             continue         seen.add(sha)         inspected += 1         if is_unsigned(runner, sha):             unsigned.append(sha)"]
    N007["scope = f'{inspected}<str>{len(refs)}<str>'"]
    N008["if unsigned"]
    N009["return SignedCommitsResult(status='<str>', detail=f'{len(unsigned)}<str>{scope}<str>', unsigned=tuple(unsigned))"]
    N010["if inspected == 0 and undeterminable"]
    N011["return SignedCommitsResult(status='<str>', detail=f'<str>{len(refs)}<str>')"]
    N012["return SignedCommitsResult(status='<str>', detail=f'<str>{scope}<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
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
