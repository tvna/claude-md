# AST graph: scripts/scan_mermaid_syntax.py

This file is generated from `scripts/scan_mermaid_syntax.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

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

## is_exempt(...)

```mermaid
flowchart TD
    N001["is_exempt(...)"]
    N002["return any((relative.startswith(prefix) for prefix in EXEMPT_PREFIXES))"]
    N001 -->|"start"| N002
```

## iter_docs_markdown(...)

```mermaid
flowchart TD
    N001["iter_docs_markdown(...)"]
    N002["docs = root / '<str>'"]
    N003["if not docs.exists()"]
    N004["return []"]
    N005["files = []"]
    N006["for path in sorted(docs.rglob('<str>')):
    if not path.is_file():
        continue
    if is_exempt(rel(path, root)):
        continue
    files.append(path)"]
    N007["return files"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## _fence_marker(...)

```mermaid
flowchart TD
    N001["_fence_marker(...)"]
    N002["for marker in ('<str>', '<str>'):
    if stripped.startswith(marker):
        return marker"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## extract_blocks(...)

```mermaid
flowchart TD
    N001["extract_blocks(...)"]
    N002["lines = splitlines(...)"]
    N003["blocks = []"]
    N004["index = 0"]
    N005["total = len(...)"]
    N006["while index < total:
    line = lines[index]
    stripped = line.strip()
    marker = _fence_marker(stripped)
    if marker is None or stripped[len(marker):].strip() != _FENCE_INFO:
        index += 1
        continue
    fence_line = index + 1
    indent = len(line) - len(line.lstrip())
    body: list[str] = []
    index += 1
    while index < total:
        current = lines[index]
        if current.strip() == marker:
            index += 1
            break
        if indent and current[:indent].strip() == '<str>':
            body.append(current[indent:])
        else:
            body.append(current)
        index += 1
    blocks.append(MermaidBlock(source=source, line=fence_line, text='<str>'.join(body)))"]
    N007["return blocks"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## collect_blocks(...)

```mermaid
flowchart TD
    N001["collect_blocks(...)"]
    N002["blocks = []"]
    N003["for path in iter_docs_markdown(root):
    blocks.extend(extract_blocks(path, path.read_text(encoding='<str>')))"]
    N004["return blocks"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## format_error(...)

```mermaid
flowchart TD
    N001["format_error(...)"]
    N002["location = rel(...)"]
    N003["return f'<str>{location}<str>{block.line}<str>{message}'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## run_parser(...)

```mermaid
flowchart TD
    N001["run_parser(...)"]
    N002["payload = [{'<str>': f'{block.source}<str>{block.line}', '<str>': block.text} for block in blocks]"]
    N003["proc = run(...)"]
    N004["if proc.returncode != 0"]
    N005["raise RuntimeError(f'<str>{proc.returncode}<str>{proc.stderr.strip() or proc.stdout.strip()}')"]
    N006["try"]
    N007["return json.loads(proc.stdout)"]
    N008["except json.JSONDecodeError"]
    N009["raise RuntimeError(f'<str>{exc}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
```

## diagnostics(...)

```mermaid
flowchart TD
    N001["diagnostics(...)"]
    N002["by_id = {f'{block.source}<str>{block.line}': block for block in blocks}"]
    N003["errors = []"]
    N004["for result in results:
    if result.get('<str>'):
        continue
    block = by_id.get(result.get('<str>', '<str>'))
    if block is None:
        continue
    errors.append(format_error(block, result.get('<str>') or '<str>', root))"]
    N005["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["blocks = collect_blocks(...)"]
    N003["if not blocks"]
    N004["return []"]
    N005["results = run_parser(...)"]
    N006["return diagnostics(blocks, results, root)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## resolve_bun(...)

```mermaid
flowchart TD
    N001["resolve_bun(...)"]
    N002["return shutil.which('<str>')"]
    N001 -->|"start"| N002
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["root = resolve(...)"]
    N003["bun = args.bun or resolve_bun()"]
    N004["if not bun"]
    N005["print(...)"]
    N006["return 1"]
    N007["try"]
    N008["errors = verify(...)"]
    N009["except RuntimeError"]
    N010["print(...)"]
    N011["return 1"]
    N012["for error in errors:
    print(error, file=sys.stderr)"]
    N013["if errors"]
    N014["print(...)"]
    N015["return 1"]
    N016["print(...)"]
    N017["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N010 --> N011
    N008 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
    N016 --> N017
```

## build_parser(...)

```mermaid
flowchart TD
    N001["build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["subparsers = add_subparsers(...)"]
    N006["verify_parser = add_parser(...)"]
    N007["set_defaults(...)"]
    N008["return parser"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = build_parser(...)"]
    N003["args = parse_args(...)"]
    N004["return int(args.func(args))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
