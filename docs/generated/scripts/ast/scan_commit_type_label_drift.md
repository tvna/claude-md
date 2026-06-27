# AST graph: scripts/scan_commit_type_label_drift.py

This file is generated from `scripts/scan_commit_type_label_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## load_toml(...)

```mermaid
flowchart TD
    N001["load_toml(...)"]
    N002["with path.open('<str>') as handle:     return tomllib.load(handle)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## parse_commit_types(...)

```mermaid
flowchart TD
    N001["parse_commit_types(...)"]
    N002["policy = get(...)"]
    N003["if not isinstance(policy, dict)"]
    N004["return (set(), '<str>')"]
    N005["types = get(...)"]
    N006["if not isinstance(types, list)"]
    N007["return (set(), '<str>')"]
    N008["return ({item for item in types if isinstance(item, str) and item}, None)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _err(...)

```mermaid
flowchart TD
    N001["_err(...)"]
    N002["return f'<str>{file.as_posix()}<str>{message}'"]
    N001 -->|"start"| N002
```

## verify_policy(...)

```mermaid
flowchart TD
    N001["verify_policy(...)"]
    N002["(types, malformed) = parse_commit_types(...)"]
    N003["if malformed is not None"]
    N004["return [_err(malformed, TITLE_POLICY_PATH)]"]
    N005["labels_raw = get(...)"]
    N006["if not isinstance(labels_raw, list)"]
    N007["return [_err('<str>')]"]
    N008["errors = []"]
    N009["for label in (entry for entry in labels_raw if isinstance(entry, dict)):     name = label.get('<str>')     family = label.get('<str>')     has_marker = '<str>' in label     marker = label.get('<str>')     if has_marker and family != '<str>':         label_id = name if isinstance(name, str) else '<str>'         errors.append(_err(f'<str>{label_id}<str>{family!r}<str>'))         continue     if family != '<str>':         continue     if not isinstance(name, str):         errors.append(_err(f'<str>{name!r}<str>'))         continue     if has_marker and (not isinstance(marker, bool)):         errors.append(_err(f'<str>{name}<str>{marker!r}'))         continue     if not name.startswith(_TYPE_PREFIX):         errors.append(_err(f'<str>{name!r}<str>{_TYPE_PREFIX!r}<str>'))         continue     stem = name[len(_TYPE_PREFIX):]     if marker is False:         if stem in types:             errors.append(_err(f'<str>{name}<str>{stem!r}<str>'))     elif stem not in types:         errors.append(_err(f'<str>{name}<str>{stem!r}<str>'))"]
    N010["return errors"]
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

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["root = resolve(...)"]
    N003["label_file = root / LABEL_POLICY_PATH"]
    N004["title_file = root / TITLE_POLICY_PATH"]
    N005["if not label_file.exists()"]
    N006["return [_err(f'<str>{LABEL_POLICY_PATH.as_posix()}<str>')]"]
    N007["if not title_file.exists()"]
    N008["return [_err(f'<str>{TITLE_POLICY_PATH.as_posix()}<str>', TITLE_POLICY_PATH)]"]
    N009["try"]
    N010["label_policy = load_toml(...)"]
    N011["except tomllib.TOMLDecodeError"]
    N012["return [_err(f'<str>{exc}')]"]
    N013["try"]
    N014["title_policy = load_toml(...)"]
    N015["except tomllib.TOMLDecodeError"]
    N016["return [_err(f'<str>{exc}', TITLE_POLICY_PATH)]"]
    N017["return verify_policy(label_policy, title_policy)"]
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
    N010 --> N013
    N013 -->|"try"| N014
    N013 -->|"raises"| N015
    N015 --> N016
    N014 --> N017
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
