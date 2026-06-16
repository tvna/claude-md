# AST graph: scripts/doc_graph.py

This file is generated from `scripts/doc_graph.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## load_graph(...)

```mermaid
flowchart TD
    N001["load_graph(...)"]
    N002["with path.open('<str>') as fh:     data = tomllib.load(fh)"]
    N003["graph = DocGraph(...)"]
    N004["for raw in data.get('<str>', []):     node_type = raw.get('<str>', '<str>')     if node_type not in VALID_NODE_TYPES:         raise GraphValidationError(f'<str>{node_type!r}<str>{raw.get('<str>')!r}<str>{sorted(VALID_NODE_TYPES)}')     node_id = raw['<str>']     if node_id in graph.nodes:         raise GraphValidationError(f'<str>{node_id!r}')     graph.nodes[node_id] = DocNode(id=node_id, path=raw['<str>'], type=node_type, description=raw.get('<str>', '<str>'))"]
    N005["for raw in data.get('<str>', []):     from_id = raw['<str>']     to_id = raw['<str>']     edge_type = raw.get('<str>', '<str>')     severity = raw.get('<str>', '<str>')     if from_id not in graph.nodes:         raise GraphValidationError(f'<str>{from_id!r}')     if to_id not in graph.nodes:         raise GraphValidationError(f'<str>{to_id!r}')     if edge_type not in VALID_EDGE_TYPES:         raise GraphValidationError(f'<str>{edge_type!r}<str>{sorted(VALID_EDGE_TYPES)}')     if severity not in VALID_SEVERITIES:         raise GraphValidationError(f'<str>{severity!r}<str>{sorted(VALID_SEVERITIES)}')     graph.edges.append(DocEdge(from_id=from_id, to_id=to_id, type=edge_type, severity=severity, note=raw.get('<str>', '<str>')))"]
    N006["return graph"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## impact_report(...)

```mermaid
flowchart TD
    N001["impact_report(...)"]
    N002["changed_paths = frozenset(...)"]
    N003["required = []"]
    N004["advisory = []"]
    N005["for file_path in changed_files:     node = graph.node_for_path(file_path)     if node is None:         continue     for dep in graph.blocking_dependents(node.id):         if dep.path not in changed_paths:             required.append((node, dep))     for dep, edge_type in graph.advisory_dependents(node.id):         advisory.append((node, dep, edge_type))"]
    N006["return ImpactReport(required_co_changes=required, advisory_notes=advisory)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## render_mermaid(...)

```mermaid
flowchart TD
    N001["render_mermaid(...)"]
    N002["lines = ['<str>', '<str>']"]
    N003["for node in graph.nodes.values():     open_bracket, close_bracket = _MERMAID_SHAPES.get(node.type, ('<str>', '<str>'))     label = node.id.replace('<str>', '<str>')     lines.append(f'<str>{node.id}{open_bracket}<str>{label}<str>{close_bracket}')"]
    N004["for edge in graph.edges:     arrow = _MERMAID_ARROWS.get((edge.severity, edge.type), '<str>')     lines.append(f'<str>{edge.from_id}<str>{arrow}<str>{edge.to_id}')"]
    N005["append(...)"]
    N006["return '<str>'.join(lines)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```
