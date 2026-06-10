# AST graph: scripts/script_ast_graph.py

This file is generated from `scripts/script_ast_graph.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

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

## _mermaid_text(...)

```mermaid
flowchart TD
    N001["_mermaid_text(...)"]
    N002["return text.replace('<str>', '<str>').replace('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## _safe_label_node(...)

```mermaid
flowchart TD
    N001["_safe_label_node(...)"]
    N002["class SafeLabelTransformer(ast.NodeTransformer):      def visit_Constant(self, node: ast.Constant) -> ast.AST:         if isinstance(node.value, str):             return ast.copy_location(ast.Constant(value='<str>'), node)         return node"]
    N003["return SafeLabelTransformer().visit(copy.deepcopy(node))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _ast_text(...)

```mermaid
flowchart TD
    N001["_ast_text(...)"]
    N002["if safe_strings"]
    N003["node = _safe_label_node(...)"]
    N004["return ast.unparse(node).strip()"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
```

## _called_name(...)

```mermaid
flowchart TD
    N001["_called_name(...)"]
    N002["if isinstance(node, ast.Call)"]
    N003["if isinstance(node.func, ast.Name)"]
    N004["return node.func.id"]
    N005["if isinstance(node.func, ast.Attribute)"]
    N006["return node.func.attr"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N002 -->|"false"| N007
```

## _stmt_label(...)

```mermaid
flowchart TD
    N001["_stmt_label(...)"]
    N002["if isinstance(stmt, ast.Assign)"]
    N003["targets = join(...)"]
    N004["called = _called_name(...)"]
    N005["if called is not None"]
    N006["return f'{targets}<str>{called}<str>'"]
    N007["return f'{targets}<str>{_ast_text(stmt.value, safe_strings=safe_strings)}'"]
    N008["if isinstance(stmt, ast.AnnAssign)"]
    N009["target = _ast_text(...)"]
    N010["if stmt.value is None"]
    N011["return target"]
    N012["called = _called_name(...)"]
    N013["if called is not None"]
    N014["return f'{target}<str>{called}<str>'"]
    N015["return f'{target}<str>{_ast_text(stmt.value, safe_strings=safe_strings)}'"]
    N016["if isinstance(stmt, ast.Expr)"]
    N017["called = _called_name(...)"]
    N018["if called is not None"]
    N019["return f'{called}<str>'"]
    N020["return _ast_text(stmt.value, safe_strings=safe_strings)"]
    N021["if isinstance(stmt, ast.Return)"]
    N022["return f'<str>{_ast_text(stmt.value, safe_strings=safe_strings)}' if stmt.value else '<str>'"]
    N023["if isinstance(stmt, ast.Raise)"]
    N024["return f'<str>{_ast_text(stmt.exc, safe_strings=safe_strings)}' if stmt.exc else '<str>'"]
    N025["if isinstance(stmt, ast.If)"]
    N026["return f'<str>{_ast_text(stmt.test, safe_strings=safe_strings)}'"]
    N027["if isinstance(stmt, ast.Try)"]
    N028["return '<str>'"]
    N029["return _ast_text(stmt, safe_strings=safe_strings)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N002 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N008 -->|"false"| N016
    N016 -->|"true"| N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N016 -->|"false"| N021
    N021 -->|"true"| N022
    N021 -->|"false"| N023
    N023 -->|"true"| N024
    N023 -->|"false"| N025
    N025 -->|"true"| N026
    N025 -->|"false"| N027
    N027 -->|"true"| N028
    N027 -->|"false"| N029
```

## _module_from_source(...)

```mermaid
flowchart TD
    N001["_module_from_source(...)"]
    N002["return ast.parse(source)"]
    N001 -->|"start"| N002
```

## _top_level_functions(...)

```mermaid
flowchart TD
    N001["_top_level_functions(...)"]
    N002["return tuple((stmt for stmt in module.body if isinstance(stmt, ast.FunctionDef)))"]
    N001 -->|"start"| N002
```

## build_function_graph_from_source(...)

```mermaid
flowchart TD
    N001["build_function_graph_from_source(...)"]
    N002["module = _module_from_source(...)"]
    N003["for function in _top_level_functions(module):     if function.name == function_name:         return AstGraphBuilder().build_function(function)"]
    N004["raise ValueError(f'<str>{function_name}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## build_function_graph(...)

```mermaid
flowchart TD
    N001["build_function_graph(...)"]
    N002["return build_function_graph_from_source(path.read_text(encoding='<str>'), function_name)"]
    N001 -->|"start"| N002
```

## build_script_graphs(...)

```mermaid
flowchart TD
    N001["build_script_graphs(...)"]
    N002["module = _module_from_source(...)"]
    N003["return tuple((AstGraphBuilder(safe_strings=safe_strings).build_function(function) for function in _top_level_functions(module)))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## render_mermaid(...)

```mermaid
flowchart TD
    N001["render_mermaid(...)"]
    N002["lines = ['<str>']"]
    N003["for node in graph.nodes:     lines.append(f'<str>{node.node_id}<str>{_mermaid_text(node.label)}<str>')"]
    N004["for edge in graph.edges:     if edge.label:         lines.append(f'<str>{edge.source}<str>{_mermaid_text(edge.label)}<str>{edge.target}')     else:         lines.append(f'<str>{edge.source}<str>{edge.target}')"]
    N005["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _safe_generated_doc_label(...)

```mermaid
flowchart TD
    N001["_safe_generated_doc_label(...)"]
    N002["return label.replace('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## _safe_generated_doc_graph(...)

```mermaid
flowchart TD
    N001["_safe_generated_doc_graph(...)"]
    N002["return FunctionGraph(name=graph.name, nodes=tuple((GraphNode(node.node_id, _safe_generated_doc_label(node.label)) for node in graph.nodes)), edges=graph.edges)"]
    N001 -->|"start"| N002
```

## render_script_ast_markdown(...)

```mermaid
flowchart TD
    N001["render_script_ast_markdown(...)"]
    N002["lines = [f'<str>{display_path}', '<str>', f'<str>{display_path}<str>', '<str>']"]
    N003["graphs = build_script_graphs(...)"]
    N004["if not graphs"]
    N005["extend(...)"]
    N006["for graph in graphs:     safe_graph = _safe_generated_doc_graph(graph)     lines.extend([f'<str>{graph.name}<str>', '<str>', '<str>', render_mermaid(safe_graph).rstrip(), '<str>', '<str>'])"]
    N007["return '<str>'.join(lines).rstrip() + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N005 --> N007
    N006 --> N007
```

## doc_filename_for(...)

```mermaid
flowchart TD
    N001["doc_filename_for(...)"]
    N002["return f'{path.stem}<str>'"]
    N001 -->|"start"| N002
```

## write_all_script_docs(...)

```mermaid
flowchart TD
    N001["write_all_script_docs(...)"]
    N002["out_dir = root / AST_DOC_DIR"]
    N003["mkdir(...)"]
    N004["written = []"]
    N005["expected = set(...)"]
    N006["for path in iter_script_paths(root):     display_path = path.relative_to(root) if path.is_absolute() else path     target = out_dir / doc_filename_for(path)     target.write_text(render_script_ast_markdown(path, display_path), encoding='<str>')     written.append(target)     expected.add(target.name)"]
    N007["for existing in sorted(out_dir.glob('<str>')):     if existing.name not in expected:         existing.unlink()"]
    N008["for legacy in LEGACY_DOC_PATHS:     legacy_path = root / legacy     if legacy_path.exists():         legacy_path.unlink()"]
    N009["return tuple(written)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## _cmd_auto_retro_decision_tree(...)

```mermaid
flowchart TD
    N001["_cmd_auto_retro_decision_tree(...)"]
    N002["write(...)"]
    N003["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _cmd_all_doc(...)

```mermaid
flowchart TD
    N001["_cmd_all_doc(...)"]
    N002["write_all_script_docs(...)"]
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
    N004["p_auto = add_parser(...)"]
    N005["set_defaults(...)"]
    N006["p_all_doc = add_parser(...)"]
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
