# AST graph: scripts/workflow_diagram.py

This file is generated from `scripts/workflow_diagram.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _get_on_section(...)

```mermaid
flowchart TD
    N001["_get_on_section(...)"]
    N002["return data.get(True, data.get('<str>', {}))"]
    N001 -->|"start"| N002
```

## _parse_triggers(...)

```mermaid
flowchart TD
    N001["_parse_triggers(...)"]
    N002["if isinstance(on_val, str)"]
    N003["return [Trigger(event=on_val)]"]
    N004["if isinstance(on_val, list)"]
    N005["return [Trigger(event=str(e)) for e in on_val]"]
    N006["if isinstance(on_val, dict)"]
    N007["result = []"]
    N008["for event, config in on_val.items():     filters: dict[str, str] = {}     if isinstance(config, dict):         for k, v in config.items():             filters[str(k)] = str(v)     result.append(Trigger(event=str(event), filters=filters))"]
    N009["return result"]
    N010["return []"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
    N006 -->|"true"| N007
    N007 --> N008
    N008 --> N009
    N006 -->|"false"| N010
```

## _parse_jobs(...)

```mermaid
flowchart TD
    N001["_parse_jobs(...)"]
    N002["if not isinstance(jobs_val, dict)"]
    N003["return []"]
    N004["result = []"]
    N005["for job_id, job_data in jobs_val.items():     if not isinstance(job_data, dict):         continue     raw_if = job_data.get('<str>')     if_cond = str(raw_if) if raw_if is not None else None     needs_raw = job_data.get('<str>', [])     if isinstance(needs_raw, str):         needs: list[str] = [needs_raw]     elif isinstance(needs_raw, list):         needs = [str(n) for n in needs_raw]     else:         needs = []     steps_with_if: list[StepBranch] = []     for step in job_data.get('<str>') or []:         if not isinstance(step, dict):             continue         step_if = step.get('<str>')         if step_if is None:             continue         name = str(step.get('<str>') or step.get('<str>') or '<str>')         steps_with_if.append(StepBranch(name=name, if_condition=str(step_if)))     result.append(Job(job_id=str(job_id), if_condition=if_cond, needs=needs, steps_with_if=steps_with_if))"]
    N006["return result"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## parse_workflow(...)

```mermaid
flowchart TD
    N001["parse_workflow(...)"]
    N002["data = yaml.safe_load(path.read_text(encoding='<str>')) or {}"]
    N003["name = str(...)"]
    N004["triggers = _parse_triggers(...)"]
    N005["jobs = _parse_jobs(...)"]
    N006["return WorkflowDiagram(workflow_name=name, source_path=path, triggers=triggers, jobs=jobs)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
```

## _mermaid_escape(...)

```mermaid
flowchart TD
    N001["_mermaid_escape(...)"]
    N002["return text.replace('<str>', '<str>').replace('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## _shorten(...)

```mermaid
flowchart TD
    N001["_shorten(...)"]
    N002["text = strip(...)"]
    N003["if len(text) <= max_len"]
    N004["return text"]
    N005["return text[:max_len - 1] + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## render_mermaid(...)

```mermaid
flowchart TD
    N001["render_mermaid(...)"]
    N002["lines = ['<str>']"]
    N003["if diagram.triggers"]
    N004["append(...)"]
    N005["for t in diagram.triggers:     lbl = _mermaid_escape(t.label())     lines.append(f'<str>{t.node_id()}<str>{lbl}<str>')"]
    N006["append(...)"]
    N007["for j in diagram.jobs:     lines.append(f'<str>{j.node_id()}<str>{_mermaid_escape(j.job_id)}<str>')     for idx, step in enumerate(j.steps_with_if):         step_node = f'<str>{j.node_id()}<str>{idx}'         lbl = _mermaid_escape(step.name)         lines.append(f'<str>{step_node}<str>{lbl}<str>')"]
    N008["append(...)"]
    N009["job_by_id = {j.job_id: j for j in diagram.jobs}"]
    N010["for j in diagram.jobs:     if j.needs:         for parent_id in j.needs:             parent_job = job_by_id.get(parent_id)             if parent_job is None:                 continue             if j.if_condition:                 lbl = _mermaid_escape(_shorten(j.if_condition))                 lines.append(f'<str>{parent_job.node_id()}<str>{lbl}<str>{j.node_id()}')             else:                 lines.append(f'<str>{parent_job.node_id()}<str>{j.node_id()}')     else:         event_names = _EVENT_NAME_RE.findall(j.if_condition or '<str>')         for t in diagram.triggers:             if event_names and t.event not in event_names:                 continue             if j.if_condition:                 lbl = _mermaid_escape(_shorten(j.if_condition))                 lines.append(f'<str>{t.node_id()}<str>{lbl}<str>{j.node_id()}')             else:                 lines.append(f'<str>{t.node_id()}<str>{j.node_id()}')     for idx, step in enumerate(j.steps_with_if):         step_node = f'<str>{j.node_id()}<str>{idx}'         lbl = _mermaid_escape(_shorten(step.if_condition))         lines.append(f'<str>{j.node_id()}<str>{lbl}<str>{step_node}')"]
    N011["return '<str>'.join(lines) + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N005 --> N006
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
```

## render_markdown(...)

```mermaid
flowchart TD
    N001["render_markdown(...)"]
    N002["source = replace(...)"]
    N003["title = f'<str>{diagram.workflow_name}'"]
    N004["return _PREAMBLE_TEMPLATE.format(title=title, source=source, mermaid=render_mermaid(diagram))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## output_path_for(...)

```mermaid
flowchart TD
    N001["output_path_for(...)"]
    N002["return output_dir / f'{workflow_path.stem}<str>'"]
    N001 -->|"start"| N002
```

## _cmd_diagram(...)

```mermaid
flowchart TD
    N001["_cmd_diagram(...)"]
    N002["path = Path(...)"]
    N003["if not path.exists()"]
    N004["print(...)"]
    N005["return 1"]
    N006["diagram = parse_workflow(...)"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N004 --> N005
    N003 -->|"false"| N006
    N006 --> N007
    N007 --> N008
```

## _cmd_diagram_doc(...)

```mermaid
flowchart TD
    N001["_cmd_diagram_doc(...)"]
    N002["output_dir = Path(...)"]
    N003["if args.workflows"]
    N004["workflow_paths = [Path(w) for w in args.workflows]"]
    N005["workflow_paths = sorted(...)"]
    N006["if not workflow_paths"]
    N007["print(...)"]
    N008["return 0"]
    N009["errors = 0"]
    N010["written = set(...)"]
    N011["for wf_path in workflow_paths:     if not wf_path.exists():         print(f'<str>{wf_path}', file=sys.stderr)         errors += 1         continue     diagram = parse_workflow(wf_path)     out = output_path_for(wf_path, output_dir)     out.parent.mkdir(parents=True, exist_ok=True)     out.write_text(render_markdown(diagram), encoding='<str>')     written.add(out.resolve())"]
    N012["if not args.workflows and output_dir.exists()"]
    N013["for stale in sorted(output_dir.glob('<str>')):     if stale.resolve() not in written:         stale.unlink()         print(f'<str>{stale}')"]
    N014["return 1 if errors else 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N004 --> N006
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N014
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_diagram = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["p_doc = add_parser(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["set_defaults(...)"]
    N011["args = parse_args(...)"]
    N012["result = func(...)"]
    N013["return result"]
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
```
