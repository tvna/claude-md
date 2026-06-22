# AST graph: scripts/scan_repo_em_dash.py

This file is generated from `scripts/scan_repo_em_dash.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## scan_text(...)

```mermaid
flowchart TD
    N001["scan_text(...)"]
    N002["hits = []"]
    N003["lineno = 1"]
    N004["column = 0"]
    N005["for char in text:     if char == '<str>':         lineno += 1         column = 0         continue     column += 1     if char == _EM_DASH:         hits.append((lineno, column))"]
    N006["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## scan_file(...)

```mermaid
flowchart TD
    N001["scan_file(...)"]
    N002["try"]
    N003["return scan_text(path.read_text(encoding='<str>'))"]
    N004["except (UnicodeDecodeError, IsADirectoryError, OSError)"]
    N005["print(...)"]
    N006["return []"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N005 --> N006
```

## _git_tracked_files(...)

```mermaid
flowchart TD
    N001["_git_tracked_files(...)"]
    N002["result = run(...)"]
    N003["if result.returncode != 0"]
    N004["print(...)"]
    N005["return None"]
    N006["return [Path(p) for p in result.stdout.splitlines() if p and (not any((p.startswith(prefix) for prefix in _SKIP_PREFIXES)))]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
```

## _verify(...)

```mermaid
flowchart TD
    N001["_verify(...)"]
    N002["total = 0"]
    N003["for path in sorted({p for p in paths if p.is_file()}):     for lineno, column in scan_file(path):         print(f'<str>{path}<str>{lineno}<str>{column}<str>', file=sys.stderr)         total += 1"]
    N004["if total"]
    N005["print(...)"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["if not args.git_tracked and (not args.path)"]
    N003["print(...)"]
    N004["return 2"]
    N005["paths = [Path(p) for p in args.path]"]
    N006["if args.git_tracked"]
    N007["tracked = _git_tracked_files(...)"]
    N008["if tracked is None"]
    N009["return 1"]
    N010["extend(...)"]
    N011["return _verify(paths)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N006 -->|"false"| N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
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
