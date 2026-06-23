# AST graph: scripts/verify_instruction_text_growth.py

This file is generated from `scripts/verify_instruction_text_growth.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

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

## net_char_delta(...)

```mermaid
flowchart TD
    N001["net_char_delta(...)"]
    N002["added = 0"]
    N003["removed = 0"]
    N004["for line in diff_text.splitlines():     if line.startswith('<str>') or line.startswith('<str>'):         continue     if line.startswith('<str>'):         added += len(line) - 1     elif line.startswith('<str>'):         removed += len(line) - 1"]
    N005["return added - removed"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## has_growth_ack(...)

```mermaid
flowchart TD
    N001["has_growth_ack(...)"]
    N002["return _ACK_RE.search(body) is not None"]
    N001 -->|"start"| N002
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["if net_delta <= 0"]
    N003["return (0, [])"]
    N004["if has_growth_ack(body)"]
    N005["return (0, [])"]
    N006["return (1, [f'<str>{net_delta}<str>'])"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## instruction_diff(...)

```mermaid
flowchart TD
    N001["instruction_diff(...)"]
    N002["result = _run(...)"]
    N003["return result.stdout"]
    N001 -->|"start"| N002
    N002 --> N003
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
    N014["diff_text = instruction_diff(...)"]
    N015["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, RuntimeError)"]
    N016["print(...)"]
    N017["return 1"]
    N018["delta = net_char_delta(...)"]
    N019["(code, errors) = evaluate(...)"]
    N020["if code == 0"]
    N021["if delta > 0"]
    N022["print(...)"]
    N023["print(...)"]
    N024["return 0"]
    N025["for line in errors:     print(line)"]
    N026["return 1"]
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
    N019 --> N020
    N020 -->|"true"| N021
    N021 -->|"true"| N022
    N021 -->|"false"| N023
    N022 --> N024
    N023 --> N024
    N020 -->|"false"| N025
    N025 --> N026
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
