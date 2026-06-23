# AST graph: scripts/scan_doc_workflow_refs.py

This file is generated from `scripts/scan_doc_workflow_refs.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _is_excluded(...)

```mermaid
flowchart TD
    N001["_is_excluded(...)"]
    N002["return any((rel_posix.startswith(prefix) for prefix in EXCLUDED_DIRS))"]
    N001 -->|"start"| N002
```

## iter_markdown(...)

```mermaid
flowchart TD
    N001["iter_markdown(...)"]
    N002["for path in sorted(repo_root.rglob('<str>')):     if '<str>' in path.parts:         continue     rel = path.relative_to(repo_root).as_posix()     if _is_excluded(rel):         continue     yield path"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## find_refs(...)

```mermaid
flowchart TD
    N001["find_refs(...)"]
    N002["refs = []"]
    N003["for path in iter_markdown(repo_root):     rel = path.relative_to(repo_root).as_posix()     try:         text = path.read_text(encoding='<str>')     except (OSError, UnicodeDecodeError):         continue     for lineno, line in enumerate(text.splitlines(), start=1):         if ACK_MARKER in line:             continue         for match in _WORKFLOW_REF_RE.finditer(line):             refs.append(WorkflowRef(doc=rel, line=lineno, name=match.group(1)))"]
    N004["return refs"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## stale_refs(...)

```mermaid
flowchart TD
    N001["stale_refs(...)"]
    N002["workflows = repo_root / '<str>' / '<str>'"]
    N003["return [ref for ref in refs if not (workflows / ref.name).is_file()]"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["refs = find_refs(...)"]
    N003["stale = stale_refs(...)"]
    N004["for ref in stale:     print(f'<str>{ref.doc}<str>{ref.line}<str>{ref.name}<str>', file=sys.stderr)"]
    N005["if stale"]
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

## _cmd_list(...)

```mermaid
flowchart TD
    N001["_cmd_list(...)"]
    N002["for ref in find_refs(REPO_ROOT):     print(f'{ref.doc}<str>{ref.line}<str>{ref.name}')"]
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
