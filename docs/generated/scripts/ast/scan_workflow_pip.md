# AST graph: scripts/scan_workflow_pip.py

This file is generated from `scripts/scan_workflow_pip.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## scan_line(...)

```mermaid
flowchart TD
    N001["scan_line(...)"]
    N002["if ACK_MARKER in line"]
    N003["return False"]
    N004["if _COMMENT_LINE.match(line)"]
    N005["return False"]
    N006["return _PIP_INSTALL.search(line) is not None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## scan_text(...)

```mermaid
flowchart TD
    N001["scan_text(...)"]
    N002["return [lineno for lineno, line in enumerate(text.splitlines(), start=1) if scan_line(line)]"]
    N001 -->|"start"| N002
```

## scan_file(...)

```mermaid
flowchart TD
    N001["scan_file(...)"]
    N002["return scan_text(path.read_text(encoding='<str>', errors='<str>'))"]
    N001 -->|"start"| N002
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["workflow_dir = repo_root / WORKFLOW_SUBDIR"]
    N003["if not workflow_dir.exists()"]
    N004["return []"]
    N005["violations = []"]
    N006["for path in _iter_workflow_files(workflow_dir):
    rel = path.relative_to(repo_root)
    for lineno in scan_file(path):
        violations.append((rel, lineno))"]
    N007["return violations"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## _iter_workflow_files(...)

```mermaid
flowchart TD
    N001["_iter_workflow_files(...)"]
    N002["for path in sorted(workflow_dir.rglob('<str>')):
    if path.is_file() and path.suffix in ('<str>', '<str>'):
        yield path"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["violations = find_violations(...)"]
    N004["for rel, lineno in violations:
    print(f'<str>{rel}<str>{lineno}<str>{ACK_MARKER}<str>', file=sys.stderr)"]
    N005["if violations"]
    N006["print(...)"]
    N007["return 1"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
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
    N008["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```
