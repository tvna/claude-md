# AST graph: scripts/scan_gitapex_schema.py

This file is generated from `scripts/scan_gitapex_schema.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## discover_toml_files(...)

```mermaid
flowchart TD
    N001["discover_toml_files(...)"]
    N002["return sorted(gitapex_dir.rglob('<str>'))"]
    N001 -->|"start"| N002
```

## verify_file(...)

```mermaid
flowchart TD
    N001["verify_file(...)"]
    N002["schema_path = with_suffix(...)"]
    N003["if not schema_path.exists()"]
    N004["return [f'{display}<str>{schema_path.name!r}<str>']"]
    N005["try"]
    N006["instance = loads(...)"]
    N007["except (OSError, tomllib.TOMLDecodeError)"]
    N008["return [f'{display}<str>{exc}']"]
    N009["try"]
    N010["schema = loads(...)"]
    N011["except (OSError, ValueError)"]
    N012["return [f'{schema_path.name}<str>{exc}']"]
    N013["if not isinstance(schema, dict)"]
    N014["raise SchemaError(f'{schema_path.name}<str>')"]
    N015["return [f'{display}<str>{message}' for message in validate_shape(instance, schema, root_path=toml_path.name)]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N009 -->|"try"| N010
    N009 -->|"raises"| N011
    N011 --> N012
    N010 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["gitapex_dir = _REPO_ROOT / args.gitapex_dir"]
    N003["if not gitapex_dir.is_dir()"]
    N004["print(...)"]
    N005["return 1"]
    N006["toml_files = discover_toml_files(...)"]
    N007["errors = []"]
    N008["for toml_path in toml_files:     try:         rel = toml_path.relative_to(gitapex_dir).as_posix()         errors.extend(verify_file(toml_path, display=f'{args.gitapex_dir}<str>{rel}'))     except SchemaError as exc:         errors.append(str(exc))"]
    N009["if errors"]
    N010["for message in errors:     print(f'<str>{_SCRIPT}<str>{message}', file=sys.stderr)"]
    N011["return 1"]
    N012["print(...)"]
    N013["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["if argv is None"]
    N003["argv = sys.argv[1:]"]
    N004["command = argv[0] if argv else None"]
    N005["if command != 'verify'"]
    N006["print(...)"]
    N007["return 64"]
    N008["parser = ArgumentParser(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["args = parse_args(...)"]
    N012["return cmd_verify(args)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
```
