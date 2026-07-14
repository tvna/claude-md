# AST graph: scripts/scan_label_sot_drift.py

This file is generated from `scripts/scan_label_sot_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## load_json(...)

```mermaid
flowchart TD
    N001["load_json(...)"]
    N002["with path.open(encoding='<str>') as handle:     return json.load(handle)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## load_toml(...)

```mermaid
flowchart TD
    N001["load_toml(...)"]
    N002["with path.open('<str>') as handle:     return tomllib.load(handle)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _err(...)

```mermaid
flowchart TD
    N001["_err(...)"]
    N002["return f'<str>{file.as_posix()}<str>{message}'"]
    N001 -->|"start"| N002
```

## index_policy_labels(...)

```mermaid
flowchart TD
    N001["index_policy_labels(...)"]
    N002["labels_raw = get(...)"]
    N003["if not isinstance(labels_raw, list)"]
    N004["return ({}, [_err('<str>', LABEL_POLICY_PATH)])"]
    N005["index = {}"]
    N006["errors = []"]
    N007["for entry in labels_raw:     if not isinstance(entry, dict):         continue     name = entry.get('<str>')     if not isinstance(name, str) or not name:         errors.append(_err(f'<str>{name!r}<str>', LABEL_POLICY_PATH))         continue     if name in index:         errors.append(_err(f'<str>{name!r}<str>', LABEL_POLICY_PATH))         continue     index[name] = entry"]
    N008["return (index, errors)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## verify_parity(...)

```mermaid
flowchart TD
    N001["verify_parity(...)"]
    N002["if not isinstance(catalog, list)"]
    N003["return [_err('<str>')]"]
    N004["(policy_index, diagnostics) = index_policy_labels(...)"]
    N005["if diagnostics"]
    N006["return diagnostics"]
    N007["errors = []"]
    N008["seen = set(...)"]
    N009["for entry in catalog:     if not isinstance(entry, dict):         errors.append(_err(f'<str>{entry!r}'))         continue     name = entry.get('<str>')     if not isinstance(name, str) or not name:         errors.append(_err(f'<str>{name!r}<str>'))         continue     if name in seen:         errors.append(_err(f'<str>{name!r}<str>'))         continue     seen.add(name)     policy_entry = policy_index.get(name)     if policy_entry is None:         errors.append(_err(f'<str>{name!r}<str>'))         continue     if entry.get('<str>') != policy_entry.get('<str>'):         errors.append(_err(f'<str>{name!r}<str>{entry.get('<str>')!r}<str>{policy_entry.get('<str>')!r}<str>'))     if entry.get('<str>') != policy_entry.get('<str>'):         errors.append(_err(f'<str>{name!r}<str>{entry.get('<str>')!r}<str>{policy_entry.get('<str>')!r}<str>'))"]
    N010["return errors"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["root = resolve(...)"]
    N003["catalog_file = root / LABELS_JSON_PATH"]
    N004["policy_file = root / LABEL_POLICY_PATH"]
    N005["if not catalog_file.exists()"]
    N006["return [_err(f'<str>{LABELS_JSON_PATH.as_posix()}<str>')]"]
    N007["if not policy_file.exists()"]
    N008["return [_err(f'<str>{LABEL_POLICY_PATH.as_posix()}<str>', LABEL_POLICY_PATH)]"]
    N009["try"]
    N010["catalog = load_json(...)"]
    N011["except json.JSONDecodeError"]
    N012["return [_err(f'<str>{exc}')]"]
    N013["except (UnicodeDecodeError, OSError)"]
    N014["return [_err(f'<str>{exc}')]"]
    N015["try"]
    N016["policy = load_toml(...)"]
    N017["except tomllib.TOMLDecodeError"]
    N018["return [_err(f'<str>{exc}', LABEL_POLICY_PATH)]"]
    N019["except (UnicodeDecodeError, OSError)"]
    N020["return [_err(f'<str>{exc}', LABEL_POLICY_PATH)]"]
    N021["return verify_parity(catalog, policy)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"try"| N010
    N009 -->|"raises"| N011
    N011 --> N012
    N009 -->|"raises"| N013
    N013 --> N014
    N010 --> N015
    N015 -->|"try"| N016
    N015 -->|"raises"| N017
    N017 --> N018
    N015 -->|"raises"| N019
    N019 --> N020
    N016 --> N021
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["args = parse_args(...)"]
    N007["errors = verify(...)"]
    N008["for error in errors:     print(error, file=sys.stderr)"]
    N009["if errors"]
    N010["return 1"]
    N011["print(...)"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
```
