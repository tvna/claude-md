# AST graph: scripts/script_dependency_graph.py

This file is generated from `scripts/script_dependency_graph.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## iter_script_paths(...)

```mermaid
flowchart TD
    N001["iter_script_paths(...)"]
    N002["scripts_dir = root / SCRIPTS_DIR"]
    N003["if not scripts_dir.is_dir()"]
    N004["return ()"]
    N005["return tuple(sorted((path for path in scripts_dir.glob('<str>') if path.is_file())))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## script_stems(...)

```mermaid
flowchart TD
    N001["script_stems(...)"]
    N002["return frozenset((path.stem for path in paths))"]
    N001 -->|"start"| N002
```

## _imported_top_levels(...)

```mermaid
flowchart TD
    N001["_imported_top_levels(...)"]
    N002["names = set(...)"]
    N003["for node in ast.walk(module):     if isinstance(node, ast.Import):         for alias in node.names:             names.add(alias.name.split('<str>')[0])     elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:         names.add(node.module.split('<str>')[0])"]
    N004["return frozenset(names)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## extract_sibling_imports(...)

```mermaid
flowchart TD
    N001["extract_sibling_imports(...)"]
    N002["module = parse(...)"]
    N003["return frozenset((name for name in _imported_top_levels(module) if name in stems and name != self_stem))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## dependency_edges(...)

```mermaid
flowchart TD
    N001["dependency_edges(...)"]
    N002["paths = iter_script_paths(...)"]
    N003["stems = script_stems(...)"]
    N004["edges = set(...)"]
    N005["for path in paths:     source = path.read_text(encoding='<str>')     for imported in extract_sibling_imports(source, stems, path.stem):         edges.add(DependencyEdge(importer=path.stem, imported=imported))"]
    N006["return tuple(sorted(edges))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _fan_in(...)

```mermaid
flowchart TD
    N001["_fan_in(...)"]
    N002["table = {}"]
    N003["for edge in edges:     table.setdefault(edge.imported, set()).add(edge.importer)"]
    N004["return {imported: sorted(importers) for imported, importers in table.items()}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _participating(...)

```mermaid
flowchart TD
    N001["_participating(...)"]
    N002["return frozenset((stem for edge in edges for stem in (edge.importer, edge.imported)))"]
    N001 -->|"start"| N002
```

## render_dependency_markdown(...)

```mermaid
flowchart TD
    N001["render_dependency_markdown(...)"]
    N002["lines = ['<str>', '<str>', '<str>', '<str>']"]
    N003["fan_in = _fan_in(...)"]
    N004["extend(...)"]
    N005["if not fan_in"]
    N006["extend(...)"]
    N007["extend(...)"]
    N008["for imported in sorted(fan_in, key=lambda name: (-len(fan_in[name]), name)):     importers = fan_in[imported]     importer_cells = '<str>'.join((f'<str>{name}<str>' for name in importers))     lines.append(f'<str>{imported}<str>{len(importers)}<str>{importer_cells}<str>')"]
    N009["append(...)"]
    N010["participating = _participating(...)"]
    N011["isolated = sorted(...)"]
    N012["extend(...)"]
    N013["if not isolated"]
    N014["extend(...)"]
    N015["append(...)"]
    N016["append(...)"]
    N017["append(...)"]
    N018["append(...)"]
    N019["extend(...)"]
    N020["if not edges"]
    N021["extend(...)"]
    N022["mermaid = ['<str>']"]
    N023["for edge in edges:     mermaid.append(f'<str>{edge.importer}<str>{edge.imported}')"]
    N024["extend(...)"]
    N025["return '<str>'.join(lines).rstrip() + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N014 --> N019
    N018 --> N019
    N019 --> N020
    N020 -->|"true"| N021
    N020 -->|"false"| N022
    N022 --> N023
    N023 --> N024
    N021 --> N025
    N024 --> N025
```

## build_document(...)

```mermaid
flowchart TD
    N001["build_document(...)"]
    N002["paths = iter_script_paths(...)"]
    N003["return render_dependency_markdown(dependency_edges(root), script_stems(paths))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## write_dependency_doc(...)

```mermaid
flowchart TD
    N001["write_dependency_doc(...)"]
    N002["target = root / DOC_PATH"]
    N003["mkdir(...)"]
    N004["write_text(...)"]
    N005["return target"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _cmd_all_doc(...)

```mermaid
flowchart TD
    N001["_cmd_all_doc(...)"]
    N002["write_dependency_doc(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_preview(...)

```mermaid
flowchart TD
    N001["_cmd_preview(...)"]
    N002["write(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_all_doc = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["p_preview = add_parser(...)"]
    N008["add_argument(...)"]
    N009["set_defaults(...)"]
    N010["args = parse_args(...)"]
    N011["return args.func(args)"]
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
```
