# AST graph: scripts/scan_non_ascii.py

This file is generated from `scripts/scan_non_ascii.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_event(...)

```mermaid
flowchart TD
    N001["extract_event(...)"]
    N002["if event_name == 'issues'"]
    N003["issue = event.get('<str>') or {}"]
    N004["user = issue.get('<str>') or {}"]
    N005["return {'<str>': '<str>', '<str>': issue.get('<str>'), '<str>': issue.get('<str>') or '<str>', '<str>': issue.get('<str>') or '<str>', '<str>': issue.get('<str>'), '<str>': user.get('<str>')}"]
    N006["if event_name == 'pull_request_target'"]
    N007["pr = event.get('<str>') or {}"]
    N008["user = pr.get('<str>') or {}"]
    N009["return {'<str>': '<str>', '<str>': pr.get('<str>'), '<str>': pr.get('<str>') or '<str>', '<str>': pr.get('<str>') or '<str>', '<str>': pr.get('<str>'), '<str>': user.get('<str>')}"]
    N010["if event_name == 'issue_comment'"]
    N011["issue = event.get('<str>') or {}"]
    N012["comment = event.get('<str>') or {}"]
    N013["user = comment.get('<str>') or {}"]
    N014["kind = '<str>' if issue.get('<str>') else '<str>'"]
    N015["return {'<str>': kind, '<str>': issue.get('<str>'), '<str>': '<str>', '<str>': comment.get('<str>') or '<str>', '<str>': comment.get('<str>'), '<str>': user.get('<str>')}"]
    N016["if event_name == 'pull_request_review_comment'"]
    N017["pr = event.get('<str>') or {}"]
    N018["comment = event.get('<str>') or {}"]
    N019["user = comment.get('<str>') or {}"]
    N020["return {'<str>': '<str>', '<str>': pr.get('<str>'), '<str>': '<str>', '<str>': comment.get('<str>') or '<str>', '<str>': comment.get('<str>'), '<str>': user.get('<str>')}"]
    N021["raise ValueError(f'<str>{event_name!r}')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N004 --> N005
    N002 -->|"false"| N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 --> N009
    N006 -->|"false"| N010
    N010 -->|"true"| N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N010 -->|"false"| N016
    N016 -->|"true"| N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N016 -->|"false"| N021
```

## detect_non_ascii(...)

```mermaid
flowchart TD
    N001["detect_non_ascii(...)"]
    N002["return _NON_ASCII_RE.search(text) is not None"]
    N001 -->|"start"| N002
```

## has_ack_marker(...)

```mermaid
flowchart TD
    N001["has_ack_marker(...)"]
    N002["return marker in body"]
    N001 -->|"start"| N002
```

## trust_class(...)

```mermaid
flowchart TD
    N001["trust_class(...)"]
    N002["if association in _TRUSTED_ASSOC"]
    N003["return '<str>'"]
    N004["return '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## classify_action(...)

```mermaid
flowchart TD
    N001["classify_action(...)"]
    N002["if not has_non_ascii"]
    N003["return '<str>'"]
    N004["trust = trust_class(...)"]
    N005["if trust == 'trusted' and has_ack and (not has_title_violation)"]
    N006["return '<str>'"]
    N007["if trust == 'trusted'"]
    N008["return '<str>'"]
    N009["if login is not None and login in _NON_ASCII_SKIP_LOGINS"]
    N010["return '<str>'"]
    N011["if login is not None and login in _TRUSTED_BOT_LOGINS"]
    N012["return '<str>'"]
    N013["return '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N011 -->|"false"| N013
```

## escape_for_comment(...)

```mermaid
flowchart TD
    N001["escape_for_comment(...)"]
    N002["encoded = dumps(...)"]
    N003["inner = encoded[1:-1]"]
    N004["if len(inner) > max_len"]
    N005["return inner[:max_len] + '<str>'"]
    N006["return inner"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## build_advisory_comment(...)

```mermaid
flowchart TD
    N001["build_advisory_comment(...)"]
    N002["if action == 'advisory'"]
    N003["verdict = f'<str>{association}<str>{label}<str>{ack_marker}<str>'"]
    N004["verdict = f'<str>{association}<str>{ack_marker}<str>'"]
    N005["title_notice = '<str>'"]
    N006["if has_title_violation"]
    N007["title_notice = f'<str>{ack_marker}<str>'"]
    N008["return f'{marker}<str>{kind}<str>{title_notice}<str>{verdict}<str>{escaped}<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N003 --> N005
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
```

## build_summary(...)

```mermaid
flowchart TD
    N001["build_summary(...)"]
    N002["assoc_str = association if association is not None else '<str>'"]
    N003["return f'<str>{event_name}<str>{(number if number is not None else '<str>')}<str>{kind}<str>{assoc_str}<str>{trust}<str>{str(has_non_ascii).lower()}<str>{str(has_title_violation).lower()}<str>{str(has_ack).lower()}<str>{action}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## gh_api(...)

```mermaid
flowchart TD
    N001["gh_api(...)"]
    N002["return rest_text(method, path, json_body)"]
    N001 -->|"start"| N002
```

## find_existing_comment_id(...)

```mermaid
flowchart TD
    N001["find_existing_comment_id(...)"]
    N002["raw = gh_api(...)"]
    N003["comments = json.loads(raw) if raw.strip() else []"]
    N004["for comment in comments:     body = comment.get('<str>') or '<str>'     if body.startswith(marker):         return comment.get('<str>')"]
    N005["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## apply_label(...)

```mermaid
flowchart TD
    N001["apply_label(...)"]
    N002["gh_api(...)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## post_or_update_comment(...)

```mermaid
flowchart TD
    N001["post_or_update_comment(...)"]
    N002["existing = find_existing_comment_id(...)"]
    N003["if existing is not None"]
    N004["gh_api(...)"]
    N005["return f'<str>{existing}'"]
    N006["gh_api(...)"]
    N007["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
```

## block_external(...)

```mermaid
flowchart TD
    N001["block_external(...)"]
    N002["if kind in {'pull_request', 'pr_comment', 'pr_review_comment'}"]
    N003["gh_api(...)"]
    N004["return f'<str>{number}'"]
    N005["if kind in {'issue', 'issue_comment'}"]
    N006["gh_api(...)"]
    N007["return f'<str>{number}<str>'"]
    N008["raise ValueError(f'<str>{kind!r}')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
```

## _append_summary(...)

```mermaid
flowchart TD
    N001["_append_summary(...)"]
    N002["path = get(...)"]
    N003["if not path"]
    N004["return"]
    N005["with Path(path).open('<str>', encoding='<str>') as fp:     fp.write(text)"]
    N006["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## run(...)

```mermaid
flowchart TD
    N001["run(...)"]
    N002["extracted = extract_event(...)"]
    N003["kind = extracted['<str>']"]
    N004["number = extracted['<str>']"]
    N005["title = extracted['<str>']"]
    N006["body = extracted['<str>']"]
    N007["association = extracted['<str>']"]
    N008["login = extracted['<str>']"]
    N009["has_title_violation = kind in {'<str>', '<str>'} and detect_non_ascii(title)"]
    N010["has_non_ascii = detect_non_ascii(...)"]
    N011["has_ack = has_ack_marker(...)"]
    N012["trust = trust_class(...)"]
    N013["action = classify_action(...)"]
    N014["_append_summary(...)"]
    N015["print(...)"]
    N016["if action in {'none', 'skip'}"]
    N017["return 0"]
    N018["if number is None"]
    N019["print(...)"]
    N020["return 1"]
    N021["escaped = escape_for_comment(...)"]
    N022["comment_body = build_advisory_comment(...)"]
    N023["apply_label(...)"]
    N024["print(...)"]
    N025["print(...)"]
    N026["if action == 'block'"]
    N027["print(...)"]
    N028["return 0"]
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
    N019 --> N020
    N018 -->|"false"| N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
    N024 --> N025
    N025 --> N026
    N026 -->|"true"| N027
    N027 --> N028
    N026 -->|"false"| N028
```

## _cmd_run(...)

```mermaid
flowchart TD
    N001["_cmd_run(...)"]
    N002["event_path = args.event_file or os.environ.get('<str>')"]
    N003["event_name = args.event_name or os.environ.get('<str>')"]
    N004["repo = args.repo or os.environ.get('<str>') or os.environ.get('<str>')"]
    N005["if not event_path"]
    N006["print(...)"]
    N007["return 1"]
    N008["if not event_name"]
    N009["print(...)"]
    N010["return 1"]
    N011["if not repo"]
    N012["print(...)"]
    N013["return 1"]
    N014["try"]
    N015["event = loads(...)"]
    N016["except (OSError, json.JSONDecodeError)"]
    N017["print(...)"]
    N018["return 1"]
    N019["return run(event, event_name, repo)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 -->|"try"| N015
    N014 -->|"raises"| N016
    N016 --> N017
    N017 --> N018
    N015 --> N019
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
    N008["set_defaults(...)"]
    N009["args = parse_args(...)"]
    N010["try"]
    N011["return args.func(args)"]
    N012["except ValueError"]
    N013["print(...)"]
    N014["return 1"]
    N015["except GitHubApiError"]
    N016["print(...)"]
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
    N010 -->|"try"| N011
    N010 -->|"raises"| N012
    N012 --> N013
    N013 --> N014
    N010 -->|"raises"| N015
    N015 --> N016
    N016 --> N017
```
