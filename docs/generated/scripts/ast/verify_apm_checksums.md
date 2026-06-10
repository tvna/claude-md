# AST graph: scripts/verify_apm_checksums.py

This file is generated from `scripts/verify_apm_checksums.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _display(...)

```mermaid
flowchart TD
    N001["_display(...)"]
    N002["return path.as_posix()"]
    N001 -->|"start"| N002
```

## _repo_path(...)

```mermaid
flowchart TD
    N001["_repo_path(...)"]
    N002["return root / rel"]
    N001 -->|"start"| N002
```

## _iter_apm_files(...)

```mermaid
flowchart TD
    N001["_iter_apm_files(...)"]
    N002["apm_dir = _repo_path(...)"]
    N003["if not apm_dir.is_dir()"]
    N004["raise FileNotFoundError(f'<str>{_display(APM_DIR_REL)}')"]
    N005["files = []"]
    N006["for path in apm_dir.rglob('<str>'):     if not path.is_file():         continue     rel = path.relative_to(root)     if rel == LOCKFILE_REL:         continue     files.append(rel)"]
    N007["return sorted(files, key=_display)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## _sha256(...)

```mermaid
flowchart TD
    N001["_sha256(...)"]
    N002["digest = sha256(...)"]
    N003["with path.open('<str>') as handle:     for chunk in iter(lambda: handle.read(1024 * 1024), b''):         digest.update(chunk)"]
    N004["return digest.hexdigest()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## build_checksums(...)

```mermaid
flowchart TD
    N001["build_checksums(...)"]
    N002["return {rel: _sha256(_repo_path(root, rel)) for rel in _iter_apm_files(root)}"]
    N001 -->|"start"| N002
```

## format_checksums(...)

```mermaid
flowchart TD
    N001["format_checksums(...)"]
    N002["lines = [f'{digest}<str>{_display(path)}' for path, digest in sorted(checksums.items(), key=lambda item: _display(item[0]))]"]
    N003["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## parse_lockfile(...)

```mermaid
flowchart TD
    N001["parse_lockfile(...)"]
    N002["rows = {}"]
    N003["errors = []"]
    N004["for lineno, raw_line in enumerate(text.splitlines(), start=1):     if not raw_line.strip():         continue     parts = raw_line.split()     if len(parts) != 2:         errors.append(f'<str>{lineno}<str>')         continue     digest, path_text = parts     rel = Path(path_text)     if len(digest) != HASH_LEN or any((ch not in '<str>' for ch in digest)):         errors.append(f'<str>{lineno}<str>')     if rel.is_absolute() or '<str>' in rel.parts or rel.parts[:1] != ('<str>',):         errors.append(f'<str>{lineno}<str>')     if rel == LOCKFILE_REL:         errors.append(f'<str>{lineno}<str>')     if rel in rows:         errors.append(f'<str>{lineno}<str>{_display(rel)}')     rows[rel] = digest"]
    N005["return (rows, errors)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _read_lockfile(...)

```mermaid
flowchart TD
    N001["_read_lockfile(...)"]
    N002["lockfile = _repo_path(...)"]
    N003["if not lockfile.exists()"]
    N004["return ({}, [f'<str>{_display(LOCKFILE_REL)}'])"]
    N005["return parse_lockfile(lockfile.read_text(encoding='<str>'))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["(expected, errors) = _read_lockfile(...)"]
    N003["if errors"]
    N004["return errors"]
    N005["actual = build_checksums(...)"]
    N006["actual_paths = set(...)"]
    N007["expected_paths = set(...)"]
    N008["problems = []"]
    N009["for rel in sorted(expected_paths - actual_paths, key=_display):     problems.append(f'<str>{_display(rel)}')"]
    N010["for rel in sorted(actual_paths - expected_paths, key=_display):     problems.append(f'<str>{_display(rel)}')"]
    N011["for rel in sorted(actual_paths & expected_paths, key=_display):     if actual[rel] != expected[rel]:         problems.append(f'<str>{_display(rel)}')"]
    N012["return problems"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
```

## update(...)

```mermaid
flowchart TD
    N001["update(...)"]
    N002["lockfile = _repo_path(...)"]
    N003["mkdir(...)"]
    N004["write_text(...)"]
    N005["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["root = resolve(...)"]
    N003["try"]
    N004["problems = verify(...)"]
    N005["except FileNotFoundError"]
    N006["problems = [str(exc)]"]
    N007["if problems"]
    N008["for problem in problems:     print(f'<str>{problem}', file=sys.stderr)"]
    N009["print(...)"]
    N010["return 1"]
    N011["print(...)"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N009 --> N010
    N007 -->|"false"| N011
    N011 --> N012
```

## _cmd_update(...)

```mermaid
flowchart TD
    N001["_cmd_update(...)"]
    N002["root = resolve(...)"]
    N003["try"]
    N004["update(...)"]
    N005["except FileNotFoundError"]
    N006["print(...)"]
    N007["return 1"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 --> N009
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["sub = add_subparsers(...)"]
    N005["p_verify = add_parser(...)"]
    N006["set_defaults(...)"]
    N007["p_update = add_parser(...)"]
    N008["set_defaults(...)"]
    N009["args = parse_args(...)"]
    N010["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
```
