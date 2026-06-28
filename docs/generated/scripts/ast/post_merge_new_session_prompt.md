# AST graph: scripts/post_merge_new_session_prompt.py

This file is generated from `scripts/post_merge_new_session_prompt.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

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

## extract_merge_coords(...)

```mermaid
flowchart TD
    N001["extract_merge_coords(...)"]
    N002["owner = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N003["repo = tool_input.get('<str>') if isinstance(tool_input, dict) else None"]
    N004["pr_number = None"]
    N005["if isinstance(tool_input, dict)"]
    N006["val = get(...)"]
    N007["if isinstance(val, int) and val > 0"]
    N008["pr_number = str(...)"]
    N009["if isinstance(val, str) and val.isdecimal()"]
    N010["pr_number = val"]
    N011["if pr_number is None"]
    N012["for node in _walk(tool_response):     if isinstance(node, str):         m = _PR_URL_RE.search(node)         if m:             if owner is None:                 owner = m.group(1)             if repo is None:                 repo = m.group(2)             pr_number = m.group(3)             break"]
    N013["return (owner, repo, pr_number)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N008 --> N011
    N010 --> N011
    N009 -->|"false"| N011
    N005 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N013
```

## provisioning_scripts(...)

```mermaid
flowchart TD
    N001["provisioning_scripts(...)"]
    N002["try"]
    N003["data = loads(...)"]
    N004["except (OSError, json.JSONDecodeError)"]
    N005["return frozenset()"]
    N006["hooks = data.get('<str>') if isinstance(data, dict) else None"]
    N007["groups = hooks.get('<str>') if isinstance(hooks, dict) else None"]
    N008["if not isinstance(groups, list)"]
    N009["return frozenset()"]
    N010["referenced = set(...)"]
    N011["for group in groups:     if not isinstance(group, dict):         continue     for handler in group.get('<str>', []) or []:         if not isinstance(handler, dict):             continue         command = handler.get('<str>')         if isinstance(command, str):             referenced.update(_SCRIPT_SH_RE.findall(command))"]
    N012["scripts_dir = settings_path.resolve().parent.parent / '<str>'"]
    N013["found = set(...)"]
    N014["for rel in referenced:     found.add(rel)     script_file = settings_path.resolve().parent.parent / rel     try:         text = script_file.read_text(encoding='<str>')     except OSError:         continue     for line in text.splitlines():         m = _SOURCE_RE.match(line)         if m and (scripts_dir / m.group(1)).is_file():             found.add(f'<str>{m.group(1)}')"]
    N015["return frozenset(found)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
```

## classify(...)

```mermaid
flowchart TD
    N001["classify(...)"]
    N002["hook_config = sorted(...)"]
    N003["prov = sorted(...)"]
    N004["devcontainer = sorted(...)"]
    N005["result = {}"]
    N006["if hook_config"]
    N007["result['<str>'] = hook_config"]
    N008["if prov"]
    N009["result['<str>'] = prov"]
    N010["if devcontainer"]
    N011["result['<str>'] = devcontainer"]
    N012["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N010
    N010 -->|"true"| N011
    N011 --> N012
    N010 -->|"false"| N012
```

## _list_pr_files(...)

```mermaid
flowchart TD
    N001["_list_pr_files(...)"]
    N002["if not token"]
    N003["return None"]
    N004["filenames = []"]
    N005["for page in range(1, _MAX_PAGES + 1):     url = f'{_API_BASE}<str>{owner}<str>{repo}<str>{pr_number}<str>{_PER_PAGE}<str>{page}'     try:         code, body = apply_call(method='<str>', url=url, payload=None, token=token, opener=opener)     except Exception as exc:         print(f'<str>{exc}', file=sys.stderr)         return None     if not 200 <= code < 300:         return None     try:         items = json.loads(body)     except json.JSONDecodeError:         return None     if not isinstance(items, list):         return None     for item in items:         if isinstance(item, dict) and isinstance(item.get('<str>'), str):             filenames.append(item['<str>'])     if len(items) < _PER_PAGE:         break"]
    N006["return filenames"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
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

## build_message(...)

```mermaid
flowchart TD
    N001["build_message(...)"]
    N002["repo_label = f'{owner}<str>{repo}<str>{pr_number}' if owner and repo else f'<str>{pr_number}'"]
    N003["repo_ja = f'{owner}<str>{repo}' if owner and repo else '<str>'"]
    N004["en_lines = []"]
    N005["ja_lines = []"]
    N006["for key, (en, ja) in _CATEGORY_LABELS.items():     files = categories.get(key)     if not files:         continue     joined = '<str>'.join(files)     en_lines.append(f'<str>{en}<str>{joined}')     ja_lines.append(f'<str>{ja}<str>{joined}')"]
    N007["paste_prompt = f'<str>{pr_number}<str>{repo_ja}<str>' + '<str>'.join(ja_lines) + f'<str>{pr_number}<str>'"]
    N008["return f'<str>{repo_label}<str>' + '<str>'.join(en_lines) + f'<str>{paste_prompt}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') != TARGET_TOOL"]
    N003["return None"]
    N004["tool_input = event.get('<str>') or {}"]
    N005["tool_response = get(...)"]
    N006["(owner, repo, pr_number) = extract_merge_coords(...)"]
    N007["if pr_number is None or owner is None or repo is None"]
    N008["return None"]
    N009["actual_token = token if token is not None else os.environ.get('<str>', '<str>')"]
    N010["changed = list_files(...)"]
    N011["if not changed"]
    N012["return None"]
    N013["categories = classify(...)"]
    N014["if not categories"]
    N015["return None"]
    N016["return _build_context(build_message(owner, repo, pr_number, categories))"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N014 -->|"false"| N016
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["event = read_event(...)"]
    N004["if event is None or not isinstance(event, dict)"]
    N005["return 0"]
    N006["emit_decision(...)"]
    N007["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```
