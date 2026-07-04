# AST graph: scripts/audit_loop_engineering.py

This file is generated from `scripts/audit_loop_engineering.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## load_audit(...)

```mermaid
flowchart TD
    N001["load_audit(...)"]
    N002["doc = loads(...)"]
    N003["return (doc.get('<str>', {}), doc.get('<str>', []))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## detect(...)

```mermaid
flowchart TD
    N001["detect(...)"]
    N002["kind = check['<str>']"]
    N003["if kind == 'path_exists'"]
    N004["return (root / check['<str>']).exists()"]
    N005["if kind == 'glob_exists'"]
    N006["return any(root.glob(check['<str>']))"]
    N007["if kind == 'grep_in_glob'"]
    N008["pattern = check['<str>']"]
    N009["for path in root.glob(check['<str>']):     if path.is_file() and pattern in path.read_text(encoding='<str>', errors='<str>'):         return True"]
    N010["return False"]
    N011["raise ValueError(f'<str>{kind}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N009 --> N010
    N007 -->|"false"| N011
```

## computed_status(...)

```mermaid
flowchart TD
    N001["computed_status(...)"]
    N002["if not item.get('machine_checkable')"]
    N003["return None"]
    N004["return '<str>' if detect(item['<str>'], root) else '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## is_drift(...)

```mermaid
flowchart TD
    N001["is_drift(...)"]
    N002["if computed is None"]
    N003["return False"]
    N004["recorded = get(...)"]
    N005["return recorded in ('<str>', '<str>') and recorded != computed"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["rows = []"]
    N003["for item in items:     computed = computed_status(item, root)     rows.append((item, computed, is_drift(item, computed)))"]
    N004["return rows"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## render(...)

```mermaid
flowchart TD
    N001["render(...)"]
    N002["evaluated = evaluate(...)"]
    N003["lines = [f'<str>{meta.get('<str>', '<str>')}<str>', f'<str>{meta.get('<str>', '<str>')}<str>{meta.get('<str>', '<str>')}<str>{len(items)}', '<str>', f'{'<str>':<str>}<str>{'<str>':<str>}<str>{'<str>':<str>}<str>{'<str>':<str>}<str>']"]
    N004["for item, computed, drift in evaluated:     machine = '<str>' if computed is None else computed     flag = '<str>' if drift else '<str>'     lines.append(f'{item.get('<str>', '<str>'):<str>}<str>{item.get('<str>', '<str>'):<str>}<str>{item.get('<str>', '<str>'):<str>}<str>{machine:<str>}{flag}<str>{item.get('<str>', '<str>')}')"]
    N005["drifts = [item.get('<str>', '<str>') for item, _computed, drift in evaluated if drift]"]
    N006["lines += ['<str>', f'<str>{('<str>'.join(drifts) if drifts else '<str>')}']"]
    N007["return '<str>'.join(lines)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## run(...)

```mermaid
flowchart TD
    N001["run(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["run_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["args = parse_args(...)"]
    N008["(meta, items) = load_audit(...)"]
    N009["print(...)"]
    N010["return 0"]
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
