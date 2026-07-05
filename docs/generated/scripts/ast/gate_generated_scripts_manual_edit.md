# AST graph: scripts/gate_generated_scripts_manual_edit.py

This file is generated from `scripts/gate_generated_scripts_manual_edit.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _is_protected(...)

```mermaid
flowchart TD
    N001["_is_protected(...)"]
    N002["return path.startswith(_PROTECTED_FOLDER_PREFIXES) or path in _PROTECTED_EXACT_FILES"]
    N001 -->|"start"| N002
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

## resolve_branch(...)

```mermaid
flowchart TD
    N001["resolve_branch(...)"]
    N002["if explicit"]
    N003["return explicit"]
    N004["head_ref = get(...)"]
    N005["if head_ref"]
    N006["return head_ref"]
    N007["try"]
    N008["result = _run(...)"]
    N009["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError)"]
    N010["return '<str>'"]
    N011["return result.stdout.strip()"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
```

## changed_generated_docs(...)

```mermaid
flowchart TD
    N001["changed_generated_docs(...)"]
    N002["result = _run(...)"]
    N003["touched = set(...)"]
    N004["for line in result.stdout.splitlines():     if not line.strip():         continue     parts = line.split('<str>')     status = parts[0]     if status.startswith('<str>') and len(parts) == 3:         old_path, new_path = (parts[1], parts[2])         if not _is_protected(old_path) and new_path in _PROTECTED_EXACT_FILES:             continue         touched.update((p for p in (old_path, new_path) if _is_protected(p)))     elif len(parts) == 2:         path = parts[1]         if _is_protected(path):             touched.add(path)"]
    N005["return frozenset(touched)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## is_exempt(...)

```mermaid
flowchart TD
    N001["is_exempt(...)"]
    N002["return branch in EXEMPT_BRANCHES"]
    N001 -->|"start"| N002
```

## evaluate(...)

```mermaid
flowchart TD
    N001["evaluate(...)"]
    N002["if not changed"]
    N003["return (0, [])"]
    N004["if is_exempt(branch)"]
    N005["return (0, [])"]
    N006["pretty = join(...)"]
    N007["return (1, [f'<str>{branch or '<str>'!r}<str>{pretty}<str>'])"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["base = args.base_ref or resolve_base()"]
    N003["branch = resolve_branch(...)"]
    N004["try"]
    N005["changed = changed_generated_docs(...)"]
    N006["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError)"]
    N007["print(...)"]
    N008["return 1"]
    N009["(code, errors) = evaluate(...)"]
    N010["if code == 0"]
    N011["if changed"]
    N012["pretty = join(...)"]
    N013["print(...)"]
    N014["print(...)"]
    N015["return 0"]
    N016["for line in errors:     print(line, file=sys.stderr)"]
    N017["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N007 --> N008
    N005 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N013 --> N015
    N014 --> N015
    N010 -->|"false"| N016
    N016 --> N017
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

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["return runner(cmd, capture_output=True, text=True, check=True)"]
    N001 -->|"start"| N002
```
