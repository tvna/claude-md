# AST graph: scripts/scan_doc_graph_registration.py

This file is generated from `scripts/scan_doc_graph_registration.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## classify_path(...)

```mermaid
flowchart TD
    N001["classify_path(...)"]
    N002["if file_path.startswith('docs/standards/') or file_path.startswith('docs/prd/')"]
    N003["return '<str>'"]
    N004["if file_path.startswith('docs/runbooks/')"]
    N005["return '<str>'"]
    N006["p = Path(...)"]
    N007["if p.parent == Path('scripts') and p.suffix == '.py'"]
    N008["return '<str>'"]
    N009["if p.parent == Path('.github/workflows') and p.suffix == '.yml'"]
    N010["return '<str>'"]
    N011["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## parse_waivers(...)

```mermaid
flowchart TD
    N001["parse_waivers(...)"]
    N002["return frozenset((m.group(1) for m in _WAIVER_RE.finditer(body)))"]
    N001 -->|"start"| N002
```

## get_added_files(...)

```mermaid
flowchart TD
    N001["get_added_files(...)"]
    N002["committed_result = run(...)"]
    N003["if committed_result.returncode != 0"]
    N004["return None"]
    N005["committed = {f.strip() for f in committed_result.stdout.splitlines() if f.strip()}"]
    N006["cached_result = run(...)"]
    N007["staged = {f.strip() for f in cached_result.stdout.splitlines() if f.strip()} if cached_result.returncode == 0 else set()"]
    N008["return sorted(committed | staged)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## registered_paths(...)

```mermaid
flowchart TD
    N001["registered_paths(...)"]
    N002["return frozenset((node.path for node in graph.nodes.values()))"]
    N001 -->|"start"| N002
```

## run_gate(...)

```mermaid
flowchart TD
    N001["run_gate(...)"]
    N002["if not added_files"]
    N003["print(...)"]
    N004["return True"]
    N005["passed = True"]
    N006["any_governed = False"]
    N007["for file_path in added_files:     severity = classify_path(file_path)     if severity is None:         continue     any_governed = True     if file_path in known_paths:         continue     if file_path in waivers:         print(f'<str>{file_path!r}<str>', file=sys.stderr)         continue     if severity == '<str>':         print(f'<str>{file_path}<str>{_SCRIPT}<str>{file_path!r}<str>{file_path!r}<str>{file_path}<str>', file=sys.stderr)         passed = False     else:         print(f'<str>{_SCRIPT}<str>{file_path!r}<str>{file_path}<str>', file=sys.stderr)"]
    N008["if passed"]
    N009["if any_governed"]
    N010["print(...)"]
    N011["print(...)"]
    N012["return passed"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N010 --> N012
    N011 --> N012
    N008 -->|"false"| N012
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["if argv is None"]
    N003["argv = sys.argv[1:]"]
    N004["command = argv[0] if argv else None"]
    N005["if command != 'verify'"]
    N006["print(...)"]
    N007["return 64"]
    N008["parser = ArgumentParser(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["add_argument(...)"]
    N013["args = parse_args(...)"]
    N014["graph_path = Path(...)"]
    N015["if not graph_path.exists()"]
    N016["print(...)"]
    N017["return 0"]
    N018["try"]
    N019["graph = load_graph(...)"]
    N020["except GraphValidationError"]
    N021["print(...)"]
    N022["return 1"]
    N023["body = '<str>'"]
    N024["if args.body_file"]
    N025["try"]
    N026["body = read_text(...)"]
    N027["except OSError"]
    N028["print(...)"]
    N029["body = get(...)"]
    N030["waivers = parse_waivers(...)"]
    N031["added_files = get_added_files(...)"]
    N032["if added_files is None"]
    N033["print(...)"]
    N034["return 0"]
    N035["known = registered_paths(...)"]
    N036["passed = run_gate(...)"]
    N037["return 0 if passed else 1"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N018
    N018 -->|"try"| N019
    N018 -->|"raises"| N020
    N020 --> N021
    N021 --> N022
    N019 --> N023
    N023 --> N024
    N024 -->|"true"| N025
    N025 -->|"try"| N026
    N025 -->|"raises"| N027
    N027 --> N028
    N024 -->|"false"| N029
    N026 --> N030
    N028 --> N030
    N029 --> N030
    N030 --> N031
    N031 --> N032
    N032 -->|"true"| N033
    N033 --> N034
    N032 -->|"false"| N035
    N035 --> N036
    N036 --> N037
```
