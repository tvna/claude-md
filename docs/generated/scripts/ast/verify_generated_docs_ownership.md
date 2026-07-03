# AST graph: scripts/verify_generated_docs_ownership.py

This file is generated from `scripts/verify_generated_docs_ownership.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## pattern_matches(...)

```mermaid
flowchart TD
    N001["pattern_matches(...)"]
    N002["pattern_parts = PurePosixPath(pattern).parts"]
    N003["path_parts = rel_path.parts"]
    N004["if len(pattern_parts) != len(path_parts)"]
    N005["return False"]
    N006["return all((fnmatchcase(part, pattern_part) for part, pattern_part in zip(path_parts, pattern_parts, strict=True)))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## owner_for(...)

```mermaid
flowchart TD
    N001["owner_for(...)"]
    N002["for surface in OWNERSHIP:     if pattern_matches(surface.pattern, rel_path):         return surface"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## iter_generated_files(...)

```mermaid
flowchart TD
    N001["iter_generated_files(...)"]
    N002["base = root / Path(GENERATED_ROOT)"]
    N003["if not base.is_dir()"]
    N004["return"]
    N005["for path in sorted(base.rglob('<str>')):     if path.is_file():         yield path"]
    N006["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## registry_errors(...)

```mermaid
flowchart TD
    N001["registry_errors(...)"]
    N002["errors = []"]
    N003["for surface in OWNERSHIP:     pattern = PurePosixPath(surface.pattern)     if pattern.is_absolute() or '<str>' in pattern.parts or (not surface.pattern):         errors.append(f'<str>{surface.pattern!r}<str>{GENERATED_ROOT}<str>')     if not (root / surface.producer).is_file():         errors.append(f'<str>{surface.producer!r}<str>{surface.pattern!r}<str>')"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## orphaned_files(...)

```mermaid
flowchart TD
    N001["orphaned_files(...)"]
    N002["base = root / Path(GENERATED_ROOT)"]
    N003["return [path for path in iter_generated_files(root) if owner_for(PurePosixPath(path.relative_to(base).as_posix())) is None]"]
    N001 -->|"start"| N002
    N002 --> N003
```

## retire_orphans(...)

```mermaid
flowchart TD
    N001["retire_orphans(...)"]
    N002["base = root / Path(GENERATED_ROOT)"]
    N003["orphans = orphaned_files(...)"]
    N004["for path in orphans:     path.unlink()"]
    N005["if base.is_dir()"]
    N006["for directory in sorted(base.rglob('<str>'), key=lambda p: len(p.parts), reverse=True):     if directory.is_dir() and (not any(directory.iterdir())):         directory.rmdir()"]
    N007["return orphans"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["errors = registry_errors(...)"]
    N003["for error in errors:     print(f'<str>{error}', file=sys.stderr)"]
    N004["if errors"]
    N005["return 1"]
    N006["print(...)"]
    N007["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```

## _cmd_list(...)

```mermaid
flowchart TD
    N001["_cmd_list(...)"]
    N002["root = Path(...)"]
    N003["base = root / Path(GENERATED_ROOT)"]
    N004["for path in iter_generated_files(root):     rel = PurePosixPath(path.relative_to(base).as_posix())     surface = owner_for(rel)     owner = surface.producer if surface is not None else '<str>'     print(f'{GENERATED_ROOT / rel}<str>{owner}')"]
    N005["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _cmd_retire(...)

```mermaid
flowchart TD
    N001["_cmd_retire(...)"]
    N002["root = Path(...)"]
    N003["retired = retire_orphans(...)"]
    N004["for path in retired:     print(f'<str>{path.relative_to(root)}')"]
    N005["print(...)"]
    N006["return 0"]
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
    N004["p_verify = add_parser(...)"]
    N005["set_defaults(...)"]
    N006["p_list = add_parser(...)"]
    N007["set_defaults(...)"]
    N008["p_retire = add_parser(...)"]
    N009["set_defaults(...)"]
    N010["for sub in (p_verify, p_list, p_retire):     sub.add_argument('<str>', default=str(REPO_ROOT), help='<str>')"]
    N011["args = parse_args(...)"]
    N012["return int(args.func(args))"]
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
```
