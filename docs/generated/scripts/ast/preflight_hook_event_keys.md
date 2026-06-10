# AST graph: scripts/preflight_hook_event_keys.py

This file is generated from `scripts/preflight_hook_event_keys.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## offending_event_keys(...)

```mermaid
flowchart TD
    N001["offending_event_keys(...)"]
    N002["if not isinstance(hooks, dict)"]
    N003["return []"]
    N004["return sorted((key for key in hooks if not PASCAL_CASE_RE.match(str(key))))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## check_file(...)

```mermaid
flowchart TD
    N001["check_file(...)"]
    N002["data = loads(...)"]
    N003["hooks = data.get('<str>') if isinstance(data, dict) else None"]
    N004["try"]
    N005["rel = relative_to(...)"]
    N006["except ValueError"]
    N007["rel = path"]
    N008["return [f'{rel}<str>{key!r}<str>' for key in offending_event_keys(hooks)]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N007 --> N008
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["violations = []"]
    N003["for rel in HOOK_CONFIG_FILES:
    path = REPO_ROOT / rel
    if not path.exists():
        violations.append(f'{rel}<str>')
        continue
    violations.extend(check_file(path))"]
    N004["if violations"]
    N005["for message in violations:
    print(f'<str>{message}', file=sys.stderr)"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["parse_args(...)"]
    N005["return verify()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```
