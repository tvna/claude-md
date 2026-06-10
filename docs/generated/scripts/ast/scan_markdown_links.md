# AST graph: scripts/scan_markdown_links.py

This file is generated from `scripts/scan_markdown_links.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

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

## iter_markdown_files(...)

```mermaid
flowchart TD
    N001["iter_markdown_files(...)"]
    N002["files = set(...)"]
    N003["for pattern in DOC_GLOBS:     files.update((path for path in root.glob(pattern) if path.is_file()))"]
    N004["return sorted(files)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
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

## iter_links(...)

```mermaid
flowchart TD
    N001["iter_links(...)"]
    N002["text = read_text(...)"]
    N003["links = []"]
    N004["for pattern in (INLINE_LINK_RE, REFERENCE_LINK_RE):     for match in pattern.finditer(text):         line = text.count('<str>', 0, match.start()) + 1         links.append(MarkdownLink(source=path, line=line, target=extract_target(match.group(1))))"]
    N005["return links"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## strip_inline_markdown(...)

```mermaid
flowchart TD
    N001["strip_inline_markdown(...)"]
    N002["text = sub(...)"]
    N003["text = sub(...)"]
    N004["text = sub(...)"]
    N005["text = strip(...)"]
    N006["return text"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## slugify_heading(...)

```mermaid
flowchart TD
    N001["slugify_heading(...)"]
    N002["text = lower(...)"]
    N003["chars = []"]
    N004["for char in unicodedata.normalize('<str>', text):     category = unicodedata.category(char)     if category[0] in {'<str>', '<str>'} or char in {'<str>', '<str>'}:         chars.append(char)"]
    N005["slug = strip(...)"]
    N006["slug = sub(...)"]
    N007["return slug"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## collect_anchors(...)

```mermaid
flowchart TD
    N001["collect_anchors(...)"]
    N002["anchors = set(...)"]
    N003["counts = {}"]
    N004["for line in path.read_text(encoding='<str>').splitlines():     match = HEADING_RE.match(line)     if not match:         continue     base = slugify_heading(match.group(2))     if not base:         continue     seen = counts.get(base, 0)     counts[base] = seen + 1     anchors.add(base if seen == 0 else f'{base}<str>{seen}')"]
    N005["return anchors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## should_skip_target(...)

```mermaid
flowchart TD
    N001["should_skip_target(...)"]
    N002["if not target or target in IGNORED_TARGETS"]
    N003["return True"]
    N004["parts = urlsplit(...)"]
    N005["return parts.scheme in IGNORED_SCHEMES or target.startswith('<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## resolve_link(...)

```mermaid
flowchart TD
    N001["resolve_link(...)"]
    N002["parts = urlsplit(...)"]
    N003["raw_path = unquote(...)"]
    N004["fragment = unquote(...)"]
    N005["if raw_path in {'', '.'}"]
    N006["return (link.source, fragment)"]
    N007["if Path(raw_path).is_absolute()"]
    N008["target_path = root / raw_path.lstrip('<str>')"]
    N009["target_path = link.source.parent / raw_path"]
    N010["return (target_path.resolve(), fragment)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N008 --> N010
    N009 --> N010
```

## verify_link(...)

```mermaid
flowchart TD
    N001["verify_link(...)"]
    N002["if should_skip_target(link.target)"]
    N003["return None"]
    N004["(target_path, fragment) = resolve_link(...)"]
    N005["if root.resolve() not in (target_path, *target_path.parents)"]
    N006["return f'{rel(link.source, root)}<str>{link.line}<str>{link.target}'"]
    N007["if not target_path.exists()"]
    N008["return f'{rel(link.source, root)}<str>{link.line}<str>{link.target}'"]
    N009["if not fragment"]
    N010["return None"]
    N011["if LINE_FRAGMENT_RE.match(fragment)"]
    N012["return None"]
    N013["if target_path.suffix.lower() != '.md'"]
    N014["return f'{rel(link.source, root)}<str>{link.line}<str>{link.target}'"]
    N015["anchors = collect_anchors(...)"]
    N016["if fragment.lower() not in anchors"]
    N017["return f'{rel(link.source, root)}<str>{link.line}<str>{link.target}'"]
    N018["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["errors = []"]
    N003["for path in iter_markdown_files(root):     for link in iter_links(path):         error = verify_link(link, root)         if error is not None:             errors.append(error)"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["root = resolve(...)"]
    N003["errors = verify(...)"]
    N004["for error in errors:     print(f'<str>{error}', file=sys.stderr)"]
    N005["if errors"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
```

## build_parser(...)

```mermaid
flowchart TD
    N001["build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["subparsers = add_subparsers(...)"]
    N005["verify_parser = add_parser(...)"]
    N006["set_defaults(...)"]
    N007["return parser"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
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
