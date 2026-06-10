# AST graph: scripts/backup_archive.py

This file is generated from `scripts/backup_archive.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## build_payload(...)

```mermaid
flowchart TD
    N001["build_payload(...)"]
    N002["payload = {'<str>': timestamp, '<str>': repo}"]
    N003["counts = []"]
    N004["for key, fname in sources:
    path = indir / fname
    try:
        raw = path.read_text(encoding='<str>')
    except OSError as exc:
        raise ValueError(f'<str>{path}<str>{exc}<str>') from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f'<str>{path}<str>{exc}') from exc
    if not isinstance(data, list):
        raise ValueError(f'<str>{path}<str>{type(data).__name__}')
    payload[key] = data
    counts.append((key, len(data)))"]
    N005["return (payload, counts)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## write_gzip(...)

```mermaid
flowchart TD
    N001["write_gzip(...)"]
    N002["with gzip.open(archive, '<str>', encoding='<str>') as fh:
    json.dump(payload, fh, ensure_ascii=True, indent=None)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_build(...)

```mermaid
flowchart TD
    N001["_cmd_build(...)"]
    N002["try"]
    N003["(payload, counts) = build_payload(...)"]
    N004["except ValueError"]
    N005["print(...)"]
    N006["return 1"]
    N007["for key, count in counts:
    print(f'{key}<str>{count}<str>', flush=True)"]
    N008["archive = Path(...)"]
    N009["write_gzip(...)"]
    N010["print(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N005 --> N006
    N003 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["build_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["args = parse_args(...)"]
    N010["if args.cmd == 'build'"]
    N011["return _cmd_build(args)"]
    N012["return 0"]
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
    N010 -->|"false"| N012
```
