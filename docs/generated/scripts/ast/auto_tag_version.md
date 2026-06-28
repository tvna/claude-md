# AST graph: scripts/auto_tag_version.py

This file is generated from `scripts/auto_tag_version.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## tag_name(...)

```mermaid
flowchart TD
    N001["tag_name(...)"]
    N002["return f'<str>{format_version(version)}'"]
    N001 -->|"start"| N002
```

## tag_for_change(...)

```mermaid
flowchart TD
    N001["tag_for_change(...)"]
    N002["if head_version == base_version"]
    N003["return None"]
    N004["return tag_name(head_version)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## read_version_at(...)

```mermaid
flowchart TD
    N001["read_version_at(...)"]
    N002["result = _run(...)"]
    N003["return parse_version(result.stdout)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## tag_exists(...)

```mermaid
flowchart TD
    N001["tag_exists(...)"]
    N002["result = _run(...)"]
    N003["return any((line.strip() == tag for line in result.stdout.splitlines()))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## create_and_push_tag(...)

```mermaid
flowchart TD
    N001["create_and_push_tag(...)"]
    N002["_run(...)"]
    N003["_run(...)"]
    N004["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _resolve_merge_sha(...)

```mermaid
flowchart TD
    N001["_resolve_merge_sha(...)"]
    N002["if args.merge_sha"]
    N003["return args.merge_sha"]
    N004["return os.environ.get('<str>') or '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _cmd_run(...)

```mermaid
flowchart TD
    N001["_cmd_run(...)"]
    N002["sha = _resolve_merge_sha(...)"]
    N003["remote = args.remote"]
    N004["try"]
    N005["head_version = read_version_at(...)"]
    N006["base_version = read_version_at(...)"]
    N007["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, RuntimeError, ValueError)"]
    N008["print(...)"]
    N009["return 1"]
    N010["tag = tag_for_change(...)"]
    N011["if tag is None"]
    N012["print(...)"]
    N013["return 0"]
    N014["try"]
    N015["if tag_exists(tag)"]
    N016["print(...)"]
    N017["return 0"]
    N018["if args.dry_run"]
    N019["print(...)"]
    N020["return 0"]
    N021["create_and_push_tag(...)"]
    N022["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, RuntimeError)"]
    N023["print(...)"]
    N024["return 1"]
    N025["print(...)"]
    N026["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"try"| N005
    N005 --> N006
    N004 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 -->|"try"| N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N018
    N018 -->|"true"| N019
    N019 --> N020
    N018 -->|"false"| N021
    N014 -->|"raises"| N022
    N022 --> N023
    N023 --> N024
    N021 --> N025
    N025 --> N026
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_run = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["set_defaults(...)"]
    N009["args = parse_args(...)"]
    N010["return args.func(args)"]
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

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["return runner(cmd, capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS, check=True)"]
    N001 -->|"start"| N002
```
