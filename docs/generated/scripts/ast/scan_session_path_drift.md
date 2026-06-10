# AST graph: scripts/scan_session_path_drift.py

This file is generated from `scripts/scan_session_path_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _iter_writes(...)

```mermaid
flowchart TD
    N001["_iter_writes(...)"]
    N002["writes = []"]
    N003["for path in sorted(scripts_dir.glob('<str>')):
    for lineno, line in enumerate(path.read_text(encoding='<str>').splitlines(), 1):
        if _ENV_FILE_WRITE.search(line):
            writes.append(EnvFileWrite(script=path.name, lineno=lineno, line=line.strip()))"]
    N004["return writes"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## stray_writes(...)

```mermaid
flowchart TD
    N001["stray_writes(...)"]
    N002["return [w for w in _iter_writes(scripts_dir) if w.script != HELPER_NAME]"]
    N001 -->|"start"| N002
```

## helper_writes_env_file(...)

```mermaid
flowchart TD
    N001["helper_writes_env_file(...)"]
    N002["return any((w.script == HELPER_NAME for w in _iter_writes(scripts_dir)))"]
    N001 -->|"start"| N002
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["scripts_dir = Path(...)"]
    N003["errors = 0"]
    N004["for write in stray_writes(scripts_dir):
    errors += 1
    print(f'<str>{write.script}<str>{write.lineno}<str>{write.script}<str>{write.lineno}<str>{write.line!r}<str>{HELPER_NAME}<str>', file=sys.stderr)"]
    N005["if not helper_writes_env_file(scripts_dir)"]
    N006["errors += 1"]
    N007["print(...)"]
    N008["if errors"]
    N009["print(...)"]
    N010["return 1"]
    N011["print(...)"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N007 --> N008
    N005 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 --> N012
```

## _cmd_list(...)

```mermaid
flowchart TD
    N001["_cmd_list(...)"]
    N002["for write in _iter_writes(Path(args.scripts_dir)):
    print(f'<str>{write.script}<str>{write.lineno}<str>{write.line}')"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["p_list = add_parser(...)"]
    N008["add_argument(...)"]
    N009["set_defaults(...)"]
    N010["args = parse_args(...)"]
    N011["return args.func(args)"]
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
