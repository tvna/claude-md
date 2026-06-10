# AST graph: scripts/scan_nonexhaustive_invariant_drift.py

This file is generated from `scripts/scan_nonexhaustive_invariant_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["lines = splitlines(...)"]
    N003["problems = []"]
    N004["for label, anchor in REGISTERED_BULLETS.items():
    matches = [(i, ln) for i, ln in enumerate(lines, start=1) if anchor in ln]
    if not matches:
        problems.append(f'<str>{label}<str>{anchor!r}<str>')
        continue
    for lineno, line in matches:
        if MARKER not in line:
            problems.append(f'<str>{path}<str>{lineno}<str>{MARKER!r}<str>{label}<str>')"]
    N005["return problems"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["master = Path(...)"]
    N003["if not master.is_file()"]
    N004["print(...)"]
    N005["return 2"]
    N006["problems = find_violations(...)"]
    N007["if problems"]
    N008["for problem in problems:
    print(problem, file=sys.stderr)"]
    N009["return 1"]
    N010["print(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["args = parse_args(...)"]
    N008["return int(args.func(args))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```
