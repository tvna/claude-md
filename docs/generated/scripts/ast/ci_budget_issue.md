# AST graph: scripts/ci_budget_issue.py

This file is generated from `scripts/ci_budget_issue.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## parse_dry_run(...)

```mermaid
flowchart TD
    N001["parse_dry_run(...)"]
    N002["normalized = lower(...)"]
    N003["if normalized in {'true', '1', 'yes'}"]
    N004["return True"]
    N005["if normalized in {'false', '0', 'no', ''}"]
    N006["return False"]
    N007["raise ValueError(f'<str>{raw!r}')"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## load_breaches(...)

```mermaid
flowchart TD
    N001["load_breaches(...)"]
    N002["data = loads(...)"]
    N003["if not isinstance(data, dict)"]
    N004["raise ValueError(f'<str>{path}<str>')"]
    N005["budget = get(...)"]
    N006["if not isinstance(budget, int | float)"]
    N007["raise ValueError(f'<str>{path}<str>')"]
    N008["breaches = get(...)"]
    N009["if not isinstance(breaches, list)"]
    N010["raise ValueError(f'<str>{path}<str>')"]
    N011["for entry in breaches:     if not isinstance(entry, dict) or '<str>' not in entry or '<str>' not in entry:         raise ValueError(f'<str>{path}<str>{entry!r}')"]
    N012["return (float(budget), breaches)"]
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
```

## render_breach_table(...)

```mermaid
flowchart TD
    N001["render_breach_table(...)"]
    N002["rows = ['<str>', '<str>']"]
    N003["for entry in breaches:     rows.append(f'<str>{entry['<str>']}<str>{float(entry['<str>']):<str>}<str>')"]
    N004["return '<str>'.join(rows)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## render_issue_body(...)

```mermaid
flowchart TD
    N001["render_issue_body(...)"]
    N002["return f'{ISSUE_MARKER}<str>{PARENT_ISSUE}<str>{budget_seconds:<str>}<str>{run_url}<str>{render_breach_table(breaches)}<str>'"]
    N001 -->|"start"| N002
```

## render_update_comment(...)

```mermaid
flowchart TD
    N001["render_update_comment(...)"]
    N002["return f'<str>{budget_seconds:<str>}<str>{run_url}<str>{render_breach_table(breaches)}<str>'"]
    N001 -->|"start"| N002
```

## find_existing_issue(...)

```mermaid
flowchart TD
    N001["find_existing_issue(...)"]
    N002["query = f'<str>{repo}<str>{ISSUE_TITLE}<str>'"]
    N003["encoded = quote(...)"]
    N004["(code, body) = apply_call(...)"]
    N005["if not 200 <= code < 300"]
    N006["raise RuntimeError(f'<str>{code}<str>{body[:200]}')"]
    N007["items = json.loads(body).get('<str>') or []"]
    N008["for item in items:     if not isinstance(item, dict):         continue     if ISSUE_MARKER in (item.get('<str>') or '<str>') and isinstance(item.get('<str>'), int):         return item['<str>']"]
    N009["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
```

## open_or_update_issue(...)

```mermaid
flowchart TD
    N001["open_or_update_issue(...)"]
    N002["existing = find_existing_issue(...)"]
    N003["if existing is not None"]
    N004["(code, body) = apply_call(...)"]
    N005["if not 200 <= code < 300"]
    N006["raise RuntimeError(f'<str>{code}<str>{body[:200]}')"]
    N007["print(...)"]
    N008["return '<str>'"]
    N009["(code, body) = apply_call(...)"]
    N010["if not 200 <= code < 300"]
    N011["raise RuntimeError(f'<str>{code}<str>{body[:200]}')"]
    N012["print(...)"]
    N013["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N003 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
```

## _cmd_run(...)

```mermaid
flowchart TD
    N001["_cmd_run(...)"]
    N002["dry_run = parse_dry_run(...)"]
    N003["(budget_seconds, breaches) = load_breaches(...)"]
    N004["if not breaches"]
    N005["print(...)"]
    N006["return 0"]
    N007["if dry_run"]
    N008["print(...)"]
    N009["return 0"]
    N010["repo = args.repo or os.environ.get('<str>', '<str>')"]
    N011["if not repo"]
    N012["print(...)"]
    N013["return 1"]
    N014["token = get(...)"]
    N015["if not token"]
    N016["print(...)"]
    N017["return 1"]
    N018["open_or_update_issue(...)"]
    N019["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 --> N017
    N015 -->|"false"| N018
    N018 --> N019
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_run = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["set_defaults(...)"]
    N010["args = parse_args(...)"]
    N011["try"]
    N012["return args.func(args)"]
    N013["except (RuntimeError, ValueError, OSError, json.JSONDecodeError)"]
    N014["print(...)"]
    N015["return 1"]
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
    N011 -->|"try"| N012
    N011 -->|"raises"| N013
    N013 --> N014
    N014 --> N015
```
