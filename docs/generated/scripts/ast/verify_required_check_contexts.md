# AST graph: scripts/verify_required_check_contexts.py

This file is generated from `scripts/verify_required_check_contexts.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## load_sot_contexts(...)

```mermaid
flowchart TD
    N001["load_sot_contexts(...)"]
    N002["data = loads(...)"]
    N003["rules = data.get('<str>') or []"]
    N004["for rule in rules:     if rule.get('<str>') != '<str>':         continue     params = rule.get('<str>') or {}     checks = params.get('<str>') or []     return [str(item.get('<str>') or '<str>') for item in checks if item.get('<str>')]"]
    N005["return []"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## parse_workflow(...)

```mermaid
flowchart TD
    N001["parse_workflow(...)"]
    N002["workflow_name = '<str>'"]
    N003["jobs = {}"]
    N004["current_job = None"]
    N005["in_jobs = False"]
    N006["for line in yaml_text.splitlines():     if line.startswith('<str>'):         workflow_name = _strip_scalar(line[len('<str>'):])         continue     if line.startswith('<str>'):         in_jobs = True         continue     if not in_jobs:         continue     if line.startswith('<str>') and (not line.startswith('<str>')):         stripped = line[2:]         if stripped.endswith('<str>') and '<str>' not in stripped[:-1]:             current_job = stripped[:-1].strip()             jobs[current_job] = {}             continue     if current_job and line.startswith('<str>'):         jobs[current_job]['<str>'] = _strip_scalar(line[len('<str>'):])"]
    N007["return {'<str>': workflow_name, '<str>': jobs}"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## _strip_scalar(...)

```mermaid
flowchart TD
    N001["_strip_scalar(...)"]
    N002["value = strip(...)"]
    N003["if len(value) >= 2 and value[0] == value[-1] and (value[0] in (''', '''))"]
    N004["value = value[1:-1]"]
    N005["return value"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N005
```

## produced_check_names(...)

```mermaid
flowchart TD
    N001["produced_check_names(...)"]
    N002["produced = {}"]
    N003["for yaml_file in sorted(workflows_dir.glob('<str>')):     try:         text = yaml_file.read_text(encoding='<str>')     except OSError:         continue     parsed = parse_workflow(text)     jobs = parsed.get('<str>') or {}     if not isinstance(jobs, dict):         continue     for job_id, job_def in jobs.items():         if not isinstance(job_def, dict):             continue         explicit_name = job_def.get('<str>')         check_name = str(explicit_name) if explicit_name else str(job_id)         produced.setdefault(check_name, (yaml_file.name, str(job_id)))"]
    N004["return produced"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## find_missing(...)

```mermaid
flowchart TD
    N001["find_missing(...)"]
    N002["return [ctx for ctx in sot_contexts if ctx not in produced]"]
    N001 -->|"start"| N002
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["sot_path = Path(...)"]
    N003["workflows_dir = Path(...)"]
    N004["sot_contexts = load_sot_contexts(...)"]
    N005["if not sot_contexts"]
    N006["print(...)"]
    N007["return 0"]
    N008["produced = produced_check_names(...)"]
    N009["missing = find_missing(...)"]
    N010["if missing"]
    N011["print(...)"]
    N012["for ctx in missing:     print(f'<str>{ctx!r}', file=sys.stderr)"]
    N013["return 1"]
    N014["print(...)"]
    N015["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
    N009 --> N010
    N010 -->|"true"| N011
    N011 --> N012
    N012 --> N013
    N010 -->|"false"| N014
    N014 --> N015
```

## _build_parser(...)

```mermaid
flowchart TD
    N001["_build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["return parser"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = _build_parser(...)"]
    N003["args = parse_args(...)"]
    N004["return int(args.func(args))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
