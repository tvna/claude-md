# AST graph: scripts/scan_workflow_action_pins.py

This file is generated from `scripts/scan_workflow_action_pins.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _is_local_ref(...)

```mermaid
flowchart TD
    N001["_is_local_ref(...)"]
    N002["return ref.startswith('<str>') or ref.startswith('<str>')"]
    N001 -->|"start"| N002
```

## _is_docker_ref(...)

```mermaid
flowchart TD
    N001["_is_docker_ref(...)"]
    N002["return ref.startswith('<str>')"]
    N001 -->|"start"| N002
```

## scan_line(...)

```mermaid
flowchart TD
    N001["scan_line(...)"]
    N002["if ACK_MARKER in line"]
    N003["return None"]
    N004["if _COMMENT_LINE.match(line)"]
    N005["return None"]
    N006["match = match(...)"]
    N007["if not match"]
    N008["return None"]
    N009["ref = group(...)"]
    N010["if _is_local_ref(ref) or _is_docker_ref(ref)"]
    N011["return None"]
    N012["if '@' not in ref"]
    N013["return f'<str>{ref!r}<str>'"]
    N014["(owner_repo, _, rev) = rpartition(...)"]
    N015["if not owner_repo"]
    N016["return f'<str>{ref!r}<str>'"]
    N017["if not _FULL_SHA.match(rev)"]
    N018["return f'<str>{ref!r}<str>{rev!r}<str>'"]
    N019["tag_match = search(...)"]
    N020["if not tag_match"]
    N021["return f'<str>{ref!r}<str>'"]
    N022["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
    N019 --> N020
    N020 -->|"true"| N021
    N020 -->|"false"| N022
```

## scan_text(...)

```mermaid
flowchart TD
    N001["scan_text(...)"]
    N002["out = []"]
    N003["for lineno, line in enumerate(text.splitlines(), start=1):
    reason = scan_line(line)
    if reason is not None:
        out.append((lineno, reason))"]
    N004["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
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
    for lineno, reason in scan_file(path):
        violations.append((rel, lineno, reason))"]
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
    N004["for rel, lineno, reason in violations:
    print(f'<str>{rel}<str>{lineno}<str>{reason}<str>{ACK_MARKER}<str>', file=sys.stderr)"]
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
