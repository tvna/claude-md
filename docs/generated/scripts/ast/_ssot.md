# AST graph: scripts/_ssot.py

This file is generated from `scripts/_ssot.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _load(...)

```mermaid
flowchart TD
    N001["_load(...)"]
    N002["global _registry"]
    N003["if _registry is None"]
    N004["_registry = loads(...)"]
    N005["return _registry"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## consumer_labels(...)

```mermaid
flowchart TD
    N001["consumer_labels(...)"]
    N002["for entry in _load().get('<str>', []):     if isinstance(entry, dict) and entry.get('<str>') == path:         labels = entry.get('<str>')         if not isinstance(labels, list):             raise TypeError(f'<str>{path!r}<str>{labels!r}<str>{_REGISTRY_PATH}')         return tuple(labels)"]
    N003["raise KeyError(f'<str>{path!r}<str>{_REGISTRY_PATH}')"]
    N001 -->|"start"| N002
    N002 --> N003
```

## consumer_discovery_only_labels(...)

```mermaid
flowchart TD
    N001["consumer_discovery_only_labels(...)"]
    N002["for entry in _load().get('<str>', []):     if isinstance(entry, dict) and entry.get('<str>') == path:         labels = entry.get('<str>', [])         if not isinstance(labels, list):             raise TypeError(f'<str>{path!r}<str>{labels!r}<str>{_REGISTRY_PATH}')         return tuple(labels)"]
    N003["raise KeyError(f'<str>{path!r}<str>{_REGISTRY_PATH}')"]
    N001 -->|"start"| N002
    N002 --> N003
```

## routing_rules(...)

```mermaid
flowchart TD
    N001["routing_rules(...)"]
    N002["routing = get(...)"]
    N003["if not isinstance(routing, dict)"]
    N004["raise TypeError(f'<str>{_REGISTRY_PATH}')"]
    N005["rules = get(...)"]
    N006["if not isinstance(rules, list)"]
    N007["raise TypeError(f'<str>{_REGISTRY_PATH}')"]
    N008["return tuple(rules)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## policy_source_path(...)

```mermaid
flowchart TD
    N001["policy_source_path(...)"]
    N002["for entry in _load().get('<str>', []):     if isinstance(entry, dict) and entry.get('<str>') == source_id:         path = entry.get('<str>')         if not isinstance(path, str):             raise TypeError(f'<str>{source_id!r}<str>{path!r}<str>{_REGISTRY_PATH}')         return _REGISTRY_PATH.parent.parent / path"]
    N003["raise KeyError(f'<str>{source_id!r}<str>{_REGISTRY_PATH}')"]
    N001 -->|"start"| N002
    N002 --> N003
```

## required_issue_axes(...)

```mermaid
flowchart TD
    N001["required_issue_axes(...)"]
    N002["policy_path = policy_source_path(...)"]
    N003["try"]
    N004["policy = loads(...)"]
    N005["except (OSError, UnicodeDecodeError)"]
    N006["raise RuntimeError(f'<str>{policy_path}<str>{exc}')"]
    N007["except tomllib.TOMLDecodeError"]
    N008["raise RuntimeError(f'<str>{policy_path}<str>{exc}')"]
    N009["families = get(...)"]
    N010["if not isinstance(families, list)"]
    N011["raise TypeError(f'<str>{policy_path}<str>')"]
    N012["axes = []"]
    N013["for family in families:     if not isinstance(family, dict):         raise TypeError(f'<str>{family!r}')     name = family.get('<str>')     cardinality = family.get('<str>')     if not isinstance(name, str) or not isinstance(cardinality, str):         raise TypeError(f'<str>{family!r}')     if cardinality in _MANDATORY_AT_CREATE_CARDINALITIES:         axes.append(name)"]
    N014["if not axes"]
    N015["raise RuntimeError(f'<str>{policy_path}<str>{sorted(_MANDATORY_AT_CREATE_CARDINALITIES)}<str>')"]
    N016["return tuple(axes)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N003 -->|"raises"| N007
    N007 --> N008
    N004 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
```

## retired_label_names(...)

```mermaid
flowchart TD
    N001["retired_label_names(...)"]
    N002["policy_path = policy_source_path(...)"]
    N003["try"]
    N004["policy = loads(...)"]
    N005["except (OSError, UnicodeDecodeError)"]
    N006["raise RuntimeError(f'<str>{policy_path}<str>{exc}')"]
    N007["except tomllib.TOMLDecodeError"]
    N008["raise RuntimeError(f'<str>{policy_path}<str>{exc}')"]
    N009["retired = get(...)"]
    N010["if not isinstance(retired, list)"]
    N011["raise TypeError(f'<str>{policy_path}<str>')"]
    N012["names = set(...)"]
    N013["for entry in retired:     if not isinstance(entry, dict):         raise TypeError(f'<str>{entry!r}')     name = entry.get('<str>')     if not isinstance(name, str):         raise TypeError(f'<str>{entry!r}')     if '<str>' not in name:         names.add(name)"]
    N014["return frozenset(names)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N003 -->|"raises"| N007
    N007 --> N008
    N004 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
```

## group_labels_by_family(...)

```mermaid
flowchart TD
    N001["group_labels_by_family(...)"]
    N002["order = []"]
    N003["groups = {}"]
    N004["for label in labels:     family = label.split('<str>', 1)[0]     if family not in groups:         groups[family] = []         order.append(family)     groups[family].append(label)"]
    N005["return ['<str>'.join(groups[family]) for family in order]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _reset_for_tests(...)

```mermaid
flowchart TD
    N001["_reset_for_tests(...)"]
    N002["global _registry"]
    N003["_registry = None"]
    N004["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
