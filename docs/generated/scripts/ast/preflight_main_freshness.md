# AST graph: scripts/preflight_main_freshness.py

This file is generated from `scripts/preflight_main_freshness.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _now_utc(...)

```mermaid
flowchart TD
    N001["_now_utc(...)"]
    N002["return datetime.now(UTC)"]
    N001 -->|"start"| N002
```

## read_stamp(...)

```mermaid
flowchart TD
    N001["read_stamp(...)"]
    N002["try"]
    N003["text = read_text(...)"]
    N004["except FileNotFoundError"]
    N005["return None"]
    N006["data = {}"]
    N007["for line in text.splitlines():
    if '<str>' in line:
        k, _, v = line.partition('<str>')
        data[k.strip()] = v.strip()"]
    N008["sha = get(...)"]
    N009["fetched_at_str = get(...)"]
    N010["if not sha or not fetched_at_str"]
    N011["return None"]
    N012["try"]
    N013["fetched_at = fromisoformat(...)"]
    N014["if fetched_at.tzinfo is None"]
    N015["fetched_at = replace(...)"]
    N016["except ValueError"]
    N017["return None"]
    N018["return FreshnessStamp(sha=sha, fetched_at=fetched_at)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 -->|"try"| N013
    N013 --> N014
    N014 -->|"true"| N015
    N012 -->|"raises"| N016
    N016 --> N017
    N015 --> N018
    N014 -->|"false"| N018
```

## write_stamp(...)

```mermaid
flowchart TD
    N001["write_stamp(...)"]
    N002["now = _now_utc(...)"]
    N003["write_text(...)"]
    N004["return FreshnessStamp(sha=sha, fetched_at=now)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## check_freshness(...)

```mermaid
flowchart TD
    N001["check_freshness(...)"]
    N002["stamp = read_stamp(...)"]
    N003["if stamp is None"]
    N004["return FreshnessResult(status='<str>', detail='<str>')"]
    N005["age = _now_utc() - stamp.fetched_at"]
    N006["if age > timedelta(seconds=ttl_seconds)"]
    N007["age_minutes = int(...)"]
    N008["return FreshnessResult(status='<str>', detail=f'<str>{age_minutes}<str>{ttl_seconds // 60}<str>{stamp.sha[:12]}<str>', stamp=stamp)"]
    N009["age_seconds = int(...)"]
    N010["return FreshnessResult(status='<str>', detail=f'<str>{stamp.sha[:12]}<str>{age_seconds}<str>', stamp=stamp)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
```

## fetch_and_record(...)

```mermaid
flowchart TD
    N001["fetch_and_record(...)"]
    N002["if stamp_path is None"]
    N003["stamp_path = STAMP_FILE"]
    N004["fetch = run_git(...)"]
    N005["if fetch.returncode != 0"]
    N006["detail = strip(...)"]
    N007["raise RuntimeError(f'<str>{remote}<str>{branch}<str>{detail}')"]
    N008["rev = run_git(...)"]
    N009["if rev.returncode != 0"]
    N010["detail = strip(...)"]
    N011["raise RuntimeError(f'<str>{remote}<str>{branch}<str>{detail}')"]
    N012["sha = strip(...)"]
    N013["return write_stamp(sha, path=stamp_path)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
```

## build_deny_reason(...)

```mermaid
flowchart TD
    N001["build_deny_reason(...)"]
    N002["return f'<str>{tool_name}<str>{result.detail}<str>'"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if tool_name not in _TARGET_TOOLS"]
    N003["return None"]
    N004["result = check_freshness(...)"]
    N005["if result.status == 'fresh'"]
    N006["return None"]
    N007["return {'<str>': {'<str>': '<str>', '<str>': '<str>', '<str>': build_deny_reason(tool_name, result)}}"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## _build_deny_dict(...)

```mermaid
flowchart TD
    N001["_build_deny_dict(...)"]
    N002["return {'<str>': {'<str>': '<str>', '<str>': '<str>', '<str>': reason}}"]
    N001 -->|"start"| N002
```

## _cmd_record(...)

```mermaid
flowchart TD
    N001["_cmd_record(...)"]
    N002["try"]
    N003["stamp = fetch_and_record(...)"]
    N004["print(...)"]
    N005["return 0"]
    N006["except RuntimeError"]
    N007["print(...)"]
    N008["return 1"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 --> N004
    N004 --> N005
    N002 -->|"raises"| N006
    N006 --> N007
    N007 --> N008
```

## _cmd_check(...)

```mermaid
flowchart TD
    N001["_cmd_check(...)"]
    N002["result = check_freshness(...)"]
    N003["if result.status == 'fresh'"]
    N004["print(...)"]
    N005["return 0"]
    N006["print(...)"]
    N007["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
```

## _hook_mode(...)

```mermaid
flowchart TD
    N001["_hook_mode(...)"]
    N002["event = read_event(...)"]
    N003["if event is None"]
    N004["return 0"]
    N005["tool_name = get(...)"]
    N006["tool_input = event.get('<str>') or {}"]
    N007["if not isinstance(tool_name, str) or not isinstance(tool_input, dict)"]
    N008["print(...)"]
    N009["return 0"]
    N010["emit_decision(...)"]
    N011["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_record = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["p_check = add_parser(...)"]
    N009["add_argument(...)"]
    N010["set_defaults(...)"]
    N011["args = parse_args(...)"]
    N012["if args.cmd is None"]
    N013["return _hook_mode()"]
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
    N012 -->|"true"| N013
    N012 -->|"false"| N014
```
