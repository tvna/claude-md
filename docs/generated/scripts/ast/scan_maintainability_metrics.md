# AST graph: scripts/scan_maintainability_metrics.py

This file is generated from `scripts/scan_maintainability_metrics.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## count_lines(...)

```mermaid
flowchart TD
    N001["count_lines(...)"]
    N002["return len(path.read_text(encoding='<str>', errors='<str>').splitlines())"]
    N001 -->|"start"| N002
```

## measure_module(...)

```mermaid
flowchart TD
    N001["measure_module(...)"]
    N002["rel = relative_to(...)"]
    N003["return ModuleSize(path=rel, line_count=count_lines(path), max_lines=MAX_MODULE_LINES, warn_lines=WARN_MODULE_LINES, deferred_reason=DEFERRED_OVERSIZE_MODULES.get(rel))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## find_module_sizes(...)

```mermaid
flowchart TD
    N001["find_module_sizes(...)"]
    N002["scripts_dir = repo_root / SCRIPT_SUBDIR"]
    N003["if not scripts_dir.exists()"]
    N004["return []"]
    N005["return [measure_module(path, repo_root) for path in _iter_python_files(scripts_dir)]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["return [metric for metric in find_module_sizes(repo_root) if metric.is_violation]"]
    N001 -->|"start"| N002
```

## _iter_python_files(...)

```mermaid
flowchart TD
    N001["_iter_python_files(...)"]
    N002["for path in sorted(scripts_dir.rglob('<str>')):     if path.is_file():         yield path"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["metrics = find_module_sizes(...)"]
    N004["violations = [metric for metric in metrics if metric.is_violation]"]
    N005["warned = [metric for metric in metrics if metric.is_in_warn_band]"]
    N006["deferred = [metric for metric in metrics if metric.is_over_budget and metric.deferred_reason is not None]"]
    N007["for metric in violations:     print(f'<str>{metric.path}<str>{metric.path}<str>{metric.line_count}<str>{metric.max_lines}<str>', file=sys.stderr)"]
    N008["for metric in warned:     print(f'<str>{metric.path}<str>{metric.path}<str>{metric.line_count}<str>{metric.warn_lines}<str>{metric.max_lines}<str>{int(WARN_RATIO * 100)}<str>')"]
    N009["for metric in deferred:     print(f'<str>{metric.path}<str>{metric.path}<str>{metric.line_count}<str>{metric.max_lines}<str>{metric.deferred_reason}<str>')"]
    N010["if violations"]
    N011["print(...)"]
    N012["return 1"]
    N013["print(...)"]
    N014["return 0"]
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
