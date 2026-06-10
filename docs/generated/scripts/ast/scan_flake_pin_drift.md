# AST graph: scripts/scan_flake_pin_drift.py

This file is generated from `scripts/scan_flake_pin_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## sri_to_hex(...)

```mermaid
flowchart TD
    N001["sri_to_hex(...)"]
    N002["b64 = sri[len('<str>'):]"]
    N003["try"]
    N004["raw = b64decode(...)"]
    N005["except (binascii.Error, ValueError)"]
    N006["return None"]
    N007["if len(raw) != 32"]
    N008["return None"]
    N009["return raw.hex()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## flake_hashes(...)

```mermaid
flowchart TD
    N001["flake_hashes(...)"]
    N002["forbidden = set(...)"]
    N003["for sri in _SRI_RE.findall(flake_text):     hexd = sri_to_hex(sri)     if hexd is None:         continue     forbidden.add(sri)     forbidden.add(hexd)"]
    N004["return forbidden"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
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

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["if not forbidden"]
    N003["return []"]
    N004["errors = []"]
    N005["for path in _iter_files(repo_root):     try:         text = path.read_text(encoding='<str>')     except (OSError, UnicodeDecodeError):         continue     for lineno, line in enumerate(text.splitlines(), start=1):         if ACK_MARKER in line:             continue         for literal in forbidden:             if literal in line:                 rel = path.relative_to(repo_root)                 errors.append(f'<str>{rel}<str>{lineno}<str>{literal}<str>')                 break"]
    N006["return errors"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## _read_flake(...)

```mermaid
flowchart TD
    N001["_read_flake(...)"]
    N002["flake = repo_root / '<str>'"]
    N003["if not flake.is_file()"]
    N004["raise SystemExit(f'<str>{flake}')"]
    N005["return flake.read_text(encoding='<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["forbidden = flake_hashes(...)"]
    N003["errors = find_drift(...)"]
    N004["if errors"]
    N005["for err in errors:     print(err, file=sys.stderr)"]
    N006["print(...)"]
    N007["return 1"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N006 --> N007
    N004 -->|"false"| N008
    N008 --> N009
```

## _cmd_list(...)

```mermaid
flowchart TD
    N001["_cmd_list(...)"]
    N002["for literal in sorted(flake_hashes(_read_flake(REPO_ROOT))):     print(literal)"]
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
