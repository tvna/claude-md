# AST graph: scripts/session_cost_structure.py

This file is generated from `scripts/session_cost_structure.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _coerce_int(...)

```mermaid
flowchart TD
    N001["_coerce_int(...)"]
    N002["if isinstance(value, bool) or not isinstance(value, int | float)"]
    N003["return 0"]
    N004["return max(0, int(value))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _message_usage(...)

```mermaid
flowchart TD
    N001["_message_usage(...)"]
    N002["if not isinstance(entry, dict)"]
    N003["return None"]
    N004["message = get(...)"]
    N005["if not isinstance(message, dict)"]
    N006["return None"]
    N007["usage = get(...)"]
    N008["if not isinstance(usage, dict)"]
    N009["return None"]
    N010["message_id = get(...)"]
    N011["return (message_id if isinstance(message_id, str) else '<str>', usage)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
```

## aggregate_usages(...)

```mermaid
flowchart TD
    N001["aggregate_usages(...)"]
    N002["by_id = {}"]
    N003["for entry in entries:
    found = _message_usage(entry)
    if found is not None:
        by_id[found[0]] = found[1]"]
    N004["input_t, output_t, read_t, write_5m, write_1h = 0"]
    N005["for usage in by_id.values():
    input_t += _coerce_int(usage.get('<str>'))
    output_t += _coerce_int(usage.get('<str>'))
    read_t += _coerce_int(usage.get('<str>'))
    creation = usage.get('<str>')
    if isinstance(creation, dict):
        write_5m += _coerce_int(creation.get('<str>'))
        write_1h += _coerce_int(creation.get('<str>'))
    else:
        write_5m += _coerce_int(usage.get('<str>'))"]
    N006["return Tokens(input=input_t, output=output_t, cache_read=read_t, cache_write_5m=write_5m, cache_write_1h=write_1h)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## compute_costs(...)

```mermaid
flowchart TD
    N001["compute_costs(...)"]
    N002["input_c = tokens.input / 1000000.0 * rates['<str>']"]
    N003["output_c = tokens.output / 1000000.0 * rates['<str>']"]
    N004["read_c = tokens.cache_read / 1000000.0 * rates['<str>']"]
    N005["write_5m_c = tokens.cache_write_5m / 1000000.0 * rates['<str>']"]
    N006["write_1h_c = tokens.cache_write_1h / 1000000.0 * rates['<str>']"]
    N007["return Costs(input=input_c, output=output_c, cache_read=read_c, cache_write_5m=write_5m_c, cache_write_1h=write_1h_c, total=input_c + output_c + read_c + write_5m_c + write_1h_c)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## load_transcript(...)

```mermaid
flowchart TD
    N001["load_transcript(...)"]
    N002["try"]
    N003["raw = read_text(...)"]
    N004["except OSError"]
    N005["return []"]
    N006["entries = []"]
    N007["for line in raw.splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        entries.append(json.loads(line))
    except json.JSONDecodeError:
        continue"]
    N008["return entries"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
```

## _slug_for(...)

```mermaid
flowchart TD
    N001["_slug_for(...)"]
    N002["return str(cwd).replace('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## discover_transcript(...)

```mermaid
flowchart TD
    N001["discover_transcript(...)"]
    N002["session_dir = projects_dir / _slug_for(cwd)"]
    N003["try"]
    N004["candidates = [p for p in session_dir.glob('<str>') if p.is_file()]"]
    N005["except OSError"]
    N006["return None"]
    N007["if not candidates"]
    N008["return None"]
    N009["return max(candidates, key=lambda p: p.stat().st_mtime)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N004 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## _run_ccusage_total(...)

```mermaid
flowchart TD
    N001["_run_ccusage_total(...)"]
    N002["if not session_id"]
    N003["return None"]
    N004["binary = which(...)"]
    N005["if binary is None"]
    N006["return None"]
    N007["try"]
    N008["proc = run(...)"]
    N009["except (OSError, subprocess.SubprocessError)"]
    N010["return None"]
    N011["if proc.returncode != 0"]
    N012["return None"]
    N013["try"]
    N014["data = loads(...)"]
    N015["except (TypeError, ValueError)"]
    N016["return None"]
    N017["rows = data.get('<str>') if isinstance(data, dict) else None"]
    N018["if not isinstance(rows, list)"]
    N019["return None"]
    N020["for row in rows:
    if isinstance(row, dict) and row.get('<str>') == session_id:
        cost = row.get('<str>')
        if isinstance(cost, int | float) and (not isinstance(cost, bool)):
            return float(cost)"]
    N021["return None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N008 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 -->|"try"| N014
    N013 -->|"raises"| N015
    N015 --> N016
    N014 --> N017
    N017 --> N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 --> N021
```

## agreement_pct(...)

```mermaid
flowchart TD
    N001["agreement_pct(...)"]
    N002["if reference <= 0"]
    N003["return None"]
    N004["return 100.0 - abs(derived - reference) / reference * 100.0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## render_report(...)

```mermaid
flowchart TD
    N001["render_report(...)"]
    N002["lines = ['<str>', '<str>']"]
    N003["total = costs.total"]
    N004["for key, label in _CATEGORY_LABELS:
    tok = getattr(tokens, key)
    cost = getattr(costs, key)
    share = cost / total * 100.0 if total > 0 else 0.0
    lines.append(f'<str>{label:<str>}<str>{tok:<str>}<str>{cost:<str>}<str>{share:<str>}<str>')"]
    N005["append(...)"]
    N006["append(...)"]
    N007["if ccusage_total is not None"]
    N008["pct = agreement_pct(...)"]
    N009["pct_txt = f'{pct:<str>}<str>' if pct is not None else '<str>'"]
    N010["append(...)"]
    N011["append(...)"]
    N012["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N007 -->|"false"| N012
```

## _build_rates(...)

```mermaid
flowchart TD
    N001["_build_rates(...)"]
    N002["rates = dict(...)"]
    N003["for key in rates:
    override = getattr(args, f'{key}<str>', None)
    if override is not None:
        rates[key] = override"]
    N004["return rates"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _parse_args(...)

```mermaid
flowchart TD
    N001["_parse_args(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["for key in _DEFAULT_RATES:
    parser.add_argument(f'<str>{key.replace('<str>', '<str>')}<str>', dest=f'{key}<str>', type=float, default=None, help=f'<str>{key}<str>{_DEFAULT_RATES[key]}<str>')"]
    N008["return parser.parse_args(argv)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["args = _parse_args(...)"]
    N003["transcript = args.transcript"]
    N004["if transcript is None"]
    N005["transcript = discover_transcript(...)"]
    N006["entries = load_transcript(transcript) if transcript is not None else []"]
    N007["tokens = aggregate_usages(...)"]
    N008["rates = _build_rates(...)"]
    N009["costs = compute_costs(...)"]
    N010["ccusage_total = _run_ccusage_total(args.session_id) if args.ccusage_check else None"]
    N011["write(...)"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
```
