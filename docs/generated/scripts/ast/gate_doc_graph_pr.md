# AST graph: scripts/gate_doc_graph_pr.py

This file is generated from `scripts/gate_doc_graph_pr.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## parse_waivers(...)

```mermaid
flowchart TD
    N001["parse_waivers(...)"]
    N002["return frozenset((m.group(1) for m in _WAIVER_RE.finditer(body)))"]
    N001 -->|"start"| N002
```

## get_changed_files(...)

```mermaid
flowchart TD
    N001["get_changed_files(...)"]
    N002["result = run(...)"]
    N003["if result.returncode != 0"]
    N004["print(...)"]
    N005["return []"]
    N006["return [f.strip() for f in result.stdout.splitlines() if f.strip()]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
```

## run_gate(...)

```mermaid
flowchart TD
    N001["run_gate(...)"]
    N002["if not changed_files"]
    N003["print(...)"]
    N004["return True"]
    N005["report = impact_report(...)"]
    N006["passed = True"]
    N007["for changed_node, required_node in report.required_co_changes:     if required_node.id in waivers:         print(f'<str>{required_node.path!r}<str>{required_node.id!r}<str>', file=sys.stderr)         continue     print(f'<str>{changed_node.path}<str>{_SCRIPT}<str>{changed_node.path!r}<str>{required_node.path!r}<str>{required_node.id!r}<str>{required_node.id}<str>', file=sys.stderr)     passed = False"]
    N008["for changed_node, noted_node, edge_type in report.advisory_notes:     print(f'<str>{edge_type}<str>{changed_node.path!r}<str>{noted_node.path!r}<str>', file=sys.stderr)"]
    N009["if passed"]
    N010["print(...)"]
    N011["return passed"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["args = parse_args(...)"]
    N007["graph_path = Path(...)"]
    N008["if not graph_path.exists()"]
    N009["print(...)"]
    N010["return 0"]
    N011["try"]
    N012["graph = load_graph(...)"]
    N013["except GraphValidationError"]
    N014["print(...)"]
    N015["return 1"]
    N016["body = '<str>'"]
    N017["if args.body_file"]
    N018["try"]
    N019["body = read_text(...)"]
    N020["except OSError"]
    N021["print(...)"]
    N022["body = get(...)"]
    N023["waivers = parse_waivers(...)"]
    N024["changed_files = get_changed_files(...)"]
    N025["passed = run_gate(...)"]
    N026["return 0 if passed else 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 -->|"try"| N012
    N011 -->|"raises"| N013
    N013 --> N014
    N014 --> N015
    N012 --> N016
    N016 --> N017
    N017 -->|"true"| N018
    N018 -->|"try"| N019
    N018 -->|"raises"| N020
    N020 --> N021
    N017 -->|"false"| N022
    N019 --> N023
    N021 --> N023
    N022 --> N023
    N023 --> N024
    N024 --> N025
    N025 --> N026
```
