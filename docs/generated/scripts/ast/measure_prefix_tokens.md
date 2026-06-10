# AST graph: scripts/measure_prefix_tokens.py

This file is generated from `scripts/measure_prefix_tokens.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## repo_targets(...)

```mermaid
flowchart TD
    N001["repo_targets(...)"]
    N002["return [Target(label, repo_root / rel) for label, rel in _REPO_TARGETS]"]
    N001 -->|"start"| N002
```

## extra_targets(...)

```mermaid
flowchart TD
    N001["extra_targets(...)"]
    N002["return [Target(f'<str>{p}', Path(p)) for p in paths]"]
    N001 -->|"start"| N002
```

## measure_target(...)

```mermaid
flowchart TD
    N001["measure_target(...)"]
    N002["try"]
    N003["text = read_text(...)"]
    N004["except OSError"]
    N005["return Measurement(target.label, target.path, None, None, f'<str>{exc}')"]
    N006["byte_size = len(...)"]
    N007["if counter is None"]
    N008["return Measurement(target.label, target.path, byte_size, None, '<str>')"]
    N009["try"]
    N010["tokens = counter(...)"]
    N011["except Exception"]
    N012["return Measurement(target.label, target.path, byte_size, None, f'<str>{exc}')"]
    N013["return Measurement(target.label, target.path, byte_size, tokens, None)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"try"| N010
    N009 -->|"raises"| N011
    N011 --> N012
    N010 --> N013
```

## measure(...)

```mermaid
flowchart TD
    N001["measure(...)"]
    N002["return [measure_target(t, counter) for t in targets]"]
    N001 -->|"start"| N002
```

## _share(...)

```mermaid
flowchart TD
    N001["_share(...)"]
    N002["if tokens is None or total <= 0"]
    N003["return '<str>'"]
    N004["return f'{tokens / total * 100:<str>}<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## render_table(...)

```mermaid
flowchart TD
    N001["render_table(...)"]
    N002["measured_total = sum(...)"]
    N003["lines = [f'<str>{model}<str>', '<str>', '<str>', '<str>']"]
    N004["for m in measurements:
    bytes_txt = f'{m.byte_size:<str>}' if m.byte_size is not None else _UNAVAILABLE
    tokens_txt = f'{m.tokens:<str>}' if m.tokens is not None else _UNAVAILABLE
    rel = _display_path(m.path)
    lines.append(f'<str>{m.label}<str>{rel}<str>{bytes_txt}<str>{tokens_txt}<str>{_share(m.tokens, measured_total)}<str>')"]
    N005["total_txt = f'{measured_total:<str>}' if measured_total else _UNAVAILABLE"]
    N006["append(...)"]
    N007["append(...)"]
    N008["errors = [m for m in measurements if m.error]"]
    N009["if errors"]
    N010["append(...)"]
    N011["extend(...)"]
    N012["append(...)"]
    N013["append(...)"]
    N014["extend(...)"]
    N015["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N009 -->|"false"| N013
    N013 --> N014
    N014 --> N015
```

## render_json(...)

```mermaid
flowchart TD
    N001["render_json(...)"]
    N002["payload = {'<str>': model, '<str>': sum((m.tokens for m in measurements if m.tokens is not None)), '<str>': [{'<str>': m.label, '<str>': _display_path(m.path), '<str>': m.byte_size, '<str>': m.tokens, '<str>': m.error} for m in measurements], '<str>': list(_HARNESS_OWNED)}"]
    N003["return json.dumps(payload, indent=2, sort_keys=True) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _display_path(...)

```mermaid
flowchart TD
    N001["_display_path(...)"]
    N002["try"]
    N003["return str(path.resolve().relative_to(REPO_ROOT))"]
    N004["except ValueError"]
    N005["return str(path)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## make_api_counter(...)

```mermaid
flowchart TD
    N001["make_api_counter(...)"]
    N002["try"]
    N003["import anthropic"]
    N004["except ImportError"]
    N005["raise RuntimeError('<str>')"]
    N006["if not (os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN'))"]
    N007["raise RuntimeError('<str>')"]
    N008["client = Anthropic(...)"]
    N009["def counter(text: str) -> int:
    resp = client.messages.count_tokens(model=model, messages=[{'<str>': '<str>', '<str>': text}])
    return int(resp.input_tokens)"]
    N010["return counter"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
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
    N007["args = parse_args(...)"]
    N008["counter"]
    N009["try"]
    N010["counter = make_api_counter(...)"]
    N011["except RuntimeError"]
    N012["print(...)"]
    N013["counter = None"]
    N014["targets = repo_targets(Path(args.repo_root)) + extra_targets(args.extra_paths)"]
    N015["measurements = measure(...)"]
    N016["render = render_json if args.json else render_table"]
    N017["write(...)"]
    N018["return 0 if counter is not None else 2"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"try"| N010
    N009 -->|"raises"| N011
    N011 --> N012
    N012 --> N013
    N010 --> N014
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
```
