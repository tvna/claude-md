# AST graph: scripts/labels_apply.py

This file is generated from `scripts/labels_apply.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## validate_sot(...)

```mermaid
flowchart TD
    N001["validate_sot(...)"]
    N002["if not isinstance(sot, list)"]
    N003["raise ValueError('<str>')"]
    N004["for entry in sot:
    name = entry.get('<str>') if isinstance(entry, dict) else None
    display_name = name if isinstance(name, str) and name else '<str>'
    if not isinstance(name, str) or not name:
        raise ValueError('<str>')
    color = entry.get('<str>')
    if not isinstance(color, str) or not HEX_COLOR_RE.fullmatch(color):
        raise ValueError(f'<str>{display_name}<str>')
    description = entry.get('<str>')
    if not isinstance(description, str):
        raise ValueError(f'<str>{display_name}<str>')
    if len(description) > 100:
        raise ValueError(f'<str>{display_name}<str>')"]
    N005["end"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## decide_label_action(...)

```mermaid
flowchart TD
    N001["decide_label_action(...)"]
    N002["name = str(...)"]
    N003["color = str(...)"]
    N004["description = str(...)"]
    N005["if live_entry is None"]
    N006["return {'<str>': '<str>', '<str>': '<str>', '<str>': '<str>', '<str>': {'<str>': name, '<str>': color, '<str>': description}, '<str>': False, '<str>': False}"]
    N007["color_changed = live_entry.get('<str>') != color"]
    N008["desc_changed = (live_entry.get('<str>') or '<str>') != description"]
    N009["if not color_changed and (not desc_changed)"]
    N010["return {'<str>': '<str>', '<str>': '<str>', '<str>': '<str>', '<str>': None, '<str>': False, '<str>': False}"]
    N011["return {'<str>': '<str>', '<str>': '<str>', '<str>': f\"<str>{urllib.parse.quote(name, safe='<str>')}\", '<str>': {'<str>': color, '<str>': description}, '<str>': color_changed, '<str>': desc_changed}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
```

## decide_prune_action(...)

```mermaid
flowchart TD
    N001["decide_prune_action(...)"]
    N002["_ = live_name"]
    N003["if in_sot"]
    N004["return '<str>'"]
    N005["if not prune"]
    N006["return '<str>'"]
    N007["if dry_run"]
    N008["return '<str>'"]
    N009["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## render_action_row(...)

```mermaid
flowchart TD
    N001["render_action_row(...)"]
    N002["return f'<str>{_escape_cell(name)}<str>{_escape_cell(action)}<str>{_escape_cell(color_changed)}<str>{_escape_cell(desc_changed)}<str>{_escape_cell(result)}<str>'"]
    N001 -->|"start"| N002
```

## fetch_live_labels(...)

```mermaid
flowchart TD
    N001["fetch_live_labels(...)"]
    N002["request = Request(...)"]
    N003["add_header(...)"]
    N004["add_header(...)"]
    N005["add_header(...)"]
    N006["with opener(request) as response:
    labels = json.loads(response.read().decode('<str>'))"]
    N007["if len(labels) >= 100"]
    N008["raise RuntimeError(f'<str>{len(labels)}<str>')"]
    N009["return labels"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## load_sot(...)

```mermaid
flowchart TD
    N001["load_sot(...)"]
    N002["with path.open(encoding='<str>') as handle:
    sot = json.load(handle)"]
    N003["validate_sot(...)"]
    N004["return sot"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## run(...)

```mermaid
flowchart TD
    N001["run(...)"]
    N002["sot = load_sot(...)"]
    N003["live = live_labels if live_labels is not None else fetch_live_labels(repo, token)"]
    N004["live_by_name = {str(entry.get('<str>')): entry for entry in live}"]
    N005["sot_names = {str(entry['<str>']) for entry in sot}"]
    N006["rows = []"]
    N007["_write_summary_header(...)"]
    N008["for entry in sot:
    name = str(entry['<str>'])
    decision = decide_label_action(sot_entry=entry, live_entry=live_by_name.get(name))
    action = str(decision['<str>'])
    if action == '<str>':
        rows.append(render_action_row(name, '<str>', '<str>', '<str>', '<str>'))
        continue
    color_changed = _changed_cell(decision['<str>'], is_post=action == '<str>')
    desc_changed = _changed_cell(decision['<str>'], is_post=action == '<str>')
    if mode == '<str>' or dry_run:
        rows.append(render_action_row(name, f'<str>{action}<str>', color_changed, desc_changed, '<str>'))
        continue
    code, body = apply_call(method=str(decision['<str>']), url=f\"{API_ROOT}<str>{repo}{decision['<str>']}\", payload=decision['<str>'], token=token)
    if not 200 <= code < 300:
        _append_rows(summary_file, rows)
        _append_error(summary_file, f\"<str>{name}<str>{decision['<str>']}<str>{_format_code(code)}<str>\", body)
        print(f\"<str>{decision['<str>']}<str>{name}<str>{_format_code(code)}<str>\")
        return 1
    rows.append(render_action_row(name, f'{action}<str>', color_changed, desc_changed, f'<str>{code}'))"]
    N009["for live_entry in live:
    live_name = str(live_entry.get('<str>'))
    prune_action = decide_prune_action(live_name=live_name, in_sot=live_name in sot_names, prune=prune, dry_run=mode == '<str>' or dry_run)
    if prune_action == '<str>':
        continue
    if prune_action == '<str>':
        rows.append(render_action_row(live_name, '<str>', '<str>', '<str>', '<str>'))
        continue
    if prune_action == '<str>':
        rows.append(render_action_row(live_name, '<str>', '<str>', '<str>', '<str>'))
        continue
    code, body = apply_call(method='<str>', url=f\"{API_ROOT}<str>{repo}<str>{urllib.parse.quote(live_name, safe='<str>')}\", payload=None, token=token)
    if not 200 <= code < 300:
        _append_rows(summary_file, rows)
        _append_error(summary_file, f'<str>{live_name}<str>{_format_code(code)}<str>', body)
        print(f'<str>{live_name}<str>{_format_code(code)}<str>')
        return 1
    rows.append(render_action_row(live_name, '<str>', '<str>', '<str>', f'<str>{code}'))"]
    N010["_append_rows(...)"]
    N011["return 0"]
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
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["subparsers = add_subparsers(...)"]
    N004["_add_common_args(...)"]
    N005["_add_common_args(...)"]
    N006["_add_common_args(...)"]
    N007["args = parse_args(...)"]
    N008["try"]
    N009["if args.command == 'validate'"]
    N010["load_sot(...)"]
    N011["return 0"]
    N012["token = get(...)"]
    N013["if not token"]
    N014["print(...)"]
    N015["return 1"]
    N016["return run(mode=args.command, repo=args.repo, sot_path=args.sot, prune=_parse_bool(args.prune), dry_run=_parse_bool(args.dry_run), summary_file=args.summary_file, token=token)"]
    N017["except (OSError, json.JSONDecodeError, RuntimeError, ValueError)"]
    N018["print(...)"]
    N019["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"try"| N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
    N008 -->|"raises"| N017
    N017 --> N018
    N018 --> N019
```

## _add_common_args(...)

```mermaid
flowchart TD
    N001["_add_common_args(...)"]
    N002["add_argument(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## _write_summary_header(...)

```mermaid
flowchart TD
    N001["_write_summary_header(...)"]
    N002["mkdir(...)"]
    N003["with summary_file.open('<str>', encoding='<str>') as handle:
    handle.write('<str>')
    handle.write(f'<str>{str(dry_run).lower()}<str>')
    handle.write(f'<str>{str(prune).lower()}<str>')
    handle.write(f'<str>{sot_count}<str>')
    handle.write(f'<str>{live_count}<str>')
    handle.write('<str>')
    handle.write('<str>')"]
    N004["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _append_rows(...)

```mermaid
flowchart TD
    N001["_append_rows(...)"]
    N002["with summary_file.open('<str>', encoding='<str>') as handle:
    for row in rows:
        handle.write(f'{row}<str>')"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _append_error(...)

```mermaid
flowchart TD
    N001["_append_error(...)"]
    N002["with summary_file.open('<str>', encoding='<str>') as handle:
    handle.write(f'<str>{title}<str>')
    handle.write('<str>')
    handle.write(body)
    if body and (not body.endswith('<str>')):
        handle.write('<str>')
    handle.write('<str>')"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _parse_bool(...)

```mermaid
flowchart TD
    N001["_parse_bool(...)"]
    N002["if isinstance(raw, bool)"]
    N003["return raw"]
    N004["if raw == 'true'"]
    N005["return True"]
    N006["if raw == 'false'"]
    N007["return False"]
    N008["raise ValueError(f'<str>{raw}')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _changed_cell(...)

```mermaid
flowchart TD
    N001["_changed_cell(...)"]
    N002["if is_post"]
    N003["return '<str>'"]
    N004["return '<str>' if changed else '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _escape_cell(...)

```mermaid
flowchart TD
    N001["_escape_cell(...)"]
    N002["return value.replace('<str>', '<str>').replace('<str>', '<str>').replace('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## _format_code(...)

```mermaid
flowchart TD
    N001["_format_code(...)"]
    N002["return '<str>' if code == 0 else str(code)"]
    N001 -->|"start"| N002
```
