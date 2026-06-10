# AST graph: scripts/validate_json_syntax.py

This file is generated from `scripts/validate_json_syntax.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## validate_files(...)

```mermaid
flowchart TD
    N001["validate_files(...)"]
    N002["errors = []"]
    N003["for path in paths:     try:         raw = Path(path).read_text(encoding='<str>')     except OSError as exc:         errors.append((path, f'<str>{exc}'))         continue     try:         json.loads(raw)     except json.JSONDecodeError as exc:         errors.append((path, f'<str>{exc}'))"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["errors = validate_files(...)"]
    N003["for path, reason in errors:     print(f'<str>{path}<str>{reason}', file=sys.stderr)"]
    N004["return 1 if errors else 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["args = parse_args(...)"]
    N007["if args.cmd == 'verify'"]
    N008["return _cmd_verify(args)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```
