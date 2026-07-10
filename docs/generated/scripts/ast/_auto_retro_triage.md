# AST graph: scripts/_auto_retro_triage.py

This file is generated from `scripts/_auto_retro_triage.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## compute_prior_from_labels(...)

```mermaid
flowchart TD
    N001["compute_prior_from_labels(...)"]
    N002["eligible = past_retros if epoch_min_number <= 0 else [r for r in past_retros if r.number >= epoch_min_number]"]
    N003["prior = {}"]
    N004["for name in signal_names:     denom = sum((1 for r in eligible if name in r.signals))     if denom == 0:         prior[name] = (0.0, 0)         continue     numer = sum((1 for r in eligible if name in r.signals and RETRO_FP in r.labels))     prior[name] = (numer / denom, denom)"]
    N005["return prior"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _retro_status(...)

```mermaid
flowchart TD
    N001["_retro_status(...)"]
    N002["for label in _TRIAGE_LABELS:     if label in labels:         return label"]
    N003["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _retro_fp_rate(...)

```mermaid
flowchart TD
    N001["_retro_fp_rate(...)"]
    N002["triaged = [r for r in retros if RETRO_FP in r.labels or RETRO_TP in r.labels]"]
    N003["if not triaged"]
    N004["return (0.0, 0)"]
    N005["fp = sum(...)"]
    N006["return (fp / len(triaged), len(triaged))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## compute_triage_report(...)

```mermaid
flowchart TD
    N001["compute_triage_report(...)"]
    N002["total = len(...)"]
    N003["population_total = total if total_live is None else total_live"]
    N004["label_counts = {label: sum((1 for r in past_retros if label in r.labels)) for label in _TRIAGE_LABELS}"]
    N005["label_counts[_UNLABELLED_KEY] = sum(...)"]
    N006["prior = compute_prior_from_labels(...)"]
    N007["signal_stats = []"]
    N008["for name in signal_names:     fp_rate, sample = prior[name]     fp_count = round(fp_rate * sample)     fire_rate = sample / total if total else 0.0     signal_stats.append(SignalStat(name=name, fire_count=sample, fire_rate=fire_rate, fp_count=fp_count, fp_rate=fp_rate, sample_size=sample))"]
    N009["open_untriaged = sum(...)"]
    N010["by_recency = sorted(...)"]
    N011["recent = tuple(...)"]
    N012["(fp_rate_all, fp_triaged) = _retro_fp_rate(...)"]
    N013["(fp_rate_recent, fp_recent_triaged) = _retro_fp_rate(...)"]
    N014["return TriageReport(total=total, label_counts=label_counts, signal_stats=tuple(signal_stats), open_untriaged=open_untriaged, recent=recent, fp_rate_all=fp_rate_all, fp_triaged=fp_triaged, fp_rate_recent=fp_rate_recent, fp_recent_triaged=fp_recent_triaged, population_total=population_total)"]
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
    N013 --> N014
```

## render_triage_report_markdown(...)

```mermaid
flowchart TD
    N001["render_triage_report_markdown(...)"]
    N002["observed_line = f'<str>{report.total}<str>'"]
    N003["if report.truncated"]
    N004["observed_line = f'<str>{report.total}<str>{report.population_total}<str>'"]
    N005["lines = ['<str>', '<str>', '<str>', '<str>', observed_line, '<str>', f'<str>{report.open_untriaged}<str>', '<str>', '<str>', '<str>']"]
    N006["if report.anomalies"]
    N007["append(...)"]
    N008["append(...)"]
    N009["for stat in report.anomalies:     lines.append(f'<str>{stat.name}<str>{stat.fp_rate:<str>}<str>{stat.sample_size}<str>')"]
    N010["append(...)"]
    N011["extend(...)"]
    N012["if report.total == 0"]
    N013["append(...)"]
    N014["append(...)"]
    N015["append(...)"]
    N016["append(...)"]
    N017["for label in (*_TRIAGE_LABELS, _UNLABELLED_KEY):     lines.append(f'<str>{label}<str>{report.label_counts[label]}')"]
    N018["append(...)"]
    N019["extend(...)"]
    N020["for stat in report.signal_stats:     marker = '<str>' if stat.is_anomaly else '<str>'     lines.append(f'<str>{stat.name}<str>{stat.fire_count}<str>{stat.fire_rate:<str>}<str>{stat.fp_count}<str>{stat.fp_rate:<str>}<str>{stat.sample_size}<str>{marker}<str>')"]
    N021["extend(...)"]
    N022["extend(...)"]
    N023["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 --> N009
    N006 -->|"false"| N010
    N009 --> N011
    N010 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N013 --> N019
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
```

## _render_fp_trend(...)

```mermaid
flowchart TD
    N001["_render_fp_trend(...)"]
    N002["lines = ['<str>', '<str>', '<str>']"]
    N003["if report.fp_triaged == 0"]
    N004["append(...)"]
    N005["return lines"]
    N006["delta = report.fp_rate_recent - report.fp_rate_all"]
    N007["if report.fp_recent_triaged == 0"]
    N008["direction = '<str>'"]
    N009["if abs(delta) < 0.005"]
    N010["direction = '<str>'"]
    N011["if delta > 0"]
    N012["direction = '<str>'"]
    N013["direction = '<str>'"]
    N014["append(...)"]
    N015["append(...)"]
    N016["return lines"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N008 --> N014
    N010 --> N014
    N012 --> N014
    N013 --> N014
    N014 --> N015
    N015 --> N016
```

## _render_recent_retros(...)

```mermaid
flowchart TD
    N001["_render_recent_retros(...)"]
    N002["lines = ['<str>', '<str>', '<str>']"]
    N003["if not report.recent"]
    N004["append(...)"]
    N005["return lines"]
    N006["append(...)"]
    N007["append(...)"]
    N008["for r in report.recent:     title = r.title or '<str>'     lines.append(f'<str>{r.number}<str>{r.state}<str>{r.status}<str>{title}<str>')"]
    N009["return lines"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## _max_active_fp(...)

```mermaid
flowchart TD
    N001["_max_active_fp(...)"]
    N002["best = (0.0, None, 0)"]
    N003["for name, fired in signals.items():     if not fired:         continue     rate, sample = prior.get(name, (0.0, 0))     if sample < min_sample_size:         continue     if rate >= best[0]:         best = (rate, name, sample)"]
    N004["return best"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## should_skip_by_prior(...)

```mermaid
flowchart TD
    N001["should_skip_by_prior(...)"]
    N002["(rate, name, sample) = _max_active_fp(...)"]
    N003["if name is not None and rate >= skip_threshold"]
    N004["return (True, f'<str>{rate:<str>}<str>{name!r}<str>{sample}<str>{skip_threshold}')"]
    N005["return (False, '<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## is_tentative_by_prior(...)

```mermaid
flowchart TD
    N001["is_tentative_by_prior(...)"]
    N002["(rate, name, _sample) = _max_active_fp(...)"]
    N003["if name is None"]
    N004["return False"]
    N005["return tentative_threshold <= rate < skip_threshold"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```
