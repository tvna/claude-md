# AST graph: scripts/measure_devcontainer_startup.py

This file is generated from `scripts/measure_devcontainer_startup.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["start = clock(...)"]
    N003["proc = runner(...)"]
    N004["elapsed = clock() - start"]
    N005["return RunResult(returncode=proc.returncode, stdout=proc.stdout, seconds=elapsed, stderr=getattr(proc, '<str>', '<str>') or '<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## resolve_runtime(...)

```mermaid
flowchart TD
    N001["resolve_runtime(...)"]
    N002["path = which(...)"]
    N003["if path is None"]
    N004["raise ValueError(f'<str>{name!r}')"]
    N005["return path"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## load_config(...)

```mermaid
flowchart TD
    N001["load_config(...)"]
    N002["try"]
    N003["text = read_text(...)"]
    N004["except FileNotFoundError"]
    N005["raise ValueError(f'<str>{path}')"]
    N006["try"]
    N007["data = loads(...)"]
    N008["except json.JSONDecodeError"]
    N009["raise ValueError(f'<str>{path}<str>{exc}')"]
    N010["if not isinstance(data, dict)"]
    N011["raise ValueError(f'<str>{path}')"]
    N012["return data"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
```

## reject_mutable_tag(...)

```mermaid
flowchart TD
    N001["reject_mutable_tag(...)"]
    N002["if image.endswith((':main', ':latest'))"]
    N003["raise ValueError(f'<str>{image}')"]
    N004["return image"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## get_image(...)

```mermaid
flowchart TD
    N001["get_image(...)"]
    N002["image = get(...)"]
    N003["if not isinstance(image, str) or not image"]
    N004["raise ValueError('<str>')"]
    N005["return reject_mutable_tag(image)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## split_segments(...)

```mermaid
flowchart TD
    N001["split_segments(...)"]
    N002["if not command"]
    N003["return []"]
    N004["return [segment.strip() for segment in command.split(_SEGMENT_SEP) if segment.strip()]"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _parse_du(...)

```mermaid
flowchart TD
    N001["_parse_du(...)"]
    N002["entries = []"]
    N003["for raw in stdout.splitlines():
    line = raw.strip()
    if not line:
        continue
    parts = line.split(None, 1)
    if len(parts) != 2:
        continue
    size_text, path = parts
    try:
        size = int(size_text)
    except ValueError:
        continue
    entries.append({'<str>': size, '<str>': path})"]
    N004["return entries"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## probe_composition(...)

```mermaid
flowchart TD
    N001["probe_composition(...)"]
    N002["store = _parse_du(...)"]
    N003["total = next(...)"]
    N004["top = [entry for entry in store if entry['<str>'] != '<str>'][:top_n]"]
    N005["base = _parse_du(...)"]
    N006["return {'<str>': total, '<str>': top, '<str>': base}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _stderr_tail(...)

```mermaid
flowchart TD
    N001["_stderr_tail(...)"]
    N002["tail = join(...)"]
    N003["if len(tail) > _STDERR_TAIL_CHARS"]
    N004["tail = tail[-_STDERR_TAIL_CHARS:]"]
    N005["return tail.encode('<str>', '<str>').decode('<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## measure(...)

```mermaid
flowchart TD
    N001["measure(...)"]
    N002["report = {'<str>': session.image, '<str>': []}"]
    N003["if do_pull"]
    N004["pull = pull(...)"]
    N005["report['<str>'] = round(...)"]
    N006["report['<str>'] = pull.returncode"]
    N007["report['<str>'] = image_size(...)"]
    N008["start(...)"]
    N009["try"]
    N010["phases = (('<str>', warmup or []), ('<str>', post_create), ('<str>', post_start))"]
    N011["for phase, segments in phases:
    for segment in segments:
        result = session.exec(segment)
        entry: dict[str, Any] = {'<str>': phase, '<str>': segment, '<str>': round(result.seconds, 3), '<str>': result.returncode}
        if result.returncode != 0 and result.stderr.strip():
            entry['<str>'] = _stderr_tail(result.stderr)
        report['<str>'].append(entry)"]
    N012["if probe"]
    N013["report['<str>'] = probe_composition(...)"]
    N014["close(...)"]
    N015["report['<str>'] = round(...)"]
    N016["return report"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N003 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 -->|"try"| N010
    N010 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N014
    N014 --> N015
    N015 --> N016
```

## _human_size(...)

```mermaid
flowchart TD
    N001["_human_size(...)"]
    N002["mib = num_bytes / (1024 * 1024)"]
    N003["if mib >= 1024"]
    N004["return f'{mib / 1024:<str>}<str>'"]
    N005["return f'{mib:<str>}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## format_summary(...)

```mermaid
flowchart TD
    N001["format_summary(...)"]
    N002["lines = ['<str>', '<str>', f'<str>{report['<str>']}<str>', f'<str>{_human_size(report['<str>'])}<str>{report['<str>']}<str>']"]
    N003["if 'pull_seconds' in report"]
    N004["flag = '<str>' if report['<str>'] == 0 else '<str>'"]
    N005["append(...)"]
    N006["lines += [f'<str>{report['<str>']:<str>}<str>', '<str>', '<str>', '<str>']"]
    N007["for entry in report['<str>']:
    command = entry['<str>']
    if len(command) > 70:
        command = command[:67] + '<str>'
    lines.append(f'<str>{entry['<str>']}<str>{entry['<str>']:<str>}<str>{entry['<str>']}<str>{command}<str>')"]
    N008["failures = [entry for entry in report['<str>'] if entry.get('<str>')]"]
    N009["if failures"]
    N010["lines += ['<str>', '<str>', '<str>']"]
    N011["for entry in failures:
    lines += [f'<str>{entry['<str>']}<str>{entry['<str>']}<str>{entry['<str>']}<str>', '<str>', '<str>', entry['<str>'], '<str>', '<str>']"]
    N012["composition = get(...)"]
    N013["if composition"]
    N014["lines += ['<str>', '<str>', '<str>', f'<str>{_human_size(composition['<str>'])}<str>{composition['<str>']}<str>', '<str>', '<str>', '<str>']"]
    N015["lines += [f'<str>{entry['<str>']}<str>{_human_size(entry['<str>'])}<str>' for entry in composition['<str>']]"]
    N016["lines += ['<str>', '<str>', '<str>']"]
    N017["lines += [f'<str>{entry['<str>']}<str>{_human_size(entry['<str>'])}<str>' for entry in composition['<str>']]"]
    N018["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 --> N006
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N011 --> N012
    N009 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N013 -->|"false"| N018
```

## run(...)

```mermaid
flowchart TD
    N001["run(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["add_argument(...)"]
    N013["add_argument(...)"]
    N014["add_argument(...)"]
    N015["args = parse_args(...)"]
    N016["config = load_config(...)"]
    N017["image = reject_mutable_tag(args.image) if args.image else get_image(config)"]
    N018["post_create = split_segments(...)"]
    N019["post_start = split_segments(...)"]
    N020["runtime = resolve_runtime(...)"]
    N021["session = session_factory(...)"]
    N022["report = measure(...)"]
    N023["payload = dumps(...)"]
    N024["if args.output is not None"]
    N025["write_text(...)"]
    N026["print(...)"]
    N027["print(...)"]
    N028["return 0"]
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
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
    N024 -->|"true"| N025
    N025 --> N026
    N024 -->|"false"| N026
    N026 --> N027
    N027 --> N028
```
