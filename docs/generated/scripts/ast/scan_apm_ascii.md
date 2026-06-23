# AST graph: scripts/scan_apm_ascii.py

This file is generated from `scripts/scan_apm_ascii.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _codepoint_label(...)

```mermaid
flowchart TD
    N001["_codepoint_label(...)"]
    N002["name = name(...)"]
    N003["code = f'<str>{ord(char):<str>}'"]
    N004["return f'{code}<str>{name}'.rstrip()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## scan_text(...)

```mermaid
flowchart TD
    N001["scan_text(...)"]
    N002["hits = []"]
    N003["lineno = 1"]
    N004["column = 0"]
    N005["for char in text:     if char == '<str>':         lineno += 1         column = 0         continue     column += 1     if ord(char) > 127 and char not in _ALLOWED_NON_ASCII:         hits.append((lineno, column, char))"]
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
    N002["return scan_text(path.read_text(encoding='<str>'))"]
    N001 -->|"start"| N002
```

## _verify(...)

```mermaid
flowchart TD
    N001["_verify(...)"]
    N002["total = 0"]
    N003["for path in paths:     if not path.exists():         print(f'<str>{path}', file=sys.stderr)         total += 1         continue     for lineno, column, char in scan_file(path):         print(f'<str>{path}<str>{lineno}<str>{column}<str>{_codepoint_label(char)}<str>', file=sys.stderr)         total += 1"]
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
    N002["if not args.path"]
    N003["print(...)"]
    N004["return 2"]
    N005["paths = [Path(p) for p in args.path]"]
    N006["return _verify(paths)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
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
