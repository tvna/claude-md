# AST graph: scripts/scan_scripts_gh_calls.py

This file is generated from `scripts/scan_scripts_gh_calls.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _argv_list_starts_with_gh(...)

```mermaid
flowchart TD
    N001["_argv_list_starts_with_gh(...)"]
    N002["if not node.elts"]
    N003["return False"]
    N004["first = node.elts[0]"]
    N005["return isinstance(first, ast.Constant) and first.value == '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## _str_command_is_gh(...)

```mermaid
flowchart TD
    N001["_str_command_is_gh(...)"]
    N002["if not isinstance(node, ast.Constant) or not isinstance(node.value, str)"]
    N003["return False"]
    N004["tokens = split(...)"]
    N005["return bool(tokens) and tokens[0] == '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## _is_subprocess_call(...)

```mermaid
flowchart TD
    N001["_is_subprocess_call(...)"]
    N002["func = node.func"]
    N003["if isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_FUNCS"]
    N004["return True"]
    N005["return bool(isinstance(func, ast.Name) and func.id in _SUBPROCESS_FUNCS)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _iter_violations_in_tree(...)

```mermaid
flowchart TD
    N001["_iter_violations_in_tree(...)"]
    N002["for node in ast.walk(tree):     if isinstance(node, ast.List | ast.Tuple) and _argv_list_starts_with_gh(node):         yield (node.lineno, '<str>')         continue     if isinstance(node, ast.Call) and _is_subprocess_call(node) and node.args and _str_command_is_gh(node.args[0]):         yield (node.lineno, '<str>')"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _iter_matches(...)

```mermaid
flowchart TD
    N001["_iter_matches(...)"]
    N002["self_name = Path(__file__).name"]
    N003["for path in sorted(scripts_dir.glob('<str>')):     if path.name == self_name:         continue     try:         tree = ast.parse(path.read_text(encoding='<str>'))     except (OSError, SyntaxError):         continue     for line, fragment in _iter_violations_in_tree(tree):         yield Violation(script=path.name, line=line, fragment=fragment)"]
    N004["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["return [v for v in _iter_matches(scripts_dir) if v.script not in ALLOWLIST_SCRIPTS]"]
    N001 -->|"start"| N002
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["add_parser(...)"]
    N005["add_parser(...)"]
    N006["args = parse_args(...)"]
    N007["if args.cmd == 'list'"]
    N008["for v in _iter_matches(SCRIPTS_DIR):     status = '<str>' if v.script in ALLOWLIST_SCRIPTS else '<str>'     print(f'<str>{status}<str>{v.script}<str>{v.line}<str>{v.fragment}')"]
    N009["return 0"]
    N010["violations = find_violations(...)"]
    N011["if not violations"]
    N012["return 0"]
    N013["for v in violations:     print(f'<str>{v.script}<str>{v.line}<str>{v.fragment}<str>{v.script}<str>', file=sys.stderr)"]
    N014["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
```
