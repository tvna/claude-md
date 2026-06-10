# AST graph: scripts/analyze_ci_timings.py

This file is generated from `scripts/analyze_ci_timings.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _parse_iso(...)

```mermaid
flowchart TD
    N001["_parse_iso(...)"]
    N002["return datetime.strptime(ts, _GH_TS_FORMAT).replace(tzinfo=UTC)"]
    N001 -->|"start"| N002
```

## _duration_seconds(...)

```mermaid
flowchart TD
    N001["_duration_seconds(...)"]
    N002["if not start or not end"]
    N003["return None"]
    N004["try"]
    N005["delta = total_seconds(...)"]
    N006["except ValueError"]
    N007["return None"]
    N008["if delta < 0"]
    N009["return None"]
    N010["return delta"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
```

## _percentile(...)

```mermaid
flowchart TD
    N001["_percentile(...)"]
    N002["if not values"]
    N003["return 0.0"]
    N004["ordered = sorted(...)"]
    N005["if len(ordered) == 1"]
    N006["return ordered[0]"]
    N007["k = (len(ordered) - 1) * (p / 100.0)"]
    N008["lo = int(...)"]
    N009["hi = min(...)"]
    N010["frac = k - lo"]
    N011["return ordered[lo] + (ordered[hi] - ordered[lo]) * frac"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
```

## _trend_arrow(...)

```mermaid
flowchart TD
    N001["_trend_arrow(...)"]
    N002["last = samples_chronological[-5:]"]
    N003["if len(last) < 2"]
    N004["return '<str>'"]
    N005["mid = len(last) // 2"]
    N006["older = last[:mid] if mid else last[:1]"]
    N007["newer = last[mid:]"]
    N008["older_med = median(...)"]
    N009["newer_med = median(...)"]
    N010["if older_med == 0"]
    N011["return '<str>' if newer_med == 0 else '<str>'"]
    N012["ratio = newer_med / older_med"]
    N013["if ratio > 1.1"]
    N014["return '<str>'"]
    N015["if ratio < 0.9"]
    N016["return '<str>'"]
    N017["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
```

## _expand_paths(...)

```mermaid
flowchart TD
    N001["_expand_paths(...)"]
    N002["for p in paths:
    if p.is_dir():
        yield from sorted(p.glob('<str>'))
    else:
        yield p"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## load_jobs(...)

```mermaid
flowchart TD
    N001["load_jobs(...)"]
    N002["out = []"]
    N003["for path in _expand_paths(paths):
    text = path.read_text(encoding='<str>')
    data = json.loads(text)
    if not isinstance(data, dict):
        continue
    jobs = data.get('<str>')
    if not isinstance(jobs, list):
        continue
    for j in jobs:
        if isinstance(j, dict):
            out.append(j)"]
    N004["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## filter_jobs(...)

```mermaid
flowchart TD
    N001["filter_jobs(...)"]
    N002["out = []"]
    N003["for j in jobs:
    if workflow_name is not None and j.get('<str>') != workflow_name:
        continue
    if job_name is not None and j.get('<str>') != job_name:
        continue
    if since is not None:
        start = j.get('<str>')
        if not isinstance(start, str):
            continue
        try:
            started = _parse_iso(start)
        except ValueError:
            continue
        if started < since:
            continue
    out.append(j)"]
    N004["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## aggregate_job_durations(...)

```mermaid
flowchart TD
    N001["aggregate_job_durations(...)"]
    N002["bucket = {}"]
    N003["for j in jobs:
    name = j.get('<str>')
    start_raw = j.get('<str>')
    end_raw = j.get('<str>')
    if not isinstance(name, str) or not isinstance(start_raw, str):
        continue
    if not isinstance(end_raw, str):
        continue
    dur = _duration_seconds(start_raw, end_raw)
    if dur is None:
        continue
    try:
        started = _parse_iso(start_raw)
    except ValueError:
        continue
    bucket.setdefault(name, []).append((started, dur))"]
    N004["for v in bucket.values():
    v.sort(key=lambda t: t[0])"]
    N005["return bucket"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## aggregate_step_durations(...)

```mermaid
flowchart TD
    N001["aggregate_step_durations(...)"]
    N002["bucket = {}"]
    N003["for j in jobs:
    job_name = j.get('<str>')
    if not isinstance(job_name, str):
        continue
    steps = j.get('<str>')
    if not isinstance(steps, list):
        continue
    for s in steps:
        if not isinstance(s, dict):
            continue
        step_name = s.get('<str>')
        start_raw = s.get('<str>')
        end_raw = s.get('<str>')
        if not isinstance(step_name, str) or not isinstance(start_raw, str):
            continue
        if not isinstance(end_raw, str):
            continue
        dur = _duration_seconds(start_raw, end_raw)
        if dur is None:
            continue
        try:
            started = _parse_iso(start_raw)
        except ValueError:
            continue
        bucket.setdefault((job_name, step_name), []).append((started, dur))"]
    N004["for v in bucket.values():
    v.sort(key=lambda t: t[0])"]
    N005["return bucket"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## partition_aggregates_by_cutoff(...)

```mermaid
flowchart TD
    N001["partition_aggregates_by_cutoff(...)"]
    N002["pre = {}"]
    N003["post = {}"]
    N004["for key, samples in aggregates.items():
    for ts, val in samples:
        if ts < cutoff:
            pre.setdefault(key, []).append(val)
        else:
            post.setdefault(key, []).append(val)"]
    N005["return (pre, post)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _delta_p50_marker(...)

```mermaid
flowchart TD
    N001["_delta_p50_marker(...)"]
    N002["if not pre_samples and (not post_samples)"]
    N003["return '<str>'"]
    N004["if not pre_samples"]
    N005["return '<str>'"]
    N006["if not post_samples"]
    N007["return '<str>'"]
    N008["pre_p50 = _percentile(...)"]
    N009["post_p50 = _percentile(...)"]
    N010["if pre_p50 == 0"]
    N011["return '<str>' if post_p50 > 0 else '<str>'"]
    N012["pct = (post_p50 - pre_p50) / pre_p50 * 100.0"]
    N013["sign = '<str>' if pct >= 0 else '<str>'"]
    N014["return f'{sign}{pct:<str>}<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
```

## _fmt_seconds(...)

```mermaid
flowchart TD
    N001["_fmt_seconds(...)"]
    N002["return f'{value:<str>}'"]
    N001 -->|"start"| N002
```

## _render_job_table(...)

```mermaid
flowchart TD
    N001["_render_job_table(...)"]
    N002["rows = []"]
    N003["append(...)"]
    N004["append(...)"]
    N005["for name in sorted(aggregates):
    samples = [v for _, v in aggregates[name]]
    rows.append(f'<str>{name}<str>{len(samples)}<str>{_fmt_seconds(_percentile(samples, 50))}<str>{_fmt_seconds(_percentile(samples, 95))}<str>{_fmt_seconds(max(samples))}<str>{_trend_arrow(samples)}<str>')"]
    N006["return '<str>'.join(rows)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _render_step_table(...)

```mermaid
flowchart TD
    N001["_render_step_table(...)"]
    N002["rows = []"]
    N003["append(...)"]
    N004["append(...)"]
    N005["for key in sorted(aggregates):
    job_name, step_name = key
    samples = [v for _, v in aggregates[key]]
    rows.append(f'<str>{job_name}<str>{step_name}<str>{len(samples)}<str>{_fmt_seconds(_percentile(samples, 50))}<str>{_fmt_seconds(_percentile(samples, 95))}<str>{_fmt_seconds(max(samples))}<str>{_trend_arrow(samples)}<str>')"]
    N006["return '<str>'.join(rows)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _render_compare_job_table(...)

```mermaid
flowchart TD
    N001["_render_compare_job_table(...)"]
    N002["rows = []"]
    N003["append(...)"]
    N004["append(...)"]
    N005["for name in sorted(set(pre) | set(post)):
    pre_samples = pre.get(name, [])
    post_samples = post.get(name, [])
    rows.append(f'<str>{name}<str>{len(pre_samples)}<str>{_fmt_seconds(_percentile(pre_samples, 50))}<str>{len(post_samples)}<str>{_fmt_seconds(_percentile(post_samples, 50))}<str>{_delta_p50_marker(pre_samples, post_samples)}<str>')"]
    N006["return '<str>'.join(rows)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _render_compare_step_table(...)

```mermaid
flowchart TD
    N001["_render_compare_step_table(...)"]
    N002["rows = []"]
    N003["append(...)"]
    N004["append(...)"]
    N005["for key in sorted(set(pre) | set(post)):
    job_name, step_name = key
    pre_samples = pre.get(key, [])
    post_samples = post.get(key, [])
    rows.append(f'<str>{job_name}<str>{step_name}<str>{len(pre_samples)}<str>{_fmt_seconds(_percentile(pre_samples, 50))}<str>{len(post_samples)}<str>{_fmt_seconds(_percentile(post_samples, 50))}<str>{_delta_p50_marker(pre_samples, post_samples)}<str>')"]
    N006["return '<str>'.join(rows)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## budget_breaches(...)

```mermaid
flowchart TD
    N001["budget_breaches(...)"]
    N002["out = []"]
    N003["for name, samples in job_agg.items():
    durations = [v for _, v in samples]
    if not durations:
        continue
    p50 = _percentile(durations, 50)
    if p50 > budget_seconds:
        out.append((name, p50))"]
    N004["return sorted(out, key=lambda item: item[1], reverse=True)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## budget_breach_payload(...)

```mermaid
flowchart TD
    N001["budget_breach_payload(...)"]
    N002["breaches = budget_breaches(...)"]
    N003["return {'<str>': budget_seconds, '<str>': [{'<str>': name, '<str>': p50} for name, p50 in breaches]}"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _render_budget_section(...)

```mermaid
flowchart TD
    N001["_render_budget_section(...)"]
    N002["parts = []"]
    N003["append(...)"]
    N004["append(...)"]
    N005["breaches = budget_breaches(...)"]
    N006["if not breaches"]
    N007["append(...)"]
    N008["return '<str>'.join(parts)"]
    N009["append(...)"]
    N010["append(...)"]
    N011["append(...)"]
    N012["append(...)"]
    N013["for name, p50 in breaches:
    parts.append(f'<str>{name}<str>{_fmt_seconds(p50)}<str>{_fmt_seconds(budget_seconds)}<str>')"]
    N014["return '<str>'.join(parts)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
```

## render_report(...)

```mermaid
flowchart TD
    N001["render_report(...)"]
    N002["if cutoff is None"]
    N003["return _render_single_window_report(jobs, title=title, budget_seconds=budget_seconds)"]
    N004["return _render_compare_report(jobs, title=title, cutoff=cutoff)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _render_single_window_report(...)

```mermaid
flowchart TD
    N001["_render_single_window_report(...)"]
    N002["job_agg = aggregate_job_durations(...)"]
    N003["step_agg = aggregate_step_durations(...)"]
    N004["parts = []"]
    N005["append(...)"]
    N006["append(...)"]
    N007["append(...)"]
    N008["append(...)"]
    N009["append(...)"]
    N010["append(...)"]
    N011["if job_agg"]
    N012["append(...)"]
    N013["append(...)"]
    N014["append(...)"]
    N015["append(...)"]
    N016["append(...)"]
    N017["if step_agg"]
    N018["append(...)"]
    N019["append(...)"]
    N020["append(...)"]
    N021["if budget_seconds is not None"]
    N022["append(...)"]
    N023["append(...)"]
    N024["append(...)"]
    N025["return '<str>'.join(parts)"]
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
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N012 --> N014
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
    N018 --> N020
    N019 --> N020
    N020 --> N021
    N021 -->|"true"| N022
    N022 --> N023
    N023 --> N024
    N021 -->|"false"| N024
    N024 --> N025
```

## _render_compare_report(...)

```mermaid
flowchart TD
    N001["_render_compare_report(...)"]
    N002["job_agg = aggregate_job_durations(...)"]
    N003["step_agg = aggregate_step_durations(...)"]
    N004["(pre_jobs, post_jobs) = partition_aggregates_by_cutoff(...)"]
    N005["(pre_steps, post_steps) = partition_aggregates_by_cutoff(...)"]
    N006["pre_total = sum(...)"]
    N007["post_total = sum(...)"]
    N008["cutoff_iso = strftime(...)"]
    N009["parts = []"]
    N010["append(...)"]
    N011["append(...)"]
    N012["append(...)"]
    N013["append(...)"]
    N014["append(...)"]
    N015["append(...)"]
    N016["if pre_jobs or post_jobs"]
    N017["append(...)"]
    N018["append(...)"]
    N019["append(...)"]
    N020["append(...)"]
    N021["append(...)"]
    N022["if pre_steps or post_steps"]
    N023["append(...)"]
    N024["append(...)"]
    N025["append(...)"]
    N026["append(...)"]
    N027["return '<str>'.join(parts)"]
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
    N014 --> N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N017 --> N019
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 -->|"true"| N023
    N022 -->|"false"| N024
    N023 --> N025
    N024 --> N025
    N025 --> N026
    N026 --> N027
```

## _parse_since(...)

```mermaid
flowchart TD
    N001["_parse_since(...)"]
    N002["try"]
    N003["return datetime.strptime(value, '<str>').replace(tzinfo=UTC)"]
    N004["except ValueError"]
    N005["raise argparse.ArgumentTypeError(f'<str>{value!r}')"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## _parse_cutoff(...)

```mermaid
flowchart TD
    N001["_parse_cutoff(...)"]
    N002["try"]
    N003["return datetime.strptime(value, '<str>').replace(tzinfo=UTC)"]
    N004["except ValueError"]
    N005["raise argparse.ArgumentTypeError(f'<str>{value!r}')"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["args = parse_args(...)"]
    N012["if args.budget_output is not None and args.budget_seconds is None"]
    N013["error(...)"]
    N014["jobs = load_jobs(...)"]
    N015["jobs = filter_jobs(...)"]
    N016["report = render_report(...)"]
    N017["print(...)"]
    N018["if args.budget_output is not None"]
    N019["payload = budget_breach_payload(...)"]
    N020["write_text(...)"]
    N021["return 0"]
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
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N018 -->|"true"| N019
    N019 --> N020
    N020 --> N021
    N018 -->|"false"| N021
```
