# AST graph: scripts/flake_pin_latest.py

This file is generated from `scripts/flake_pin_latest.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _load(...)

```mermaid
flowchart TD
    N001["_load(...)"]
    N002["spec = spec_from_file_location(...)"]
    N003["if spec is None or spec.loader is None"]
    N004["raise ImportError(f'<str>{module_name}<str>')"]
    N005["module = module_from_spec(...)"]
    N006["sys.modules[module_name] = module"]
    N007["exec_module(...)"]
    N008["return module"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## github_latest_release(...)

```mermaid
flowchart TD
    N001["github_latest_release(...)"]
    N002["token = os.environ.get('<str>') or os.environ.get('<str>') or '<str>'"]
    N003["url = f'<str>{repo}<str>'"]
    N004["(code, body) = apply_call(...)"]
    N005["if not 200 <= code < 300"]
    N006["raise LatestPinError(f'<str>{code or '<str>'}<str>{repo}<str>')"]
    N007["try"]
    N008["payload = loads(...)"]
    N009["except json.JSONDecodeError"]
    N010["raise LatestPinError(f'<str>{repo}<str>{exc}')"]
    N011["if not isinstance(payload, dict)"]
    N012["raise LatestPinError(f'<str>{repo}<str>{body[:80]!r}')"]
    N013["return payload"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```

## _version_tuple(...)

```mermaid
flowchart TD
    N001["_version_tuple(...)"]
    N002["bare = lstrip(...)"]
    N003["parts = split(...)"]
    N004["try"]
    N005["return tuple((int(p) for p in parts))"]
    N006["except ValueError"]
    N007["raise LatestPinError(f'<str>{version!r}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
```

## _parse_release(...)

```mermaid
flowchart TD
    N001["_parse_release(...)"]
    N002["tag = get(...)"]
    N003["if not isinstance(tag, str) or not tag"]
    N004["raise LatestPinError(f'<str>{repo}<str>')"]
    N005["published = get(...)"]
    N006["if not isinstance(published, str) or not published"]
    N007["raise LatestPinError(f'<str>{repo}<str>')"]
    N008["try"]
    N009["when = fromisoformat(...)"]
    N010["except ValueError"]
    N011["raise LatestPinError(f'<str>{repo}<str>{published!r}')"]
    N012["if when.tzinfo is None"]
    N013["when = replace(...)"]
    N014["return (tag.lstrip('<str>'), when)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N009 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N014
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if now is None"]
    N003["now = now(...)"]
    N004["if cooldown_days < 0"]
    N005["raise LatestPinError(f'<str>{cooldown_days}')"]
    N006["spec = tool_spec(...)"]
    N007["pinned = current_version(...)"]
    N008["(latest, published) = _parse_release(...)"]
    N009["if _version_tuple(latest) <= _version_tuple(pinned)"]
    N010["return None"]
    N011["age = now - published"]
    N012["if age < dt.timedelta(days=cooldown_days)"]
    N013["return None"]
    N014["return latest"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
```

## _cmd_check(...)

```mermaid
flowchart TD
    N001["_cmd_check(...)"]
    N002["cooldown_days = read_uv_cooldown_days(...)"]
    N003["target = decide(...)"]
    N004["if target is not None"]
    N005["print(...)"]
    N006["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_check = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["args = parse_args(...)"]
    N008["try"]
    N009["return args.func(args)"]
    N010["except (LatestPinError, flake_pin.FlakePinError, ValueError)"]
    N011["print(...)"]
    N012["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
```
