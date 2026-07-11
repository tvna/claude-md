# AST graph: scripts/_auto_retro_ledger.py

This file is generated from `scripts/_auto_retro_ledger.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## render_row(...)

```mermaid
flowchart TD
    N001["render_row(...)"]
    N002["flag = '<str>' if row.repair_free else '<str>'"]
    N003["return f'<str>{row.pr_number}<str>{row.merged_at}<str>{flag}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## parse_rows(...)

```mermaid
flowchart TD
    N001["parse_rows(...)"]
    N002["open_idx = find(...)"]
    N003["close_idx = find(...)"]
    N004["if open_idx == -1 or close_idx == -1 or close_idx < open_idx"]
    N005["return []"]
    N006["block = body[open_idx:close_idx]"]
    N007["rows = []"]
    N008["for match in _ROW_RE.finditer(block):     number_s, merged_at, flag = match.groups()     rows.append(LedgerRow(pr_number=int(number_s), merged_at=merged_at, repair_free=flag == '<str>'))"]
    N009["return rows"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## insert_row(...)

```mermaid
flowchart TD
    N001["insert_row(...)"]
    N002["if any((row.pr_number == new_row.pr_number for row in rows))"]
    N003["return (rows, False)"]
    N004["return ([*rows, new_row], True)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _iso_week(...)

```mermaid
flowchart TD
    N001["_iso_week(...)"]
    N002["dt = replace(...)"]
    N003["(year, week, _weekday) = isocalendar(...)"]
    N004["return f'{year:<str>}<str>{week:<str>}'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _iso_week_monday(...)

```mermaid
flowchart TD
    N001["_iso_week_monday(...)"]
    N002["return datetime.strptime(f'{iso_week}<str>', '<str>').replace(tzinfo=UTC)"]
    N001 -->|"start"| N002
```

## _next_iso_week(...)

```mermaid
flowchart TD
    N001["_next_iso_week(...)"]
    N002["(year, week, _weekday) = isocalendar(...)"]
    N003["return f'{year:<str>}<str>{week:<str>}'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## compute_weekly_stats(...)

```mermaid
flowchart TD
    N001["compute_weekly_stats(...)"]
    N002["by_week = {}"]
    N003["for row in rows:     by_week.setdefault(_iso_week(row.merged_at), []).append(row)"]
    N004["if not by_week"]
    N005["return []"]
    N006["observed_weeks = sorted(...)"]
    N007["full_weeks = [observed_weeks[0]]"]
    N008["while full_weeks[-1] != observed_weeks[-1]:     full_weeks.append(_next_iso_week(full_weeks[-1]))"]
    N009["stats = []"]
    N010["window_rates = []"]
    N011["for week in full_weeks:     week_rows = by_week.get(week, [])     merges = len(week_rows)     if merges:         repair_free_count = sum((1 for r in week_rows if r.repair_free))         rate: float | None = repair_free_count / merges * 100.0     else:         repair_free_count = 0         rate = None     window_rates.append(rate)     trailing = [r for r in window_rates[-MOVING_AVERAGE_WINDOW:] if r is not None]     moving_avg = sum(trailing) / len(trailing) if len(window_rates) >= MOVING_AVERAGE_WINDOW and trailing else None     stats.append(WeeklyStat(week, merges, repair_free_count, rate, moving_avg))"]
    N012["return stats"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
```

## render_weekly_table(...)

```mermaid
flowchart TD
    N001["render_weekly_table(...)"]
    N002["total = len(...)"]
    N003["windowed = stats[-window:] if total > window else stats"]
    N004["lines = []"]
    N005["if total > window"]
    N006["append(...)"]
    N007["append(...)"]
    N008["append(...)"]
    N009["for stat in windowed:     rate = f'{stat.rate:<str>}<str>' if stat.rate is not None else '<str>'     avg = f'{stat.moving_avg:<str>}<str>' if stat.moving_avg is not None else '<str>'     lines.append(f'<str>{stat.iso_week}<str>{stat.merges}<str>{stat.repair_free_count}<str>{rate}<str>{avg}<str>')"]
    N010["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
```

## render_ledger_markdown(...)

```mermaid
flowchart TD
    N001["render_ledger_markdown(...)"]
    N002["stats = compute_weekly_stats(...)"]
    N003["rows_block = join(...)"]
    N004["return f'{LEDGER_TITLE}<str>{_STOP_RULE}<str>{render_weekly_table(stats)}<str>{_ROWS_OPEN}<str>{rows_block}<str>{_ROWS_CLOSE}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## upsert_ledger_markdown(...)

```mermaid
flowchart TD
    N001["upsert_ledger_markdown(...)"]
    N002["body = existing.decode('<str>') if existing is not None else '<str>'"]
    N003["rows = parse_rows(...)"]
    N004["(new_rows, changed) = insert_row(...)"]
    N005["if not changed"]
    N006["return (existing if existing is not None else b'', False)"]
    N007["return (render_ledger_markdown(new_rows).encode('<str>'), True)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```
