# AST graph: scripts/scan_ssot_schema.py

This file is generated from `scripts/scan_ssot_schema.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## live_label_names(...)

```mermaid
flowchart TD
    N001["live_label_names(...)"]
    N002["if not isinstance(labels_data, list)"]
    N003["return frozenset()"]
    N004["return frozenset((entry['<str>'] for entry in labels_data if isinstance(entry, dict) and isinstance(entry.get('<str>'), str)))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## consumer_label_universe(...)

```mermaid
flowchart TD
    N001["consumer_label_universe(...)"]
    N002["extra = set(...)"]
    N003["if isinstance(label_policy, dict)"]
    N004["for entry in label_policy.get('<str>', []) or []:     if isinstance(entry, dict) and isinstance(entry.get('<str>'), str):         extra.add(entry['<str>'])"]
    N005["for entry in label_policy.get('<str>', []) or []:     if isinstance(entry, dict) and isinstance(entry.get('<str>'), str):         extra.add(entry['<str>'])"]
    N006["return live | frozenset(extra)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 --> N006
    N003 -->|"false"| N006
```

## _as_list(...)

```mermaid
flowchart TD
    N001["_as_list(...)"]
    N002["return value if isinstance(value, list) else []"]
    N001 -->|"start"| N002
```

## _assert_schema_shape(...)

```mermaid
flowchart TD
    N001["_assert_schema_shape(...)"]
    N002["if not isinstance(schema, dict)"]
    N003["raise SchemaError('<str>')"]
    N004["defs = get(...)"]
    N005["props = get(...)"]
    N006["if not isinstance(defs, dict) or not isinstance(props, dict)"]
    N007["raise SchemaError('<str>')"]
    N008["for name in ('<str>', '<str>', '<str>'):     node = defs.get(name)     if not isinstance(node, dict) or not isinstance(node.get('<str>'), list):         raise SchemaError(f'<str>{name}<str>')"]
    N009["if not isinstance(schema.get('required'), list)"]
    N010["raise SchemaError('<str>')"]
    N011["end"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## _check_gate_kinds(...)

```mermaid
flowchart TD
    N001["_check_gate_kinds(...)"]
    N002["errors = []"]
    N003["for i, gate in enumerate(_as_list(registry.get('<str>'))):     if not isinstance(gate, dict):         continue     gid = gate.get('<str>')     kind = gate.get('<str>')     if kind == '<str>':         if not gate.get('<str>'):             errors.append(f'<str>{i}<str>{gid!r}<str>')         if gate.get('<str>'):             errors.append(f'<str>{i}<str>{gid!r}<str>')     elif kind == '<str>':         if not gate.get('<str>'):             errors.append(f'<str>{i}<str>{gid!r}<str>')         if gate.get('<str>'):             errors.append(f'<str>{i}<str>{gid!r}<str>')"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _check_tracked_paths(...)

```mermaid
flowchart TD
    N001["_check_tracked_paths(...)"]
    N002["errors = []"]
    N003["for i, ps in enumerate(_as_list(registry.get('<str>'))):     if isinstance(ps, dict) and isinstance(ps.get('<str>'), str) and (not is_tracked(ps['<str>'])):         errors.append(f'<str>{i}<str>{ps.get('<str>')!r}<str>{ps['<str>']!r}<str>')"]
    N004["for i, gate in enumerate(_as_list(registry.get('<str>'))):     if not isinstance(gate, dict):         continue     script = gate.get('<str>')     if isinstance(script, str) and (not is_tracked(script)):         errors.append(f'<str>{i}<str>{gate.get('<str>')!r}<str>{script!r}<str>')"]
    N005["for i, con in enumerate(_as_list(registry.get('<str>'))):     if isinstance(con, dict) and isinstance(con.get('<str>'), str) and (not is_tracked(con['<str>'])):         errors.append(f'<str>{i}<str>{con['<str>']!r}<str>')"]
    N006["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _check_id_refs(...)

```mermaid
flowchart TD
    N001["_check_id_refs(...)"]
    N002["errors = []"]
    N003["source_ids = {ps['<str>'] for ps in _as_list(registry.get('<str>')) if isinstance(ps, dict) and isinstance(ps.get('<str>'), str)}"]
    N004["cluster_ids = {cl['<str>'] for cl in _as_list(registry.get('<str>')) if isinstance(cl, dict) and isinstance(cl.get('<str>'), str)}"]
    N005["for i, gate in enumerate(_as_list(registry.get('<str>'))):     if not isinstance(gate, dict):         continue     gid = gate.get('<str>')     for ref in _as_list(gate.get('<str>')):         if ref not in source_ids:             errors.append(f'<str>{i}<str>{gid!r}<str>{ref!r}<str>')     cluster = gate.get('<str>')     if cluster is not None and cluster not in cluster_ids:         errors.append(f'<str>{i}<str>{gid!r}<str>{cluster!r}<str>')"]
    N006["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _routing_labels(...)

```mermaid
flowchart TD
    N001["_routing_labels(...)"]
    N002["labels = []"]
    N003["for rule in _as_list(routing.get('<str>')):     if not isinstance(rule, dict):         continue     for key in ('<str>', '<str>', '<str>'):         labels.extend((v for v in _as_list(rule.get(key)) if isinstance(v, str)))"]
    N004["return labels"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _check_routing(...)

```mermaid
flowchart TD
    N001["_check_routing(...)"]
    N002["routing = get(...)"]
    N003["if not isinstance(routing, dict)"]
    N004["return []"]
    N005["errors = []"]
    N006["for label in _routing_labels(routing):     if label not in live_labels:         errors.append(f'<str>{label!r}<str>{_LABELS_PATH}')"]
    N007["rules = _as_list(...)"]
    N008["default_indexes = [i for i, rule in enumerate(rules) if isinstance(rule, dict) and rule.get('<str>') is True]"]
    N009["if len(default_indexes) != 1"]
    N010["append(...)"]
    N011["if default_indexes[0] != len(rules) - 1"]
    N012["append(...)"]
    N013["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N010 --> N013
    N012 --> N013
    N011 -->|"false"| N013
```

## _check_consumers(...)

```mermaid
flowchart TD
    N001["_check_consumers(...)"]
    N002["errors = []"]
    N003["for i, con in enumerate(_as_list(registry.get('<str>'))):     if not isinstance(con, dict):         continue     for field in ('<str>', '<str>'):         for label in _as_list(con.get(field)):             if label not in consumer_labels:                 errors.append(f'<str>{i}<str>{con.get('<str>')!r}<str>{field}<str>{label!r}<str>{_LABELS_PATH}<str>')"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## verify_registry(...)

```mermaid
flowchart TD
    N001["verify_registry(...)"]
    N002["_assert_schema_shape(...)"]
    N003["assert isinstance(schema, dict)"]
    N004["errors = validate_shape(...)"]
    N005["if not isinstance(registry, dict)"]
    N006["return errors"]
    N007["errors += _check_gate_kinds(registry)"]
    N008["errors += _check_tracked_paths(registry, is_tracked)"]
    N009["errors += _check_id_refs(registry)"]
    N010["errors += _check_routing(registry, live_labels)"]
    N011["errors += _check_consumers(registry, consumer_labels)"]
    N012["return errors"]
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
```

## build_tracked_checker(...)

```mermaid
flowchart TD
    N001["build_tracked_checker(...)"]
    N002["tracked = None"]
    N003["try"]
    N004["completed = run(...)"]
    N005["if completed.returncode == 0"]
    N006["tracked = frozenset(...)"]
    N007["except (OSError, subprocess.SubprocessError)"]
    N008["tracked = None"]
    N009["def is_tracked(path: str) -> bool:     if tracked is not None:         return path in tracked     return (repo_root / path).is_file()"]
    N010["return is_tracked"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N003 -->|"raises"| N007
    N007 --> N008
    N006 --> N009
    N005 -->|"false"| N009
    N008 --> N009
    N009 --> N010
```

## _load_json(...)

```mermaid
flowchart TD
    N001["_load_json(...)"]
    N002["return json.loads(path.read_text(encoding='<str>'))"]
    N001 -->|"start"| N002
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
    N011["add_argument(...)"]
    N012["add_argument(...)"]
    N013["add_argument(...)"]
    N014["args = parse_args(...)"]
    N015["registry_path = _REPO_ROOT / args.registry"]
    N016["schema_path = _REPO_ROOT / args.schema"]
    N017["labels_path = _REPO_ROOT / args.labels"]
    N018["label_policy_path = _REPO_ROOT / args.label_policy"]
    N019["for label, path in (('<str>', registry_path), ('<str>', schema_path), ('<str>', labels_path), ('<str>', label_policy_path)):     if not path.exists():         print(f'<str>{_SCRIPT}<str>{label}<str>{path}<str>', file=sys.stderr)         return 1"]
    N020["try"]
    N021["registry = _load_json(...)"]
    N022["schema = _load_json(...)"]
    N023["labels_data = _load_json(...)"]
    N024["label_policy = loads(...)"]
    N025["except (OSError, ValueError, tomllib.TOMLDecodeError)"]
    N026["print(...)"]
    N027["return 1"]
    N028["live_labels = live_label_names(...)"]
    N029["consumer_labels = consumer_label_universe(...)"]
    N030["is_tracked = build_tracked_checker(...)"]
    N031["try"]
    N032["errors = verify_registry(...)"]
    N033["except SchemaError"]
    N034["print(...)"]
    N035["return 1"]
    N036["if errors"]
    N037["for message in errors:     print(f'<str>{_SCRIPT}<str>{message}', file=sys.stderr)"]
    N038["return 1"]
    N039["print(...)"]
    N040["return 0"]
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
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 -->|"try"| N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
    N020 -->|"raises"| N025
    N025 --> N026
    N026 --> N027
    N024 --> N028
    N028 --> N029
    N029 --> N030
    N030 --> N031
    N031 -->|"try"| N032
    N031 -->|"raises"| N033
    N033 --> N034
    N034 --> N035
    N032 --> N036
    N036 -->|"true"| N037
    N037 --> N038
    N036 -->|"false"| N039
    N039 --> N040
```
