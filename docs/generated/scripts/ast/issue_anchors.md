# AST graph: scripts/issue_anchors.py

This file is generated from `scripts/issue_anchors.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## load_anchors(...)

```mermaid
flowchart TD
    N001["load_anchors(...)"]
    N002["data = loads(...)"]
    N003["if data.get('schema_version') != 1"]
    N004["raise ValueError(f'{config_path}<str>{data.get('<str>')!r}')"]
    N005["raw_anchors = get(...)"]
    N006["if not isinstance(raw_anchors, list) or not raw_anchors"]
    N007["raise ValueError(f'{config_path}<str>')"]
    N008["anchors = {}"]
    N009["for entry in raw_anchors:     if not isinstance(entry, dict):         raise ValueError(f'{config_path}<str>{entry!r}')     key = entry.get('<str>')     if not isinstance(key, str) or not _KEY_PATTERN.match(key):         raise ValueError(f'{config_path}<str>{_KEY_PATTERN.pattern}<str>{key!r}')     if key in anchors:         raise ValueError(f'{config_path}<str>{key!r}')     issue = entry.get('<str>')     if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:         raise ValueError(f'{config_path}<str>{key!r}<str>{issue!r}')     consumers = entry.get('<str>')     if not isinstance(consumers, list) or not consumers or (not all((isinstance(c, str) for c in consumers))):         raise ValueError(f'{config_path}<str>{key!r}<str>')     anchors[key] = issue"]
    N010["return anchors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
```

## resolve(...)

```mermaid
flowchart TD
    N001["resolve(...)"]
    N002["anchors = load_anchors(...)"]
    N003["if key not in anchors"]
    N004["raise ValueError(f'{config_path}<str>{key!r}<str>{'<str>'.join(sorted(anchors))}')"]
    N005["return anchors[key]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## substitute(...)

```mermaid
flowchart TD
    N001["substitute(...)"]
    N002["anchors = load_anchors(...)"]
    N003["def _replace(match: re.Match[str]) -> str:     key = match.group(1)     if key not in anchors:         raise ValueError(f'<str>{key!r}<str>{match.group(0)!r}<str>{'<str>'.join(sorted(anchors))}')     return str(anchors[key])"]
    N004["return ANCHOR_TOKEN.sub(_replace, text)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _cmd_get(...)

```mermaid
flowchart TD
    N001["_cmd_get(...)"]
    N002["print(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_render(...)

```mermaid
flowchart TD
    N001["_cmd_render(...)"]
    N002["path = Path(...)"]
    N003["rendered = substitute(...)"]
    N004["write_text(...)"]
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
    N003["sub = add_subparsers(...)"]
    N004["p_get = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["p_render = add_parser(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["set_defaults(...)"]
    N012["args = parse_args(...)"]
    N013["try"]
    N014["return int(args.func(args))"]
    N015["except (ValueError, OSError, tomllib.TOMLDecodeError)"]
    N016["print(...)"]
    N017["return 1"]
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
    N012 --> N013
    N013 -->|"try"| N014
    N013 -->|"raises"| N015
    N015 --> N016
    N016 --> N017
```
