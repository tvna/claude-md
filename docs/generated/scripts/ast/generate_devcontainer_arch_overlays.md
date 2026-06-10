# AST graph: scripts/generate_devcontainer_arch_overlays.py

This file is generated from `scripts/generate_devcontainer_arch_overlays.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## base_path(...)

```mermaid
flowchart TD
    N001["base_path(...)"]
    N002["return repo_root / '<str>' / agent / '<str>'"]
    N001 -->|"start"| N002
```

## overlay_path(...)

```mermaid
flowchart TD
    N001["overlay_path(...)"]
    N002["return repo_root / '<str>' / f'{agent}<str>{arch}' / '<str>'"]
    N001 -->|"start"| N002
```

## render_overlay(...)

```mermaid
flowchart TD
    N001["render_overlay(...)"]
    N002["overlay = {'<str>': _MARKER_TEMPLATE.format(agent=agent, arch=arch)}"]
    N003["update(...)"]
    N004["name = get(...)"]
    N005["if isinstance(name, str)"]
    N006["overlay['<str>'] = f'{name}<str>{arch}<str>'"]
    N007["platform_arg = f'<str>{arch}'"]
    N008["run_args = get(...)"]
    N009["if not isinstance(run_args, list)"]
    N010["raise ValueError(f'{agent}<str>{type(run_args).__name__}')"]
    N011["overlay['<str>'] = [platform_arg, *run_args]"]
    N012["init = get(...)"]
    N013["if isinstance(init, str)"]
    N014["token = f'<str>{agent}'"]
    N015["count = count(...)"]
    N016["if count != 1"]
    N017["raise ValueError(f'{agent}<str>{token}<str>{count}')"]
    N018["overlay['<str>'] = replace(...)"]
    N019["return overlay"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N018 --> N019
    N013 -->|"false"| N019
```

## render_overlay_text(...)

```mermaid
flowchart TD
    N001["render_overlay_text(...)"]
    N002["return json.dumps(render_overlay(base, agent, arch), indent=2) + '<str>'"]
    N001 -->|"start"| N002
```

## _load_base(...)

```mermaid
flowchart TD
    N001["_load_base(...)"]
    N002["path = base_path(...)"]
    N003["return json.loads(path.read_text(encoding='<str>'))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## generate(...)

```mermaid
flowchart TD
    N001["generate(...)"]
    N002["changed = []"]
    N003["for agent in AGENTS:     base = _load_base(repo_root, agent)     for arch in ARCHES:         path = overlay_path(repo_root, agent, arch)         expected = render_overlay_text(base, agent, arch)         current = path.read_text(encoding='<str>') if path.is_file() else None         if current == expected:             continue         path.parent.mkdir(parents=True, exist_ok=True)         path.write_text(expected, encoding='<str>')         changed.append(str(path.relative_to(repo_root)))"]
    N004["return changed"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["errors = []"]
    N003["for agent in AGENTS:     base_file = base_path(repo_root, agent)     if not base_file.is_file():         errors.append(f'<str>{base_file}<str>{agent}<str>')         continue     base = json.loads(base_file.read_text(encoding='<str>'))     for arch in ARCHES:         path = overlay_path(repo_root, agent, arch)         expected = render_overlay_text(base, agent, arch)         if not path.is_file():             errors.append(f'<str>{path}<str>')             continue         if path.read_text(encoding='<str>') != expected:             errors.append(f'<str>{path}<str>{base_file}<str>')"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _cmd_generate(...)

```mermaid
flowchart TD
    N001["_cmd_generate(...)"]
    N002["repo_root = resolve(...)"]
    N003["changed = generate(...)"]
    N004["if changed"]
    N005["for path in changed:     print(f'<str>{path}')"]
    N006["print(...)"]
    N007["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N005 --> N007
    N006 --> N007
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["errors = verify(...)"]
    N004["for err in errors:     print(err, file=sys.stderr)"]
    N005["if errors"]
    N006["print(...)"]
    N007["return 1"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_generate = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["p_verify = add_parser(...)"]
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
