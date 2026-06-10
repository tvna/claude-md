# AST graph: scripts/nixpkgs_cooldown.py

This file is generated from `scripts/nixpkgs_cooldown.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## read_uv_cooldown_days(...)

```mermaid
flowchart TD
    N001["read_uv_cooldown_days(...)"]
    N002["try"]
    N003["with pyproject_path.open('<str>') as fp:
    data = tomllib.load(fp)"]
    N004["except FileNotFoundError"]
    N005["raise ValueError(f'<str>{pyproject_path}<str>{exc}')"]
    N006["except tomllib.TOMLDecodeError"]
    N007["raise ValueError(f'<str>{pyproject_path}<str>{exc}')"]
    N008["try"]
    N009["raw = data['<str>']['<str>']['<str>']"]
    N010["except (KeyError, TypeError)"]
    N011["raise ValueError(f'<str>{pyproject_path}')"]
    N012["if not isinstance(raw, str)"]
    N013["raise ValueError(f'<str>{raw!r}')"]
    N014["match = fullmatch(...)"]
    N015["if match is None"]
    N016["raise ValueError(f'<str>{raw!r}')"]
    N017["return int(match.group('<str>'))"]
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
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
```

## read_nixpkgs_last_modified(...)

```mermaid
flowchart TD
    N001["read_nixpkgs_last_modified(...)"]
    N002["try"]
    N003["data = loads(...)"]
    N004["except FileNotFoundError"]
    N005["raise ValueError(f'<str>{flake_lock_path}<str>{exc}')"]
    N006["except json.JSONDecodeError"]
    N007["raise ValueError(f'<str>{flake_lock_path}<str>{exc}')"]
    N008["try"]
    N009["last_modified = data['<str>']['<str>']['<str>']['<str>']"]
    N010["except (KeyError, TypeError)"]
    N011["raise ValueError(f'<str>{flake_lock_path}')"]
    N012["if not isinstance(last_modified, int) or last_modified <= 0"]
    N013["raise ValueError(f'<str>{last_modified!r}')"]
    N014["return last_modified"]
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
    N012 -->|"true"| N013
    N012 -->|"false"| N014
```

## verify_cooldown(...)

```mermaid
flowchart TD
    N001["verify_cooldown(...)"]
    N002["cooldown_days = read_uv_cooldown_days(...)"]
    N003["last_modified = read_nixpkgs_last_modified(...)"]
    N004["now = int(time.time()) if now_epoch is None else now_epoch"]
    N005["minimum_age_seconds = cooldown_days * 24 * 60 * 60"]
    N006["actual_age_seconds = now - last_modified"]
    N007["if actual_age_seconds < minimum_age_seconds"]
    N008["actual_days = max(0, actual_age_seconds) / (24 * 60 * 60)"]
    N009["return [f'<str>{cooldown_days}<str>{actual_days:<str>}<str>']"]
    N010["return []"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["errors = verify_cooldown(...)"]
    N004["for err in errors:
    print(f'<str>{err}')"]
    N005["if errors"]
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

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["args = parse_args(...)"]
    N009["try"]
    N010["return args.func(args)"]
    N011["except ValueError"]
    N012["print(...)"]
    N013["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"try"| N010
    N009 -->|"raises"| N011
    N011 --> N012
    N012 --> N013
```
