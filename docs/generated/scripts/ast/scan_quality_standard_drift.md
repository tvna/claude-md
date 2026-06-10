# AST graph: scripts/scan_quality_standard_drift.py

This file is generated from `scripts/scan_quality_standard_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## parse_must_haves(...)

```mermaid
flowchart TD
    N001["parse_must_haves(...)"]
    N002["return set(_MUST_HAVE_HEADING.findall(standard_text))"]
    N001 -->|"start"| N002
```

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
    N013["if kind == 'tool'"]
    N014["if name not in _KNOWN_TOOLS"]
    N015["return f'<str>{ref}<str>{sorted(_KNOWN_TOOLS)}<str>'"]
    N016["if name not in pyproject_text"]
    N017["return f'<str>{ref}<str>'"]
    N018["return None"]
    N019["return f'<str>{ref}<str>{kind}<str>'"]
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
    N013 -->|"true"| N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N013 -->|"false"| N019
```

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["defects = []"]
    N003["registry_keys = set(...)"]
    N004["for missing in sorted(must_haves - registry_keys):     defects.append(f'{missing}<str>')"]
    N005["for orphan in sorted(registry_keys - must_haves):     defects.append(f'{orphan}<str>')"]
    N006["for key in sorted(must_haves & registry_keys):     entry = registry[key]     if not isinstance(entry, dict):         defects.append(f'{key}<str>')         continue     status = entry.get('<str>')     backing = entry.get('<str>')     if status not in _VALID_STATUS:         defects.append(f'{key}<str>{status!r}<str>{sorted(_VALID_STATUS)}<str>')         continue     if not isinstance(backing, list) or not all((isinstance(item, str) for item in backing)):         defects.append(f'{key}<str>')         continue     if status == '<str>':         if backing:             defects.append(f'{key}<str>{backing}<str>')         continue     if not backing:         defects.append(f'{key}<str>{status}<str>')         continue     for ref in backing:         problem = resolve_backing(ref, repo_root, pyproject_text)         if problem is not None:             defects.append(f'{key}<str>{problem}')"]
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
    N002["standard = Path(...)"]
    N003["registry_path = Path(...)"]
    N004["repo_root = Path(...)"]
    N005["pyproject_text = read_text(...)"]
    N006["must_haves = parse_must_haves(...)"]
    N007["with registry_path.open('<str>') as handle:     registry = tomllib.load(handle)"]
    N008["defects = find_drift(...)"]
    N009["for defect in defects:     print(f'<str>{defect}<str>', file=sys.stderr)"]
    N010["if defects"]
    N011["return 1"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
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
