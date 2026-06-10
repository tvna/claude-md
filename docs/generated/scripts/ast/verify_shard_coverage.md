# AST graph: scripts/verify_shard_coverage.py

This file is generated from `scripts/verify_shard_coverage.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## parse_collected(...)

```mermaid
flowchart TD
    N001["parse_collected(...)"]
    N002["nodes = set(...)"]
    N003["for raw in text.splitlines():     line = raw.strip()     if not line or '<str>' not in line:         continue     nodes.add(line)"]
    N004["return nodes"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _classname_to_path_and_class(...)

```mermaid
flowchart TD
    N001["_classname_to_path_and_class(...)"]
    N002["parts = split(...)"]
    N003["if len(parts) < 2"]
    N004["return (classname, '<str>')"]
    N005["file_path = f'{parts[0]}<str>{parts[1]}<str>'"]
    N006["klass = join(...)"]
    N007["return (file_path, klass)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## junit_node_id(...)

```mermaid
flowchart TD
    N001["junit_node_id(...)"]
    N002["(file_path, klass) = _classname_to_path_and_class(...)"]
    N003["if klass"]
    N004["return f'{file_path}<str>{klass}<str>{name}'"]
    N005["return f'{file_path}<str>{name}'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## parse_junit(...)

```mermaid
flowchart TD
    N001["parse_junit(...)"]
    N002["root = fromstring(...)"]
    N003["nodes = set(...)"]
    N004["for case in root.iter('<str>'):     classname = case.get('<str>') or '<str>'     name = case.get('<str>') or '<str>'     if not classname and (not name):         continue     nodes.add(junit_node_id(classname, name))"]
    N005["return nodes"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## compare(...)

```mermaid
flowchart TD
    N001["compare(...)"]
    N002["seen_in = defaultdict(...)"]
    N003["for shard, nodes in per_shard.items():     for node in nodes:         seen_in[node].append(shard)"]
    N004["union = set(...)"]
    N005["missing = collected - union"]
    N006["duplicated = {n: shards for n, shards in seen_in.items() if len(shards) > 1}"]
    N007["return (missing, duplicated)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## format_errors(...)

```mermaid
flowchart TD
    N001["format_errors(...)"]
    N002["lines = []"]
    N003["for node in sorted(missing):     lines.append(f'<str>{node}<str>')"]
    N004["for node in sorted(duplicated):     shards = '<str>'.join(duplicated[node])     lines.append(f'<str>{node}<str>{shards}<str>')"]
    N005["for node in sorted(extra):     lines.append(f'<str>{node}<str>')"]
    N006["return lines"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["if not junit_paths"]
    N003["print(...)"]
    N004["return 1"]
    N005["try"]
    N006["collected = parse_collected(...)"]
    N007["except OSError"]
    N008["print(...)"]
    N009["return 1"]
    N010["per_shard = {}"]
    N011["for jp in junit_paths:     try:         xml_text = jp.read_text(encoding='<str>')     except OSError as exc:         print(f'<str>{jp}<str>{exc}', file=sys.stderr)         return 1     try:         per_shard[jp.stem] = parse_junit(xml_text)     except ET.ParseError as exc:         print(f'<str>{jp}<str>{exc}', file=sys.stderr)         return 1"]
    N012["(missing, duplicated) = compare(...)"]
    N013["union = set().union(*per_shard.values()) if per_shard else set()"]
    N014["extra = union - collected"]
    N015["errors = format_errors(...)"]
    N016["for line in errors:     print(line, file=sys.stderr)"]
    N017["if errors"]
    N018["return 1"]
    N019["total = len(...)"]
    N020["shard_summary = join(...)"]
    N021["print(...)"]
    N022["return 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["args = parse_args(...)"]
    N006["junit_paths = [Path(p) for p in args.junit]"]
    N007["return verify(Path(args.collected), junit_paths)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```
