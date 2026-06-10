# AST graph: scripts/compare_cache_regimes.py

This file is generated from `scripts/compare_cache_regimes.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _as_number(...)

```mermaid
flowchart TD
    N001["_as_number(...)"]
    N002["if isinstance(value, bool) or not isinstance(value, int | float)"]
    N003["raise InputError(f'{where}<str>{value!r}')"]
    N004["return float(value)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _resource_section(...)

```mermaid
flowchart TD
    N001["_resource_section(...)"]
    N002["match = search(...)"]
    N003["if match is None"]
    N004["return None"]
    N005["rest = body[match.end():]"]
    N006["nxt = search(...)"]
    N007["return rest if nxt is None else rest[:nxt.start()]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
```

## parse_pr_cost(...)

```mermaid
flowchart TD
    N001["parse_pr_cost(...)"]
    N002["section = _resource_section(...)"]
    N003["if section is None"]
    N004["raise InputError(f'{where}<str>')"]
    N005["match = search(...)"]
    N006["if match is None"]
    N007["if _COST_UNAVAILABLE in section"]
    N008["raise InputError(f'{where}<str>{_COST_UNAVAILABLE}<str>')"]
    N009["raise InputError(f'{where}<str>')"]
    N010["return float(match.group(1))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N006 -->|"false"| N010
```

## _first_table_cell(...)

```mermaid
flowchart TD
    N001["_first_table_cell(...)"]
    N002["inner = strip(...)"]
    N003["if not inner"]
    N004["return None"]
    N005["return inner.split('<str>', 1)[0].strip()"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## parse_retro_repairs(...)

```mermaid
flowchart TD
    N001["parse_retro_repairs(...)"]
    N002["lines = splitlines(...)"]
    N003["header_idx = next(...)"]
    N004["if header_idx is None"]
    N005["raise InputError(f'{where}<str>')"]
    N006["count = 0"]
    N007["for line in lines[header_idx + 1:]:     stripped = line.strip()     if not stripped.startswith('<str>'):         break     first = _first_table_cell(stripped)     if first is None:         break     if not first.isdigit() or int(first) <= 0:         continue     if _POLICY_ARTIFACT_MARKER in line and _ITERATION_COMMIT_REPAIR not in line:         continue     count += 1"]
    N008["return count"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
```

## _resolve_cost(...)

```mermaid
flowchart TD
    N001["_resolve_cost(...)"]
    N002["if 'cost' in pr"]
    N003["return _as_number(pr.get('<str>'), f'{where}<str>')"]
    N004["body = get(...)"]
    N005["if isinstance(body, str)"]
    N006["return parse_pr_cost(body, f'{where}<str>')"]
    N007["raise InputError(f'{where}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## _resolve_repairs(...)

```mermaid
flowchart TD
    N001["_resolve_repairs(...)"]
    N002["if 'repairs' in pr"]
    N003["return _as_number(pr.get('<str>'), f'{where}<str>')"]
    N004["body = get(...)"]
    N005["if isinstance(body, str)"]
    N006["return float(parse_retro_repairs(body, f'{where}<str>'))"]
    N007["raise InputError(f'{where}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## parse_regimes(...)

```mermaid
flowchart TD
    N001["parse_regimes(...)"]
    N002["if not isinstance(data, dict)"]
    N003["raise InputError('<str>')"]
    N004["regimes = get(...)"]
    N005["if not isinstance(regimes, list) or not regimes"]
    N006["raise InputError('<str>')"]
    N007["summaries = []"]
    N008["for idx, regime in enumerate(regimes):     if not isinstance(regime, dict):         raise InputError(f'<str>{idx}<str>')     name = regime.get('<str>')     if not isinstance(name, str) or not name:         raise InputError(f'<str>{idx}<str>')     prs = regime.get('<str>')     if not isinstance(prs, list) or not prs:         raise InputError(f'<str>{name!r}<str>')     total_cost = 0.0     total_repairs = 0.0     for j, pr in enumerate(prs):         if not isinstance(pr, dict):             raise InputError(f'<str>{name!r}<str>{j}<str>')         where = f'<str>{name!r}<str>{j}<str>'         total_cost += _resolve_cost(pr, where)         total_repairs += _resolve_repairs(pr, where)     n = len(prs)     summaries.append(RegimeSummary(name=name, n=n, cost_per_pr=total_cost / n, repairs_per_pr=total_repairs / n))"]
    N009["return summaries"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
```

## _delta(...)

```mermaid
flowchart TD
    N001["_delta(...)"]
    N002["diff = value - baseline"]
    N003["return f'{diff:<str>}'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## render_comparison(...)

```mermaid
flowchart TD
    N001["render_comparison(...)"]
    N002["baseline = summaries[0]"]
    N003["lines = ['<str>', '<str>', f'<str>{'<str>':<str>}<str>{'<str>':<str>}<str>{'<str>':<str>}<str>{'<str>':<str>}<str>{'<str>':<str>}<str>{'<str>':<str>}']"]
    N004["for s in summaries:     if s is baseline:         d_cost = d_rep = '<str>'     else:         d_cost = _delta(s.cost_per_pr, baseline.cost_per_pr)         d_rep = _delta(s.repairs_per_pr, baseline.repairs_per_pr)     lines.append(f'<str>{s.name:<str>}<str>{s.n:<str>}<str>{s.cost_per_pr:<str>}<str>{d_cost:<str>}<str>{s.repairs_per_pr:<str>}<str>{d_rep:<str>}')"]
    N005["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _load_input(...)

```mermaid
flowchart TD
    N001["_load_input(...)"]
    N002["try"]
    N003["raw = path.read_text(encoding='<str>') if path is not None else sys.stdin.read()"]
    N004["except OSError"]
    N005["raise InputError(f'<str>{exc}')"]
    N006["try"]
    N007["return json.loads(raw)"]
    N008["except (TypeError, ValueError)"]
    N009["raise InputError(f'<str>{exc}')"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
```

## _parse_args(...)

```mermaid
flowchart TD
    N001["_parse_args(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["return parser.parse_args(argv)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["args = _parse_args(...)"]
    N003["try"]
    N004["summaries = parse_regimes(...)"]
    N005["except InputError"]
    N006["print(...)"]
    N007["return 1"]
    N008["write(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 --> N009
```
