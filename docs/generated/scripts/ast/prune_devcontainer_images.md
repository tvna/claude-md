# AST graph: scripts/prune_devcontainer_images.py

This file is generated from `scripts/prune_devcontainer_images.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

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

## parse_pinned_shas(...)

```mermaid
flowchart TD
    N001["parse_pinned_shas(...)"]
    N002["shas = set(...)"]
    N003["for raw in paths:
    path = Path(raw)
    data = json.loads(path.read_text(encoding='<str>'))
    image = data.get('<str>')
    if not isinstance(image, str) or '<str>' not in image:
        raise ValueError(f'{path}<str>')
    tag = image.rsplit('<str>', 1)[1]
    if _SHA_RE.fullmatch(tag):
        shas.add(tag)"]
    N004["return shas"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## is_protected_tag(...)

```mermaid
flowchart TD
    N001["is_protected_tag(...)"]
    N002["if tag == 'main'"]
    N003["return True"]
    N004["if tag.startswith('buildcache-')"]
    N005["return True"]
    N006["base = tag"]
    N007["for suffix in _ARCH_SUFFIXES:
    if base.endswith(suffix):
        base = base[:-len(suffix)]
        break"]
    N008["return base in pinned_shas"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
    N007 --> N008
```

## version_tags(...)

```mermaid
flowchart TD
    N001["version_tags(...)"]
    N002["tags = get(...)"]
    N003["return [t for t in tags if isinstance(t, str)]"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _parse_created_at(...)

```mermaid
flowchart TD
    N001["_parse_created_at(...)"]
    N002["raw = get(...)"]
    N003["if not isinstance(raw, str) or not raw"]
    N004["return datetime.fromtimestamp(0, tz=UTC)"]
    N005["return datetime.fromisoformat(raw.replace('<str>', '<str>'))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _deletion_order_key(...)

```mermaid
flowchart TD
    N001["_deletion_order_key(...)"]
    N002["for tag in version_tags(version):
    if not any((tag.endswith(suffix) for suffix in _ARCH_SUFFIXES)):
        return 0"]
    N003["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
```

## select_versions_to_delete(...)

```mermaid
flowchart TD
    N001["select_versions_to_delete(...)"]
    N002["if keep_recent < 0 or min_age_days < 0"]
    N003["raise ValueError('<str>')"]
    N004["candidates = [v for v in versions if version_tags(v) and (not any((is_protected_tag(t, pinned_shas) for t in version_tags(v))))]"]
    N005["sort(...)"]
    N006["aged_out = candidates[keep_recent:]"]
    N007["cutoff = now - timedelta(days=min_age_days)"]
    N008["to_delete = [v for v in aged_out if _parse_created_at(v) < cutoff]"]
    N009["sort(...)"]
    N010["return to_delete"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
```

## _list_versions(...)

```mermaid
flowchart TD
    N001["_list_versions(...)"]
    N002["results = []"]
    N003["for page in range(1, _MAX_PAGES + 1):
    url = f'{API_ROOT}<str>{owner}<str>{package}<str>{_PER_PAGE}<str>{page}<str>'
    code, body = _call(method='<str>', url=url, token=token, opener=opener)
    if not 200 <= code < 300:
        raise RuntimeError(f'<str>{package}<str>{code}<str>{body[:200]}')
    try:
        chunk = json.loads(body) if body else []
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'<str>{package}<str>{body[:200]}') from exc
    if not isinstance(chunk, list):
        raise RuntimeError(f'<str>{package}<str>{body[:200]}')
    results.extend(chunk)
    if len(chunk) < _PER_PAGE:
        break"]
    N004["return results"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _delete_version(...)

```mermaid
flowchart TD
    N001["_delete_version(...)"]
    N002["url = f'{API_ROOT}<str>{owner}<str>{package}<str>{version_id}'"]
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

## _format_plan(...)

```mermaid
flowchart TD
    N001["_format_plan(...)"]
    N002["lines = [f'<str>{package}', '<str>']"]
    N003["if not to_delete"]
    N004["append(...)"]
    N005["append(...)"]
    N006["return lines"]
    N007["for version in to_delete:
    tags = '<str>'.join(version_tags(version)) or '<str>'
    created = version.get('<str>', '<str>')
    lines.append(f\"<str>{version.get('<str>')}<str>{created}<str>{tags}\")"]
    N008["append(...)"]
    N009["return lines"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 --> N006
    N003 -->|"false"| N007
    N007 --> N008
    N008 --> N009
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
    N008["pinned_shas = parse_pinned_shas(...)"]
    N009["except (ValueError, OSError, json.JSONDecodeError)"]
    N010["print(...)"]
    N011["return 1"]
    N012["now = now(...)"]
    N013["mode = '<str>' if dry_run else '<str>'"]
    N014["report = [f'<str>{mode}<str>', '<str>']"]
    N015["deleted = 0"]
    N016["failures = []"]
    N017["for package in args.package:
    try:
        versions = _list_versions(args.owner, package, token)
    except RuntimeError as exc:
        print(f'<str>{exc}', file=sys.stderr)
        return 1
    to_delete = select_versions_to_delete(versions, pinned_shas, args.keep_recent, args.min_age_days, now)
    report.extend(_format_plan(package, to_delete))
    print(f'{package}<str>{len(versions)}<str>{len(to_delete)}<str>{mode}<str>')
    if dry_run:
        continue
    for version in to_delete:
        raw_id = version.get('<str>')
        if raw_id is None:
            failures.append(f'{package}<str>')
            continue
        version_id = int(raw_id)
        code, body = _delete_version(args.owner, package, version_id, token)
        if 200 <= code < 300:
            deleted += 1
            print(f'<str>{package}<str>{version_id}')
        else:
            failures.append(f'{package}<str>{version_id}<str>{code}<str>{body[:120]}')"]
    N018["if not dry_run"]
    N019["append(...)"]
    N020["append(...)"]
    N021["if args.summary_file"]
    N022["with Path(args.summary_file).open('<str>', encoding='<str>') as handle:
    handle.write('<str>'.join(report) + '<str>')"]
    N023["for failure in failures:
    print(f'<str>{failure}', file=sys.stderr)"]
    N024["return 1 if failures else 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 -->|"try"| N007
    N007 --> N008
    N006 -->|"raises"| N009
    N009 --> N010
    N010 --> N011
    N008 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N018 -->|"true"| N019
    N019 --> N020
    N020 --> N021
    N018 -->|"false"| N021
    N021 -->|"true"| N022
    N022 --> N023
    N021 -->|"false"| N023
    N023 --> N024
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
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["set_defaults(...)"]
    N013["args = parse_args(...)"]
    N014["return args.func(args)"]
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
