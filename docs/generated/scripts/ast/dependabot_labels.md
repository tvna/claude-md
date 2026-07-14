# AST graph: scripts/dependabot_labels.py

This file is generated from `scripts/dependabot_labels.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## parse_dependabot_labels(...)

```mermaid
flowchart TD
    N001["parse_dependabot_labels(...)"]
    N002["labels = []"]
    N003["in_block = False"]
    N004["block_indent = -1"]
    N005["for raw_line in yaml_text.splitlines():     stripped = raw_line.lstrip()     if not stripped or stripped.startswith('<str>'):         continue     indent = len(raw_line) - len(stripped)     if in_block:         if indent > block_indent and stripped.startswith('<str>'):             labels.append(_unquote(stripped[2:].strip()))             continue         if indent <= block_indent:             in_block = False     if not in_block and stripped == '<str>':         in_block = True         block_indent = indent"]
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

## load_sot_label_names_from_policy(...)

```mermaid
flowchart TD
    N001["load_sot_label_names_from_policy(...)"]
    N002["catalog = load_sot_from_policy(...)"]
    N003["return {str(entry['<str>']) for entry in catalog}"]
    N001 -->|"start"| N002
    N002 --> N003
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
    N002["if len(value) >= 2 and value[0] == value[-1] and (value[0] in (''', '''))"]
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
    N004["label_policy_path = Path(...)"]
    N005["if not dependabot_path.is_file()"]
    N006["print(...)"]
    N007["return 1"]
    N008["if not labels_path.is_file()"]
    N009["print(...)"]
    N010["return 1"]
    N011["if args.source == 'label-policy' and (not label_policy_path.is_file())"]
    N012["print(...)"]
    N013["return 1"]
    N014["try"]
    N015["referenced = parse_dependabot_labels(...)"]
    N016["if args.source == 'label-policy'"]
    N017["defined = load_sot_label_names_from_policy(...)"]
    N018["defined = load_sot_label_names(...)"]
    N019["except (OSError, ValueError, json.JSONDecodeError)"]
    N020["print(...)"]
    N021["return 1"]
    N022["drift = find_drift(...)"]
    N023["if drift"]
    N024["for name in drift:     print(f'<str>{dependabot_path}<str>{name}<str>{dependabot_path}<str>{labels_path}<str>')"]
    N025["print(...)"]
    N026["return 1"]
    N027["print(...)"]
    N028["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 -->|"try"| N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N014 -->|"raises"| N019
    N019 --> N020
    N020 --> N021
    N017 --> N022
    N018 --> N022
    N022 --> N023
    N023 -->|"true"| N024
    N024 --> N025
    N025 --> N026
    N023 -->|"false"| N027
    N027 --> N028
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
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["set_defaults(...)"]
    N010["args = parse_args(...)"]
    N011["return args.func(args)"]
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
```
