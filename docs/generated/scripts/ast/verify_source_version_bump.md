# AST graph: scripts/verify_source_version_bump.py

This file is generated from `scripts/verify_source_version_bump.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## parse_version(...)

```mermaid
flowchart TD
    N001["parse_version(...)"]
    N002["match = search(...)"]
    N003["if match is None"]
    N004["raise ValueError('<str>')"]
    N005["return (int(match.group(1)), int(match.group(2)), int(match.group(3)))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## format_version(...)

```mermaid
flowchart TD
    N001["format_version(...)"]
    N002["return '<str>'.join((str(part) for part in version))"]
    N001 -->|"start"| N002
```

## is_universal_text_path(...)

```mermaid
flowchart TD
    N001["is_universal_text_path(...)"]
    N002["return path.strip() in _UNIVERSAL_TEXT_FILES"]
    N001 -->|"start"| N002
```

## touches_universal_text(...)

```mermaid
flowchart TD
    N001["touches_universal_text(...)"]
    N002["return any((is_universal_text_path(path) for path in changed_paths))"]
    N001 -->|"start"| N002
```

## bump_component(...)

```mermaid
flowchart TD
    N001["bump_component(...)"]
    N002["(b_major, b_minor, b_patch) = base"]
    N003["(h_major, h_minor, h_patch) = head"]
    N004["if h_major > b_major"]
    N005["return '<str>' if h_minor == 0 and h_patch == 0 else None"]
    N006["if h_major == b_major and h_minor > b_minor"]
    N007["return '<str>' if h_patch == 0 else None"]
    N008["if h_major == b_major and h_minor == b_minor and (h_patch > b_patch)"]
    N009["return '<str>'"]
    N010["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
```

## extract_semver_labels(...)

```mermaid
flowchart TD
    N001["extract_semver_labels(...)"]
    N002["components = []"]
    N003["for label in labels:     name = label.strip()     if name.startswith(_SEMVER_LABEL_PREFIX):         component = name[len(_SEMVER_LABEL_PREFIX):]         if component in _SEMVER_COMPONENTS:             components.append(component)"]
    N004["return components"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["version_changed = base_version != head_version"]
    N003["errors = []"]
    N004["if not text_changed and (not version_changed)"]
    N005["return (0, [])"]
    N006["if text_changed and (not version_changed)"]
    N007["return (1, ['<str>'])"]
    N008["if version_changed and (not text_changed)"]
    N009["return (1, [f'<str>{format_version(base_version)}<str>{format_version(head_version)}<str>'])"]
    N010["component = bump_component(...)"]
    N011["if component is None"]
    N012["return (1, [f'<str>{format_version(base_version)}<str>{format_version(head_version)}<str>'])"]
    N013["if labels is None"]
    N014["return (0, [])"]
    N015["components = extract_semver_labels(...)"]
    N016["if len(components) != 1"]
    N017["append(...)"]
    N018["return (1, errors)"]
    N019["declared = components[0]"]
    N020["if declared != component"]
    N021["append(...)"]
    N022["return (1, errors)"]
    N023["return (0, [])"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 --> N016
    N016 -->|"true"| N017
    N017 --> N018
    N016 -->|"false"| N019
    N019 --> N020
    N020 -->|"true"| N021
    N021 --> N022
    N020 -->|"false"| N023
```

## resolve_base(...)

```mermaid
flowchart TD
    N001["resolve_base(...)"]
    N002["explicit = get(...)"]
    N003["if explicit"]
    N004["return explicit"]
    N005["actions_base = get(...)"]
    N006["if actions_base"]
    N007["return f'<str>{actions_base}'"]
    N008["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## changed_files(...)

```mermaid
flowchart TD
    N001["changed_files(...)"]
    N002["result = _run(...)"]
    N003["return frozenset((line.strip() for line in result.stdout.splitlines() if line.strip()))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## read_version_at(...)

```mermaid
flowchart TD
    N001["read_version_at(...)"]
    N002["result = _run(...)"]
    N003["return parse_version(result.stdout)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _resolve_labels(...)

```mermaid
flowchart TD
    N001["_resolve_labels(...)"]
    N002["if args.labels is not None"]
    N003["return [item.strip() for item in args.labels.split('<str>') if item.strip()]"]
    N004["if 'PR_LABELS' in os.environ"]
    N005["raw = os.environ['<str>']"]
    N006["return [item.strip() for item in raw.split('<str>') if item.strip()]"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["base = args.base_ref or resolve_base()"]
    N003["head = args.head"]
    N004["labels = _resolve_labels(...)"]
    N005["try"]
    N006["changed = changed_files(...)"]
    N007["base_version = read_version_at(...)"]
    N008["head_version = read_version_at(...)"]
    N009["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, RuntimeError, ValueError)"]
    N010["print(...)"]
    N011["return 1"]
    N012["text_changed = touches_universal_text(...)"]
    N013["(code, errors) = evaluate(...)"]
    N014["if code == 0"]
    N015["if text_changed"]
    N016["label_note = '<str>' if labels is None else '<str>'"]
    N017["print(...)"]
    N018["print(...)"]
    N019["return 0"]
    N020["for line in errors:     print(line)"]
    N021["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"try"| N006
    N006 --> N007
    N007 --> N008
    N005 -->|"raises"| N009
    N009 --> N010
    N010 --> N011
    N008 --> N012
    N012 --> N013
    N013 --> N014
    N014 -->|"true"| N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N018
    N017 --> N019
    N018 --> N019
    N014 -->|"false"| N020
    N020 --> N021
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
    N008["set_defaults(...)"]
    N009["args = parse_args(...)"]
    N010["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
```

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["return runner(cmd, capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS, check=True)"]
    N001 -->|"start"| N002
```
