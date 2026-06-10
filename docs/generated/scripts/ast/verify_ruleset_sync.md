# AST graph: scripts/verify_ruleset_sync.py

This file is generated from `scripts/verify_ruleset_sync.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## extract_required_contexts(...)

```mermaid
flowchart TD
    N001["extract_required_contexts(...)"]
    N002["for rule in ruleset.get('<str>', []) or []:     if rule.get('<str>') != '<str>':         continue     params = rule.get('<str>') or {}     checks = params.get('<str>') or []     return {check['<str>'] for check in checks if isinstance(check, dict) and '<str>' in check}"]
    N003["return set()"]
    N001 -->|"start"| N002
    N002 --> N003
```

## compute_missing(...)

```mermaid
flowchart TD
    N001["compute_missing(...)"]
    N002["return sot_contexts - live_contexts"]
    N001 -->|"start"| N002
```

## decode_base64_content(...)

```mermaid
flowchart TD
    N001["decode_base64_content(...)"]
    N002["encoding = get(...)"]
    N003["if encoding != 'base64'"]
    N004["raise ValueError(f'<str>{encoding!r}<str>')"]
    N005["raw = get(...)"]
    N006["if not isinstance(raw, str)"]
    N007["raise ValueError('<str>')"]
    N008["return base64.b64decode(raw).decode('<str>')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## format_error_lines(...)

```mermaid
flowchart TD
    N001["format_error_lines(...)"]
    N002["lines = [f'<str>{context}' for context in sorted(missing)]"]
    N003["append(...)"]
    N004["return lines"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _api_request(...)

```mermaid
flowchart TD
    N001["_api_request(...)"]
    N002["request = Request(...)"]
    N003["add_header(...)"]
    N004["add_header(...)"]
    N005["add_header(...)"]
    N006["return request"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## fetch_live_ruleset_by_name(...)

```mermaid
flowchart TD
    N001["fetch_live_ruleset_by_name(...)"]
    N002["list_req = _api_request(...)"]
    N003["with opener(list_req) as response:     listing = json.loads(response.read().decode('<str>'))"]
    N004["matches = [r for r in listing if r.get('<str>') == name]"]
    N005["if len(matches) > 1"]
    N006["raise RuntimeError(f'<str>{name!r}<str>{len(matches)}<str>')"]
    N007["if not matches"]
    N008["raise RuntimeError(f'<str>{name!r}<str>')"]
    N009["ruleset_id = matches[0]['<str>']"]
    N010["detail_req = _api_request(...)"]
    N011["with opener(detail_req) as response:     return json.loads(response.read().decode('<str>'))"]
    N012["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
```

## fetch_base_ref_sot(...)

```mermaid
flowchart TD
    N001["fetch_base_ref_sot(...)"]
    N002["url = f'{API_ROOT}<str>{repo}<str>{sot_path}<str>{base_ref}'"]
    N003["request = _api_request(...)"]
    N004["with opener(request) as response:     payload = json.loads(response.read().decode('<str>'))"]
    N005["return decode_base64_content(payload)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["live_fn = live_fetcher or (lambda r, n, t: fetch_live_ruleset_by_name(r, n, t))"]
    N003["sot_fn = sot_fetcher or (lambda r, b, p, t: fetch_base_ref_sot(r, b, p, t))"]
    N004["try"]
    N005["live = live_fn(...)"]
    N006["except (RuntimeError, urllib.error.HTTPError, urllib.error.URLError)"]
    N007["print(...)"]
    N008["return 1"]
    N009["try"]
    N010["sot_text = sot_fn(...)"]
    N011["sot = loads(...)"]
    N012["except (ValueError, urllib.error.HTTPError, urllib.error.URLError)"]
    N013["print(...)"]
    N014["return 1"]
    N015["sot_contexts = extract_required_contexts(...)"]
    N016["live_contexts = extract_required_contexts(...)"]
    N017["missing = compute_missing(...)"]
    N018["if not missing"]
    N019["print(...)"]
    N020["return 0"]
    N021["for line in format_error_lines(missing, docs_url):     print(line, file=err_stream)"]
    N022["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N007 --> N008
    N005 --> N009
    N009 -->|"try"| N010
    N010 --> N011
    N009 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
    N011 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N018 -->|"true"| N019
    N019 --> N020
    N018 -->|"false"| N021
    N021 --> N022
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["subparsers = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["args = parse_args(...)"]
    N011["if args.command == 'verify'"]
    N012["token = get(...)"]
    N013["if not token"]
    N014["print(...)"]
    N015["return 1"]
    N016["return verify(repo=args.repo, base_ref=args.base_ref, sot_path=args.sot_path, ruleset_name=args.ruleset_name, token=token, docs_url=args.docs_url, out_stream=sys.stdout, err_stream=sys.stderr)"]
    N017["return 1"]
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
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
    N011 -->|"false"| N017
```
