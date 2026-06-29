# AST graph: scripts/scan_workflow_gh_calls.py

This file is generated from `scripts/scan_workflow_gh_calls.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _load_yaml(...)

```mermaid
flowchart TD
    N001["_load_yaml(...)"]
    N002["try"]
    N003["data = safe_load(...)"]
    N004["return data if isinstance(data, dict) else None"]
    N005["except Exception"]
    N006["return None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N003 --> N004
    N002 -->|"raises"| N005
    N005 --> N006
```

## _iter_run_steps(...)

```mermaid
flowchart TD
    N001["_iter_run_steps(...)"]
    N002["for wf_path in sorted(workflow_dir.glob('<str>')):     data = _load_yaml(wf_path)     if data is None:         continue     jobs = data.get('<str>') or {}     if not isinstance(jobs, dict):         continue     for job_id, job in jobs.items():         if not isinstance(job, dict):             continue         steps = job.get('<str>') or []         if not isinstance(steps, list):             continue         for step in steps:             if not isinstance(step, dict):                 continue             run_text = step.get('<str>')             if not isinstance(run_text, str):                 continue             step_name = str(step.get('<str>') or '<str>')             yield (wf_path.name, str(job_id), step_name, run_text)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## _fragment_at(...)

```mermaid
flowchart TD
    N001["_fragment_at(...)"]
    N002["return run_text[start:start + _FRAGMENT_LEN].strip()"]
    N001 -->|"start"| N002
```

## _flatten(...)

```mermaid
flowchart TD
    N001["_flatten(...)"]
    N002["return '<str>'.join((text for _, text in flatten_shell_continuations(run_text)))"]
    N001 -->|"start"| N002
```

## scan_run_text(...)

```mermaid
flowchart TD
    N001["scan_run_text(...)"]
    N002["flat = _flatten(...)"]
    N003["out = []"]
    N004["gh_match = search(...)"]
    N005["if gh_match is not None"]
    N006["append(...)"]
    N007["if _CURL_RE.search(flat) is not None"]
    N008["api_match = search(...)"]
    N009["if api_match is not None"]
    N010["append(...)"]
    N011["return out"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N011
    N007 -->|"false"| N011
```

## _iter_matches(...)

```mermaid
flowchart TD
    N001["_iter_matches(...)"]
    N002["for wf_name, job_id, step_name, run_text in _iter_run_steps(workflow_dir):     for kind, fragment in scan_run_text(run_text):         yield Violation(workflow=wf_name, job=job_id, step=step_name, fragment=fragment, kind=kind)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["return [v for v in _iter_matches(workflow_dir) if (v.workflow, v.step) not in _ALLOWLIST_KEYS]"]
    N001 -->|"start"| N002
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["add_parser(...)"]
    N005["add_parser(...)"]
    N006["args = parse_args(...)"]
    N007["wf_dir = WORKFLOW_DIR"]
    N008["if args.cmd == 'list'"]
    N009["for v in _iter_matches(wf_dir):     status = '<str>' if (v.workflow, v.step) in _ALLOWLIST_KEYS else '<str>'     print(f'<str>{status}<str>{v.kind}<str>{v.workflow}<str>{v.job}<str>{v.step!r}<str>{v.fragment!r}')"]
    N010["return 0"]
    N011["violations = find_violations(...)"]
    N012["if not violations"]
    N013["return 0"]
    N014["for v in violations:     what = '<str>' if v.kind == '<str>' else '<str>'     print(f'<str>{v.workflow}<str>{what}<str>{v.step!r}<str>{v.job}<str>{v.fragment!r}<str>', file=sys.stderr)"]
    N015["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 --> N012
    N012 -->|"true"| N013
    N012 -->|"false"| N014
    N014 --> N015
```
