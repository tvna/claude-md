# AST graph: scripts/ci_early_status_probe.py

This file is generated from `scripts/ci_early_status_probe.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _walk_strings(...)

```mermaid
flowchart TD
    N001["_walk_strings(...)"]
    N002["if isinstance(value, str)"]
    N003["return [value]"]
    N004["if isinstance(value, dict)"]
    N005["out = []"]
    N006["for item in value.values():     out.extend(_walk_strings(item))"]
    N007["return out"]
    N008["if isinstance(value, list)"]
    N009["out = []"]
    N010["for item in value:     out.extend(_walk_strings(item))"]
    N011["return out"]
    N012["return []"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N005 --> N006
    N006 --> N007
    N004 -->|"false"| N008
    N008 -->|"true"| N009
    N009 --> N010
    N010 --> N011
    N008 -->|"false"| N012
```

## extract_pr_target(...)

```mermaid
flowchart TD
    N001["extract_pr_target(...)"]
    N002["tool_input = get(...)"]
    N003["if not isinstance(tool_input, dict)"]
    N004["tool_input = {}"]
    N005["repo = tool_input.get('<str>') or tool_input.get('<str>')"]
    N006["if not isinstance(repo, str) or not repo.strip()"]
    N007["repo = None"]
    N008["repo = strip(...)"]
    N009["for key in ('<str>', '<str>', '<str>'):     value = tool_input.get(key)     if isinstance(value, int):         return (repo, str(value))     if isinstance(value, str) and value.strip().isdigit():         return (repo, value.strip())"]
    N010["strings = _walk_strings(...)"]
    N011["extend(...)"]
    N012["for text in strings:     match = _PR_URL_RE.search(text)     if match:         url_repo, number = match.groups()         return (repo or url_repo, number)"]
    N013["return (repo, None)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N007 --> N009
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
```

## parse_delay(...)

```mermaid
flowchart TD
    N001["parse_delay(...)"]
    N002["env = os.environ if environ is None else environ"]
    N003["raw = get(...)"]
    N004["if raw is None"]
    N005["return _DEFAULT_DELAY_SECONDS"]
    N006["try"]
    N007["delay = float(...)"]
    N008["except ValueError"]
    N009["return _DEFAULT_DELAY_SECONDS"]
    N010["return max(0.0, delay)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"try"| N007
    N006 -->|"raises"| N008
    N008 --> N009
    N007 --> N010
```

## _rest_get(...)

```mermaid
flowchart TD
    N001["_rest_get(...)"]
    N002["url = f'<str>{path}'"]
    N003["try"]
    N004["(code, body) = apply_call(...)"]
    N005["except Exception"]
    N006["print(...)"]
    N007["return (0, None)"]
    N008["try"]
    N009["return (code, json.loads(body))"]
    N010["except json.JSONDecodeError"]
    N011["return (code, None)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
```

## run_checks(...)

```mermaid
flowchart TD
    N001["run_checks(...)"]
    N002["actual_token = token or os.environ.get('<str>', '<str>')"]
    N003["if not actual_token"]
    N004["print(...)"]
    N005["return []"]
    N006["if not repo or '/' not in repo"]
    N007["print(...)"]
    N008["return []"]
    N009["(owner, repo_name) = split(...)"]
    N010["(code, pr_data) = _rest_get(...)"]
    N011["if not isinstance(pr_data, dict) or not 200 <= code < 300"]
    N012["print(...)"]
    N013["return []"]
    N014["sha = get(...)"]
    N015["if not isinstance(sha, str)"]
    N016["return []"]
    N017["(code, checks_data) = _rest_get(...)"]
    N018["if not isinstance(checks_data, dict) or not 200 <= code < 300"]
    N019["print(...)"]
    N020["return []"]
    N021["check_runs = checks_data.get('<str>') or []"]
    N022["wf_map = {}"]
    N023["(wf_code, wf_data) = _rest_get(...)"]
    N024["if isinstance(wf_data, dict) and 200 <= wf_code < 300"]
    N025["for wf_run in wf_data.get('<str>') or []:     if not isinstance(wf_run, dict):         continue     cs_id = str(wf_run.get('<str>') or wf_run.get('<str>', {}).get('<str>') or '<str>')     wf_name = wf_run.get('<str>') or '<str>'     if cs_id and wf_name:         wf_map[cs_id] = wf_name"]
    N026["rows = []"]
    N027["for run in check_runs:     if not isinstance(run, dict):         continue     cs_id = str((run.get('<str>') or {}).get('<str>') or '<str>')     rows.append({'<str>': run.get('<str>') or '<str>', '<str>': (run.get('<str>') or '<str>').upper(), '<str>': run.get('<str>') or '<str>', '<str>': wf_map.get(cs_id, '<str>')})"]
    N028["return rows"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 --> N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
    N017 --> N018
    N018 -->|"true"| N019
    N019 --> N020
    N018 -->|"false"| N021
    N021 --> N022
    N022 --> N023
    N023 --> N024
    N024 -->|"true"| N025
    N025 --> N026
    N024 -->|"false"| N026
    N026 --> N027
    N027 --> N028
```

## _load_check_rows(...)

```mermaid
flowchart TD
    N001["_load_check_rows(...)"]
    N002["return [row for row in rows if isinstance(row, dict)]"]
    N001 -->|"start"| N002
```

## failed_checks(...)

```mermaid
flowchart TD
    N001["failed_checks(...)"]
    N002["failed = []"]
    N003["for row in rows:     conclusion = str(row.get('<str>') or '<str>').lower()     state = str(row.get('<str>') or '<str>').lower()     if conclusion in _FAIL_CONCLUSIONS or state in _FAIL_CONCLUSIONS:         failed.append(row)"]
    N004["return failed"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _check_name(...)

```mermaid
flowchart TD
    N001["_check_name(...)"]
    N002["name = get(...)"]
    N003["workflow = get(...)"]
    N004["if isinstance(workflow, str) and workflow and isinstance(name, str) and name"]
    N005["return f'{workflow}<str>{name}'"]
    N006["if isinstance(name, str) and name"]
    N007["return name"]
    N008["if isinstance(workflow, str) and workflow"]
    N009["return workflow"]
    N010["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 -->|"true"| N009
    N008 -->|"false"| N010
```

## build_additional_context(...)

```mermaid
flowchart TD
    N001["build_additional_context(...)"]
    N002["label = f'{repo}<str>{pr}' if repo else f'<str>{pr}'"]
    N003["lines = [f'<str>{delay_seconds:<str>}<str>{label}<str>', '<str>', '<str>', '<str>']"]
    N004["for row in failed[:10]:     conclusion = row.get('<str>') or row.get('<str>') or '<str>'     lines.append(f'<str>{_check_name(row)}<str>{conclusion}')"]
    N005["if len(failed) > 10"]
    N006["append(...)"]
    N007["return {'<str>': {'<str>': '<str>', '<str>': '<str>'.join(lines)}}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if event.get('tool_name') not in _TARGET_TOOLS"]
    N003["return None"]
    N004["(repo, pr) = extract_pr_target(...)"]
    N005["if pr is None"]
    N006["return None"]
    N007["delay = parse_delay(...)"]
    N008["sleeper(...)"]
    N009["try"]
    N010["rows = run_checks(...)"]
    N011["except (OSError, Exception)"]
    N012["print(...)"]
    N013["return None"]
    N014["loaded = _load_check_rows(...)"]
    N015["failed = failed_checks(...)"]
    N016["if not failed"]
    N017["return None"]
    N018["return build_additional_context(repo, pr, failed, delay)"]
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
    N012 --> N013
    N010 --> N014
    N014 --> N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
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
