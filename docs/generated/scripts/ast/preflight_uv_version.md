# AST graph: scripts/preflight_uv_version.py

This file is generated from `scripts/preflight_uv_version.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## parse_uv_version(...)

```mermaid
flowchart TD
    N001["parse_uv_version(...)"]
    N002["tokens = split(...)"]
    N003["if len(tokens) < 2 or tokens[0] != 'uv'"]
    N004["return None"]
    N005["return tokens[1]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## probe_uv_version(...)

```mermaid
flowchart TD
    N001["probe_uv_version(...)"]
    N002["resolved = uv_path or shutil.which('<str>')"]
    N003["if resolved is None"]
    N004["return None"]
    N005["try"]
    N006["completed = run(...)"]
    N007["except (OSError, subprocess.SubprocessError)"]
    N008["return None"]
    N009["if completed.returncode != 0"]
    N010["return None"]
    N011["return parse_uv_version(completed.stdout)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## check_version(...)

```mermaid
flowchart TD
    N001["check_version(...)"]
    N002["if running is None"]
    N003["return VersionResult(status='<str>', detail=f'<str>{pin}')"]
    N004["if running != pin"]
    N005["return VersionResult(status='<str>', detail=f'<str>{running}<str>{pin}')"]
    N006["return VersionResult(status='<str>', detail=f'<str>{running}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["pyproject = Path(args.pyproject) if args.pyproject else Path(args.repo_root) / '<str>'"]
    N003["try"]
    N004["pin = read_pin(...)"]
    N005["except ValueError"]
    N006["print(...)"]
    N007["return 1"]
    N008["running = probe_uv_version(...)"]
    N009["result = check_version(...)"]
    N010["if result.status == 'pass'"]
    N011["print(...)"]
    N012["return 0"]
    N013["print(...)"]
    N014["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N013
    N013 --> N014
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["args = parse_args(...)"]
    N009["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```
