# AST graph: scripts/verify_security_control_floor.py

This file is generated from `scripts/verify_security_control_floor.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["errors = []"]
    N003["floor = get(...)"]
    N004["if floor not in TIER_ORDER"]
    N005["append(...)"]
    N006["return errors"]
    N007["floor_rank = TIER_ORDER[floor]"]
    N008["families = get(...)"]
    N009["if not isinstance(families, dict) or not families"]
    N010["append(...)"]
    N011["return errors"]
    N012["for name, spec in families.items():     if not isinstance(spec, dict):         errors.append(f'<str>{name!r}<str>')         continue     tier = spec.get('<str>')     if tier not in TIER_ORDER:         errors.append(f'<str>{name!r}<str>{sorted(TIER_ORDER)}<str>{tier!r}')         continue     if TIER_ORDER[tier] < floor_rank:         reason = spec.get('<str>')         if not (isinstance(reason, str) and reason.strip()):             errors.append(f'<str>{name!r}<str>{tier!r}<str>{floor!r}<str>{floor}<str>')"]
    N013["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
```

## _load_config(...)

```mermaid
flowchart TD
    N001["_load_config(...)"]
    N002["with path.open('<str>') as handle:     return tomllib.load(handle)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["args = parse_args(...)"]
    N005["try"]
    N006["config = _load_config(...)"]
    N007["except (OSError, tomllib.TOMLDecodeError)"]
    N008["print(...)"]
    N009["return 1"]
    N010["errors = evaluate(...)"]
    N011["for message in errors:     print(f'<str>{message}', file=sys.stderr)"]
    N012["if errors"]
    N013["print(...)"]
    N014["return 1"]
    N015["print(...)"]
    N016["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N015
    N015 --> N016
```
