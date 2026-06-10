# AST graph: scripts/uv_pin.py

This file is generated from `scripts/uv_pin.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## read_pin(...)

```mermaid
flowchart TD
    N001["read_pin(...)"]
    N002["try"]
    N003["with pyproject_path.open('<str>') as fp:
    data = tomllib.load(fp)"]
    N004["except FileNotFoundError"]
    N005["raise ValueError(f'<str>{pyproject_path}<str>{exc}')"]
    N006["except tomllib.TOMLDecodeError"]
    N007["raise ValueError(f'<str>{pyproject_path}<str>{exc}')"]
    N008["try"]
    N009["spec = data['<str>']['<str>']['<str>']"]
    N010["except (KeyError, TypeError)"]
    N011["raise ValueError(f'<str>{pyproject_path}')"]
    N012["if not isinstance(spec, str) or not spec.startswith('==')"]
    N013["raise ValueError(f'<str>{spec!r}')"]
    N014["return spec[2:]"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N002 -->|"raises"| N006
    N006 --> N007
    N003 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N009 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
```

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["errors = []"]
    N003["for path in _iter_files(repo_root, DRIFT_SUBDIRS):
    rel = path.relative_to(repo_root)
    if rel.as_posix() in DRIFT_EXCLUDE_RELPATHS:
        continue
    for line_num, line in _read_lines(path):
        if pin in line:
            errors.append(f'{rel}<str>{line_num}<str>{pin!r}<str>')"]
    N004["workflow_dir = repo_root / WORKFLOW_SUBDIR"]
    N005["if workflow_dir.exists()"]
    N006["for path in workflow_dir.rglob('<str>'):
    if not path.is_file() or path.suffix not in ('<str>', '<str>'):
        continue
    for line_num, line in _read_lines(path):
        if _UV_PIN_SYMBOL_ASSIGN.match(line) and (not _GHA_EXPR.search(line)):
            rel = path.relative_to(repo_root)
            errors.append(f'{rel}<str>{line_num}<str>')"]
    N007["docs_dir = repo_root / DOCS_SUBDIR"]
    N008["if docs_dir.exists()"]
    N009["for path in docs_dir.rglob('<str>'):
    if not path.is_file():
        continue
    for line_num, line in _read_lines(path):
        if _UV_PIN_SYMBOL_SYMBOL.search(line):
            rel = path.relative_to(repo_root)
            errors.append(f'{rel}<str>{line_num}<str>')"]
    N010["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
```

## fetch_latest_uv_release(...)

```mermaid
flowchart TD
    N001["fetch_latest_uv_release(...)"]
    N002["try"]
    N003["result = run(...)"]
    N004["except (subprocess.SubprocessError, FileNotFoundError, OSError)"]
    N005["return None"]
    N006["tag = strip(...)"]
    N007["return tag or None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
```

## _iter_files(...)

```mermaid
flowchart TD
    N001["_iter_files(...)"]
    N002["for sub in subdirs:
    base = root / sub
    if not base.exists():
        continue
    for path in base.rglob('<str>'):
        if path.is_file():
            yield path"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _read_lines(...)

```mermaid
flowchart TD
    N001["_read_lines(...)"]
    N002["try"]
    N003["content = read_text(...)"]
    N004["except OSError"]
    N005["return"]
    N006["(yield from enumerate(content.splitlines(), 1))"]
    N007["end"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
```

## _cmd_read(...)

```mermaid
flowchart TD
    N001["_cmd_read(...)"]
    N002["print(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_drift(...)

```mermaid
flowchart TD
    N001["_cmd_drift(...)"]
    N002["repo_root = resolve(...)"]
    N003["pin = read_pin(...)"]
    N004["print(...)"]
    N005["errors = find_drift(...)"]
    N006["for err in errors:
    print(f'<str>{err}')"]
    N007["if errors"]
    N008["print(...)"]
    N009["return 1"]
    N010["print(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
```

## _cmd_stale(...)

```mermaid
flowchart TD
    N001["_cmd_stale(...)"]
    N002["repo_root = resolve(...)"]
    N003["pin = read_pin(...)"]
    N004["latest = fetch_latest_uv_release(...)"]
    N005["if latest is None"]
    N006["print(...)"]
    N007["return 0"]
    N008["if pin != latest"]
    N009["print(...)"]
    N010["print(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N009 --> N011
    N010 --> N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_read = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["p_drift = add_parser(...)"]
    N008["add_argument(...)"]
    N009["set_defaults(...)"]
    N010["p_stale = add_parser(...)"]
    N011["add_argument(...)"]
    N012["set_defaults(...)"]
    N013["args = parse_args(...)"]
    N014["try"]
    N015["return args.func(args)"]
    N016["except ValueError"]
    N017["print(...)"]
    N018["return 1"]
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
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 -->|"try"| N015
    N014 -->|"raises"| N016
    N016 --> N017
    N017 --> N018
```
