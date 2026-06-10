# AST graph: scripts/_ci_watch.py

This file is generated from `scripts/_ci_watch.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _rest_get(...)

```mermaid
flowchart TD
    N001["_rest_get(...)"]
    N002["try"]
    N003["(code, body) = apply_call(...)"]
    N004["except Exception"]
    N005["return (0, None)"]
    N006["try"]
    N007["return (code, json.loads(body))"]
    N008["except json.JSONDecodeError"]
    N009["return (code, None)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
```

## poll_ci(...)

```mermaid
flowchart TD
    N001["poll_ci(...)"]
    N002["print(...)"]
    N003["(code, pr_data) = _rest_get(...)"]
    N004["if not isinstance(pr_data, dict) or not 200 <= code < 300"]
    N005["print(...)"]
    N006["return 1"]
    N007["sha = get(...)"]
    N008["if not isinstance(sha, str)"]
    N009["print(...)"]
    N010["return 1"]
    N011["print(...)"]
    N012["for poll in range(_MAX_POLLS):     if poll > 0:         time.sleep(_POLL_INTERVAL)     code, data = _rest_get(f'<str>{owner}<str>{repo}<str>{sha}<str>', token=token)     if not isinstance(data, dict) or not 200 <= code < 300:         print(f'<str>{poll + 1}<str>{code}', flush=True)         continue     runs = data.get('<str>') or []     total = len(runs)     completed = sum((1 for r in runs if r.get('<str>') == '<str>'))     failed = [r for r in runs if str(r.get('<str>') or '<str>').lower() in _FAIL_CONCLUSIONS]     print(f'<str>{poll + 1}<str>{completed}<str>{total}<str>{len(failed)}<str>', flush=True)     for r in failed:         print(f'<str>{r.get('<str>')}<str>{r.get('<str>')}<str>', flush=True)     if total > 0 and completed == total:         if failed:             print(f'<str>{len(failed)}<str>', flush=True)         else:             print('<str>', flush=True)         return 0"]
    N013["print(...)"]
    N014["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["add_argument(...)"]
    N005["args = parse_args(...)"]
    N006["token = get(...)"]
    N007["if not token"]
    N008["print(...)"]
    N009["return 1"]
    N010["pr_str = args.pr"]
    N011["m = match(...)"]
    N012["if m"]
    N013["(owner, repo, pr_number) = (m.group(1), m.group(2), m.group(3))"]
    N014["if not args.repo or '/' not in args.repo"]
    N015["print(...)"]
    N016["return 1"]
    N017["parts = split(...)"]
    N018["(owner, repo, pr_number) = (parts[0], parts[1], pr_str)"]
    N019["return poll_ci(owner, repo, pr_number, token=token)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N017
    N017 --> N018
    N013 --> N019
    N018 --> N019
```
