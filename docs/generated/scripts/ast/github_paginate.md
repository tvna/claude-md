# AST graph: scripts/github_paginate.py

This file is generated from `scripts/github_paginate.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _paginate_get(...)

```mermaid
flowchart TD
    N001["_paginate_get(...)"]
    N002["results = []"]
    N003["next_url = url"]
    N004["while next_url:
    request = urllib.request.Request(next_url, method='<str>')
    request.add_header('<str>', f'<str>{token}')
    request.add_header('<str>', '<str>')
    request.add_header('<str>', _API_VERSION)
    try:
        with opener(request) as response:
            code = int(response.status)
            body_str = response.read().decode('<str>', errors='<str>')
            link_header = str(response.headers.get('<str>') or '<str>')
    except urllib.error.HTTPError as error:
        code = int(error.code)
        body_str = error.read().decode('<str>', errors='<str>')
        link_header = '<str>'
    if not 200 <= code < 300:
        raise RuntimeError(f'<str>{code}<str>{body_str[:200]}')
    try:
        page_data = json.loads(body_str)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'<str>{body_str[:200]}') from exc
    if not isinstance(page_data, list):
        raise RuntimeError(f'<str>{body_str[:200]}')
    results.extend(page_data)
    next_url = None
    if link_header:
        match = re.search('<str>', link_header)
        if match:
            next_url = match.group(1)"]
    N005["return results"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _get_single(...)

```mermaid
flowchart TD
    N001["_get_single(...)"]
    N002["request = Request(...)"]
    N003["add_header(...)"]
    N004["add_header(...)"]
    N005["add_header(...)"]
    N006["try"]
    N007["with opener(request) as response:
    code = int(response.status)
    body_str = response.read().decode('<str>', errors='<str>')"]
    N008["except urllib.error.HTTPError"]
    N009["code = int(...)"]
    N010["body_str = decode(...)"]
    N011["if not 200 <= code < 300"]
    N012["raise RuntimeError(f'<str>{code}<str>{body_str[:200]}')"]
    N013["return body_str"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N009 --> N010
    N007 --> N011
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```

## _cmd_get(...)

```mermaid
flowchart TD
    N001["_cmd_get(...)"]
    N002["token = get(...)"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["if not args.output and (not args.field)"]
    N007["print(...)"]
    N008["return 1"]
    N009["url = f\"{_API_ROOT}<str>{args.path.lstrip('<str>')}\""]
    N010["try"]
    N011["body_str = _get_single(...)"]
    N012["except RuntimeError"]
    N013["print(...)"]
    N014["return 1"]
    N015["if args.output"]
    N016["write_text(...)"]
    N017["if args.field"]
    N018["try"]
    N019["data = loads(...)"]
    N020["except json.JSONDecodeError"]
    N021["print(...)"]
    N022["return 1"]
    N023["value = get(...)"]
    N024["if value is None"]
    N025["print(...)"]
    N026["return 1"]
    N027["print(...)"]
    N028["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
    N011 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N018 -->|"try"| N019
    N018 -->|"raises"| N020
    N020 --> N021
    N021 --> N022
    N019 --> N023
    N023 --> N024
    N024 -->|"true"| N025
    N025 --> N026
    N024 -->|"false"| N027
    N027 --> N028
    N017 -->|"false"| N028
```

## extract_run_ids(...)

```mermaid
flowchart TD
    N001["extract_run_ids(...)"]
    N002["try"]
    N003["data = loads(...)"]
    N004["except json.JSONDecodeError"]
    N005["raise ValueError(f'<str>{exc}')"]
    N006["runs = data.get('<str>') if isinstance(data, dict) else None"]
    N007["if not isinstance(runs, list)"]
    N008["return []"]
    N009["return [int(run['<str>']) for run in runs if isinstance(run, dict) and '<str>' in run]"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
```

## _cmd_fetch_run_jobs(...)

```mermaid
flowchart TD
    N001["_cmd_fetch_run_jobs(...)"]
    N002["token = get(...)"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["try"]
    N007["run_ids = extract_run_ids(...)"]
    N008["except (OSError, ValueError)"]
    N009["print(...)"]
    N010["return 1"]
    N011["outdir = Path(...)"]
    N012["mkdir(...)"]
    N013["for run_id in run_ids:
    url = f'{_API_ROOT}<str>{args.repo}<str>{run_id}<str>'
    try:
        body_str = _get_single(url=url, token=token)
    except RuntimeError as exc:
        print(f'<str>{exc}', file=sys.stderr)
        return 1
    (outdir / f'{run_id}<str>').write_text(body_str, encoding='<str>')"]
    N014["print(...)"]
    N015["return 0"]
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
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
```

## _cmd_fetch(...)

```mermaid
flowchart TD
    N001["_cmd_fetch(...)"]
    N002["token = get(...)"]
    N003["if not token"]
    N004["print(...)"]
    N005["return 1"]
    N006["url = f\"{_API_ROOT}<str>{args.path.lstrip('<str>')}\""]
    N007["try"]
    N008["data = _paginate_get(...)"]
    N009["except RuntimeError"]
    N010["print(...)"]
    N011["return 1"]
    N012["write_text(...)"]
    N013["print(...)"]
    N014["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"try"| N008
    N007 -->|"raises"| N009
    N009 --> N010
    N010 --> N011
    N008 --> N012
    N012 --> N013
    N013 --> N014
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["fetch_p = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["get_p = add_parser(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["jobs_p = add_parser(...)"]
    N012["add_argument(...)"]
    N013["add_argument(...)"]
    N014["add_argument(...)"]
    N015["args = parse_args(...)"]
    N016["if args.cmd == 'fetch'"]
    N017["return _cmd_fetch(args)"]
    N018["if args.cmd == 'get'"]
    N019["return _cmd_get(args)"]
    N020["if args.cmd == 'fetch-run-jobs'"]
    N021["return _cmd_fetch_run_jobs(args)"]
    N022["return 0"]
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
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 -->|"true"| N021
    N020 -->|"false"| N022
```
