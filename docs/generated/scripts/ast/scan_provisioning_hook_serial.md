# AST graph: scripts/scan_provisioning_hook_serial.py

This file is generated from `scripts/scan_provisioning_hook_serial.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## provisioning_hooks(...)

```mermaid
flowchart TD
    N001["provisioning_hooks(...)"]
    N002["hooks = []"]
    N003["for repo in config.get('<str>', []) or []:
    for hook in repo.get('<str>', []) or []:
        entry = str(hook.get('<str>', '<str>'))
        if _PROVISIONING_RE.search(entry):
            hooks.append(hook)"]
    N004["return hooks"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## find_gaps(...)

```mermaid
flowchart TD
    N001["find_gaps(...)"]
    N002["errors = []"]
    N003["for hook in provisioning_hooks(config):
    if hook.get('<str>') is not True:
        hook_id = hook.get('<str>', '<str>')
        errors.append(f'<str>{hook_id}<str>')"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _load_config(...)

```mermaid
flowchart TD
    N001["_load_config(...)"]
    N002["try"]
    N003["text = read_text(...)"]
    N004["except OSError"]
    N005["raise SystemExit(f'<str>{path}<str>{exc}')"]
    N006["data = safe_load(...)"]
    N007["if not isinstance(data, dict)"]
    N008["raise SystemExit(f'<str>{path}<str>')"]
    N009["return data"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["errors = find_gaps(...)"]
    N003["if errors"]
    N004["for err in errors:
    print(err, file=sys.stderr)"]
    N005["print(...)"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 --> N006
    N003 -->|"false"| N007
    N007 --> N008
```

## _cmd_list(...)

```mermaid
flowchart TD
    N001["_cmd_list(...)"]
    N002["for hook in provisioning_hooks(_load_config()):
    print(f'{hook.get('<str>', '<str>')}<str>{hook.get('<str>')}')"]
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
    N004["set_defaults(...)"]
    N005["set_defaults(...)"]
    N006["args = parse_args(...)"]
    N007["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```
