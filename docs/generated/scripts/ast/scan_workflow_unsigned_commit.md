# AST graph: scripts/scan_workflow_unsigned_commit.py

This file is generated from `scripts/scan_workflow_unsigned_commit.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _load_yaml(...)

```mermaid
flowchart TD
    N001["_load_yaml(...)"]
    N002["try"]
    N003["data = safe_load(...)"]
    N004["except Exception"]
    N005["return None"]
    N006["return data if isinstance(data, dict) else None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
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

## scan_run_text(...)

```mermaid
flowchart TD
    N001["scan_run_text(...)"]
    N002["hits = []"]
    N003["for lineno, line in enumerate(run_text.splitlines(), start=1):     if ACK_MARKER in line:         continue     match = _GIT_PUSH.search(line)     if match is not None:         fragment = line[match.start():match.start() + _FRAGMENT_LEN].strip()         hits.append((lineno, fragment))"]
    N004["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _iter_matches(...)

```mermaid
flowchart TD
    N001["_iter_matches(...)"]
    N002["for wf_name, job_id, step_name, run_text in _iter_run_steps(workflow_dir):     for lineno, fragment in scan_run_text(run_text):         yield Violation(workflow=wf_name, job=job_id, step=step_name, line=lineno, fragment=fragment)"]
    N003["end"]
    N001 -->|"start"| N002
    N002 --> N003
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["return list(_iter_matches(workflow_dir))"]
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
    N009["for v in _iter_matches(wf_dir):     print(f'{v.workflow}<str>{v.job}<str>{v.step!r}<str>{v.line}<str>{v.fragment!r}')"]
    N010["return 0"]
    N011["violations = find_violations(...)"]
    N012["if not violations"]
    N013["print(...)"]
    N014["return 0"]
    N015["for v in violations:     print(f'<str>{v.workflow}<str>{v.step!r}<str>{v.job}<str>{v.fragment!r}<str>{ACK_MARKER}<str>', file=sys.stderr)"]
    N016["print(...)"]
    N017["return 1"]
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
    N013 --> N014
    N012 -->|"false"| N015
    N015 --> N016
    N016 --> N017
```
