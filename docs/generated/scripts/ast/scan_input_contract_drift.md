# AST graph: scripts/scan_input_contract_drift.py

This file is generated from `scripts/scan_input_contract_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## check_contract(...)

```mermaid
flowchart TD
    N001["check_contract(...)"]
    N002["if not docstring"]
    N003["return ['<str>']"]
    N004["defects = []"]
    N005["if not _CONTRACT_MARKER.search(docstring)"]
    N006["append(...)"]
    N007["if not _INPUTS.search(docstring)"]
    N008["append(...)"]
    N009["if not _OUTPUTS.search(docstring)"]
    N010["append(...)"]
    N011["match = search(...)"]
    N012["if match is None"]
    N013["append(...)"]
    N014["if not _POLICY_VALUE.search(match.group(1))"]
    N015["append(...)"]
    N016["return defects"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 -->|"true"| N015
    N013 --> N016
    N015 --> N016
    N014 -->|"false"| N016
```

## read_module_docstring(...)

```mermaid
flowchart TD
    N001["read_module_docstring(...)"]
    N002["try"]
    N003["tree = parse(...)"]
    N004["except (OSError, SyntaxError)"]
    N005["return None"]
    N006["return ast.get_docstring(tree)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
```

## collect_target_scripts(...)

```mermaid
flowchart TD
    N001["collect_target_scripts(...)"]
    N002["existing = {path.stem for path in scripts_dir.glob('<str>') if not path.name.startswith('<str>')}"]
    N003["referenced = set(...)"]
    N004["for path in sorted(workflows_dir.glob('<str>')):     referenced |= extract_script_refs(path.read_text(encoding='<str>'))"]
    N005["return referenced & existing"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["violations = []"]
    N003["for name in sorted(target_scripts):     if name in baseline:         continue     defects = check_contract(read_module_docstring(scripts_dir / f'{name}<str>'))     if defects:         violations.append((name, defects))"]
    N004["stale = []"]
    N005["for name in sorted(baseline):     if name not in target_scripts:         stale.append(name)         continue     if not check_contract(read_module_docstring(scripts_dir / f'{name}<str>')):         stale.append(name)"]
    N006["return (violations, stale)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["workflows_dir = Path(...)"]
    N003["scripts_dir = Path(...)"]
    N004["target = collect_target_scripts(...)"]
    N005["(violations, stale) = find_violations(...)"]
    N006["for name, defects in violations:     print(f'<str>{name}<str>{name}<str>{'<str>'.join(defects)}<str>', file=sys.stderr)"]
    N007["for name in stale:     print(f'<str>{name}<str>', file=sys.stderr)"]
    N008["if violations or stale"]
    N009["return 1"]
    N010["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
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
