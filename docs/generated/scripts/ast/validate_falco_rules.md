# AST graph: scripts/validate_falco_rules.py

This file is generated from `scripts/validate_falco_rules.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _entry_type(...)

```mermaid
flowchart TD
    N001["_entry_type(...)"]
    N002["for key in _REQUIRED_FIELDS:     if key in entry:         return key"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## validate_entries(...)

```mermaid
flowchart TD
    N001["validate_entries(...)"]
    N002["errors = []"]
    N003["for idx, entry in enumerate(entries):     if not isinstance(entry, dict):         errors.append(f'<str>{path}<str>{idx}<str>{type(entry).__name__}')         continue     etype = _entry_type(entry)     if etype is None:         errors.append(f'<str>{path}<str>{idx}<str>{sorted(entry.keys())}')         continue     name = str(entry.get(etype, f'<str>{idx}<str>'))     for field in sorted(_REQUIRED_FIELDS[etype] - entry.keys()):         errors.append(f'<str>{path}<str>{etype}<str>{name!r}<str>{field}<str>')     if etype == '<str>':         priority = entry.get('<str>')         if priority is not None and str(priority).upper() not in _VALID_PRIORITIES:             errors.append(f'<str>{path}<str>{name!r}<str>{priority!r}<str>{'<str>'.join(sorted(_VALID_PRIORITIES))}')     for field_key in ('<str>', '<str>'):         text = entry.get(field_key)         if not isinstance(text, str):             continue         for match in _WRONG_FIELD_RE.finditer(text):             wrong = match.group(1)             correct = _WRONG_FIELDS[wrong]             errors.append(f'<str>{path}<str>{etype}<str>{name!r}<str>{wrong}<str>{correct}<str>')"]
    N004["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## validate_file(...)

```mermaid
flowchart TD
    N001["validate_file(...)"]
    N002["try"]
    N003["raw = read_text(...)"]
    N004["except OSError"]
    N005["return [f'<str>{path}<str>{exc}']"]
    N006["try"]
    N007["entries = safe_load(...)"]
    N008["except yaml.YAMLError"]
    N009["return [f'<str>{path}<str>{exc}']"]
    N010["if not isinstance(entries, list)"]
    N011["return [f'<str>{path}<str>{type(entries).__name__}']"]
    N012["return validate_entries(path, entries)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["all_errors = []"]
    N003["for path in args.file:     all_errors.extend(validate_file(path))"]
    N004["for err in all_errors:     print(err, file=sys.stderr)"]
    N005["if all_errors"]
    N006["return 1"]
    N007["n = len(...)"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["args = parse_args(...)"]
    N007["if args.cmd == 'verify'"]
    N008["return _cmd_verify(args)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```
