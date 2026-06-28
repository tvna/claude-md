# AST graph: scripts/scan_hook_predicate_surface_drift.py

This file is generated from `scripts/scan_hook_predicate_surface_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _predicate_inner(...)

```mermaid
flowchart TD
    N001["_predicate_inner(...)"]
    N002["match = match(...)"]
    N003["return match.group('<str>') if match else None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _is_git_predicate(...)

```mermaid
flowchart TD
    N001["_is_git_predicate(...)"]
    N002["return '<str>' in inner"]
    N001 -->|"start"| N002
```

## iter_git_hooks(...)

```mermaid
flowchart TD
    N001["iter_git_hooks(...)"]
    N002["raw_hooks = get(...)"]
    N003["if not isinstance(raw_hooks, dict)"]
    N004["return"]
    N005["raw_groups = get(...)"]
    N006["if not isinstance(raw_groups, list)"]
    N007["return"]
    N008["for group in raw_groups:     if not isinstance(group, dict):         continue     handlers = group.get('<str>')     if not isinstance(handlers, list):         continue     for handler in handlers:         if not isinstance(handler, dict):             continue         predicate = handler.get('<str>')         command = handler.get('<str>')         if not isinstance(predicate, str) or not isinstance(command, str):             continue         inner = _predicate_inner(predicate)         if inner is None or not _is_git_predicate(inner):             continue         scripts = _SCRIPT_REF.findall(command)         if not scripts:             continue         yield GitHook(script=scripts[0], command=command, predicate=predicate, inner=inner)"]
    N009["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## _load_surface(...)

```mermaid
flowchart TD
    N001["_load_surface(...)"]
    N002["module = import_module(...)"]
    N003["return getattr(module, SURFACE_ATTR, None)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _admits(...)

```mermaid
flowchart TD
    N001["_admits(...)"]
    N002["return fnmatch.fnmatchcase(f'<str>{subcommand}', inner)"]
    N001 -->|"start"| N002
```

## check_hook(...)

```mermaid
flowchart TD
    N001["check_hook(...)"]
    N002["is_broad = hook.inner == BROAD_INNER"]
    N003["if surface is None"]
    N004["if is_broad"]
    N005["return []"]
    N006["return [f'<str>{hook.script}<str>{hook.predicate!r}<str>{SURFACE_ATTR}<str>{SURFACE_ATTR}<str>']"]
    N007["if surface == ANY_GIT"]
    N008["if not is_broad"]
    N009["return [f'<str>{hook.script}<str>{SURFACE_ATTR}<str>{hook.predicate!r}<str>{BROAD_INNER!r}<str>']"]
    N010["return []"]
    N011["if not isinstance(surface, set | frozenset) or not all((isinstance(s, str) for s in surface))"]
    N012["return [f'<str>{hook.script}<str>{SURFACE_ATTR}<str>{type(surface).__name__}<str>']"]
    N013["if not surface"]
    N014["return [f'<str>{hook.script}<str>{SURFACE_ATTR}<str>']"]
    N015["unadmitted = sorted(...)"]
    N016["if unadmitted"]
    N017["return [f'<str>{hook.script}<str>{hook.predicate!r}<str>{unadmitted}<str>{SURFACE_ATTR}<str>{BROAD_INNER!r}<str>']"]
    N018["return []"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N003 -->|"false"| N007
    N007 -->|"true"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N007 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
```

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["problems = []"]
    N003["for hook in iter_git_hooks(source):     try:         surface = _load_surface(hook.script)     except Exception as exc:         problems.append(f'<str>{hook.script}<str>{SURFACE_ATTR}<str>{exc}')         continue     problems.extend(check_hook(hook, surface))"]
    N004["return problems"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["settings = loads(...)"]
    N003["problems = find_drift(...)"]
    N004["for message in problems:     print(f'<str>{message}', file=sys.stderr)"]
    N005["return 1 if problems else 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["args = parse_args(...)"]
    N008["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```
