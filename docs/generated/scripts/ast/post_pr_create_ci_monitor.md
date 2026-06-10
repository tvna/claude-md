# AST graph: scripts/post_pr_create_ci_monitor.py

This file is generated from `scripts/post_pr_create_ci_monitor.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _walk(...)

```mermaid
flowchart TD
    N001["_walk(...)"]
    N002["out = []"]
    N003["stack = [value]"]
    N004["while stack and len(out) < 200:
    current = stack.pop()
    out.append(current)
    if isinstance(current, dict):
        stack.extend(current.values())
    elif isinstance(current, list):
        stack.extend(current)"]
    N005["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## extract_pr_url(...)

```mermaid
flowchart TD
    N001["extract_pr_url(...)"]
    N002["for item in _walk(value):
    if isinstance(item, dict):
        for key, maybe_url in item.items():
            if key in URL_KEYS and isinstance(maybe_url, str):
                match = GITHUB_PR_URL_RE.search(maybe_url)
                if match is not None:
                    return match.group(0)
    elif isinstance(item, str):
        match = GITHUB_PR_URL_RE.search(item)
        if match is not None:
            return match.group(0)"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## extract_pr_number(...)

```mermaid
flowchart TD
    N001["extract_pr_number(...)"]
    N002["for item in _walk(value):
    if not isinstance(item, dict):
        continue
    for key, maybe_number in item.items():
        if key not in NUMBER_KEYS:
            continue
        if isinstance(maybe_number, int) and maybe_number > 0:
            return str(maybe_number)
        if isinstance(maybe_number, str) and maybe_number.isdecimal():
            return maybe_number"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## extract_repo(...)

```mermaid
flowchart TD
    N001["extract_repo(...)"]
    N002["for item in _walk(value):
    if not isinstance(item, dict):
        continue
    owner = item.get('<str>')
    name = item.get('<str>') or item.get('<str>') or item.get('<str>')
    if isinstance(owner, str) and isinstance(name, str):
        candidate = f'{owner}<str>{name}'
        if _is_owner_repo(candidate):
            return candidate
    for key, maybe_repo in item.items():
        if key in REPO_KEYS and isinstance(maybe_repo, str) and _is_owner_repo(maybe_repo):
            return maybe_repo"]
    N003["return None"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _is_owner_repo(...)

```mermaid
flowchart TD
    N001["_is_owner_repo(...)"]
    N002["parts = split(...)"]
    N003["return len(parts) == 2 and all((re.fullmatch('<str>', part) for part in parts))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## build_watch_command(...)

```mermaid
flowchart TD
    N001["build_watch_command(...)"]
    N002["response = get(...)"]
    N003["tool_input = event.get('<str>') if isinstance(event.get('<str>'), dict) else {}"]
    N004["pr_url = extract_pr_url(...)"]
    N005["if pr_url is not None"]
    N006["return ([sys.executable, _CI_WATCH_SCRIPT, '<str>', pr_url], pr_url)"]
    N007["pr_number = extract_pr_number(...)"]
    N008["if pr_number is None"]
    N009["return None"]
    N010["argv = [sys.executable, _CI_WATCH_SCRIPT, '<str>', pr_number]"]
    N011["repo = extract_repo(...)"]
    N012["if repo is not None"]
    N013["extend(...)"]
    N014["return (argv, pr_number)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N014
```

## start_monitor(...)

```mermaid
flowchart TD
    N001["start_monitor(...)"]
    N002["pr_label = re.sub('<str>', '<str>', argv[3]).strip('<str>') or '<str>'"]
    N003["log_path = Path(tempfile.gettempdir()) / f'<str>{pr_label}<str>'"]
    N004["try"]
    N005["with log_path.open('<str>') as log:
    subprocess.Popen(argv, cwd=cwd or None, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True, start_new_session=True)"]
    N006["except Exception"]
    N007["raise"]
    N008["return log_path"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"try"| N005
    N004 -->|"raises"| N006
    N006 --> N007
    N005 --> N008
```

## build_context(...)

```mermaid
flowchart TD
    N001["build_context(...)"]
    N002["return {'<str>': {'<str>': '<str>', '<str>': message}}"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') not in TARGET_TOOLS"]
    N003["return None"]
    N004["command = build_watch_command(...)"]
    N005["if command is None"]
    N006["return build_context('<str>')"]
    N007["(argv, pr_ref) = command"]
    N008["cwd = event.get('<str>') if isinstance(event.get('<str>'), str) else str(Path.cwd())"]
    N009["try"]
    N010["log_path = start_monitor(...)"]
    N011["except OSError"]
    N012["return build_context(f'<str>{pr_ref}<str>{exc}<str>')"]
    N013["return build_context(f'<str>{pr_ref}<str>{log_path}<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 -->|"try"| N010
    N009 -->|"raises"| N011
    N011 --> N012
    N010 --> N013
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["event = read_event(...)"]
    N004["if event is None"]
    N005["return 0"]
    N006["if not isinstance(event, dict)"]
    N007["return 0"]
    N008["emit_decision(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
```
