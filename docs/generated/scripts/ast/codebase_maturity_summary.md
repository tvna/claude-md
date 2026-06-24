# AST graph: scripts/codebase_maturity_summary.py

This file is generated from `scripts/codebase_maturity_summary.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _glob_files(...)

```mermaid
flowchart TD
    N001["_glob_files(...)"]
    N002["if not base.exists()"]
    N003["return []"]
    N004["return [p for p in sorted(base.glob(pattern)) if p.is_file()]"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## measure(...)

```mermaid
flowchart TD
    N001["measure(...)"]
    N002["sizes = find_module_sizes(...)"]
    N003["gate_scripts = [m for m in sizes if m.path.name.startswith(GATE_PREFIXES)]"]
    N004["active_over_budget = sum(...)"]
    N005["warn_band = sum(...)"]
    N006["deferred_over_budget = sum(...)"]
    N007["docs_dir = repo_root / '<str>'"]
    N008["doc_count = len([p for p in sorted(docs_dir.rglob('<str>')) if p.is_file()]) if docs_dir.exists() else 0"]
    N009["return MaturityReport(script_modules=len(sizes), script_total_lines=sum((m.line_count for m in sizes)), test_modules=len(_glob_files(repo_root / '<str>', '<str>')), workflow_count=len(_glob_files(repo_root / '<str>' / '<str>', '<str>')), doc_count=doc_count, ast_doc_count=len(_glob_files(repo_root / '<str>' / '<str>' / '<str>' / '<str>', '<str>')), gate_script_modules=len(gate_scripts), active_over_budget_modules=active_over_budget, warn_band_modules=warn_band, deferred_over_budget_modules=deferred_over_budget)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## render_markdown(...)

```mermaid
flowchart TD
    N001["render_markdown(...)"]
    N002["scale_rows = [('<str>', f'{report.script_modules}'), ('<str>', f'{report.script_total_lines}'), ('<str>', f'{report.test_modules}'), ('<str>', f'{report.workflow_count}'), ('<str>', f'{report.doc_count}')]"]
    N003["maturity_rows = [('<str>', f'{report.test_to_script_ratio:<str>}'), ('<str>', f'{report.ast_doc_coverage:<str>}<str>{report.ast_doc_count}<str>{report.script_modules}<str>'), ('<str>', f'{report.gate_script_modules}'), ('<str>', f'{report.active_over_budget_modules}'), ('<str>', f'{report.deferred_over_budget_modules}'), ('<str>', f'{report.warn_band_modules}')]"]
    N004["lines = ['<str>', '<str>']"]
    N005["append(...)"]
    N006["append(...)"]
    N007["extend(...)"]
    N008["append(...)"]
    N009["append(...)"]
    N010["append(...)"]
    N011["extend(...)"]
    N012["append(...)"]
    N013["return '<str>'.join(lines)"]
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
```

## _render_table(...)

```mermaid
flowchart TD
    N001["_render_table(...)"]
    N002["out = ['<str>', '<str>']"]
    N003["extend(...)"]
    N004["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _cmd_summary(...)

```mermaid
flowchart TD
    N001["_cmd_summary(...)"]
    N002["repo_root = resolve(...)"]
    N003["if not repo_root.exists()"]
    N004["print(...)"]
    N005["return 1"]
    N006["report = measure(...)"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_summary = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["args = parse_args(...)"]
    N008["return int(args.func(args))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```
