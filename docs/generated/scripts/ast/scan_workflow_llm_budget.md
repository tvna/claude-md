# AST graph: scripts/scan_workflow_llm_budget.py

This file is generated from `scripts/scan_workflow_llm_budget.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## load_policy(...)

```mermaid
flowchart TD
    N001["load_policy(...)"]
    N002["with path.open('<str>') as fh:     return tomllib.load(fh)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## extract_markers(...)

```mermaid
flowchart TD
    N001["extract_markers(...)"]
    N002["markers = get(...)"]
    N003["if not isinstance(markers, list)"]
    N004["return []"]
    N005["return [m['<str>'] for m in markers if isinstance(m, dict) and isinstance(m.get('<str>'), str)]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## extract_budgets(...)

```mermaid
flowchart TD
    N001["extract_budgets(...)"]
    N002["budgets = get(...)"]
    N003["if not isinstance(budgets, list)"]
    N004["return {}"]
    N005["result = {}"]
    N006["for entry in budgets:     if isinstance(entry, dict) and isinstance(entry.get('<str>'), str):         result[entry['<str>']] = entry"]
    N007["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## _is_finite_nonnegative(...)

```mermaid
flowchart TD
    N001["_is_finite_nonnegative(...)"]
    N002["return isinstance(value, int | float) and (not isinstance(value, bool)) and math.isfinite(value) and (value >= 0)"]
    N001 -->|"start"| N002
```

## _is_finite_positive(...)

```mermaid
flowchart TD
    N001["_is_finite_positive(...)"]
    N002["return isinstance(value, int | float) and (not isinstance(value, bool)) and math.isfinite(value) and (value > 0)"]
    N001 -->|"start"| N002
```

## missing_budget_keys(...)

```mermaid
flowchart TD
    N001["missing_budget_keys(...)"]
    N002["if budget is None"]
    N003["return [*_REQUIRED_BUDGET_KEYS, '<str>'.join(_COST_KEYS)]"]
    N004["missing = [key for key in _REQUIRED_BUDGET_KEYS if key not in budget or not _is_finite_nonnegative(budget[key])]"]
    N005["if not any((key in budget and _is_finite_positive(budget[key]) for key in _COST_KEYS))"]
    N006["append(...)"]
    N007["return missing"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
```

## scan_line(...)

```mermaid
flowchart TD
    N001["scan_line(...)"]
    N002["stripped = lstrip(...)"]
    N003["if stripped.startswith(_COMMENT_LINE_PREFIX)"]
    N004["return None"]
    N005["for pattern in markers:     if pattern in line:         return pattern"]
    N006["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## scan_text(...)

```mermaid
flowchart TD
    N001["scan_text(...)"]
    N002["hits = []"]
    N003["for lineno, line in flatten_shell_continuations(text):     pattern = scan_line(line, markers)     if pattern is not None:         hits.append((lineno, pattern))"]
    N004["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _iter_workflow_files(...)

```mermaid
flowchart TD
    N001["_iter_workflow_files(...)"]
    N002["for path in sorted(workflow_dir.rglob('<str>')):     if path.is_file() and path.suffix in ('<str>', '<str>'):         yield path"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## find_marker_hits(...)

```mermaid
flowchart TD
    N001["find_marker_hits(...)"]
    N002["workflow_dir = repo_root / WORKFLOW_SUBDIR"]
    N003["if not workflow_dir.exists() or not markers"]
    N004["return []"]
    N005["hits = []"]
    N006["for path in _iter_workflow_files(workflow_dir):     rel = path.relative_to(repo_root)     text = path.read_text(encoding='<str>', errors='<str>')     for lineno, pattern in scan_text(text, markers):         hits.append(MarkerHit(workflow=rel, lineno=lineno, pattern=pattern))"]
    N007["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["markers = extract_markers(...)"]
    N003["budgets = extract_budgets(...)"]
    N004["violations = []"]
    N005["for hit in find_marker_hits(repo_root, markers):     missing = missing_budget_keys(budgets.get(hit.workflow.name))     if missing:         violations.append((hit, missing))"]
    N006["return violations"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["policy_path = repo_root / args.policy"]
    N004["try"]
    N005["policy = load_policy(...)"]
    N006["except (OSError, tomllib.TOMLDecodeError)"]
    N007["print(...)"]
    N008["return 1"]
    N009["violations = find_violations(...)"]
    N010["for hit, missing in violations:     print(f'<str>{hit.workflow}<str>{hit.lineno}<str>{hit.pattern!r}<str>{args.policy}<str>{hit.workflow.name!r}<str>{'<str>'.join(missing)}<str>', file=sys.stderr)"]
    N011["if violations"]
    N012["print(...)"]
    N013["return 1"]
    N014["print(...)"]
    N015["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N007 --> N008
    N005 --> N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 --> N015
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
