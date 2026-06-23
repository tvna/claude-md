# AST graph: scripts/check_pr_mergeability.py

This file is generated from `scripts/check_pr_mergeability.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _get_token(...)

```mermaid
flowchart TD
    N001["_get_token(...)"]
    N002["return os.environ.get('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## _rest_get(...)

```mermaid
flowchart TD
    N001["_rest_get(...)"]
    N002["if not token"]
    N003["return None"]
    N004["url = f'{_API_BASE}{path}'"]
    N005["try"]
    N006["(code, body) = apply_call(...)"]
    N007["except Exception"]
    N008["print(...)"]
    N009["return None"]
    N010["if not 200 <= code < 300"]
    N011["return None"]
    N012["try"]
    N013["data = loads(...)"]
    N014["except json.JSONDecodeError"]
    N015["return None"]
    N016["return data if isinstance(data, dict) else None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 -->|"try"| N013
    N012 -->|"raises"| N014
    N014 --> N015
    N013 --> N016
```

## _rest_get_list(...)

```mermaid
flowchart TD
    N001["_rest_get_list(...)"]
    N002["if not token"]
    N003["return None"]
    N004["url = f'{_API_BASE}{path}'"]
    N005["try"]
    N006["(code, body) = apply_call(...)"]
    N007["except Exception"]
    N008["print(...)"]
    N009["return None"]
    N010["if not 200 <= code < 300"]
    N011["return None"]
    N012["try"]
    N013["data = loads(...)"]
    N014["except json.JSONDecodeError"]
    N015["return None"]
    N016["return data if isinstance(data, list) else None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"try"| N006
    N005 -->|"raises"| N007
    N007 --> N008
    N008 --> N009
    N006 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 -->|"try"| N013
    N012 -->|"raises"| N014
    N014 --> N015
    N013 --> N016
```

## _detect_repo(...)

```mermaid
flowchart TD
    N001["_detect_repo(...)"]
    N002["repo = get(...)"]
    N003["if repo and _OWNER_REPO_RE.match(repo)"]
    N004["return repo"]
    N005["try"]
    N006["result = run(...)"]
    N007["if result.returncode == 0"]
    N008["m = search(...)"]
    N009["if m"]
    N010["return m.group(1)"]
    N011["except (OSError, subprocess.SubprocessError)"]
    N012["pass"]
    N013["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"try"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N005 -->|"raises"| N011
    N011 --> N012
    N009 -->|"false"| N013
    N007 -->|"false"| N013
    N012 --> N013
```

## _walk(...)

```mermaid
flowchart TD
    N001["_walk(...)"]
    N002["out = []"]
    N003["stack = [value]"]
    N004["while stack and len(out) < 200:     node = stack.pop()     out.append(node)     if isinstance(node, dict):         stack.extend(node.values())     elif isinstance(node, list):         stack.extend(node)"]
    N005["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## _extract_pr_info(...)

```mermaid
flowchart TD
    N001["_extract_pr_info(...)"]
    N002["tool_input = event.get('<str>') or {}"]
    N003["tool_response = get(...)"]
    N004["for node in _walk(tool_response) + _walk(tool_input):     if isinstance(node, str):         m = _PR_URL_RE.search(node)         if m:             return (m.group(1), m.group(2), m.group(3))"]
    N005["owner = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N006["repo = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N007["for node in _walk(tool_response):     if not isinstance(node, dict):         continue     for key in ('<str>', '<str>', '<str>', '<str>'):         val = node.get(key)         if isinstance(val, int) and val > 0:             return (owner, repo, str(val))         if isinstance(val, str) and val.isdecimal():             return (owner, repo, val)"]
    N008["return (None, None, None)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## _poll_mergeability(...)

```mermaid
flowchart TD
    N001["_poll_mergeability(...)"]
    N002["actual_token = token or _get_token()"]
    N003["path = f'<str>{owner}<str>{repo}<str>{pr_number}'"]
    N004["data = None"]
    N005["for attempt in range(_MAX_POLLS):     if attempt > 0:         sleeper(_POLL_INTERVAL_SECONDS)     data = _rest_get(path, token=actual_token, opener=opener)     if data is None:         return None     if data.get('<str>') is not None:         return data"]
    N006["return data"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _build_context(...)

```mermaid
flowchart TD
    N001["_build_context(...)"]
    N002["return {'<str>': {'<str>': '<str>', '<str>': message}}"]
    N001 -->|"start"| N002
```

## decide_post_tool_use(...)

```mermaid
flowchart TD
    N001["decide_post_tool_use(...)"]
    N002["if event.get('tool_name') not in _POST_TOOL_USE_TARGETS"]
    N003["return None"]
    N004["(owner, repo, pr_number) = _extract_pr_info(...)"]
    N005["if pr_number is None"]
    N006["return _build_context('<str>')"]
    N007["pr_label = f'{owner}<str>{repo}<str>{pr_number}' if owner and repo else f'<str>{pr_number}'"]
    N008["if owner is None or repo is None"]
    N009["return _build_context(f'<str>{pr_label}<str>')"]
    N010["pr_data = _poll_mergeability(...)"]
    N011["if pr_data is None"]
    N012["return _build_context(f'<str>{pr_label}<str>')"]
    N013["mergeable = get(...)"]
    N014["state = lower(...)"]
    N015["if mergeable is None"]
    N016["return _build_context(f'<str>{pr_label}<str>{_MAX_POLLS}<str>')"]
    N017["if state == 'dirty'"]
    N018["return _build_context(f'<str>{pr_label}<str>')"]
    N019["if state == 'behind'"]
    N020["return _build_context(f'<str>{pr_label}<str>')"]
    N021["if state == 'clean'"]
    N022["return _build_context(f'<str>{pr_label}<str>')"]
    N023["return _build_context(f'<str>{pr_label}<str>{state}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 -->|"true"| N018
    N017 -->|"false"| N019
    N019 -->|"true"| N020
    N019 -->|"false"| N021
    N021 -->|"true"| N022
    N021 -->|"false"| N023
```

## _list_open_prs(...)

```mermaid
flowchart TD
    N001["_list_open_prs(...)"]
    N002["actual_token = token or _get_token()"]
    N003["if not actual_token"]
    N004["return []"]
    N005["user_data = _rest_get(...)"]
    N006["if user_data is None"]
    N007["return []"]
    N008["login = get(...)"]
    N009["if not isinstance(login, str) or not login"]
    N010["return []"]
    N011["repo_str = _detect_repo(...)"]
    N012["if not repo_str"]
    N013["return []"]
    N014["prs = _rest_get_list(...)"]
    N015["if prs is None"]
    N016["return []"]
    N017["result = []"]
    N018["for pr in prs:     if not isinstance(pr, dict):         continue     pr_user = pr.get('<str>') or {}     if not isinstance(pr_user, dict) or pr_user.get('<str>') != login:         continue     number = pr.get('<str>')     url = pr.get('<str>') or '<str>'     head = pr.get('<str>') or {}     head_repo = head.get('<str>') or {}     owner_login = (head_repo.get('<str>') or {}).get('<str>') or '<str>'     repo_name = head_repo.get('<str>') or '<str>'     result.append({'<str>': number, '<str>': url, '<str>': {'<str>': owner_login}, '<str>': {'<str>': repo_name}})"]
    N019["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 --> N018
    N018 --> N019
```

## run_session_start(...)

```mermaid
flowchart TD
    N001["run_session_start(...)"]
    N002["prs = _list_open_prs(...)"]
    N003["if not prs"]
    N004["return"]
    N005["dirty = []"]
    N006["behind = []"]
    N007["for pr in prs:     number = str(pr.get('<str>') or '<str>')     if not number:         continue     owner_obj = pr.get('<str>') or {}     owner = owner_obj.get('<str>') if isinstance(owner_obj, dict) else None     repo_obj = pr.get('<str>') or {}     repo = repo_obj.get('<str>') if isinstance(repo_obj, dict) else None     if not owner or not repo:         continue     pr_data = _poll_mergeability(owner, repo, number, opener=opener, token=token, sleeper=sleeper)     if pr_data is None:         continue     state = str(pr_data.get('<str>') or '<str>').lower()     url = pr.get('<str>') or f'{owner}<str>{repo}<str>{number}'     if state == '<str>':         dirty.append(url)     elif state == '<str>':         behind.append(url)"]
    N008["if dirty"]
    N009["lines = ['<str>']"]
    N010["for url in dirty:     lines.append(f'<str>{url}')"]
    N011["append(...)"]
    N012["print(...)"]
    N013["if behind"]
    N014["lines = ['<str>']"]
    N015["for url in behind:     lines.append(f'<str>{url}')"]
    N016["append(...)"]
    N017["print(...)"]
    N018["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N008 -->|"false"| N013
    N013 -->|"true"| N014
    N014 --> N015
    N015 --> N016
    N016 --> N017
    N017 --> N018
    N013 -->|"false"| N018
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["args = argv if argv is not None else sys.argv[1:]"]
    N003["if args and args[0] == 'session-start'"]
    N004["run_session_start(...)"]
    N005["return 0"]
    N006["event = read_event(...)"]
    N007["if event is None or not isinstance(event, dict)"]
    N008["return 0"]
    N009["emit_decision(...)"]
    N010["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
```
