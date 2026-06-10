# AST graph: scripts/branch_cleanup.py

This file is generated from `scripts/branch_cleanup.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## parse_dry_run(...)

```mermaid
flowchart TD
    N001["parse_dry_run(...)"]
    N002["if raw == 'true'"]
    N003["return True"]
    N004["if raw == 'false'"]
    N005["return False"]
    N006["raise ValueError(f'<str>{raw}')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## parse_min_age_days(...)

```mermaid
flowchart TD
    N001["parse_min_age_days(...)"]
    N002["if not raw.isdecimal()"]
    N003["raise ValueError(f'<str>{raw}')"]
    N004["return int(raw)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## is_candidate(...)

```mermaid
flowchart TD
    N001["is_candidate(...)"]
    N002["if branch == default_branch"]
    N003["return False"]
    N004["if has_open_pr"]
    N005["return False"]
    N006["age_seconds = int(...)"]
    N007["return age_seconds > min_age_days * SECONDS_PER_DAY"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 --> N007
```

## format_summary_row(...)

```mermaid
flowchart TD
    N001["format_summary_row(...)"]
    N002["return f'<str>{branch}<str>{_format_github_datetime(last_commit_utc)}<str>{age_days}<str>{sha[:7]}<str>'"]
    N001 -->|"start"| N002
```

## decide_issue_action(...)

```mermaid
flowchart TD
    N001["decide_issue_action(...)"]
    N002["if candidate_count > 0"]
    N003["return '<str>' if existing_issue is not None else '<str>'"]
    N004["if existing_issue is None"]
    N005["return '<str>'"]
    N006["if idle_seconds >= idle_threshold_seconds"]
    N007["return '<str>'"]
    N008["return '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## list_branches(...)

```mermaid
flowchart TD
    N001["list_branches(...)"]
    N002["result = _run(...)"]
    N003["branches = []"]
    N004["for line in result.stdout.splitlines():     if not line.strip():         continue     try:         name, sha = line.split('<str>', 1)     except ValueError as exc:         raise ValueError(f'<str>{line!r}') from exc     branches.append((name, sha))"]
    N005["return branches"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## get_last_commit_date(...)

```mermaid
flowchart TD
    N001["get_last_commit_date(...)"]
    N002["result = _run(...)"]
    N003["return _parse_github_datetime(result.stdout.strip())"]
    N001 -->|"start"| N002
    N002 --> N003
```

## count_open_prs_for_head(...)

```mermaid
flowchart TD
    N001["count_open_prs_for_head(...)"]
    N002["result = _run(...)"]
    N003["return int(result.stdout.strip())"]
    N001 -->|"start"| N002
    N002 --> N003
```

## find_rolling_issue(...)

```mermaid
flowchart TD
    N001["find_rolling_issue(...)"]
    N002["result = _run(...)"]
    N003["issues = loads(...)"]
    N004["for issue in issues:     if issue.get('<str>') == title:         return _normalize_issue(issue)"]
    N005["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## comment_on_issue(...)

```mermaid
flowchart TD
    N001["comment_on_issue(...)"]
    N002["_run(...)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## create_issue(...)

```mermaid
flowchart TD
    N001["create_issue(...)"]
    N002["cmd = ['<str>', '<str>', '<str>', '<str>', repo, '<str>', title, '<str>', str(body_file)]"]
    N003["for label in ROLLING_ISSUE_LABELS:     cmd.extend(['<str>', label])"]
    N004["_run(...)"]
    N005["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## close_issue_with_comment(...)

```mermaid
flowchart TD
    N001["close_issue_with_comment(...)"]
    N002["_run(...)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## fetch_issue_last_activity(...)

```mermaid
flowchart TD
    N001["fetch_issue_last_activity(...)"]
    N002["issue = _run(...)"]
    N003["comments = _run(...)"]
    N004["comment_dates = [line for line in comments.stdout.splitlines() if line.strip()]"]
    N005["last_activity = comment_dates[-1] if comment_dates else issue.stdout.strip()"]
    N006["return _parse_github_datetime(last_activity)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## render_survey(...)

```mermaid
flowchart TD
    N001["render_survey(...)"]
    N002["dry_run = parse_dry_run(...)"]
    N003["min_age_days = parse_min_age_days(...)"]
    N004["branches = list_branches(...)"]
    N005["rows = []"]
    N006["for branch, sha in branches:     if branch == default_branch:         continue     last_commit = get_last_commit_date(repo, sha, runner=runner)     age_seconds = int((now_utc - last_commit).total_seconds())     if age_seconds <= min_age_days * SECONDS_PER_DAY:         continue     has_open_pr = count_open_prs_for_head(repo, branch, runner=runner) > 0     if not is_candidate(branch=branch, default_branch=default_branch, last_commit_utc=last_commit, now_utc=now_utc, min_age_days=min_age_days, has_open_pr=has_open_pr):         continue     age_days = age_seconds // SECONDS_PER_DAY     rows.append(format_summary_row(branch, last_commit, age_days, sha))"]
    N007["summary_lines = _survey_header(...)"]
    N008["comment_lines = _comment_header(...)"]
    N009["if rows"]
    N010["extend(...)"]
    N011["extend(...)"]
    N012["append(...)"]
    N013["footer = f'<str>{len(rows)}<str>'"]
    N014["extend(...)"]
    N015["comment = None"]
    N016["if rows"]
    N017["extend(...)"]
    N018["comment = '<str>'.join(comment_lines) + '<str>'"]
    N019["extend(...)"]
    N020["return ('<str>'.join(summary_lines) + '<str>', comment, len(rows))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N011 --> N013
    N012 --> N013
    N013 --> N014
    N014 --> N015
    N015 --> N016
    N016 -->|"true"| N017
    N017 --> N018
    N016 -->|"false"| N019
    N018 --> N020
    N019 --> N020
```

## _cmd_survey(...)

```mermaid
flowchart TD
    N001["_cmd_survey(...)"]
    N002["now = _now_utc(...)"]
    N003["(summary, comment, candidate_count) = render_survey(...)"]
    N004["print(...)"]
    N005["print(...)"]
    N006["if args.github_output"]
    N007["with Path(args.github_output).open('<str>', encoding='<str>') as fp:     fp.write(f'<str>{candidate_count}<str>')"]
    N008["out = Path(...)"]
    N009["if comment is None"]
    N010["unlink(...)"]
    N011["write_text(...)"]
    N012["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N009 -->|"false"| N011
    N010 --> N012
    N011 --> N012
```

## _cmd_reconcile(...)

```mermaid
flowchart TD
    N001["_cmd_reconcile(...)"]
    N002["candidate_count = int(...)"]
    N003["existing_issue = find_rolling_issue(...)"]
    N004["idle_threshold_seconds = int(args.idle_close_days) * SECONDS_PER_DAY"]
    N005["idle_seconds = 0"]
    N006["last_activity = None"]
    N007["now = _now_utc(...)"]
    N008["if existing_issue is not None"]
    N009["last_activity = fetch_issue_last_activity(...)"]
    N010["idle_seconds = int(...)"]
    N011["action = decide_issue_action(...)"]
    N012["if action == 'append'"]
    N013["number = existing_issue['<str>']"]
    N014["print(...)"]
    N015["comment_on_issue(...)"]
    N016["if action == 'create'"]
    N017["print(...)"]
    N018["create_issue(...)"]
    N019["if action == 'close'"]
    N020["number = existing_issue['<str>']"]
    N021["idle_days = idle_seconds // SECONDS_PER_DAY"]
    N022["assert last_activity is not None"]
    N023["print(...)"]
    N024["close_issue_with_comment(...)"]
    N025["if existing_issue is None"]
    N026["print(...)"]
    N027["number = existing_issue['<str>']"]
    N028["idle_days = idle_seconds // SECONDS_PER_DAY"]
    N029["print(...)"]
    N030["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N010 --> N011
    N008 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N014 --> N015
    N012 -->|"false"| N016
    N016 -->|"true"| N017
    N017 --> N018
    N016 -->|"false"| N019
    N019 -->|"true"| N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
    N019 -->|"false"| N025
    N025 -->|"true"| N026
    N025 -->|"false"| N027
    N027 --> N028
    N028 --> N029
    N015 --> N030
    N018 --> N030
    N024 --> N030
    N026 --> N030
    N029 --> N030
```

## _survey_header(...)

```mermaid
flowchart TD
    N001["_survey_header(...)"]
    N002["return ['<str>', '<str>', f'<str>{event_name}<str>', f'<str>{run_url}', f'<str>{str(dry_run).lower()}<str>', f'<str>{min_age_days}<str>', f'<str>{default_branch}<str>', f'<str>{branch_count}<str>', '<str>', '<str>', '<str>']"]
    N001 -->|"start"| N002
```

## _comment_header(...)

```mermaid
flowchart TD
    N001["_comment_header(...)"]
    N002["return [f'<str>{_format_github_datetime(now_utc)}', '<str>', f'<str>{event_name}<str>', f'<str>{run_url}', f'<str>{str(dry_run).lower()}<str>', f'<str>{min_age_days}<str>', '<str>', '<str>', '<str>']"]
    N001 -->|"start"| N002
```

## _close_comment(...)

```mermaid
flowchart TD
    N001["_close_comment(...)"]
    N002["return f'<str>{idle_days}<str>{_format_github_datetime(last_activity)}<str>{idle_close_days}<str>{run_url}<str>'"]
    N001 -->|"start"| N002
```

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["return runner(cmd, capture_output=True, text=True, timeout=30, check=True)"]
    N001 -->|"start"| N002
```

## _parse_github_datetime(...)

```mermaid
flowchart TD
    N001["_parse_github_datetime(...)"]
    N002["try"]
    N003["parsed = fromisoformat(...)"]
    N004["except ValueError"]
    N005["raise ValueError(f'<str>{raw!r}')"]
    N006["if parsed.tzinfo is None"]
    N007["raise ValueError(f'<str>{raw!r}')"]
    N008["return parsed.astimezone(UTC)"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## _format_github_datetime(...)

```mermaid
flowchart TD
    N001["_format_github_datetime(...)"]
    N002["return value.astimezone(UTC).isoformat().replace('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## _normalize_issue(...)

```mermaid
flowchart TD
    N001["_normalize_issue(...)"]
    N002["normalized = dict(...)"]
    N003["if 'createdAt' in normalized"]
    N004["normalized['<str>'] = pop(...)"]
    N005["return normalized"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## _now_utc(...)

```mermaid
flowchart TD
    N001["_now_utc(...)"]
    N002["return datetime.now(UTC)"]
    N001 -->|"start"| N002
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_survey = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_argument(...)"]
    N012["add_argument(...)"]
    N013["set_defaults(...)"]
    N014["p_reconcile = add_parser(...)"]
    N015["add_argument(...)"]
    N016["add_argument(...)"]
    N017["add_argument(...)"]
    N018["add_argument(...)"]
    N019["add_argument(...)"]
    N020["add_argument(...)"]
    N021["set_defaults(...)"]
    N022["args = parse_args(...)"]
    N023["try"]
    N024["return args.func(args)"]
    N025["except (subprocess.CalledProcessError, ValueError)"]
    N026["print(...)"]
    N027["return 1"]
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
    N016 --> N017
    N017 --> N018
    N018 --> N019
    N019 --> N020
    N020 --> N021
    N021 --> N022
    N022 --> N023
    N023 -->|"try"| N024
    N023 -->|"raises"| N025
    N025 --> N026
    N026 --> N027
```
