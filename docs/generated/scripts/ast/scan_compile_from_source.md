# AST graph: scripts/scan_compile_from_source.py

This file is generated from `scripts/scan_compile_from_source.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## scan_line(...)

```mermaid
flowchart TD
    N001["scan_line(...)"]
    N002["if _COMMENT_LINE.match(line)"]
    N003["return False"]
    N004["if ACK_MARKER in line"]
    N005["return False"]
    N006["return _COMPILE_RE.search(line) is not None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## _iter_files(...)

```mermaid
flowchart TD
    N001["_iter_files(...)"]
    N002["for subdir in SCANNED_SUBDIRS:     base = repo_root / subdir     if not base.is_dir():         continue     for path in sorted(base.rglob('<str>')):         if path.is_file():             yield path"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## find_hits(...)

```mermaid
flowchart TD
    N001["find_hits(...)"]
    N002["hits = []"]
    N003["for path in _iter_files(repo_root):     try:         text = path.read_text(encoding='<str>')     except (OSError, UnicodeDecodeError):         continue     for lineno, line in enumerate(text.splitlines(), start=1):         if scan_line(line):             hits.append(f'{path.relative_to(repo_root)}<str>{lineno}')"]
    N004["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["hits = find_hits(...)"]
    N003["if hits"]
    N004["for hit in hits:     path, lineno = hit.rsplit('<str>', 1)     print(f'<str>{path}<str>{lineno}<str>{ACK_MARKER}<str>', file=sys.stderr)"]
    N005["print(...)"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 --> N006
    N003 -->|"false"| N007
    N007 --> N008
```

## _cmd_list(...)

```mermaid
flowchart TD
    N001["_cmd_list(...)"]
    N002["for hit in find_hits(REPO_ROOT):     print(hit)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["set_defaults(...)"]
    N005["set_defaults(...)"]
    N006["args = parse_args(...)"]
    N007["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```
