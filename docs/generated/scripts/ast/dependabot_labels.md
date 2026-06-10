# AST graph: scripts/dependabot_labels.py

This file is generated from `scripts/dependabot_labels.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## parse_dependabot_labels(...)

```mermaid
flowchart TD
    N001["parse_dependabot_labels(...)"]
    N002["labels = []"]
    N003["in_block = False"]
    N004["block_indent = -1"]
    N005["for raw_line in yaml_text.splitlines():
    stripped = raw_line.lstrip()
    if not stripped or stripped.startswith('<str>'):
        continue
    indent = len(raw_line) - len(stripped)
    if in_block:
        if indent > block_indent and stripped.startswith('<str>'):
            labels.append(_unquote(stripped[2:].strip()))
            continue
        if indent <= block_indent:
            in_block = False
    if not in_block and stripped == '<str>':
        in_block = True
        block_indent = indent"]
    N006["return labels"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## load_sot_labels(...)

```mermaid
flowchart TD
    N001["load_sot_labels(...)"]
    N002["raw_labels = loads(...)"]
    N003["if not isinstance(raw_labels, list)"]
    N004["raise ValueError('<str>')"]
    N005["return [LabelDefinition.from_raw(raw_label, index) for index, raw_label in enumerate(raw_labels)]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## load_sot_label_names(...)

```mermaid
flowchart TD
    N001["load_sot_label_names(...)"]
    N002["return {label.name for label in load_sot_labels(json_text)}"]
    N001 -->|"start"| N002
```

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["return sorted({label for label in referenced if label not in defined})"]
    N001 -->|"start"| N002
```

## _unquote(...)

```mermaid
flowchart TD
    N001["_unquote(...)"]
    N002["if len(value) >= 2 and value[0] == value[-1] and (value[0] in ('\"', \"'\"))"]
    N003["return value[1:-1]"]
    N004["return value"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _required_string(...)

```mermaid
flowchart TD
    N001["_required_string(...)"]
    N002["value = raw[key]"]
    N003["if not isinstance(value, str) or (not allow_empty and (not value))"]
    N004["empty = '<str>' if allow_empty else '<str>'"]
    N005["raise ValueError(f'{path}<str>{key}<str>{empty}<str>')"]
    N006["return value"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["dependabot_path = Path(...)"]
    N003["labels_path = Path(...)"]
    N004["if not dependabot_path.is_file()"]
    N005["print(...)"]
    N006["return 1"]
    N007["if not labels_path.is_file()"]
    N008["print(...)"]
    N009["return 1"]
    N010["try"]
    N011["referenced = parse_dependabot_labels(...)"]
    N012["defined = load_sot_label_names(...)"]
    N013["except (OSError, ValueError, json.JSONDecodeError)"]
    N014["print(...)"]
    N015["return 1"]
    N016["drift = find_drift(...)"]
    N017["if drift"]
    N018["for name in drift:
    print(f'<str>{dependabot_path}<str>{name}<str>{dependabot_path}<str>{labels_path}<str>')"]
    N019["print(...)"]
    N020["return 1"]
    N021["print(...)"]
    N022["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 -->|"try"| N011
    N011 --> N012
    N010 -->|"raises"| N013
    N013 --> N014
    N014 --> N015
    N012 --> N016
    N016 --> N017
    N017 -->|"true"| N018
    N018 --> N019
    N019 --> N020
    N017 -->|"false"| N021
    N021 --> N022
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["args = parse_args(...)"]
    N009["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```
