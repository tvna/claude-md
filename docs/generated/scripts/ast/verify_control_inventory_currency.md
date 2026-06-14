# AST graph: scripts/verify_control_inventory_currency.py

This file is generated from `scripts/verify_control_inventory_currency.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## detect_privileged_surfaces(...)

```mermaid
flowchart TD
    N001["detect_privileged_surfaces(...)"]
    N002["detected = set(...)"]
    N003["workflows = root / WORKFLOWS_DIR"]
    N004["if workflows.is_dir()"]
    N005["for path in sorted((*workflows.glob('<str>'), *workflows.glob('<str>'))):     text = path.read_text(encoding='<str>')     secrets = {name for name in SECRET_REF_RE.findall(text) if name not in IGNORED_SECRETS}     if secrets or ENVIRONMENT_RE.search(text):         detected.add(path.relative_to(root).as_posix())"]
    N006["scripts = root / SCRIPTS_DIR"]
    N007["if scripts.is_dir()"]
    N008["for path in sorted(scripts.glob('<str>')):     text = path.read_text(encoding='<str>')     if SECRET_PATTERNS_IMPORT_RE.search(text):         detected.add(path.relative_to(root).as_posix())"]
    N009["return detected"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
```

## load_manifest(...)

```mermaid
flowchart TD
    N001["load_manifest(...)"]
    N002["errors = []"]
    N003["try"]
    N004["raw = loads(...)"]
    N005["except FileNotFoundError"]
    N006["return ([], [f'<str>{path.as_posix()}'])"]
    N007["except tomllib.TOMLDecodeError"]
    N008["return ([], [f'<str>{path.as_posix()}<str>{exc}'])"]
    N009["surfaces = []"]
    N010["for entry in raw.get('<str>', []):     surface_path = entry.get('<str>', '<str>')     status = entry.get('<str>', '<str>')     reason = entry.get('<str>', '<str>')     if not surface_path:         errors.append('<str>')         continue     if status not in VALID_STATUSES:         errors.append(f'<str>{surface_path!r}<str>{status!r}<str>{sorted(VALID_STATUSES)}')     surfaces.append(ManifestSurface(path=surface_path, status=status, reason=reason))"]
    N011["return (surfaces, errors)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N003 -->|"raises"| N007
    N007 --> N008
    N004 --> N009
    N009 --> N010
    N010 --> N011
```

## represented_in_inventory(...)

```mermaid
flowchart TD
    N001["represented_in_inventory(...)"]
    N002["basename = Path(surface_path).name"]
    N003["return f'<str>{basename}<str>' in inventory_text or f'<str>{surface_path}<str>' in inventory_text"]
    N001 -->|"start"| N002
    N002 --> N003
```

## cited_paths(...)

```mermaid
flowchart TD
    N001["cited_paths(...)"]
    N002["return {f'{SCRIPTS_DIR.as_posix()}<str>{match}' for match in CITED_SCRIPT_RE.findall(inventory_text)}"]
    N001 -->|"start"| N002
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["root = resolve(...)"]
    N003["errors = []"]
    N004["inventory_file = root / INVENTORY_PATH"]
    N005["if not inventory_file.exists()"]
    N006["return [f'<str>{INVENTORY_PATH.as_posix()}']"]
    N007["inventory_text = read_text(...)"]
    N008["(surfaces, manifest_errors) = load_manifest(...)"]
    N009["extend(...)"]
    N010["listed = {surface.path for surface in surfaces}"]
    N011["detected = detect_privileged_surfaces(...)"]
    N012["for surface_path in sorted(detected - listed):     errors.append(f'<str>{surface_path}<str>{MANIFEST_PATH.as_posix()}<str>')"]
    N013["for surface in surfaces:     if not (root / surface.path).exists():         errors.append(f'<str>{surface.path}<str>')         continue     if surface.status == '<str>' and (not represented_in_inventory(inventory_text, surface.path)):         errors.append(f'<str>{surface.path}<str>{INVENTORY_PATH.as_posix()}<str>')     if surface.status == '<str>' and (not surface.reason.strip()):         errors.append(f'<str>{surface.path}<str>')"]
    N014["for cited in sorted(cited_paths(inventory_text)):     if not (root / cited).exists():         errors.append(f'{INVENTORY_PATH.as_posix()}<str>{cited}<str>')"]
    N015["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["errors = verify(...)"]
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
