# AST graph: scripts/verify_test_shard_markers.py

This file is generated from `scripts/verify_test_shard_markers.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_shard_markers(...)

```mermaid
flowchart TD
    N001["extract_shard_markers(...)"]
    N002["tree = parse(...)"]
    N003["found = []"]
    N004["for node in tree.body:     if not isinstance(node, ast.Assign):         continue     targets = [t for t in node.targets if isinstance(t, ast.Name) and t.id == '<str>']     if not targets:         continue     value = node.value     candidates: list[ast.expr] = []     if isinstance(value, ast.List | ast.Tuple):         candidates = list(value.elts)     else:         candidates = [value]     for expr in candidates:         if not isinstance(expr, ast.Attribute):             continue         if not isinstance(expr.value, ast.Attribute):             continue         if expr.value.attr != '<str>':             continue         inner = expr.value.value         if not isinstance(inner, ast.Name) or inner.id != '<str>':             continue         if expr.attr.startswith('<str>'):             found.append(expr.attr)"]
    N005["return found"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## verify_file(...)

```mermaid
flowchart TD
    N001["verify_file(...)"]
    N002["try"]
    N003["source = read_text(...)"]
    N004["except OSError"]
    N005["return [f'<str>{path}<str>{exc}']"]
    N006["try"]
    N007["markers = extract_shard_markers(...)"]
    N008["except SyntaxError"]
    N009["return [f'<str>{path}<str>{exc}']"]
    N010["errors = []"]
    N011["if not markers"]
    N012["append(...)"]
    N013["return errors"]
    N014["if len(markers) > 1"]
    N015["append(...)"]
    N016["unknown = [m for m in markers if m not in ALLOWED_BUCKETS]"]
    N017["if unknown"]
    N018["append(...)"]
    N019["return errors"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N016
    N016 --> N017
    N017 -->|"true"| N018
    N018 --> N019
    N017 -->|"false"| N019
```

## collect_test_files(...)

```mermaid
flowchart TD
    N001["collect_test_files(...)"]
    N002["return sorted(tests_dir.glob('<str>'))"]
    N001 -->|"start"| N002
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["files = collect_test_files(...)"]
    N003["if not files"]
    N004["print(...)"]
    N005["return 1"]
    N006["all_errors = []"]
    N007["for path in files:     all_errors.extend(verify_file(path))"]
    N008["for line in all_errors:     print(line, file=sys.stderr)"]
    N009["if all_errors"]
    N010["return 1"]
    N011["print(...)"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["args = parse_args(...)"]
    N005["return verify(Path(args.tests_dir))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```
