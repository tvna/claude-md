# AST graph: scripts/_security_drift_issues.py

This file is generated from `scripts/_security_drift_issues.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## render_family_issue_title(...)

```mermaid
flowchart TD
    N001["render_family_issue_title(...)"]
    N002["spec = FAMILY_ISSUE_SPEC[family]"]
    N003["return f'<str>{spec['<str>']}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## render_family_issue_body(...)

```mermaid
flowchart TD
    N001["render_family_issue_body(...)"]
    N002["spec = FAMILY_ISSUE_SPEC[family]"]
    N003["return f'<str>{DEFAULT_TRACKING_ISSUE}<str>{family}<str>{run_url}<str>{run_date}<str>{spec['<str>']}<str>{spec['<str>']}<str>{spec['<str>']}<str>{DEFAULT_TRACKING_ISSUE}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## is_family_issue_title(...)

```mermaid
flowchart TD
    N001["is_family_issue_title(...)"]
    N002["return title == stable_title or title.startswith(f'{stable_title}<str>')"]
    N001 -->|"start"| N002
```

## list_open_family_issues(...)

```mermaid
flowchart TD
    N001["list_open_family_issues(...)"]
    N002["type_labels = [label for label in issue_labels() if label.startswith('<str>')]"]
    N003["query = urlencode(...)"]
    N004["(code, response) = apply(...)"]
    N005["if not 200 <= code < 300"]
    N006["print(...)"]
    N007["return None"]
    N008["try"]
    N009["entries = loads(...)"]
    N010["except json.JSONDecodeError"]
    N011["print(...)"]
    N012["return None"]
    N013["if not isinstance(entries, list)"]
    N014["print(...)"]
    N015["return None"]
    N016["result = []"]
    N017["for entry in entries:     if not isinstance(entry, dict) or '<str>' in entry:         continue     number, title = (entry.get('<str>'), entry.get('<str>'))     if isinstance(number, int) and isinstance(title, str):         result.append((number, title))"]
    N018["return result"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
    N016 --> N017
    N017 --> N018
```

## close_family_issue(...)

```mermaid
flowchart TD
    N001["close_family_issue(...)"]
    N002["(code, response) = apply(...)"]
    N003["if not 200 <= code < 300"]
    N004["print(...)"]
    N005["return False"]
    N006["(code, response) = apply(...)"]
    N007["if not 200 <= code < 300"]
    N008["print(...)"]
    N009["return False"]
    N010["return True"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 -->|"true"| N008
    N008 --> N009
    N007 -->|"false"| N010
```

## create_family_issue(...)

```mermaid
flowchart TD
    N001["create_family_issue(...)"]
    N002["payload = {'<str>': render_family_issue_title(family), '<str>': render_family_issue_body(family, run_url=run_url, run_date=run_date), '<str>': list(issue_labels())}"]
    N003["(code, response) = apply(...)"]
    N004["if not 200 <= code < 300"]
    N005["print(...)"]
    N006["return False"]
    N007["return True"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
```

## reconcile_family_issues(...)

```mermaid
flowchart TD
    N001["reconcile_family_issues(...)"]
    N002["if dry_run"]
    N003["for family in TARGET_FAMILIES:     if family in drifting:         print(f'<str>{family}<str>{render_family_issue_title(family)!r}<str>')     elif family in resolved:         print(f'<str>{family}<str>')     else:         print(f'<str>{family}<str>')"]
    N004["return 0"]
    N005["token = get(...)"]
    N006["if not token"]
    N007["print(...)"]
    N008["return 1"]
    N009["open_issues = list_open_family_issues(...)"]
    N010["if open_issues is None"]
    N011["return 1"]
    N012["failed = False"]
    N013["for family in TARGET_FAMILIES:     stable = render_family_issue_title(family)     matches = sorted((num for num, title in open_issues if is_family_issue_title(title, stable)))     if family in drifting:         failed |= not _ensure_single_open(apply, repo, family, matches, token, run_url=run_url, run_date=run_date)     elif family in resolved:         failed |= not _close_all(apply, repo, family, matches, token)"]
    N014["return 1 if failed else 0"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
    N010 -->|"true"| N011
    N010 -->|"false"| N012
    N012 --> N013
    N013 --> N014
```

## _ensure_single_open(...)

```mermaid
flowchart TD
    N001["_ensure_single_open(...)"]
    N002["if not matches"]
    N003["if create_family_issue(apply, repo, family, run_url=run_url, run_date=run_date, token=token)"]
    N004["print(...)"]
    N005["return True"]
    N006["return False"]
    N007["(keep, *extras) = matches"]
    N008["ok = True"]
    N009["for dup in extras:     ok &= close_family_issue(apply, repo, dup, token, DEDUP_COMMENT_TEMPLATE.format(keep=keep))"]
    N010["print(...)"]
    N011["return ok"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N002 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
```

## _close_all(...)

```mermaid
flowchart TD
    N001["_close_all(...)"]
    N002["ok = True"]
    N003["for num in matches:     if close_family_issue(apply, repo, num, token, RESOLVED_COMMENT):         print(f'{family}<str>{num}<str>')     else:         ok = False"]
    N004["return ok"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
