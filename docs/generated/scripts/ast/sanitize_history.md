# AST graph: scripts/sanitize_history.py

This file is generated from `scripts/sanitize_history.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## sha256_hex(...)

```mermaid
flowchart TD
    N001["sha256_hex(...)"]
    N002["return hashlib.sha256(text.encode('<str>')).hexdigest()"]
    N001 -->|"start"| N002
```

## load_translations(...)

```mermaid
flowchart TD
    N001["load_translations(...)"]
    N002["return json.loads(Path(path).read_text(encoding='<str>'))"]
    N001 -->|"start"| N002
```

## load_backup(...)

```mermaid
flowchart TD
    N001["load_backup(...)"]
    N002["raw = read_bytes(...)"]
    N003["if path and str(path).endswith('.gz')"]
    N004["raw = decompress(...)"]
    N005["return json.loads(raw.decode('<str>'))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## index_backup(...)

```mermaid
flowchart TD
    N001["index_backup(...)"]
    N002["out = {}"]
    N003["for item in backup.get('<str>') or []:     kind = item.get('<str>')     id_ = item.get('<str>')     comment_id = item.get('<str>')     if id_ is None or kind is None:         continue     body = item.get('<str>') or '<str>'     out[kind, id_, comment_id, '<str>'] = body     title = item.get('<str>') or '<str>'     if title:         out[kind, id_, comment_id, '<str>'] = title"]
    N004["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## item_endpoint(...)

```mermaid
flowchart TD
    N001["item_endpoint(...)"]
    N002["kind = item['<str>']"]
    N003["if kind == 'issue'"]
    N004["return f'{API_ROOT}<str>{repo}<str>{item['<str>']}'"]
    N005["if kind == 'pr'"]
    N006["return f'{API_ROOT}<str>{repo}<str>{item['<str>']}'"]
    N007["if kind == 'issue_comment'"]
    N008["if item.get('comment_id') is None"]
    N009["raise ValueError(f'<str>{item.get('<str>')}<str>')"]
    N010["return f'{API_ROOT}<str>{repo}<str>{item['<str>']}'"]
    N011["if kind == 'pr_review_comment'"]
    N012["if item.get('comment_id') is None"]
    N013["raise ValueError(f'<str>{item.get('<str>')}<str>')"]
    N014["return f'{API_ROOT}<str>{repo}<str>{item['<str>']}'"]
    N015["raise ValueError(f'<str>{kind!r}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N007 -->|"false"| N011
    N011 -->|"true"| N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N011 -->|"false"| N015
```

## is_excluded(...)

```mermaid
flowchart TD
    N001["is_excluded(...)"]
    N002["if not excluded_prs"]
    N003["return False"]
    N004["if item['type'] not in {'pr', 'pr_review_comment'}"]
    N005["return False"]
    N006["number = get(...)"]
    N007["return number in excluded_prs"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```

## classify_drift(...)

```mermaid
flowchart TD
    N001["classify_drift(...)"]
    N002["live_h = sha256_hex(...)"]
    N003["if live_h == sha256_hex(original)"]
    N004["return '<str>'"]
    N005["if live_h == sha256_hex(translated)"]
    N006["return '<str>'"]
    N007["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## parse_exclude_prs(...)

```mermaid
flowchart TD
    N001["parse_exclude_prs(...)"]
    N002["if not raw"]
    N003["return set()"]
    N004["out = set(...)"]
    N005["for chunk in raw.split('<str>'):     chunk = chunk.strip()     if not chunk:         continue     out.add(int(chunk))"]
    N006["return out"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## fetch_live_field(...)

```mermaid
flowchart TD
    N001["fetch_live_field(...)"]
    N002["kwargs = {'<str>': '<str>', '<str>': url, '<str>': None, '<str>': token, '<str>': opener}"]
    N003["if sleeper is not None"]
    N004["kwargs['<str>'] = sleeper"]
    N005["(code, body) = apply_call(...)"]
    N006["if not 200 <= code < 300"]
    N007["raise RuntimeError(f'<str>{url}<str>{code}<str>{body!r}')"]
    N008["parsed = loads(...)"]
    N009["return parsed.get(field) or '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```

## patch_field(...)

```mermaid
flowchart TD
    N001["patch_field(...)"]
    N002["kwargs = {'<str>': '<str>', '<str>': url, '<str>': {field: new_value}, '<str>': token, '<str>': opener}"]
    N003["if sleeper is not None"]
    N004["kwargs['<str>'] = sleeper"]
    N005["(code, body) = apply_call(...)"]
    N006["if not 200 <= code < 300"]
    N007["raise RuntimeError(f'<str>{url}<str>{code}<str>{body!r}')"]
    N008["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## iter_actionable(...)

```mermaid
flowchart TD
    N001["iter_actionable(...)"]
    N002["items = translations.get('<str>') or []"]
    N003["return [it for it in items if not is_excluded(it, excluded_prs)]"]
    N001 -->|"start"| N002
    N002 --> N003
```

## run_apply(...)

```mermaid
flowchart TD
    N001["run_apply(...)"]
    N002["counts = {'<str>': 0, '<str>': 0, '<str>': 0, '<str>': 0}"]
    N003["items = translations.get('<str>') or []"]
    N004["actionable = []"]
    N005["for item in items:     if is_excluded(item, excluded_prs):         counts['<str>'] += 1         continue     actionable.append(item)"]
    N006["for index, item in enumerate(actionable):     if batch_size and index and (index % batch_size == 0):         print(f'<str>{index}<str>{len(actionable)}<str>')     counts['<str>'] += 1     url = item_endpoint(repo, item)     field = item['<str>']     live = fetch_live_field(url=url, field=field, token=token, opener=opener, sleeper=sleeper)     verdict = classify_drift(live=live, original=item['<str>'], translated=item['<str>'])     if verdict == '<str>':         msg = f'<str>{item['<str>']}<str>{item.get('<str>')}<str>{field}<str>'         print(msg, file=sys.stderr)         raise SystemExit(1)     if verdict == '<str>':         counts['<str>'] += 1         print(f'<str>{item['<str>']}<str>{item.get('<str>')}<str>{field}<str>')         continue     if dry_run:         print(f'<str>{url}<str>{field}')     else:         patch_field(url=url, field=field, new_value=item['<str>'], token=token, opener=opener, sleeper=sleeper)         print(f'<str>{item['<str>']}<str>{item.get('<str>')}<str>{field}<str>')     counts['<str>'] += 1"]
    N007["return counts"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## run_plan(...)

```mermaid
flowchart TD
    N001["run_plan(...)"]
    N002["plan = []"]
    N003["for item in iter_actionable(translations, excluded_prs):     plan.append({'<str>': item['<str>'], '<str>': item.get('<str>'), '<str>': item['<str>'], '<str>': sha256_hex(item['<str>']), '<str>': sha256_hex(item['<str>'])})"]
    N004["return plan"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## cmd_plan(...)

```mermaid
flowchart TD
    N001["cmd_plan(...)"]
    N002["translations = load_translations(...)"]
    N003["excluded = parse_exclude_prs(...)"]
    N004["plan = run_plan(...)"]
    N005["print(...)"]
    N006["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## cmd_apply(...)

```mermaid
flowchart TD
    N001["cmd_apply(...)"]
    N002["repo = get(...)"]
    N003["if not repo"]
    N004["print(...)"]
    N005["return 2"]
    N006["token = get(...)"]
    N007["if not token"]
    N008["print(...)"]
    N009["return 2"]
    N010["translations = load_translations(...)"]
    N011["excluded = parse_exclude_prs(...)"]
    N012["counts = run_apply(...)"]
    N013["print(...)"]
    N014["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
```

## cmd_restore(...)

```mermaid
flowchart TD
    N001["cmd_restore(...)"]
    N002["repo = get(...)"]
    N003["if not repo"]
    N004["print(...)"]
    N005["return 2"]
    N006["token = get(...)"]
    N007["if not token"]
    N008["print(...)"]
    N009["return 2"]
    N010["backup = load_backup(...)"]
    N011["index = index_backup(...)"]
    N012["patched = 0"]
    N013["for (kind, id_, comment_id, field), original in index.items():     item = {'<str>': kind, '<str>': id_, '<str>': comment_id, '<str>': _number_for_restore(backup, kind, id_)}     try:         url = item_endpoint(repo, item)     except ValueError:         continue     if args.dry_run:         print(f'<str>{url}<str>{field}')     else:         patch_field(url=url, field=field, new_value=original, token=token)         print(f'<str>{kind}<str>{item['<str>']}<str>{field}<str>')     patched += 1"]
    N014["print(...)"]
    N015["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
```

## _number_for_restore(...)

```mermaid
flowchart TD
    N001["_number_for_restore(...)"]
    N002["for item in backup.get('<str>') or []:     if item.get('<str>') == kind and item.get('<str>') == id_:         return item.get('<str>')"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## build_parser(...)

```mermaid
flowchart TD
    N001["build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_plan = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["p_apply = add_parser(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["p_restore = add_parser(...)"]
    N013["add_argument(...)"]
    N014["add_argument(...)"]
    N015["return parser"]
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
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = build_parser(...)"]
    N003["args = parse_args(...)"]
    N004["if args.command == 'plan'"]
    N005["return cmd_plan(args)"]
    N006["if args.command == 'apply'"]
    N007["return cmd_apply(args)"]
    N008["if args.command == 'restore'"]
    N009["return cmd_restore(args)"]
    N010["error(...)"]
    N011["return 2"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
```
