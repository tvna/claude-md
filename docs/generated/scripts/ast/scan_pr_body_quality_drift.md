# AST graph: scripts/scan_pr_body_quality_drift.py

This file is generated from `scripts/scan_pr_body_quality_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## resolve_backing(...)

```mermaid
flowchart TD
    N001["resolve_backing(...)"]
    N002["(kind, _, name) = partition(...)"]
    N003["if not name"]
    N004["return f'<str>{ref}<str>'"]
    N005["if kind == 'script'"]
    N006["if not (repo_root / 'scripts' / f'{name}.py').is_file()"]
    N007["return f'<str>{ref}<str>{name}<str>'"]
    N008["return None"]
    N009["if kind == 'test'"]
    N010["if not (repo_root / 'tests' / f'{name}.py').is_file()"]
    N011["return f'<str>{ref}<str>{name}<str>'"]
    N012["return None"]
    N013["return f'<str>{ref}<str>{kind}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N005 -->|"false"| N009
    N009 -->|"true"| N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N009 -->|"false"| N013
```

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["defects = []"]
    N003["registry_keys = set(...)"]
    N004["for orphan in sorted(registry_keys - KNOWN_DEFECTS):     defects.append(f'<str>{orphan}<str>')"]
    N005["for missing in sorted(KNOWN_DEFECTS - registry_keys):     defects.append(f'<str>{missing}<str>')"]
    N006["for key in sorted(registry_keys & KNOWN_DEFECTS):     entry = registry[key]     if not isinstance(entry, dict):         defects.append(f'<str>{key}<str>')         continue     status = entry.get('<str>')     backing = entry.get('<str>')     if status not in _VALID_STATUS:         defects.append(f'<str>{key}<str>{status!r}<str>{sorted(_VALID_STATUS)}<str>')         continue     if not isinstance(backing, list) or not all((isinstance(item, str) for item in backing)):         defects.append(f'<str>{key}<str>')         continue     if status == '<str>':         if backing:             defects.append(f'<str>{key}<str>{backing}<str>')         continue     if not backing:         defects.append(f'<str>{key}<str>{status}<str>')         continue     for ref in backing:         problem = resolve_backing(ref, repo_root)         if problem is not None:             defects.append(f'<str>{key}<str>{problem}')"]
    N007["return defects"]
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
    N002["registry_path = Path(...)"]
    N003["repo_root = Path(...)"]
    N004["with registry_path.open('<str>') as handle:     registry = tomllib.load(handle)"]
    N005["defects = find_drift(...)"]
    N006["for defect in defects:     print(f'<str>{defect}<str>', file=sys.stderr)"]
    N007["if defects"]
    N008["return 1"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify = add_parser(...)"]
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
