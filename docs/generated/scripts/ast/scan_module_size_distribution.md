# AST graph: scripts/scan_module_size_distribution.py

This file is generated from `scripts/scan_module_size_distribution.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## bucket_label(...)

```mermaid
flowchart TD
    N001["bucket_label(...)"]
    N002["lower = 1 if index == 0 else BUCKET_EDGES[index - 1] + 1"]
    N003["if index < len(BUCKET_EDGES)"]
    N004["return f'{lower}<str>{BUCKET_EDGES[index]}'"]
    N005["return f'{BUCKET_EDGES[-1] + 1}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## bucket_counts(...)

```mermaid
flowchart TD
    N001["bucket_counts(...)"]
    N002["counts = [0] * (len(BUCKET_EDGES) + 1)"]
    N003["for module in modules:     index = len(BUCKET_EDGES)     for i, edge in enumerate(BUCKET_EDGES):         if module.line_count <= edge:             index = i             break     counts[index] += 1"]
    N004["return counts"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _rel_names(...)

```mermaid
flowchart TD
    N001["_rel_names(...)"]
    N002["return sorted((module.path.as_posix() for module in modules))"]
    N001 -->|"start"| N002
```

## _render_string_array(...)

```mermaid
flowchart TD
    N001["_render_string_array(...)"]
    N002["if not values"]
    N003["return [f'{name}<str>']"]
    N004["lines = [f'{name}<str>']"]
    N005["extend(...)"]
    N006["append(...)"]
    N007["return lines"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## render_snapshot(...)

```mermaid
flowchart TD
    N001["render_snapshot(...)"]
    N002["warn_band = [module for module in modules if module.is_in_warn_band]"]
    N003["over_budget = [module for module in modules if module.is_over_budget]"]
    N004["at_limit = [module for module in modules if module.line_count == MAX_MODULE_LINES]"]
    N005["counts = bucket_counts(...)"]
    N006["lines = ['<str>', '<str>', '<str>', '<str>', '<str>', '<str>', f'<str>{MAX_MODULE_LINES}', f'<str>{WARN_MODULE_LINES}', '<str>', '<str>', f'<str>{len(modules)}', f'<str>{len(warn_band)}', f'<str>{len(at_limit)}', f'<str>{len(over_budget)}', '<str>', '<str>', '<str>']"]
    N007["extend(...)"]
    N008["extend(...)"]
    N009["extend(...)"]
    N010["extend(...)"]
    N011["return '<str>'.join(lines) + '<str>'"]
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

## _cmd_write(...)

```mermaid
flowchart TD
    N001["_cmd_write(...)"]
    N002["repo_root = resolve(...)"]
    N003["snapshot = render_snapshot(...)"]
    N004["path = repo_root / SNAPSHOT_PATH"]
    N005["mkdir(...)"]
    N006["write_text(...)"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["expected = render_snapshot(...)"]
    N004["path = repo_root / SNAPSHOT_PATH"]
    N005["actual = path.read_text(encoding='<str>') if path.exists() else None"]
    N006["if actual == expected"]
    N007["print(...)"]
    N008["return 0"]
    N009["print(...)"]
    N010["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_write = add_parser(...)"]
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
