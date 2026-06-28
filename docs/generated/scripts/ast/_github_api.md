# AST graph: scripts/_github_api.py

This file is generated from `scripts/_github_api.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _default_opener(...)

```mermaid
flowchart TD
    N001["_default_opener(...)"]
    N002["return urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS)"]
    N001 -->|"start"| N002
```

## apply_call(...)

```mermaid
flowchart TD
    N001["apply_call(...)"]
    N002["sleeper = sleeper if sleeper is not None else time.sleep"]
    N003["last_code = 0"]
    N004["last_body = '<str>'"]
    N005["for attempt in range(1, 4):     data = None     if payload is not None:         data = json.dumps(payload, separators=('<str>', '<str>')).encode('<str>')     request = urllib.request.Request(url, data=data, method=method)     request.add_header('<str>', f'<str>{token}')     request.add_header('<str>', '<str>')     request.add_header('<str>', API_VERSION)     if payload is not None:         request.add_header('<str>', '<str>')     try:         with opener(request) as response:             last_code = int(response.status)             last_body = response.read().decode('<str>', errors='<str>')     except urllib.error.HTTPError as error:         last_code = int(error.code)         last_body = error.read().decode('<str>', errors='<str>')     except urllib.error.URLError as error:         last_code = 0         last_body = str(error.reason)     if 200 <= last_code < 300:         break     print(f'<str>{attempt}<str>{_format_code(last_code)}<str>{method}<str>{url}')     if last_code != 0 and last_code < 500:         break     if attempt < 3:         sleeper(attempt * 5)"]
    N006["return (last_code, last_body)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## rest_text(...)

```mermaid
flowchart TD
    N001["rest_text(...)"]
    N002["if token is None"]
    N003["token = get(...)"]
    N004["url = path if path.startswith('<str>') else f'{API_ROOT}{path}'"]
    N005["(code, body) = apply_call(...)"]
    N006["if not 200 <= code < 300"]
    N007["raise GitHubApiError(code, method, path, body)"]
    N008["return body"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## rest_json(...)

```mermaid
flowchart TD
    N001["rest_json(...)"]
    N002["body = rest_text(...)"]
    N003["if not body.strip()"]
    N004["return None"]
    N005["return json.loads(body)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## paginate(...)

```mermaid
flowchart TD
    N001["paginate(...)"]
    N002["items = []"]
    N003["page = 1"]
    N004["sep = '<str>' if '<str>' in path else '<str>'"]
    N005["while True:     page_path = f'{path}{sep}<str>{per_page}<str>{page}'     data = rest_json('<str>', page_path, token=token, opener=opener, sleeper=sleeper)     if not isinstance(data, list) or not data:         break     items.extend(data)     if len(data) < per_page:         break     page += 1"]
    N006["return items"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## upload_release_asset(...)

```mermaid
flowchart TD
    N001["upload_release_asset(...)"]
    N002["sleeper = sleeper if sleeper is not None else time.sleep"]
    N003["url = f'{_UPLOADS_ROOT}<str>{repo}<str>{release_id}<str>{urllib.parse.quote(name)}'"]
    N004["last_code = 0"]
    N005["last_body = '<str>'"]
    N006["for attempt in range(1, 4):     request = urllib.request.Request(url, data=content, method='<str>')     request.add_header('<str>', f'<str>{token}')     request.add_header('<str>', '<str>')     request.add_header('<str>', API_VERSION)     request.add_header('<str>', content_type)     try:         with opener(request) as response:             last_code = int(response.status)             last_body = response.read().decode('<str>', errors='<str>')     except urllib.error.HTTPError as error:         last_code = int(error.code)         last_body = error.read().decode('<str>', errors='<str>')     except urllib.error.URLError as error:         last_code = 0         last_body = str(error.reason)     if 200 <= last_code < 300:         break     print(f'<str>{attempt}<str>{_format_code(last_code)}<str>{url}')     if last_code != 0 and last_code < 500:         break     if attempt < 3:         sleeper(attempt * 5)"]
    N007["return (last_code, last_body)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## _graphql_is_transient(...)

```mermaid
flowchart TD
    N001["_graphql_is_transient(...)"]
    N002["if code == 0 or code >= 500"]
    N003["return True"]
    N004["errors = get(...)"]
    N005["if isinstance(errors, list)"]
    N006["for err in errors:     message = err.get('<str>', '<str>') if isinstance(err, dict) else '<str>'     if isinstance(message, str) and _GRAPHQL_TRANSIENT_ERROR_MARKER in message.lower():         return True"]
    N007["return False"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
```

## graphql_call(...)

```mermaid
flowchart TD
    N001["graphql_call(...)"]
    N002["sleeper = sleeper if sleeper is not None else time.sleep"]
    N003["payload = dumps(...)"]
    N004["last_code = 0"]
    N005["last_body = {}"]
    N006["for attempt in range(1, 4):     request = urllib.request.Request('<str>', data=payload.encode('<str>'), method='<str>')     request.add_header('<str>', f'<str>{token}')     request.add_header('<str>', '<str>')     request.add_header('<str>', API_VERSION)     request.add_header('<str>', '<str>')     try:         with opener(request) as response:             code = int(response.status)             body_str = response.read().decode('<str>', errors='<str>')     except urllib.error.HTTPError as error:         code = int(error.code)         body_str = error.read().decode('<str>', errors='<str>')     except urllib.error.URLError:         code = 0         body_str = '<str>'     try:         parsed = json.loads(body_str) if body_str else {}     except json.JSONDecodeError:         parsed = {}     last_code = code     last_body = parsed if isinstance(parsed, dict) else {}     if not _graphql_is_transient(last_code, last_body):         break     print(f'<str>{attempt}<str>{_format_code(last_code)}<str>')     if attempt < 3:         sleeper(attempt * 5)"]
    N007["return (last_code, last_body)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## _format_code(...)

```mermaid
flowchart TD
    N001["_format_code(...)"]
    N002["return '<str>' if code == 0 else str(code)"]
    N001 -->|"start"| N002
```
