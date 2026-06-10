# AST graph: scripts/gen_agent_hooks.py

This file is generated from `scripts/gen_agent_hooks.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## command_needs_wrap(...)

```mermaid
flowchart TD
    N001["command_needs_wrap(...)"]
    N002["return any((token.startswith('<str>') for token in command.split()))"]
    N001 -->|"start"| N002
```

## wrap_command(...)

```mermaid
flowchart TD
    N001["wrap_command(...)"]
    N002["if command.startswith(HOOK_CWD_PREFIX)"]
    N003["return command"]
    N004["if command_needs_wrap(command)"]
    N005["return HOOK_CWD_PREFIX + command"]
    N006["return command"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## unwrap_command(...)

```mermaid
flowchart TD
    N001["unwrap_command(...)"]
    N002["if command.startswith(HOOK_CWD_PREFIX)"]
    N003["return command[len(HOOK_CWD_PREFIX):]"]
    N004["return command"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _wrap_config(...)

```mermaid
flowchart TD
    N001["_wrap_config(...)"]
    N002["rendered = deepcopy(...)"]
    N003["hooks = get(...)"]
    N004["if isinstance(hooks, dict)"]
    N005["for groups in hooks.values():     if not isinstance(groups, list):         continue     for group in groups:         if not isinstance(group, dict):             continue         handlers = group.get('<str>')         if not isinstance(handlers, list):             continue         for handler in handlers:             if not isinstance(handler, dict):                 continue             command = handler.get('<str>')             if isinstance(command, str):                 handler['<str>'] = wrap_command(command)"]
    N006["return rendered"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
```

## _serialise(...)

```mermaid
flowchart TD
    N001["_serialise(...)"]
    N002["return json.dumps(config, indent=2) + '<str>'"]
    N001 -->|"start"| N002
```

## render_targets(...)

```mermaid
flowchart TD
    N001["render_targets(...)"]
    N002["targets = get(...)"]
    N003["if not isinstance(targets, list) or not targets"]
    N004["raise ValueError('<str>')"]
    N005["configs_by_agent = {}"]
    N006["for target in targets:     if not isinstance(target, dict):         raise ValueError(f'<str>{type(target).__name__}')     agent = target.get('<str>')     if not isinstance(agent, str) or not agent:         raise ValueError('<str>')     if '<str>' in target:         config = target['<str>']         if not isinstance(config, dict):             raise ValueError(f'<str>{agent!r}<str>')         configs_by_agent[agent] = config"]
    N007["rendered = {}"]
    N008["for target in targets:     agent = target['<str>']     path = target.get('<str>')     if not isinstance(path, str) or not path:         raise ValueError(f'<str>{agent!r}<str>')     mirror = target.get('<str>')     if mirror is not None:         if mirror not in configs_by_agent:             raise ValueError(f'<str>{agent!r}<str>{mirror!r}<str>')         config = configs_by_agent[mirror]     elif agent in configs_by_agent:         config = configs_by_agent[agent]     else:         raise ValueError(f'<str>{agent!r}<str>')     rendered[path] = _serialise(_wrap_config(config))"]
    N009["return rendered"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## _load_source(...)

```mermaid
flowchart TD
    N001["_load_source(...)"]
    N002["try"]
    N003["raw = read_text(...)"]
    N004["except OSError"]
    N005["print(...)"]
    N006["raise SystemExit(2)"]
    N007["try"]
    N008["data = loads(...)"]
    N009["except json.JSONDecodeError"]
    N010["print(...)"]
    N011["raise SystemExit(2)"]
    N012["if not isinstance(data, dict)"]
    N013["print(...)"]
    N014["raise SystemExit(2)"]
    N015["return data"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N005 --> N006
    N003 --> N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N010 --> N011
    N008 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N015
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["args = parse_args(...)"]
    N005["try"]
    N006["rendered = render_targets(...)"]
    N007["except ValueError"]
    N008["print(...)"]
    N009["return 2"]
    N010["if args.check"]
    N011["stale = False"]
    N012["for rel, text in rendered.items():     path = REPO_ROOT / rel     try:         current = path.read_text(encoding='<str>')     except OSError:         print(f'<str>{rel}<str>', file=sys.stderr)         stale = True         continue     if current != text:         print(f'<str>{rel}<str>', file=sys.stderr)         stale = True"]
    N013["return 1 if stale else 0"]
    N014["for rel, text in rendered.items():     (REPO_ROOT / rel).write_text(text, encoding='<str>')"]
    N015["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N012 --> N013
    N010 -->|"false"| N014
    N014 --> N015
```
