# AST graph: scripts/scan_docs_inventory.py

This file is generated from `scripts/scan_docs_inventory.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## rel(...)

```mermaid
flowchart TD
    N001["rel(...)"]
    N002["try"]
    N003["return path.relative_to(root).as_posix()"]
    N004["except ValueError"]
    N005["return path.as_posix()"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## extract_target(...)

```mermaid
flowchart TD
    N001["extract_target(...)"]
    N002["target = strip(...)"]
    N003["if target.startswith('<') and '>' in target"]
    N004["return target[1:target.index('<str>')]"]
    N005["if ' ' in target"]
    N006["return target.split('<str>', 1)[0]"]
    N007["return target"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## iter_docs_markdown(...)

```mermaid
flowchart TD
    N001["iter_docs_markdown(...)"]
    N002["docs = root / '<str>'"]
    N003["if not docs.exists()"]
    N004["return []"]
    N005["return sorted((path for path in docs.rglob('<str>') if path.is_file()))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## collect_index_entries(...)

```mermaid
flowchart TD
    N001["collect_index_entries(...)"]
    N002["index = root / INDEX_PATH"]
    N003["if not index.exists()"]
    N004["return set()"]
    N005["text = read_text(...)"]
    N006["entries = set(...)"]
    N007["for pattern in (INLINE_LINK_RE, REFERENCE_LINK_RE):     for match in pattern.finditer(text):         target = extract_target(match.group(1))         parts = urlsplit(target)         if parts.scheme in IGNORED_SCHEMES or target.startswith('<str>'):             continue         raw_path = unquote(parts.path)         if not raw_path or raw_path == '<str>':             continue         if Path(raw_path).is_absolute():             resolved = root / raw_path.lstrip('<str>')         else:             resolved = index.parent / raw_path         if resolved.suffix.lower() == '<str>':             entries.add(rel(resolved.resolve(), root.resolve()))"]
    N008["return entries"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["root = resolve(...)"]
    N003["errors = []"]
    N004["index_entries = collect_index_entries(...)"]
    N005["for path in iter_docs_markdown(root):     relative = rel(path, root)     if any((relative.startswith(prefix) for prefix in EXEMPT_INVENTORY_PREFIXES)):         continue     if path.parent == root / '<str>' and relative not in ALLOWED_TOP_LEVEL_DOCS:         errors.append(f'<str>{relative}<str>')     if relative == INDEX_PATH.as_posix():         continue     if relative not in index_entries:         errors.append(f'<str>{INDEX_PATH.as_posix()}<str>{relative}')"]
    N006["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["subparsers = add_subparsers(...)"]
    N004["add_parser(...)"]
    N005["args = parse_args(...)"]
    N006["if args.command == 'verify'"]
    N007["errors = verify(...)"]
    N008["for error in errors:     print(error, file=sys.stderr)"]
    N009["return 1 if errors else 0"]
    N010["error(...)"]
    N011["return 2"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 --> N009
    N006 -->|"false"| N010
    N010 --> N011
```
