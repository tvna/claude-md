# AST graph: scripts/prune_codespaces.py

This file is generated from `scripts/prune_codespaces.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## parse_bool(...)

```mermaid
flowchart TD
    N001["parse_bool(...)"]
    N002["normalized = lower(...)"]
    N003["if normalized == 'true'"]
    N004["return True"]
    N005["if normalized == 'false'"]
    N006["return False"]
    N007["raise ValueError(f'<str>{value!r}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## _activity_time(...)

```mermaid
flowchart TD
    N001["_activity_time(...)"]
    N002["for field in ('<str>', '<str>'):     raw = codespace.get(field)     if isinstance(raw, str) and raw:         try:             return datetime.fromisoformat(raw.replace('<str>', '<str>'))         except ValueError:             pass"]
    N003["return datetime.fromtimestamp(0, tz=UTC)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## select_candidates(...)

```mermaid
flowchart TD
    N001["select_candidates(...)"]
    N002["if min_age_days < 0"]
    N003["raise ValueError('<str>')"]
    N004["cutoff = now - timedelta(days=min_age_days)"]
    N005["return [cs for cs in codespaces if cs.get('<str>') in _DELETABLE_STATES and _activity_time(cs) < cutoff]"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
```

## _list_codespaces(...)

```mermaid
flowchart TD
    N001["_list_codespaces(...)"]
    N002["results = []"]
    N003["for page in range(1, _MAX_PAGES + 1):     url = f'{API_ROOT}<str>{org}<str>{_PER_PAGE}<str>{page}'     code, body = _call(method='<str>', url=url, token=token, opener=opener)     if not 200 <= code < 300:         raise RuntimeError(f'<str>{code}<str>{body[:200]}')     try:         data = json.loads(body) if body else {}     except json.JSONDecodeError as exc:         raise RuntimeError(f'<str>{body[:200]}') from exc     if not isinstance(data, dict):         raise RuntimeError(f'<str>{body[:200]}')     chunk = data.get('<str>', [])     if not isinstance(chunk, list):         raise RuntimeError(f'<str>{body[:200]}')     results.extend(chunk)     if len(chunk) < _PER_PAGE:         break"]
    N004["return results"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _delete_codespace(...)

```mermaid
flowchart TD
    N001["_delete_codespace(...)"]
    N002["url = f'{API_ROOT}<str>{org}<str>{username}<str>{name}'"]
    N003["return _call(method='<str>', url=url, token=token, opener=opener)"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _call(...)

```mermaid
flowchart TD
    N001["_call(...)"]
    N002["if opener is None"]
    N003["return apply_call(method=method, url=url, payload=None, token=token)"]
    N004["return apply_call(method=method, url=url, payload=None, token=token, opener=opener)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _format_report(...)

```mermaid
flowchart TD
    N001["_format_report(...)"]
    N002["lines = [f'<str>{mode}<str>', '<str>']"]
    N003["if not candidates"]
    N004["lines += ['<str>', '<str>']"]
    N005["return lines"]
    N006["for cs in candidates:     name = cs.get('<str>', '<str>')     owner = cs.get('<str>', {}).get('<str>', '<str>') if isinstance(cs.get('<str>'), dict) else '<str>'     repo = cs.get('<str>', {}).get('<str>', '<str>') if isinstance(cs.get('<str>'), dict) else '<str>'     last = cs.get('<str>') or cs.get('<str>') or '<str>'     lines.append(f'<str>{name}<str>{owner}<str>{repo}<str>{last}')"]
    N007["append(...)"]
    N008["if mode != 'dry-run'"]
    N009["append(...)"]
    N010["append(...)"]
    N011["return lines"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N010 --> N011
    N008 -->|"false"| N011
```

## cmd_prune(...)

```mermaid
flowchart TD
    N001["cmd_prune(...)"]
    N002["token = get(...)"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["try"]
    N007["dry_run = parse_bool(...)"]
    N008["except ValueError"]
    N009["print(...)"]
    N010["return 1"]
    N011["try"]
    N012["codespaces = _list_codespaces(...)"]
    N013["except RuntimeError"]
    N014["print(...)"]
    N015["return 1"]
    N016["now = now(...)"]
    N017["candidates = select_candidates(...)"]
    N018["mode = '<str>' if dry_run else '<str>'"]
    N019["print(...)"]
    N020["for cs in candidates:     name = cs.get('<str>', '<str>')     last = cs.get('<str>') or cs.get('<str>') or '<str>'     print(f'<str>{name}<str>{last}<str>')"]
    N021["deleted = 0"]
    N022["failures = []"]
    N023["if not dry_run"]
    N024["for cs in candidates:     name = cs.get('<str>')     if not name:         failures.append('<str>')         continue     username = cs.get('<str>', {}).get('<str>') if isinstance(cs.get('<str>'), dict) else None     if not username:         failures.append(f'{name}<str>')         continue     code, body = _delete_codespace(args.org, username, name, token)     if 200 <= code < 300:         deleted += 1         print(f'<str>{name}')     else:         failures.append(f'{name}<str>{code}<str>{body[:120]}')"]
    N025["report = _format_report(...)"]
    N026["if args.summary_file"]
    N027["with Path(args.summary_file).open('<str>', encoding='<str>') as handle:     handle.write('<str>'.join(report) + '<str>')"]
    N028["for failure in failures:     print(f'<str>{failure}', file=sys.stderr)"]
    N029["return 1 if failures else 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N009 --> N010
    N007 --> N011
    N011 -->|"try"| N012
    N011 -->|"raises"| N013
    N013 --> N014
    N014 --> N015
    N012 --> N016
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
    N023 -->|"true"| N024
    N024 --> N025
    N023 -->|"false"| N025
    N025 --> N026
    N026 -->|"true"| N027
    N027 --> N028
    N026 -->|"false"| N028
    N028 --> N029
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["prune = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["set_defaults(...)"]
    N010["args = parse_args(...)"]
    N011["return args.func(args)"]
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
