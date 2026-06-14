# AST graph: scripts/python_pin.py

This file is generated from `scripts/python_pin.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## read_pin(...)

```mermaid
flowchart TD
    N001["read_pin(...)"]
    N002["try"]
    N003["raw = read_text(...)"]
    N004["except FileNotFoundError"]
    N005["raise ValueError(f'<str>{python_version_path}<str>{exc}')"]
    N006["lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]"]
    N007["if not lines"]
    N008["raise ValueError(f'{python_version_path}<str>')"]
    N009["if len(lines) > 1"]
    N010["raise ValueError(f'{python_version_path}<str>{len(lines)}<str>')"]
    N011["pin = lines[0]"]
    N012["if not _EXACT_PATCH.match(pin)"]
    N013["raise ValueError(f'{python_version_path}<str>{pin!r}')"]
    N014["return pin"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
```

## requires_python_floor(...)

```mermaid
flowchart TD
    N001["requires_python_floor(...)"]
    N002["try"]
    N003["with pyproject_path.open('<str>') as fp:     data = tomllib.load(fp)"]
    N004["except FileNotFoundError"]
    N005["raise ValueError(f'<str>{pyproject_path}<str>{exc}')"]
    N006["except tomllib.TOMLDecodeError"]
    N007["raise ValueError(f'<str>{pyproject_path}<str>{exc}')"]
    N008["try"]
    N009["spec = data['<str>']['<str>']"]
    N010["except (KeyError, TypeError)"]
    N011["raise ValueError(f'<str>{pyproject_path}')"]
    N012["match = search(...)"]
    N013["if not match"]
    N014["raise ValueError(f'<str>{spec!r}')"]
    N015["return (int(match.group(1)), int(match.group(2)))"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N002 -->|"raises"| N006
    N006 --> N007
    N003 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N009 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
```

## find_inconsistencies(...)

```mermaid
flowchart TD
    N001["find_inconsistencies(...)"]
    N002["errors = []"]
    N003["pyproject = repo_root / '<str>'"]
    N004["(floor_major, floor_minor) = requires_python_floor(...)"]
    N005["expected = f'{floor_major}<str>{floor_minor}'"]
    N006["pin_match = match(...)"]
    N007["if pin_match and (pin_match.group(1), pin_match.group(2)) != (str(floor_major), str(floor_minor))"]
    N008["append(...)"]
    N009["with pyproject.open('<str>') as fp:     data = tomllib.load(fp)"]
    N010["ruff_target = get(...)"]
    N011["if ruff_target is not None and ruff_target != f'py{floor_major}{floor_minor}'"]
    N012["append(...)"]
    N013["mypy_version = get(...)"]
    N014["if mypy_version is not None and mypy_version != expected"]
    N015["append(...)"]
    N016["flake = repo_root / '<str>'"]
    N017["if flake.exists()"]
    N018["for minor in set(_FLAKE_PYTHON.findall(flake.read_text(encoding='<str>'))):     if int(minor) != floor_minor:         errors.append(f'<str>{minor}<str>{floor_minor}<str>')"]
    N019["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N016
    N016 --> N017
    N017 -->|"true"| N018
    N018 --> N019
    N017 -->|"false"| N019
```

## _cmd_read(...)

```mermaid
flowchart TD
    N001["_cmd_read(...)"]
    N002["print(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["pin = read_pin(...)"]
    N004["print(...)"]
    N005["errors = find_inconsistencies(...)"]
    N006["for err in errors:     print(f'<str>{err}')"]
    N007["if errors"]
    N008["print(...)"]
    N009["return 1"]
    N010["print(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_read = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["p_verify = add_parser(...)"]
    N008["add_argument(...)"]
    N009["set_defaults(...)"]
    N010["args = parse_args(...)"]
    N011["try"]
    N012["return args.func(args)"]
    N013["except ValueError"]
    N014["print(...)"]
    N015["return 1"]
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
    N011 -->|"try"| N012
    N011 -->|"raises"| N013
    N013 --> N014
    N014 --> N015
```
