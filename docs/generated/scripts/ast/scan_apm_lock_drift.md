# AST graph: scripts/scan_apm_lock_drift.py

This file is generated from `scripts/scan_apm_lock_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## declared_mcp(...)

```mermaid
flowchart TD
    N001["declared_mcp(...)"]
    N002["data = yaml.safe_load(apm_yml_text) or {}"]
    N003["deps = (data.get('<str>') or {}).get('<str>') or []"]
    N004["result = {}"]
    N005["for entry in deps:     if not isinstance(entry, dict) or '<str>' not in entry:         continue     name = str(entry['<str>'])     result[name] = {f: str(entry[f]) for f in COMPARED_FIELDS if f in entry}"]
    N006["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## locked_mcp(...)

```mermaid
flowchart TD
    N001["locked_mcp(...)"]
    N002["data = yaml.safe_load(lock_text) or {}"]
    N003["servers = {str(s) for s in data.get('<str>') or []}"]
    N004["configs = {}"]
    N005["for name, cfg in (data.get('<str>') or {}).items():     if not isinstance(cfg, dict):         continue     configs[str(name)] = {f: str(cfg[f]) for f in COMPARED_FIELDS if f in cfg}"]
    N006["return (servers, configs)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["errors = []"]
    N003["remediation = '<str>'"]
    N004["for name, decl in sorted(declared.items()):     if name not in servers:         errors.append(f'<str>{APM_LOCK_REL}<str>{name}<str>{remediation}<str>')     if name not in configs:         errors.append(f'<str>{APM_LOCK_REL}<str>{name}<str>{remediation}<str>')         continue     for field, want in decl.items():         got = configs[name].get(field)         if got != want:             errors.append(f'<str>{APM_LOCK_REL}<str>{name}<str>{field}<str>{want}<str>{got}<str>{remediation}<str>')"]
    N005["for name in sorted(servers | set(configs)):     if name not in declared:         errors.append(f'<str>{APM_LOCK_REL}<str>{name}<str>{remediation}<str>')"]
    N006["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _read(...)

```mermaid
flowchart TD
    N001["_read(...)"]
    N002["path = repo_root / rel"]
    N003["if not path.is_file()"]
    N004["raise SystemExit(f'<str>{rel}<str>{path}')"]
    N005["return path.read_text(encoding='<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _load(...)

```mermaid
flowchart TD
    N001["_load(...)"]
    N002["declared = declared_mcp(...)"]
    N003["(servers, configs) = locked_mcp(...)"]
    N004["return (declared, servers, configs)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["(declared, servers, configs) = _load(...)"]
    N003["errors = find_drift(...)"]
    N004["if errors"]
    N005["for err in errors:     print(err, file=sys.stderr)"]
    N006["print(...)"]
    N007["return 1"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N006 --> N007
    N004 -->|"false"| N008
    N008 --> N009
```

## _cmd_list(...)

```mermaid
flowchart TD
    N001["_cmd_list(...)"]
    N002["(declared, servers, configs) = _load(...)"]
    N003["print(...)"]
    N004["print(...)"]
    N005["print(...)"]
    N006["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
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
