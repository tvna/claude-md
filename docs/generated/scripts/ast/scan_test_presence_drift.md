# AST graph: scripts/scan_test_presence_drift.py

This file is generated from `scripts/scan_test_presence_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## discover_scripts(...)

```mermaid
flowchart TD
    N001["discover_scripts(...)"]
    N002["return sorted((path.stem for path in scripts_dir.glob('<str>')))"]
    N001 -->|"start"| N002
```

## test_module_candidates(...)

```mermaid
flowchart TD
    N001["test_module_candidates(...)"]
    N002["candidates = [f'<str>{stem}<str>']"]
    N003["if stem.startswith('_')"]
    N004["append(...)"]
    N005["return tuple(candidates)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## has_test_module(...)

```mermaid
flowchart TD
    N001["has_test_module(...)"]
    N002["return any(((tests_dir / name).is_file() for name in test_module_candidates(stem)))"]
    N001 -->|"start"| N002
```

## module_imports(...)

```mermaid
flowchart TD
    N001["module_imports(...)"]
    N002["try"]
    N003["tree = parse(...)"]
    N004["except (OSError, SyntaxError)"]
    N005["return set()"]
    N006["names = set(...)"]
    N007["for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        names.update((alias.name.split('<str>')[0] for alias in node.names))
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        names.add(node.module.split('<str>')[0])"]
    N008["return names"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
```

## detect_github_api_scripts(...)

```mermaid
flowchart TD
    N001["detect_github_api_scripts(...)"]
    N002["detected = set(...)"]
    N003["for path in sorted(scripts_dir.glob('<str>')):
    if path.name.startswith('<str>'):
        continue
    if module_imports(path) & _GITHUB_API_BOUNDARY:
        detected.add(path.stem)"]
    N004["return detected"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## parse_contract_registry_scripts(...)

```mermaid
flowchart TD
    N001["parse_contract_registry_scripts(...)"]
    N002["try"]
    N003["tree = parse(...)"]
    N004["except (OSError, SyntaxError)"]
    N005["return set()"]
    N006["stems = set(...)"]
    N007["for node in ast.walk(tree):
    if isinstance(node, ast.AnnAssign):
        targets: list[ast.expr] = [node.target]
        value = node.value
    elif isinstance(node, ast.Assign):
        targets = list(node.targets)
        value = node.value
    else:
        continue
    if not any((isinstance(t, ast.Name) and t.id == '<str>' for t in targets)):
        continue
    if not isinstance(value, ast.Dict):
        continue
    for key in value.keys:
        if isinstance(key, ast.Tuple) and key.elts:
            first = key.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                stems.add(first.value.removesuffix('<str>'))"]
    N008["return stems"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
```

## find_missing_tests(...)

```mermaid
flowchart TD
    N001["find_missing_tests(...)"]
    N002["script_set = set(...)"]
    N003["missing = [stem for stem in scripts if stem not in allowlist and (not has_test_module(stem, tests_dir))]"]
    N004["stale = []"]
    N005["for stem in sorted(allowlist):
    if stem not in script_set or has_test_module(stem, tests_dir):
        stale.append(stem)"]
    N006["return (missing, stale)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## find_github_api_drift(...)

```mermaid
flowchart TD
    N001["find_github_api_drift(...)"]
    N002["undeclared = sorted(...)"]
    N003["stale_declared = sorted(...)"]
    N004["return (undeclared, stale_declared)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## find_missing_cli_contracts(...)

```mermaid
flowchart TD
    N001["find_missing_cli_contracts(...)"]
    N002["return sorted(workflow_scripts - registry_scripts)"]
    N001 -->|"start"| N002
```

## collect_workflow_scripts(...)

```mermaid
flowchart TD
    N001["collect_workflow_scripts(...)"]
    N002["existing = {path.stem for path in scripts_dir.glob('<str>') if not path.name.startswith('<str>')}"]
    N003["referenced = set(...)"]
    N004["for path in sorted(workflows_dir.glob('<str>')):
    referenced |= set(_SCRIPT_INVOCATION.findall(path.read_text(encoding='<str>')))"]
    N005["return referenced & existing"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["scripts_dir = Path(...)"]
    N003["tests_dir = Path(...)"]
    N004["workflows_dir = Path(...)"]
    N005["scripts = discover_scripts(...)"]
    N006["(missing, stale) = find_missing_tests(...)"]
    N007["detected_api = detect_github_api_scripts(...)"]
    N008["(undeclared_api, stale_api) = find_github_api_drift(...)"]
    N009["workflow_scripts = collect_workflow_scripts(...)"]
    N010["registry_scripts = parse_contract_registry_scripts(...)"]
    N011["missing_contract = find_missing_cli_contracts(...)"]
    N012["for stem in missing:
    print(f\"<str>{stem}<str>{stem}<str>{stem.lstrip('<str>')}<str>\", file=sys.stderr)"]
    N013["for stem in stale:
    print(f'<str>{stem}<str>', file=sys.stderr)"]
    N014["for stem in undeclared_api:
    print(f'<str>{stem}<str>{stem}<str>{stem}<str>', file=sys.stderr)"]
    N015["for stem in stale_api:
    print(f'<str>{stem}<str>', file=sys.stderr)"]
    N016["for stem in missing_contract:
    print(f'<str>{stem}<str>{stem}<str>{CONTRACT_TEST_MODULE}<str>', file=sys.stderr)"]
    N017["if missing or stale or undeclared_api or stale_api or missing_contract"]
    N018["return 1"]
    N019["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
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
    N007["add_argument(...)"]
    N008["set_defaults(...)"]
    N009["args = parse_args(...)"]
    N010["return args.func(args)"]
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
