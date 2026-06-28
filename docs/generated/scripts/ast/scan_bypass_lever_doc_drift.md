# AST graph: scripts/scan_bypass_lever_doc_drift.py

This file is generated from `scripts/scan_bypass_lever_doc_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_levers(...)

```mermaid
flowchart TD
    N001["extract_levers(...)"]
    N002["return frozenset(_LEVER_RE.findall(text))"]
    N001 -->|"start"| N002
```

## _read(...)

```mermaid
flowchart TD
    N001["_read(...)"]
    N002["try"]
    N003["return path.read_text(encoding='<str>')"]
    N004["except OSError"]
    N005["return None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## find_drift(...)

```mermaid
flowchart TD
    N001["find_drift(...)"]
    N002["runbook_rel = relative_to(...)"]
    N003["hook_rel = relative_to(...)"]
    N004["problems = []"]
    N005["for lever in sorted(hook_levers - doc_levers):     problems.append(f'<str>{runbook_rel}<str>{_SCRIPT}<str>{lever!r}<str>{runbook_rel}<str>{lever!r}<str>')"]
    N006["for lever in sorted(doc_levers - hook_levers):     problems.append(f'<str>{runbook_rel}<str>{_SCRIPT}<str>{runbook_rel}<str>{lever!r}<str>{hook_rel}<str>')"]
    N007["return problems"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["hook_path = Path(...)"]
    N003["runbook_path = Path(...)"]
    N004["hook_text = _read(...)"]
    N005["if hook_text is None"]
    N006["print(...)"]
    N007["return 1"]
    N008["runbook_text = _read(...)"]
    N009["if runbook_text is None"]
    N010["print(...)"]
    N011["return 1"]
    N012["hook_levers = extract_levers(...)"]
    N013["doc_levers = extract_levers(...)"]
    N014["if not hook_levers"]
    N015["print(...)"]
    N016["problems = find_drift(...)"]
    N017["for message in problems:     print(message, file=sys.stderr)"]
    N018["if problems"]
    N019["return 1"]
    N020["print(...)"]
    N021["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N016
    N016 --> N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 --> N021
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify = add_parser(...)"]
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
