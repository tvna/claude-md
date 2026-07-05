# AST graph: scripts/_json_schema_subset.py

This file is generated from `scripts/_json_schema_subset.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _as_list(...)

```mermaid
flowchart TD
    N001["_as_list(...)"]
    N002["return value if isinstance(value, list) else []"]
    N001 -->|"start"| N002
```

## _resolve_ref(...)

```mermaid
flowchart TD
    N001["_resolve_ref(...)"]
    N002["node = root"]
    N003["for part in ref.lstrip('<str>').split('<str>'):     if not isinstance(node, dict) or part not in node:         raise SchemaError(f'<str>{ref!r}<str>')     node = node[part]"]
    N004["if not isinstance(node, dict)"]
    N005["raise SchemaError(f'<str>{ref!r}<str>')"]
    N006["return node"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## _type_name(...)

```mermaid
flowchart TD
    N001["_type_name(...)"]
    N002["return '<str>' if value is None else type(value).__name__"]
    N001 -->|"start"| N002
```

## _validate_instance(...)

```mermaid
flowchart TD
    N001["_validate_instance(...)"]
    N002["ref = get(...)"]
    N003["if isinstance(ref, str)"]
    N004["schema = _resolve_ref(...)"]
    N005["declared_type = get(...)"]
    N006["if declared_type is not None"]
    N007["types = declared_type if isinstance(declared_type, list) else [declared_type]"]
    N008["if not any((_TYPE_CHECKS.get(str(t), lambda _v: True)(instance) for t in types))"]
    N009["append(...)"]
    N010["return"]
    N011["enum = get(...)"]
    N012["if isinstance(enum, list) and instance not in enum"]
    N013["append(...)"]
    N014["if isinstance(instance, dict)"]
    N015["properties = get(...)"]
    N016["properties = properties if isinstance(properties, dict) else {}"]
    N017["for key in _as_list(schema.get('<str>')):     if key not in instance:         errors.append(f'{path}<str>{key!r}')"]
    N018["additional = get(...)"]
    N019["if additional is False"]
    N020["for key in instance:     if key not in properties:         errors.append(f'{path}<str>{key!r}')"]
    N021["if isinstance(additional, dict)"]
    N022["for key, value in instance.items():     if key not in properties:         _validate_instance(value, additional, root, f'{path}<str>{key}', errors)"]
    N023["for key, subschema in properties.items():     if key in instance and isinstance(subschema, dict):         _validate_instance(instance[key], subschema, root, f'{path}<str>{key}', errors)"]
    N024["if isinstance(instance, list)"]
    N025["min_items = get(...)"]
    N026["if isinstance(min_items, int) and len(instance) < min_items"]
    N027["append(...)"]
    N028["item_schema = get(...)"]
    N029["if isinstance(item_schema, dict)"]
    N030["for idx, item in enumerate(instance):     _validate_instance(item, item_schema, root, f'{path}<str>{idx}<str>', errors)"]
    N031["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N006 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N014
    N014 -->|"true"| N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N019 -->|"true"| N020
    N019 -->|"false"| N021
    N021 -->|"true"| N022
    N020 --> N023
    N022 --> N023
    N021 -->|"false"| N023
    N014 -->|"false"| N024
    N024 -->|"true"| N025
    N025 --> N026
    N026 -->|"true"| N027
    N027 --> N028
    N026 -->|"false"| N028
    N028 --> N029
    N029 -->|"true"| N030
    N023 --> N031
    N030 --> N031
    N029 -->|"false"| N031
    N024 -->|"false"| N031
```

## validate_shape(...)

```mermaid
flowchart TD
    N001["validate_shape(...)"]
    N002["errors = []"]
    N003["_validate_instance(...)"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
