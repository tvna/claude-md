# AST graph: scripts/verify_text_delta_section.py

This file is generated from `scripts/verify_text_delta_section.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## is_instruction_path(...)

```mermaid
flowchart TD
    N001["is_instruction_path(...)"]
    N002["cleaned = strip(...)"]
    N003["if not cleaned"]
    N004["return False"]
    N005["return cleaned in _INSTRUCTION_FILES or cleaned.startswith(_INSTRUCTION_DIR_PREFIX)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
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

## changed_instruction_files(...)

```mermaid
flowchart TD
    N001["changed_instruction_files(...)"]
    N002["result = _run(...)"]
    N003["return frozenset((line.strip() for line in result.stdout.splitlines() if is_instruction_path(line)))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## section_errors(...)

```mermaid
flowchart TD
    N001["section_errors(...)"]
    N002["errors = []"]
    N003["if _CHAR_DELTA_RE.search(section) is None"]
    N004["append(...)"]
    N005["if _ADDED_RE.search(section) is None"]
    N006["append(...)"]
    N007["if _REMOVED_RE.search(section) is None"]
    N008["append(...)"]
    N009["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["if not changed"]
    N003["return (0, [])"]
    N004["section = extract_section_body(...)"]
    N005["if not section.strip()"]
    N006["return (1, ['<str>'])"]
    N007["errors = section_errors(...)"]
    N008["if errors"]
    N009["return (1, errors)"]
    N010["return (0, [])"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
```

## _resolve_body(...)

```mermaid
flowchart TD
    N001["_resolve_body(...)"]
    N002["if args.body_file is not None"]
    N003["return Path(args.body_file).read_text(encoding='<str>')"]
    N004["return os.environ.get('<str>', '<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _resolve_base_ref(...)

```mermaid
flowchart TD
    N001["_resolve_base_ref(...)"]
    N002["if args.base_ref"]
    N003["return args.base_ref"]
    N004["return resolve_base()"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _resolve_created_at(...)

```mermaid
flowchart TD
    N001["_resolve_created_at(...)"]
    N002["if args.created_at is not None"]
    N003["return args.created_at"]
    N004["return os.environ.get('<str>', '<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _resolve_cutoff(...)

```mermaid
flowchart TD
    N001["_resolve_cutoff(...)"]
    N002["if args.cutoff is not None"]
    N003["return args.cutoff"]
    N004["return os.environ.get('<str>', '<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["created_at = _resolve_created_at(...)"]
    N003["cutoff = _resolve_cutoff(...)"]
    N004["if created_at and cutoff and (not is_within_gate_window(created_at, cutoff))"]
    N005["print(...)"]
    N006["return 0"]
    N007["base = _resolve_base_ref(...)"]
    N008["try"]
    N009["body = _resolve_body(...)"]
    N010["except FileNotFoundError"]
    N011["print(...)"]
    N012["return 1"]
    N013["try"]
    N014["changed = changed_instruction_files(...)"]
    N015["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, RuntimeError)"]
    N016["print(...)"]
    N017["return 1"]
    N018["(code, errors) = evaluate(...)"]
    N019["if code == 0"]
    N020["if changed"]
    N021["print(...)"]
    N022["print(...)"]
    N023["return 0"]
    N024["for line in errors:     print(line)"]
    N025["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N013 -->|"try"| N014
    N013 -->|"raises"| N015
    N015 --> N016
    N016 --> N017
    N014 --> N018
    N018 --> N019
    N019 -->|"true"| N020
    N020 -->|"true"| N021
    N020 -->|"false"| N022
    N021 --> N023
    N022 --> N023
    N019 -->|"false"| N024
    N024 --> N025
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

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["return runner(cmd, capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS, check=True)"]
    N001 -->|"start"| N002
```
