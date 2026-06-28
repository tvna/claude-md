# AST graph: scripts/scan_devcontainer_tool_drift.py

This file is generated from `scripts/scan_devcontainer_tool_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## required_bins(...)

```mermaid
flowchart TD
    N001["required_bins(...)"]
    N002["import preflight_all"]
    N003["bins = set(...)"]
    N004["for step in preflight_all.STEPS:     bins.update(step.required_bin)"]
    N005["return bins"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["flake_path = repo_root / '<str>'"]
    N003["if not flake_path.is_file()"]
    N004["return [f'<str>{flake_path}<str>']"]
    N005["flake_text = read_text(...)"]
    N006["errors = []"]
    N007["for tool in sorted(required_bins()):     if tool in ALLOWLIST:         continue     marker = TOOL_FLAKE_MARKERS.get(tool)     if marker is None:         errors.append(f'<str>{tool}<str>{tool}<str>')         continue     if marker not in flake_text:         errors.append(f'<str>{tool}<str>{marker}<str>{marker}<str>')"]
    N008["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
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
